"""
repo_card.py — Accordion-style repo card widget for the main dashboard.
Collapsed: compact bar with checkbox + name + branch/profile hint + status + action buttons.
Expanded: reveals branch selector, profile/BD selectors, npm ci/mvn install, custom command.
"""
import customtkinter as ctk
import tkinter as tk
import threading
import webbrowser
import os
import subprocess
import re
from datetime import datetime

from gui.tooltip import ToolTip
from gui import theme

# ── String constants ────────────────────────────────────────────
NO_DB_PRESET = "- Ninguna (Local) -"
REINSTALL_LBL = "Reinstall ✓"
BTN_CLICK = "<Button-1>"
BTN_CONFIG_TEXT = "⚙ Config"
BTN_CONFIG_TOOLTIP = "Editar configuración"

PORT_REGEXES = [
    re.compile(r"Tomcat (?:started on|initialized with) port.*?(\d+)", re.IGNORECASE),
    re.compile(r"http://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])[:\s]+(\d+)", re.IGNORECASE),
    re.compile(r"(?:listening on|bound to).*?port\s+(\d+)", re.IGNORECASE),
    re.compile(r"Local:\s*http://localhost:(\d+)", re.IGNORECASE),
]

# Limit concurrent git-status badge refreshes to avoid subprocess spam
_GIT_BADGE_SEMAPHORE = threading.Semaphore(3)


def _create_subprocess(cmd_str: str, cwd: str, env: dict = None, shell: bool = True) -> subprocess.Popen:
    """Helper to create a unified subprocess."""
    creationflags = (getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)) if os.name == 'nt' else 0
    return subprocess.Popen(
        cmd_str, cwd=cwd, env=env, shell=shell,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
        creationflags=creationflags
    )


class RepoCard(ctk.CTkFrame):
    """Accordion repo card — collapsed bar + expandable details."""

    def __init__(self, parent, repo_info, service_launcher, db_presets=None,
                 java_versions=None, log_callback=None, on_edit_config=None, on_change_callback=None, **kwargs):
        super().__init__(parent, corner_radius=theme.G.corner_card, border_width=theme.G.border_width,
                         border_color=theme.C.card_border,
                         fg_color=theme.C.card, **kwargs)

        self._repo = repo_info
        self._launcher = service_launcher
        self._db_presets = db_presets or {}
        self._java_versions = java_versions or {}
        self._log = self._repo_log
        self._global_log = log_callback
        self._on_edit_config = on_edit_config
        self._on_change_callback = on_change_callback
        self._status = 'stopped'
        self._branches_cache = []
        self._current_branch = ''
        self._branch_load_id = None
        self._expanded = False
        self._is_installing = False
        self.selected_var = ctk.BooleanVar(value=True)
        self.selected_java_var = ctk.StringVar(value="Sistema (Por Defecto)")
        
        self._active_compose_files = set()
        self._docker_compose_buttons = {}
        self._docker_profile_services: dict = {}   # compose_file -> [service_names]
        self._compose_status_thread_running = False
        self._compose_stop_event = threading.Event()
        self._badge_timer = None
        self._log_line_count = 0
        self._detached_log_line_count = 0
        self._expand_panel_built = False

        self._build_ui()
        self._update_header_hints()

        from domain.ports.event_bus import bus
        bus.subscribe("SERVICE_STATUS_CHANGED", self._on_bus_status_changed)

        self._header.bind("<Enter>", self._on_hover_enter)
        self._header.bind("<Leave>", self._on_hover_leave)
        
        # Vincular evento Map para el FocusIn a Toplevel
        self.bind("<Map>", self._on_map)
        
        self._branch_load_id = self.after(200, self._refresh_branch)
        self._badge_timer = self.after(3000, self._refresh_badge_loop)
        
    def destroy(self):
        """Cancel pending timers and stop background threads before destroying."""
        self._compose_stop_event.set()
        self._compose_status_thread_running = False
        if self._badge_timer:
            try:
                self.after_cancel(self._badge_timer)
            except Exception:
                pass
        if self._branch_load_id:
            try:
                self.after_cancel(self._branch_load_id)
            except Exception:
                pass
        from domain.ports.event_bus import bus
        try:
            bus.unsubscribe("SERVICE_STATUS_CHANGED", self._on_bus_status_changed)
        except Exception:
            pass
        super().destroy()

    def _on_bus_status_changed(self, event: dict):
        if event.get("name") == self._repo.name:
            self._update_status(self._repo.name, event.get("status"))

    def _trigger_change_callback(self):
        if hasattr(self, '_on_change_callback') and self._on_change_callback:
            try:
                self.after(0, self._on_change_callback)
            except tk.TclError:
                pass

    def get_config_key(self, target_file: str) -> str:
        """Get the unique config key for a specific module's target file.
        Format: 'repo-name::relative/dir/path'
        e.g. 'boa2-backend-configuracion::src/main/resources'
        """
        import os
        repo_path = self._repo.path
        if not target_file:
            return self._repo.name

        rel_path = os.path.relpath(target_file, repo_path).replace('\\', '/')
        dir_path = '/'.join(rel_path.split('/')[:-1])  # strip filename
        if not dir_path or dir_path == '.':
            dir_path = 'root'

        return f"{self._repo.name}::{dir_path}"

    def _refresh_badge_loop(self):
        """Periodically refresh the unsigned changes badge."""
        self._refresh_badge()
        if self.winfo_exists():
            self._badge_timer = self.after(30000, self._refresh_badge_loop)

    def _refresh_badge(self, event=None):
        """Count modified files and update the badge label."""
        def _run():
            if not _GIT_BADGE_SEMAPHORE.acquire(blocking=False):
                return  # Too many concurrent git calls — skip this cycle
            try:
                from core.git_manager import count_modified_files
                count = count_modified_files(self._repo.path)
                if count > 0:
                    def _update():
                        if hasattr(self, '_changes_count_label'):
                            self._changes_count_label.configure(text=f"📝 {count}")
                    self.after(0, _update)
                else:
                    def _update():
                        if hasattr(self, '_changes_count_label'):
                            self._changes_count_label.configure(text="")
                    self.after(0, _update)
            finally:
                _GIT_BADGE_SEMAPHORE.release()
        threading.Thread(target=_run, daemon=True).start()

    def _on_hover_enter(self, event=None):
        self._header.configure(fg_color=theme.C.card_hover)

    def _on_hover_leave(self, event=None):
        self._header.configure(fg_color="transparent")

    def _on_map(self, event=None):
        # Cuando se muestra visualmente, vinculamos FocusIn del TopLevel de forma aditiva
        if not hasattr(self, '_focus_bound'):
            try:
                self.winfo_toplevel().bind("<FocusIn>", self._refresh_badge, add="+")
                self._focus_bound = True
            except tk.TclError:
                pass

    def _build_ui(self):
        """Build all UI elements for the card."""
        self._build_header()
        # Expand panel is built lazily on first _toggle_expand call

    # ─── HEADER (always visible, compact) ────────────────────────

    def _build_header(self):
        """Build the collapsed header bar."""
        repo = self._repo
        type_color = repo.ui_config.get('color', '#888')

        self._header = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2")
        self._header.pack(fill="x", padx=6, pady=4)
        self._header.bind(BTN_CLICK, self._toggle_expand)

        # Checkbox
        ctk.CTkCheckBox(
            self._header, text="", variable=self.selected_var,
            checkbox_width=18, checkbox_height=18, width=20, corner_radius=4
        ).pack(side="left", padx=(4, 4))

        # Status dot
        self._status_label = ctk.CTkLabel(
            self._header, text="🔴",
            font=theme.font("xl"), width=30,
            text_color=theme.STATUS_ICONS.get('stopped', theme.C.status_stopped)
        )
        self._status_label.pack(side="left", padx=(0, 6))
        self._status_label.bind(BTN_CLICK, self._toggle_expand)

        # Type badge
        ctk.CTkLabel(
            self._header,
            text=f" {repo.repo_type.replace('-', ' ').title()} ",
            font=theme.font("xs", bold=True),
            text_color=theme.C.text_white, fg_color=type_color,
            corner_radius=theme.G.corner_badge, height=18
        ).pack(side="left", padx=(0, 8))

        # Name
        name_label = ctk.CTkLabel(
            self._header, text=f"{repo.ui_config.get('icon', '📁')} {repo.name}",
            font=theme.font("h2", bold=True), anchor="w",
            text_color=theme.C.text_primary
        )
        name_label.pack(side="left")
        name_label.bind(BTN_CLICK, self._toggle_expand)
        if repo.git_remote_url:
            ToolTip(name_label, "🔗 Clic derecho: abrir repositorio")
            name_label.bind("<Button-3>", lambda e: webbrowser.open(repo.git_remote_url))

        # Unsaved changes badge
        self._changes_count_label = ctk.CTkLabel(
            self._header, text="",
            font=theme.font("md", bold=True), text_color=theme.C.text_warning_badge
        )
        self._changes_count_label.pack(side="left", padx=(4, 4))
        ToolTip(self._changes_count_label, "Ficheros modificados sin guardar en el directorio vinculados al repo.")

        # Branch + profile hints (grey, right of name)
        self._branch_hint = ctk.CTkLabel(
            self._header, text="",
            font=theme.font("xs", mono=True), text_color=theme.C.text_faint, anchor="w"
        )
        self._branch_hint.pack(side="left", padx=(6, 0), fill="x", expand=True)
        self._branch_hint.bind(BTN_CLICK, self._toggle_expand)

        # Status text
        self._status_text = ctk.CTkLabel(
            self._header, text="Detenido",
            font=theme.font("base"), text_color=theme.C.text_muted
        )
        self._status_text.pack(side="left", padx=(0, 4))

        if repo.server_port:
            ctk.CTkLabel(
                self._header, text=f":{repo.server_port}",
                font=theme.font("md", bold=True, mono=True), text_color=theme.C.text_accent
            ).pack(side="left", padx=(0, 8))

        # Main action buttons
        self._action_btns_frame = ctk.CTkFrame(self._header, fg_color="transparent")
        self._action_btns_frame.pack(side="left", padx=(0, 4))

        self._start_btn = ctk.CTkButton(
            self._action_btns_frame, text="▶", width=32,
            command=self._start, **theme.btn_style("start", font_size="lg")
        )
        ToolTip(self._start_btn, "Iniciar servicio")

        self._stop_btn = ctk.CTkButton(
            self._action_btns_frame, text="⬛", width=32,
            command=self._stop, **theme.btn_style("danger", font_size="lg")
        )
        ToolTip(self._stop_btn, "Detener servicio")

        self._restart_btn = ctk.CTkButton(
            self._action_btns_frame, text="🔄", width=32,
            command=self._restart, **theme.btn_style("warning", font_size="lg")
        )
        ToolTip(self._restart_btn, "Reiniciar servicio")

        self._update_button_visibility()

        # Expand toggle
        self._toggle_btn = ctk.CTkButton(
            self._header, text="▼", width=28,
            text_color=theme.C.text_accent_bright,
            command=self._toggle_expand, **theme.btn_style("toggle_expand", font_size="md")
        )
        self._toggle_btn.pack(side="right", padx=(4, 2))
        ToolTip(self._toggle_btn, "Expandir / Colapsar opciones")

        # Open in Explorer
        self._explorer_btn = ctk.CTkButton(
            self._header, text="📁", width=28,
            command=self._open_in_explorer, **theme.btn_style("neutral", font_size="md")
        )
        self._explorer_btn.pack(side="right", padx=(4, 2))
        ToolTip(self._explorer_btn, "Abrir en el explorador")

    def _open_in_explorer(self):
        import os
        import sys
        import subprocess
        
        path = self._repo.path
        try:
            if os.name == 'nt':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            if hasattr(self, '_global_log') and self._global_log:
                self._global_log(f"Error opening explorer: {e}", level="error")

    def _update_button_visibility(self):
        """Show only relevant action buttons based on status."""
        if not hasattr(self, '_start_btn'):
            return
            
        self._start_btn.pack_forget()
        self._stop_btn.pack_forget()
        self._restart_btn.pack_forget()

        is_installing = getattr(self, '_is_installing', False)

        if is_installing:
            if self._status in ('running', 'starting'):
                self._stop_btn.pack(side="left", padx=(0, 2))
                self._stop_btn.configure(state="disabled")
                self._restart_btn.pack(side="left", padx=(0, 2))
                self._restart_btn.configure(state="disabled")
            else:
                self._start_btn.pack(side="left", padx=(0, 2))
                self._start_btn.configure(state="disabled")
        else:
            if self._status in ('running', 'starting'):
                self._stop_btn.pack(side="left", padx=(0, 2))
                self._stop_btn.configure(state="normal")
                self._restart_btn.pack(side="left", padx=(0, 2))
                self._restart_btn.configure(state="normal")
            else:
                self._start_btn.pack(side="left", padx=(0, 2))
                self._start_btn.configure(state="normal")

        is_running = self._status in ('running', 'starting')
        if hasattr(self, '_install_btn'):
            if is_running:
                self._install_btn.configure(state="disabled")
            elif not is_installing:
                self._install_btn.configure(state="normal")

    def _update_header_hints(self):
        """Update the branch + profile hint text in the header."""
        parts = []
        # Branch
        if hasattr(self, '_branch_combo'):
            branch = self._branch_combo.get()
            if branch and branch != "cargando...":
                parts.append(f"⎇ {branch}")
        # Profile / Env
        if hasattr(self, '_profile_combo'):
            parts.append(f"⚙ {self._profile_combo.get()}")
        elif hasattr(self, '_env_combo'):
            parts.append(f"🌐 {self._env_combo.get()}")
        elif hasattr(self, '_config_combos') and self._config_combos:
            for _, combo in self._config_combos.items():
                v = combo.get()
                if v and v not in ('- Sin Seleccionar -', ''):
                    parts.append(f"⚙ {v}")
                    break
        # Custom command
        if hasattr(self, '_cmd_entry'):
            cmd = self._cmd_entry.get().strip()
            if cmd:
                parts.append(f"$ {cmd}")
            elif self._repo.run_command:
                parts.append(f"$ {self._repo.run_command}")
        elif self._repo.run_command:
            parts.append(f"$ {self._repo.run_command}")

        is_installed = True
        install_cfg = getattr(self._repo, 'ui_config', {}).get('install', {})
        check_dirs = install_cfg.get('check_dirs', []) if install_cfg else []
        
        if check_dirs:
            for cd in check_dirs:
                if not os.path.isdir(os.path.join(self._repo.path, cd)):
                    is_installed = False
                    break
                    
        if not is_installed and self._repo.run_install_cmd:
            deps_text = install_cfg.get('status_label_deps_missing', '⚠ Falta instalar')
            parts.insert(0, deps_text)
            self._branch_hint.configure(text="   ".join(parts), text_color=theme.C.text_warning_badge)
        else:
            self._branch_hint.configure(text="   ".join(parts), text_color=theme.C.text_faint)

    def install_dependencies(self, skip_if_installed=False):
        """Method to trigger dependency installation via YAML commands."""
        install_cfg = getattr(self._repo, 'ui_config', {}).get('install', {})
        check_dirs = install_cfg.get('check_dirs', [])
        
        if not self._repo.run_install_cmd:
            return
            
        is_installed = False
        if check_dirs:
            is_installed = True
            for cd in check_dirs:
                if not os.path.isdir(os.path.join(self._repo.path, cd)):
                    is_installed = False
                    break
        else:
            is_installed = True
            
        if skip_if_installed and is_installed:
            return
            
        self._run_install_cmd(bypass_confirm=True)

    # ─── EXPAND PANEL ────────────────────────────────────────────

    def _build_expand_panel(self):
        """Build the expandable details panel."""
        repo = self._repo

        # corner_radius para encajar bien sin tapar las esquinas del padre
        self._expand_panel = ctk.CTkFrame(self, fg_color=theme.C.expand_panel, corner_radius=theme.G.corner_panel)

        ctk.CTkFrame(self._expand_panel, height=1, fg_color=theme.C.divider).pack(fill="x", padx=10)

        content = ctk.CTkFrame(self._expand_panel, fg_color="transparent")
        content.pack(fill="x", padx=12, pady=(4, 4))

        # Row 1: Branch + secondary buttons
        self._build_branch_row(content, repo)
        # Row 2: Conditional selectors
        self._build_selector_row(content, repo)
        # Row 3: Custom start command
        if repo.repo_type != 'docker-infra':
            self._build_command_row(content, repo)
        # Row 3.5: Docker Checkboxes (Below Cmd)
        self._build_docker_row(content, repo)
        # Row 4: Logs
        self._build_log_row(content)

    def _build_log_row(self, content):
        """Build the repository log console."""
        self._log_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._log_frame.pack(fill="x", pady=(4, 0))

        header = ctk.CTkFrame(self._log_frame, fg_color="transparent")
        header.pack(fill="x")
        
        ctk.CTkLabel(header, text="📋 Logs del Repositorio", font=theme.font("base", bold=True), text_color=theme.C.text_secondary).pack(side="left")

        clear_btn = ctk.CTkButton(
            header, text="🗑 Limpiar", width=60,
            command=self._clear_logs, **theme.btn_style("log_action", height="sm")
        )
        clear_btn.pack(side="right")

        detach_btn = ctk.CTkButton(
            header, text="🗗 Desacoplar", width=80,
            command=self._detach_logs, **theme.btn_style("log_action", height="sm")
        )
        detach_btn.pack(side="right", padx=(0, 6))

        self._log_textbox = ctk.CTkTextbox(
            self._log_frame, height=120,
            state="disabled", **theme.log_textbox_style()
        )
        self._log_textbox.pack(fill="x", pady=(4, 0))
        
    def _clear_logs(self):
        """Clear the embedded and detached logs, and hide the console."""
        if hasattr(self, '_log_textbox'):
            self._log_textbox.configure(state="normal")
            self._log_textbox.delete("1.0", "end")
            self._log_textbox.configure(state="disabled")
            
        if getattr(self, '_detached_log_textbox', None) and self._detached_log_textbox.winfo_exists():
            self._detached_log_textbox.configure(state="normal")
            self._detached_log_textbox.delete("1.0", "end")
            self._detached_log_textbox.configure(state="disabled")

        self._has_logs = False

    def _detach_logs(self):
        """Open the logs in a separate detached window."""
        # Prevent multiple detached windows
        if getattr(self, '_detached_log_window', None) and self._detached_log_window.winfo_exists():
            self._detached_log_window.focus()
            return
            
        self._detached_log_window = ctk.CTkToplevel(self)
        self._detached_log_window.title(f"Logs - {self._repo.name}")
        self._detached_log_window.geometry("800x600")

        # Set window icon (green if running/starting, red otherwise)
        try:
            app_dir = getattr(self.winfo_toplevel(), '_app_dir', None)
            if app_dir:
                _icon_color = "green" if self._status in ('running', 'starting') else "red"
                _icon_path = os.path.join(app_dir, f"icon_{_icon_color}.ico")
                if os.path.exists(_icon_path):
                    self._detached_log_window.after(200, lambda p=_icon_path: self._detached_log_window.iconbitmap(p))
        except Exception:
            pass

        # Bring window to front
        self.after(100, lambda: self._detached_log_window.lift())
        self.after(110, lambda: self._detached_log_window.focus_force())
        
        self._detached_log_textbox = ctk.CTkTextbox(
            self._detached_log_window,
            **theme.log_textbox_style(detached=True)
        )
        self._detached_log_textbox.pack(fill="both", expand=True)
        
        # Copy current content
        current_logs = self._log_textbox.get("1.0", "end")
        self._detached_log_textbox.insert("end", current_logs)
        self._detached_log_textbox.configure(state="disabled")
        self._detached_log_textbox.see("end")

    def _repo_log(self, message: str):
        """Add a timestamped log message to this repo's console. Thread-safe."""
        if message:
            # Eliminar secuencias de escape ANSI (ej. colores)
            message = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', message)
            
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        def _insert():
            self._has_logs = True

            if hasattr(self, '_log_textbox'):
                self._log_textbox.configure(state="normal")
                self._log_textbox.insert("end", line)
                self._log_line_count += 1
                if self._log_line_count > 500:
                    excess = self._log_line_count - 500
                    self._log_textbox.delete("1.0", f"{excess + 1}.0")
                    self._log_line_count = 500
                self._log_textbox.see("end")
                self._log_textbox.configure(state="disabled")

            if getattr(self, '_detached_log_textbox', None) and self._detached_log_textbox.winfo_exists():
                self._detached_log_textbox.configure(state="normal")
                self._detached_log_textbox.insert("end", line)
                self._detached_log_line_count += 1
                if self._detached_log_line_count > 500:
                    excess = self._detached_log_line_count - 500
                    self._detached_log_textbox.delete("1.0", f"{excess + 1}.0")
                    self._detached_log_line_count = 500
                self._detached_log_textbox.see("end")
                self._detached_log_textbox.configure(state="disabled")
            
            self._flash_log_icon()

        try:
            self.after(0, _insert)
        except tk.TclError:
            pass

    def _flash_log_icon(self):
        """Temporarily change the status icon color to orange when a log is received."""
        if not hasattr(self, '_status_label'):
            return
            
        # Only flash orange if status is already running or starting
        if getattr(self, '_status', 'stopped') not in ('running', 'starting'):
            return
            
        if hasattr(self, '_log_flash_timer') and self._log_flash_timer:
            self.after_cancel(self._log_flash_timer)

        self._status_label.configure(text="🔴", text_color=theme.STATUS_ICONS.get('logging', theme.C.status_logging))

        def _revert():
            if hasattr(self, '_status_label') and hasattr(self, '_status'):
                self._status_label.configure(text="🔴", text_color=theme.STATUS_ICONS.get(self._status, theme.C.status_stopped))
            self._log_flash_timer = None

        self._log_flash_timer = self.after(3000, _revert)

    def _build_branch_row(self, content, repo):
        """Build branch + secondary buttons row."""
        row1 = ctk.CTkFrame(content, fg_color="transparent")
        row1.pack(fill="x")

        ctk.CTkLabel(row1, text="Rama:", font=theme.font("lg"),
                     text_color=theme.C.text_secondary, width=50, anchor="e").pack(side="left")

        initial_branches = self._branches_cache if getattr(self, '_branches_cache', None) else ["cargando..."]
        self._branch_combo = ctk.CTkComboBox(
            row1, values=initial_branches, width=180,
            command=self._on_branch_change, **theme.combo_style()
        )
        if getattr(self, '_current_branch', None):
            self._branch_combo.set(self._current_branch)
        self._branch_combo.pack(side="left", padx=(6, 4))

        def _on_branch_type(event):
            text = self._branch_combo.get().lower()
            filtered = [b for b in self._branches_cache if text in b.lower()]
            self._branch_combo.configure(values=filtered if filtered else self._branches_cache)

        self._branch_combo.bind("<KeyRelease>", _on_branch_type)

        search_btn = ctk.CTkButton(
            row1, text="🔍", width=28,
            command=self._fetch_branches, **theme.btn_style("log_action")
        )
        search_btn.pack(side="left", padx=(0, 10))
        ToolTip(search_btn, "Buscar ramas remotas (fetch)")

        # Pull
        self._pull_btn = ctk.CTkButton(
            row1, text="⬇ Pull", width=65,
            command=self._pull, **theme.btn_style("blue")
        )
        self._pull_btn.pack(side="left", padx=(0, 3))
        ToolTip(self._pull_btn, "Descargar cambios (git pull)")

        # Clean
        self._clean_btn = ctk.CTkButton(
            row1, text="🧹 Limpiar", width=80,
            command=self._clean_repo, **theme.btn_style("purple")
        )
        self._clean_btn.pack(side="left", padx=(0, 3))
        ToolTip(self._clean_btn, "Limpiar ficheros no commiteados y reestablecer cambios")

        # Config
        if not repo.environment_files and repo.repo_type != 'docker-infra':
            edit_btn = ctk.CTkButton(
                row1, text=BTN_CONFIG_TEXT, width=80,
                command=self._edit_config, **theme.btn_style("neutral")
            )
            edit_btn.pack(side="left")
            ToolTip(edit_btn, BTN_CONFIG_TOOLTIP)

        # Right-aligned frame for install buttons
        self.right_frame = ctk.CTkFrame(row1, fg_color="transparent", width=0, height=0)
        self.right_frame.pack(side="right", padx=(10, 0))

        # Install Button
        self._build_install_btn(self.right_frame)

        # Seed
        if repo.has_seeds or ('docker_checkboxes' in repo.features and repo.has_database):
            seed_btn = ctk.CTkButton(
                row1, text="🌱 Seed", width=70,
                command=self._seed, **theme.btn_style("purple_global")
            )
            seed_btn.pack(side="left", padx=(0, 3))
            ToolTip(seed_btn, "Ejecutar seeds de BD")

    def _build_install_btn(self, parent):
        """Build the general install button (Install or Reinstall) based on UI Config."""
        repo = self._repo
        path = repo.path
        
        install_cfg = getattr(repo, 'ui_config', {}).get('install', {})
        if not install_cfg and not repo.run_install_cmd:
            return

        check_dirs = install_cfg.get('check_dirs', [])
        
        # If check_dirs exist, check them. If not, we assume it's not installed yet,
        # or it can never be "installed" in a persistent folder sense.
        is_installed = False
        if check_dirs:
            is_installed = True
            for cd in check_dirs:
                if not os.path.isdir(os.path.join(path, cd)):
                    is_installed = False
                    break
        
        # Exact command
        if is_installed and repo.run_reinstall_cmd:
            cmd_str = repo.run_reinstall_cmd
        elif repo.run_install_cmd:
            cmd_str = repo.run_install_cmd
        else:
            cmd_str = "" # Should never happen if 'install' config is present, but just in case
            
        if not cmd_str:
            return

        tooltip_text = cmd_str
        
        if is_installed:
            btn_text = install_cfg.get('label_ok', REINSTALL_LBL)
            _variant = "neutral_alt"
        else:
            btn_text = install_cfg.get('label_missing', "Install")
            _variant = "danger_alt"

        self._install_btn = ctk.CTkButton(
            parent, text=btn_text, width=100,
            command=self._run_install_cmd, **theme.btn_style(_variant)
        )
        self._install_btn.pack(side="left", padx=(0, 6))
        self._install_tooltip = ToolTip(self._install_btn, tooltip_text)


    def _build_selector_row(self, content, repo):
        """Build conditional selector row (profile, DB, env, docker)."""
        row2 = ctk.CTkFrame(content, fg_color="transparent")
        has_row2 = False

        combo_style = theme.combo_style()

        if repo.environment_files and repo.repo_type != 'docker-infra':
            has_row2 = True
            from core.config_manager import load_repo_configs, load_active_config
            
            target_files = []
            env_dirs: dict = {}
            for f in repo.environment_files:
                parent = os.path.dirname(f)
                basename = os.path.basename(f)
                
                # If we haven't seen this directory yet, add it
                if parent not in env_dirs:
                    env_dirs[parent] = f
                else:
                    # Priority rules if we already have a file for this directory:
                    # 1. Prefer .yml over .properties
                    # 2. Prefer environment.ts over specific like environment.prod.ts
                    current_file = env_dirs[parent]
                    if (current_file.endswith('.properties') and basename.endswith('.yml')) or basename == 'environment.ts':
                        env_dirs[parent] = f

            target_files = sorted(list(env_dirs.values()))
            
            self._config_combos = {} 
            
            # Extract label prefix from UI config if defined, defaults to 'App'
            lbl_prefix = "App"
            if getattr(repo, 'ui_config', {}) and 'selectors' in repo.ui_config:
                selectors = repo.ui_config['selectors']
                if selectors and isinstance(selectors, list):
                    lbl_prefix = selectors[0].get('label', 'App').replace(':', '')
            
            # Vertical container — use fill=x only, no expand, to keep compact height
            selectors_container = ctk.CTkFrame(row2, fg_color="transparent")
            selectors_container.pack(side="left", padx=0, fill="x", expand=True)
            
            for target_file in target_files:
                sel_frame = ctk.CTkFrame(selectors_container, fg_color="transparent")
                sel_frame.pack(side="top", fill="x", pady=(0, 4))
                
                # Identify submodule name for tooltip/label
                try:
                    rel_path = os.path.relpath(target_file, repo.path)
                    mod_name = os.path.dirname(rel_path) or "root"
                except ValueError:
                    mod_name = "unknown"

                # Load config values for THIS specific target file
                config_key = self.get_config_key(target_file)
                configs = load_repo_configs(config_key)
                    
                opts = ["- Sin Seleccionar -"] + list(configs.keys())
                
                lbl_text = f"{lbl_prefix}:"

                ctk.CTkLabel(sel_frame, text=lbl_text, font=theme.font("lg"),
                             text_color=theme.C.text_secondary, width=50, anchor="e").pack(side="left")

                combo = ctk.CTkComboBox(
                    sel_frame, values=opts, width=180,
                    command=lambda val, tf=target_file: self._on_config_change(val, tf), **combo_style
                )
                combo.pack(side="left", padx=(6, 4))
                
                active_config = load_active_config(config_key)
                if active_config in opts:
                    combo.set(active_config)
                    # Force application of the active config just in case it was lost
                    self.after(500, self._on_config_change, active_config, target_file, True)
                else:
                    combo.set("- Sin Seleccionar -")
                    
                self._config_combos[target_file] = combo
                
                # Config Button inside the selector row
                cfg_btn = ctk.CTkButton(
                    sel_frame, text="⚙", width=28,
                    command=lambda tf=target_file: self._open_config_manager(tf),
                    **theme.btn_style("neutral", font_size="xl")
                )
                cfg_btn.pack(side="left", padx=(0, 6))
                ToolTip(cfg_btn, f"Modificar esta configuración ({mod_name})")

                # Type label on the right as plain grey hint
                if len(target_files) > 1:
                    ctk.CTkLabel(sel_frame, text=mod_name, font=theme.font("xs", mono=True),
                                 text_color=theme.C.text_faint, anchor="w").pack(side="left", padx=(0, 8))

        if repo.has_database and 'database_selector' in repo.features:
            has_row2 = True
            ctk.CTkLabel(row2, text="BD:", font=theme.font("lg"),
                         text_color=theme.C.text_secondary, width=35, anchor="e").pack(side="left")
            db_options = list(self._db_presets.keys()) if self._db_presets else [NO_DB_PRESET]
            self._db_combo = ctk.CTkComboBox(
                row2, values=db_options, width=140,
                command=self._on_db_change, **combo_style
            )
            self._db_combo.pack(side="left", padx=(6, 0))
            if self._db_presets:
                self._db_combo.set(db_options[0])
            else:
                self._db_combo.set(NO_DB_PRESET)

        if has_row2:
            row2.pack(fill="x", pady=(4, 0))

        row_java = ctk.CTkFrame(content, fg_color="transparent")
        has_row_java = False

        if 'java_version' in repo.features:
            has_row_java = True
            ctk.CTkLabel(row_java, text="Java:", font=theme.font("lg"),
                         text_color=theme.C.text_secondary, width=50, anchor="e").pack(side="left")
            java_options = ["Sistema (Por Defecto)"] + list(self._java_versions.keys())
            self._java_combo = ctk.CTkComboBox(
                row_java, values=java_options, width=150,
                variable=self.selected_java_var, **combo_style
            )
            self._java_combo.pack(side="left", padx=(6, 12))

            if getattr(repo, 'java_version', None):
                self._java_hint_label = ctk.CTkLabel(row_java, text=f"Recomendado: Java {repo.java_version}", font=theme.font("md"), text_color=theme.C.text_faint)
                self._java_hint_label.pack(side="left", padx=(0, 10))

                def _on_java_change(*args):
                    if not hasattr(self, '_java_hint_label') or not self._java_hint_label.winfo_exists():
                        return
                    if self.selected_java_var.get() == "Sistema (Por Defecto)":
                        self._java_hint_label.pack(side="left", padx=(0, 10))
                    else:
                        self._java_hint_label.pack_forget()

                self.selected_java_var.trace("w", _on_java_change)
                _on_java_change()

        if has_row_java:
            row_java.pack(fill="x", pady=(4, 0))

    def update_java_versions(self, versions: dict):
        """Update available Java versions without restarting."""
        self._java_versions = versions
        if hasattr(self, '_java_combo'):
            java_options = ["Sistema (Por Defecto)"] + list(self._java_versions.keys())
            self._java_combo.configure(values=java_options)
            
            # If current selection is no longer valid, reset to default
            current = self.selected_java_var.get()
            if current not in java_options:
                self.selected_java_var.set("Sistema (Por Defecto)")

    def _build_command_row(self, content, repo):
        """Build custom start command row."""
        row3 = ctk.CTkFrame(content, fg_color="transparent")
        row3.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(row3, text="Cmd:", font=theme.font("lg"),
                     text_color=theme.C.text_secondary, width=50, anchor="e").pack(side="left")

        self._cmd_entry = ctk.CTkEntry(
            row3, height=theme.G.btn_height_md, font=theme.font("md", mono=True),
            corner_radius=theme.G.corner_btn, fg_color=theme.C.section,
            border_color=theme.C.default_border,
            placeholder_text=repo.run_command or "comando de inicio"
        )
        self._cmd_entry.pack(side="left", padx=(6, 4), fill="x", expand=True)
        ToolTip(self._cmd_entry,
                "Comando de inicio personalizado. Dejar vacío para usar el por defecto.\n"
                f"Por defecto: {repo.run_command or 'N/A'}")

        # Update header hints when command changes
        def _on_cmd_changed(e):
            self._update_header_hints()
            self._trigger_change_callback()
        
        self._cmd_entry.bind("<FocusOut>", _on_cmd_changed)
        self._cmd_entry.bind("<Return>", _on_cmd_changed)

    def _build_docker_row(self, content, repo):
        """Build docker-compose checkboxes row."""
        if 'docker_checkboxes' not in repo.features or not repo.docker_compose_files:
            return

        row_docker = ctk.CTkFrame(content, fg_color="transparent")
        row_docker.pack(fill="x", pady=(4, 0))

        docker_frame = ctk.CTkFrame(row_docker, fg_color="transparent")
        docker_frame.pack(side="left", padx=(1, 0))

        for dc_file in repo.docker_compose_files:
            dc_name = os.path.basename(dc_file)
            if dc_name == 'docker-compose.yml':
                dc_name = 'docker-compose'
            elif dc_name.startswith('docker-compose.'):
                dc_name = dc_name.replace('docker-compose.', '').replace('.yml', '')

            if dc_name == 'all':
                continue

            # Default assume stopped styling
            btn_color = theme.C.docker_stopped_fg if dc_file not in self._active_compose_files else theme.C.docker_active_fg
            border_color = theme.C.docker_border_stopped if dc_file not in self._active_compose_files else theme.C.docker_border_active

            btn = ctk.CTkButton(
                docker_frame, text=f"🐳 {dc_name.title()} [?/?]",
                font=theme.font("md"), height=26,
                fg_color=btn_color, hover_color=theme.C.subtle_border,
                border_width=theme.G.border_width, border_color=border_color,
                corner_radius=theme.G.corner_btn,
                command=lambda f=dc_file: self._open_docker_compose_dialog(f)
            )
            btn.pack(side="left", padx=(0, 6))
            self._docker_compose_buttons[dc_file] = btn

            if dc_file in self._active_compose_files:
                ToolTip(btn, "Haga clic para gestionar servicios (Activo en perfil)")
            else:
                ToolTip(btn, "Haga clic para gestionar servicios")

        # Start thread to update container counts if not running
        if not self._compose_status_thread_running:
            self._compose_status_thread_running = True
            self._start_compose_status_thread()

    # ─── Toggle expand ───────────────────────────────────────────

    def _toggle_expand(self, event=None):
        """Toggle expanded/collapsed state. Builds the panel lazily on first open."""
        self._expanded = not self._expanded
        if self._expanded:
            if not self._expand_panel_built:
                self._build_expand_panel()
                self._expand_panel_built = True
            self._expand_panel.pack(fill="x", padx=3, pady=(0, 2), after=self._header)
            self._toggle_btn.configure(text="▲")
        else:
            self._expand_panel.pack_forget()
            self._toggle_btn.configure(text="▼")

    # ─── Actions ─────────────────────────────────────────────────

    def _refresh_branch(self):
        """Refresh current branch display."""
        def _run():
            from core.git_manager import get_current_branch, get_branches
            current = get_current_branch(self._repo.path)
            branches = get_branches(self._repo.path)
            self._branches_cache = branches

            def _update():
                self._current_branch = current
                if branches:
                    if hasattr(self, '_branch_combo'):
                        self._branch_combo.configure(values=branches)
                if hasattr(self, '_branch_combo'):
                    self._branch_combo.set(current)
                self._update_header_hints()
                self._check_pull_status()
                self._refresh_badge()
            self.after(0, _update)

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _fetch_branches(self):
        """Fetch remote branches."""
        def _run():
            from core.git_manager import fetch, get_branches
            fetch(self._repo.path, self._log)
            branches = get_branches(self._repo.path)
            self._branches_cache = branches

            def _update():
                self._branch_combo.configure(values=branches)
            self.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _on_branch_change(self, branch: str):
        """Handle branch change."""
        if branch not in self._branches_cache and branch != "cargando...":
            return
            
        def _run():
            from core.git_manager import checkout, get_current_branch
            from tkinter import messagebox
            success, msg = checkout(self._repo.path, branch, self._log)
            actual_branch = get_current_branch(self._repo.path)
            
            if success and actual_branch == branch:
                def _update():
                    self._current_branch = branch
                    if hasattr(self, '_branch_combo'):
                        self._branch_combo.set(branch)
                    self._update_header_hints()
                    self._check_pull_status()
                    self._refresh_badge()
                    self._trigger_change_callback()
                self.after(0, _update)
            else:
                def _err():
                    messagebox.showerror("Error al cambiar de rama", f"No se pudo cambiar a '{branch}'.\nComprueba si hay ficheros modificados en conflicto.\n\nDetalles:\n{msg}")
                    if hasattr(self, '_branch_combo'):
                        self._branch_combo.set(actual_branch)
                        self._update_header_hints()
                self.after(0, _err)

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _resolve_target_file(self, repo, target_file: str) -> str:
        """Resolve the target config file path."""
        if target_file:
            return target_file
            
        main_filename = getattr(repo, 'env_main_config_filename', '')
        if not main_filename:
            return target_file
            
        for ef in repo.environment_files:
            if os.path.basename(ef) == main_filename:
                return ef
                
        if hasattr(repo, 'env_default_dir'):
            return os.path.join(repo.path, repo.env_default_dir, main_filename)
            
        return target_file

    def _handle_unselect_config(self, target_file: str, skip_log: bool, is_real_change: bool):
        """Restore original config when unselected."""
        should_log = not skip_log or is_real_change
        if self._log and should_log:
            self._log(f"[{self._repo.name}] Configuración deseleccionada. Restaurando configuración original.")
            
        if target_file and os.path.isfile(target_file):
            import subprocess
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            subprocess.run(['git', 'checkout', '--', target_file], cwd=self._repo.path, capture_output=True, creationflags=flags)
        
        self.after(0, self._update_header_hints)
        self._trigger_change_callback()

    def _write_spring_config(self, repo, target_file: str, config_data) -> tuple[bool, str]:
        """Write Spring Boot specific configuration."""
        from core.config_manager import write_config_file_raw
        config_str = str(config_data)
        
        is_props = "=" in config_str.split("\n", 3)[0] or "=" in config_str
        if is_props and not config_str.startswith("spring:") and not config_str.startswith("server:"):
            target_file = target_file.replace('.yml', '.properties')
        else:
            target_file = target_file.replace('.properties', '.yml')
            
        opposite_file = target_file.replace('.properties', '.yml') if target_file.endswith('.properties') else target_file.replace('.yml', '.properties')
        
        if os.path.exists(opposite_file):
            try:
                os.remove(opposite_file)
            except OSError:
                pass
                
        target_classes_file = os.path.join(repo.path, 'target', 'classes', os.path.basename(opposite_file))
        if os.path.exists(target_classes_file):
            try:
                os.remove(target_classes_file)
            except OSError:
                pass
                
        return write_config_file_raw(target_file, config_data), target_file

    def _apply_config_data(self, target_file: str, config_name: str, config_data, skip_log: bool, is_real_change: bool):
        """Write config data to the target file."""
        from core.config_manager import write_angular_environment_raw, write_config_file_raw
        from tkinter import messagebox
        import json
        
        should_log = not skip_log or is_real_change
        
        if not config_data:
            if self._log and should_log:
                self._log(f"[{self._repo.name}] La configuración '{config_name}' no se encontró.")
            return

        writer_type = getattr(self._repo, 'env_config_writer_type', 'raw')
        
        if writer_type == 'angular':
            content = "\n".join([f"export const environment = {json.dumps(config_data, indent=2)};", ""]) if isinstance(config_data, dict) else str(config_data)
            res = write_angular_environment_raw(target_file, content)
        elif writer_type == 'spring':
            res, target_file = self._write_spring_config(self._repo, target_file, config_data)
        else:
            res = write_config_file_raw(target_file, config_data)

        if res:
            if self._log and should_log:
                self._log(f"[{self._repo.name}] Configuración '{config_name}' aplicada.")
        elif should_log:
            self.after(0, lambda tf=target_file: messagebox.showerror("Error", f"No se pudo escribir en '{tf}'"))
            
        self.after(0, self._update_header_hints)
        self._trigger_change_callback()

    def _on_config_change(self, config_name: str, target_file: str = None, skip_log: bool = False):
        """Handle env/app change and overwrite target config file."""
        from core.config_manager import load_repo_configs, save_active_config, load_active_config
        
        repo = self._repo
        target_file = self._resolve_target_file(repo, target_file)
        config_key = self.get_config_key(target_file)
        
        active_before = load_active_config(config_key)
        is_real_change = (active_before != config_name)
        save_active_config(config_key, config_name)
        
        def _run_change():
            if config_name == "- Sin Seleccionar -":
                self._handle_unselect_config(target_file, skip_log, is_real_change)
                return

            configs = load_repo_configs(config_key)
            self._apply_config_data(target_file, config_name, configs.get(config_name), skip_log, is_real_change)

        import threading
        threading.Thread(target=_run_change, daemon=True).start()

    def _open_config_manager(self, target_file: str = None):
        """Open the RepoConfigManagerDialog for this repository."""
        from gui.dialogs import RepoConfigManagerDialog

        config_key = self.get_config_key(target_file) if target_file else self._repo.name

        if target_file:
            source_dir = os.path.dirname(target_file)
        else:
            default_dir = getattr(self._repo, 'env_default_dir', '')
            source_dir = os.path.join(self._repo.path, default_dir) if default_dir else ''

        def _on_configs_updated():
            def _do_update():
                from core.config_manager import load_repo_configs
                configs = load_repo_configs(config_key)
                opts = ["- Sin Seleccionar -"] + list(configs.keys())
                if hasattr(self, '_config_combos'):
                    combo = self._config_combos.get(target_file)
                    if combo and combo.winfo_exists():
                        combo.configure(values=opts)
                        curr = combo.get()
                        if curr not in opts:
                            combo.set("- Sin Seleccionar -")
                    self._update_header_hints()
                elif hasattr(self, '_config_combo') and self._config_combo.winfo_exists():
                    self._config_combo.configure(values=opts)
                    curr = self._config_combo.get()
                    if curr not in opts:
                        self._config_combo.set("- Sin Seleccionar -")
                        self._update_header_hints()
            self.after(0, _do_update)

        RepoConfigManagerDialog(
            self.winfo_toplevel(),
            repo=self._repo,
            config_key=config_key,
            log_callback=self._log,
            on_close_callback=_on_configs_updated,
            source_dir=source_dir,
        )

    def _on_db_change(self, preset_name: str):
        """Handle DB preset change."""
        if preset_name == NO_DB_PRESET:
            return
        preset = self._db_presets.get(preset_name)
        if not preset:
            return

        def _run():
            from core.config_manager import set_spring_db_preset
            profile = getattr(self, '_profile_combo', None)
            active_profile = profile.get() if profile else 'default'
            resources_dir = os.path.join(self._repo.path, getattr(self._repo, 'env_default_dir', 'src/main/resources'))
            success = set_spring_db_preset(resources_dir, active_profile, preset)
            if self._log:
                msg = f"BD cambiada a: {preset_name}" if success else "Error al cambiar BD"
                self._log(f"[{self._repo.name}] {msg}")

        threading.Thread(target=_run, daemon=True).start()

    # ─── install_cmd ─────────────────────────────────────────────

    def _run_install_cmd(self, bypass_confirm=False):
        """Run the appropriate install command."""
        from tkinter import messagebox
        repo = self._repo
        path = repo.path
        
        install_cfg = getattr(repo, 'ui_config', {}).get('install', {})
        check_dirs = install_cfg.get('check_dirs', [])
        already_installed = False
        
        if check_dirs:
            already_installed = True
            for cd in check_dirs:
                if not os.path.isdir(os.path.join(path, cd)):
                    already_installed = False
                    break
            
        if hasattr(self, '_install_btn') and already_installed and not bypass_confirm:
            if not messagebox.askyesno("Reinstalar", "¿Estás seguro de que deseas volver a instalar dependencias?"):
                return
                
        if already_installed and repo.run_reinstall_cmd:
            cmd_str = repo.run_reinstall_cmd
        elif repo.run_install_cmd:
            cmd_str = repo.run_install_cmd
        else:
            return
                
        running_text = "Installing..."
        success_text = install_cfg.get('label_ok', REINSTALL_LBL)
        fail_text = "Error!"
            
        if self._log:
            self._log(f"Running {cmd_str}...")
            
        self._install_btn.configure(text=running_text, state="disabled")
        self._is_installing = True
        self._update_button_visibility()

        env = None
        if 'java_version' in repo.features:
            from core.java_manager import build_java_env
            java_choice = getattr(self, 'selected_java_var', None)
            if java_choice:
                java_home = self._java_versions.get(java_choice.get(), "")
                env = build_java_env(java_home)
                if java_home and self._log:
                    self._log(f"Usando JAVA_HOME: {java_home}")

        def _run():
            try:
                # Use shell=True for all config-driven commands, allowing &&, &, and shell features.
                use_shell = True
                process = _create_subprocess(cmd_str, cwd=repo.path, env=env, shell=use_shell)
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    if self._log:
                        self._log(line.strip())
                try:
                    process.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    if self._log:
                        self._log(f"[{self._repo.name}] ⚠️ Instalación superó 10 min, proceso terminado")
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except OSError:
                        pass

                def _done():
                    self._is_installing = False
                    is_ok = True
                    if check_dirs:
                        for cd in check_dirs:
                            if not os.path.isdir(os.path.join(self._repo.path, cd)):
                                is_ok = False
                                break
                    if is_ok:
                        _ok_style = theme.btn_style("neutral_alt")
                        self._install_btn.configure(
                            text=success_text,
                            fg_color=_ok_style["fg_color"],
                            border_color=_ok_style["border_color"],
                            hover_color=_ok_style["hover_color"]
                        )
                        self._update_header_hints()
                        if self._log:
                            self._log(f"[{self._repo.name}] Instalación finalizada ✓")
                    else:
                        _fail_style = theme.btn_style("danger_alt")
                        self._install_btn.configure(
                            text=fail_text,
                            fg_color=_fail_style["fg_color"],
                            border_color=_fail_style["border_color"],
                            hover_color=_fail_style["hover_color"]
                        )
                        if self._log:
                            self._log(f"[{self._repo.name}] Fallo al instalar. Archivos clave no encontrados.")
                    self._update_button_visibility()
                self.after(0, _done)
            except Exception as e:
                if self._log:
                    self._log(f"Error en instalación: {e}")
                def _err():
                    self._is_installing = False
                    self._install_btn.configure(text=fail_text, state="normal")
                    self._update_button_visibility()
                self.after(0, _err)

        threading.Thread(target=_run, daemon=True).start()

    # ─── Start / Stop / Restart ──────────────────────────────────

    def _detect_port_from_log(self, line: str):
        """Dynamically detect and update the server port from log output."""
        if self._repo.server_port:
            return  # Port is already statically defined

        for regex in PORT_REGEXES:
            match = regex.search(line)
            if match:
                try:
                    port = int(match.group(1))
                    if self._repo.server_port != port:
                        self._repo.server_port = port
                        self.after(0, lambda: self._update_status(self._repo.name, self._status))
                except ValueError:
                    pass
                break

    def _detect_status_from_log(self, line: str):
        """Detect service readiness or failure from log output using configurable patterns."""
        if self._status != 'starting':
            return

        ready = self._repo.ready_pattern
        error = self._repo.error_pattern

        if error and re.search(error, line):
            self.after(0, lambda: self._update_status(self._repo.name, 'error'))
            return

        if ready and re.search(ready, line):
            self.after(0, lambda: self._update_status(self._repo.name, 'running'))

    def _get_start_command(self):
        """Get the start command — custom or default."""
        if hasattr(self, '_cmd_entry'):
            custom = self._cmd_entry.get().strip()
            if custom:
                return custom
        return self._repo.run_command or ''

    def _start(self):
        """Start the service using the config-driven run_command from the YAML definition."""
        repo = self._repo

        if 'docker_checkboxes' in repo.features:
            self._start_docker_services()
            return

        # Check for custom command entered by user
        custom_cmd = self._get_start_command()
        if custom_cmd and custom_cmd != repo.run_command:
            self._start_custom(custom_cmd)
            return

        # --- Config-driven generic start ---
        # run_command comes from the YAML (e.g. "npx nx serve cart", "mvnw.cmd spring-boot:run")
        cmd = repo.run_command or ''
        if not cmd:
            if self._log:
                self._log(f"[{repo.name}] ⚠ Sin comando de inicio definido en la configuración YAML.")
            return

        # Append profile flag if selected
        profile = ''
        if hasattr(self, '_profile_combo'):
            profile = self._profile_combo.get()
        elif hasattr(self, '_config_combos') and self._config_combos:
            for _, combo in self._config_combos.items():
                v = combo.get()
                if v and v not in ('- Sin Seleccionar -', ''):
                    profile = v
                    break

        if profile and repo.run_profile_flag:
            cmd = f"{cmd} {repo.run_profile_flag}{profile}"

        # Build env with Java if needed
        java_home = ''
        if hasattr(self, 'selected_java_var'):
            java_choice = self.selected_java_var.get()
            java_home = self._java_versions.get(java_choice, '')

        env = None
        if java_home:
            try:
                from core.java_manager import build_java_env
                env = build_java_env(java_home)
            except (ImportError, OSError):
                pass

        self._update_status(repo.name, 'starting')
        if self._log:
            self._log(f"[{repo.name}] ▶ {cmd}")

        def _run():
            try:
                process = _create_subprocess(cmd, cwd=repo.path, env=env, shell=True)
                # Track process in legacy launcher so stop/restart work
                from domain.models.running_service import RunningService
                svc = RunningService(name=repo.name, repo_path=repo.path, port=0, profile=profile, status='starting')
                svc.process = process
                self._launcher._services[repo.name] = svc

                # Stay in 'starting' — transition to 'running' is driven by ready_pattern
                if not repo.ready_pattern:
                    self.after(0, lambda: self._update_status(repo.name, 'running'))

                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    
                    decoded_line = line.strip()
                    self._detect_port_from_log(decoded_line)
                    self._detect_status_from_log(decoded_line)
                    
                    if self._log:
                        self._log(decoded_line)

                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except OSError:
                        pass
                # If still 'starting' when process exits, it failed (unless stopped manually)
                if getattr(self, '_is_stopping_manually', False):
                    final_status = 'stopped'
                    self._is_stopping_manually = False
                else:
                    final_status = 'error' if self._status == 'starting' else 'stopped'

                self.after(0, lambda s=final_status: self._update_status(repo.name, s))
                if self._log:
                    self._log(f"[{repo.name}] ⏹ Proceso terminado (código {process.returncode})")
            except Exception as e:
                self.after(0, lambda: self._update_status(repo.name, 'error'))
                if self._log:
                    self._log(f"[{repo.name}] ✗ Error: {e}")

        threading.Thread(target=_run, daemon=True, name=f'svc-{repo.name}').start()

    def _start_custom(self, cmd_str: str):
        """Start with a custom command."""
        repo = self._repo
        if self._log:
            self._log(f"Ejecutando: {cmd_str}")

        self._update_status(repo.name, 'starting')

        def _run():
            try:
                process = _create_subprocess(cmd_str, cwd=repo.path, env=None, shell=True)

                # Stay in 'starting' — transition to 'running' is driven by ready_pattern
                if not repo.ready_pattern:
                    self._update_status(repo.name, 'running')

                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    
                    decoded_line = line.strip()
                    self._detect_port_from_log(decoded_line)
                    self._detect_status_from_log(decoded_line)
                    
                    if self._log:
                        self._log(decoded_line)

                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except OSError:
                        pass
                # If still 'starting' when process exits, it failed (unless stopped manually)
                if getattr(self, '_is_stopping_manually', False):
                    final_status = 'stopped'
                    self._is_stopping_manually = False
                else:
                    final_status = 'error' if self._status == 'starting' else 'stopped'

                self._update_status(repo.name, final_status)
            except Exception as e:
                self._update_status(repo.name, 'error')
                if self._log:
                    self._log(f"Error: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _open_docker_compose_dialog(self, compose_file: str):
        """Open the modal to manage services for a specific compose file."""
        from gui.dialogs import DockerComposeDialog
        DockerComposeDialog(
            self.master.master if hasattr(self, 'master') and hasattr(self.master, 'master') else self,
            compose_file=compose_file,
            log_callback=self._log,
            on_status_change=self._update_compose_counts_now,
            profile_services=self._docker_profile_services.get(compose_file, []),
            on_profile_change=self._on_docker_profile_change,
        )

    def _on_docker_profile_change(self, compose_file: str, services: list):
        """Called by DockerComposeDialog when the user toggles profile checkboxes."""
        self._docker_profile_services[compose_file] = services
        
        # Auto-manage active state based on selected services
        if services:
            self._active_compose_files.add(compose_file)
        else:
            self._active_compose_files.discard(compose_file)
            
        # Update UI border if initialized
        if hasattr(self, '_docker_compose_buttons') and compose_file in self._docker_compose_buttons:
            btn = self._docker_compose_buttons[compose_file]
            if compose_file in self._active_compose_files:
                btn.configure(fg_color=theme.C.docker_active_fg, border_color=theme.C.docker_border_active)
            else:
                btn.configure(fg_color=theme.C.docker_stopped_fg, border_color=theme.C.docker_border_stopped)
                
        self._trigger_change_callback()

    def _update_compose_counts_now(self):
        """Immediate trigger for the background count updater."""
        pass # Background thread polls every 4s, which is enough

    def _start_compose_status_thread(self):
        """Background thread to poll docker container status for active compose files."""
        def _loop():
            import time
            from core.db_manager import parse_compose_services, get_compose_service_status
            while self._compose_status_thread_running and self.winfo_exists():
                total_running = 0
                for dc_file, btn in self._docker_compose_buttons.items():
                    try:
                        services = parse_compose_services(dc_file)
                        total = len(services)
                        status_map = get_compose_service_status(dc_file)
                        running = sum(1 for s in status_map.values() if s == "running")
                        
                        dc_name = os.path.basename(dc_file)
                        if dc_name == 'docker-compose.yml':
                            dc_name = 'docker-compose'
                        elif dc_name.startswith('docker-compose.'):
                            dc_name = dc_name.replace('docker-compose.', '').replace('.yml', '')
                            
                        text = f"🐳 {dc_name.title()} [{running}/{total}]"
                        
                        if dc_file in self._active_compose_files:
                            total_running += running
                            
                        # Update button thread-safely
                        def _update_btn(b=btn, t=text, r=running, f=dc_file):
                            if not b.winfo_exists(): return
                            b.configure(text=t)
                            if r > 0:
                                b.configure(border_color=theme.C.docker_border_running)
                            elif f in self._active_compose_files:
                                b.configure(border_color=theme.C.docker_border_active)
                            else:
                                b.configure(border_color=theme.C.docker_border_stopped)
                        
                        self.after(0, _update_btn)
                    except Exception:
                        pass
                
                # Update global repo status
                if self._active_compose_files:
                    def _update_global_status(r=total_running):
                        if not self.winfo_exists(): return
                        if r > 0:
                            self._status_label.configure(text="🔴", text_color=theme.C.docker_border_running)
                            self._status_text.configure(text=f"En ejecución ({r} servicios)", text_color=theme.C.docker_border_running)
                            self._status = "running"
                        else:
                            self._status_label.configure(text="🔴", text_color=theme.C.status_error)
                            self._status_text.configure(text="Detenido", text_color=theme.C.text_placeholder)
                            self._status = "stopped"
                            
                        self._update_button_visibility()
                    self.after(0, _update_global_status)
                        
                self._compose_stop_event.wait(timeout=15)
                if self._compose_stop_event.is_set():
                    break

        threading.Thread(target=_loop, daemon=True).start()

    def _start_docker_services(self):
        """Start active docker-compose services."""
        def _run():
            from core.db_manager import docker_compose_up
            for dc_file in self._active_compose_files:
                svcs = self._docker_profile_services.get(dc_file, [])
                if svcs:
                    docker_compose_up(dc_file, services=svcs, log=self._log)
                else:
                    docker_compose_up(dc_file, log=self._log)
            self._update_compose_counts_now()
        threading.Thread(target=_run, daemon=True).start()

    def _stop(self):
        """Stop the service using the service launcher."""
        repo = self._repo
        if 'docker_checkboxes' in repo.features:
            self._stop_docker_services()
            return

        self._is_stopping_manually = True
        self._launcher.stop_service(repo.name, self._log, self._update_status)

    def _stop_docker_services(self):
        """Stop active docker-compose services."""
        def _run():
            from core.db_manager import docker_compose_down
            for dc_file in self._active_compose_files:
                docker_compose_down(dc_file, log=self._log)
            self._update_compose_counts_now()
        threading.Thread(target=_run, daemon=True).start()

    def _restart(self):
        """Restart the service using the service launcher."""
        repo = self._repo
        if 'docker_checkboxes' in repo.features:
            self._stop_docker_services()
            self.after(2000, self._start_docker_services)
            return

        def _run():
            self._stop()
            import time
            time.sleep(0.3)
            self.after(0, self._start)
            
        threading.Thread(target=_run, daemon=True).start()

    def _pull(self):
        """Pull latest changes."""
        def _run():
            from core.git_manager import get_local_changes, get_commits_behind, get_current_branch, pull
            from tkinter import messagebox
            
            ignore = getattr(self._repo, 'env_pull_ignore_patterns', [])
            
            changes = get_local_changes(self._repo.path, ignore_files=ignore)
            if changes:
                def _err():
                     limit = 10
                     display_changes = "\n".join(changes[:limit]) + ("\n..." if len(changes) > limit else "")
                     messagebox.showerror("Error de Pull", f"No se puede hacer pull en '{self._repo.name}', tienes cambios locales sin guardar que podrían sobreescribirse:\n\n{display_changes}")
                self.after(0, _err)
                return

            branch = get_current_branch(self._repo.path)
            commits = get_commits_behind(self._repo.path, branch)
            
            if commits > 0:
                def _ask():
                    if messagebox.askyesno("Confirmar Pull", f"Hay {commits} nuevo(s) commit(s) en '{branch}'. ¿Quieres descargarlos ahora?"):
                        import threading
                        threading.Thread(target=_do_pull, daemon=True).start()
                self.after(0, _ask)
            else:
                _do_pull()
                
        def _do_pull():
            from core.git_manager import pull
            pull(self._repo.path, self._log)
            self._refresh_branch()
            self._check_pull_status()
            self._refresh_badge()

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _check_pull_status(self):
        """Update pull button state with commits behind count."""
        def _run():
            from core.git_manager import get_commits_behind, get_current_branch
            branch = get_current_branch(self._repo.path)
            if branch != 'unknown':
                commits = get_commits_behind(self._repo.path, branch)
                def _update():
                    if hasattr(self, '_pull_btn'):
                        if commits > 0:
                            self._pull_btn.configure(text=f"⬇ Pull ({commits})", fg_color=theme.btn_style("blue_active")["fg_color"])
                        else:
                            self._pull_btn.configure(text="⬇ Pull", fg_color=theme.btn_style("blue")["fg_color"])
                self.after(0, _update)
        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _clean_repo(self):
        """Clean all local untracked and modified files, removing env overrides."""
        from tkinter import messagebox
        if not messagebox.askyesno("Confirmar Limpieza", "¿Seguro que quieres borrar todos los cambios locales no commiteados? Se deseleccionará la configuración (Env/App) y se restaurarán los ficheros originales."):
            return
            
        def _run():
            from core.git_manager import clean_repo
            success, _ = clean_repo(self._repo.path, self._log)
            if success:
                def _restore():
                    if hasattr(self, '_config_combo'):
                        self._config_combo.set("- Sin Seleccionar -")
                        self._on_config_change("- Sin Seleccionar -")
                    if hasattr(self, '_config_combos'):
                        for target_file, combo in self._config_combos.items():
                            combo.set("- Sin Seleccionar -")
                            from core.config_manager import save_active_config
                            save_active_config(self.get_config_key(target_file), "- Sin Seleccionar -")
                            # We don't trigger self._on_config_change for all because clean reverting
                            # the files makes git restore the originals automatically.
                    self._refresh_badge()
                    self._check_pull_status()
                self.after(500, _restore)
        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _seed(self):
        """Run database seeds."""
        def _run():
            from core.db_manager import run_flyway_seeds
            run_flyway_seeds(self._repo.path, self._log)
        threading.Thread(target=_run, daemon=True).start()

    def _edit_config(self):
        """Open config editor."""
        repo = self._repo
        config_files = self._get_config_files(repo)
        if not config_files:
            return
        if len(config_files) == 1:
            if self._on_edit_config:
                self._on_edit_config(config_files[0])
        else:
            self._show_file_selector(config_files)

    def _get_config_files(self, repo):
        """Collect config files for the repo type."""
        files = list(repo.environment_files) if repo.environment_files else []
        if getattr(repo, 'docker_compose_files', None):
            files.extend(repo.docker_compose_files)
        return files

    def _show_file_selector(self, files: list):
        """Show a popup to select which config file to edit."""
        popup = ctk.CTkToplevel(self)
        popup.title("Seleccionar archivo")
        popup.geometry("400x300")
        popup.transient(self)
        popup.grab_set()

        ctk.CTkLabel(popup, text="Seleccionar archivo para editar:",
                     font=theme.font("base", bold=True)).pack(pady=(15, 10))

        scroll = ctk.CTkScrollableFrame(popup)
        scroll.pack(fill="both", expand=True, padx=15, pady=5)

        for f in files:
            btn = ctk.CTkButton(
                scroll, text=os.path.basename(f),
                font=theme.font("md"), height=32,
                fg_color="transparent",
                text_color=(theme.C.file_btn_light, theme.C.file_btn_dark),
                hover_color=(theme.C.file_btn_hover_light, theme.C.file_btn_hover_dark),
                anchor="w",
                command=lambda fp=f: (popup.destroy(),
                                      self._on_edit_config(fp) if self._on_edit_config else None)
            )
            btn.pack(fill="x", padx=5, pady=2)

    def _update_status(self, name: str, status: str):
        """Update the status display."""
        self._status = status

        def _update():
            color = theme.STATUS_ICONS.get(status, theme.C.status_error)
            if status == 'logging':
                color = theme.STATUS_ICONS.get('logging', theme.C.status_logging)
            self._status_label.configure(text="🔴", text_color=color)
            status_texts = {
                'running': f"Ejecutando :{self._repo.server_port or '?'}",
                'starting': "Iniciando...",
                'stopped': "Detenido",
                'error': "Error",
            }
            self._status_text.configure(
                text=status_texts.get(status, status),
                text_color=COLORS.get(status, '#888')
            )
            self._update_button_visibility()
            # Update detached log window icon to match running state
            if getattr(self, '_detached_log_window', None) and self._detached_log_window.winfo_exists():
                try:
                    app_dir = getattr(self.winfo_toplevel(), '_app_dir', None)
                    if app_dir:
                        _icon_color = "green" if status in ('running', 'starting') else "red"
                        _icon_path = os.path.join(app_dir, f"icon_{_icon_color}.ico")
                        if os.path.exists(_icon_path):
                            self._detached_log_window.iconbitmap(_icon_path)
                except Exception:
                    pass

        try:
            self.after(0, _update)
        except tk.TclError:
            pass

    # ─── Public API ──────────────────────────────────────────────

    def is_selected(self) -> bool:
        return self.selected_var.get()

    def set_selected(self, value: bool):
        self.selected_var.set(value)

    def set_branch(self, branch: str) -> bool:
        def _run():
            from core.git_manager import has_branch
            if has_branch(self._repo.path, branch):
                self._on_branch_change(branch)
        import threading
        threading.Thread(target=_run, daemon=True).start()
        return True

    def set_db_preset(self, preset_name: str):
        if hasattr(self, '_db_combo'):
            self._db_combo.set(preset_name)
            self._on_db_change(preset_name)

    def set_profile(self, profile):
        if hasattr(self, '_config_combo'):
            p = profile if isinstance(profile, str) else ''
            self._config_combo.set(p if p else '- Sin Seleccionar -')
            self._update_header_hints()
            self._on_config_change(p if p else '- Sin Seleccionar -')
        elif hasattr(self, '_config_combos') and self._config_combos:
            if isinstance(profile, dict):
                for target_file, combo in self._config_combos.items():
                    val = profile.get(target_file, '- Sin Seleccionar -')
                    combo.set(val)
                    self._update_header_hints()
                    self._on_config_change(val, target_file, skip_log=True)
            else:
                p = profile if isinstance(profile, str) and profile else '- Sin Seleccionar -'
                for target_file, combo in self._config_combos.items():
                    combo.set(p)
                    self._update_header_hints()
                    self._on_config_change(p, target_file, skip_log=True)


    def _on_status_change(self, name: str, status: str):
        """Callback from ServiceLauncher when status changes."""
        if name != self._repo.name:
            return

        self._status = status
        
        def _update():
            # Basic info updater that was decoupled
            color = theme.STATUS_ICONS.get(status, theme.C.status_error)
            if status == 'logging':
                color = theme.STATUS_ICONS.get('logging', theme.C.status_logging)
            self._status_label.configure(text="🔴", text_color=color)
            
            status_text = {
                'running': 'En ejecución',
                'starting': 'Iniciando...',
                'stopped': 'Detenido',
                'error': 'Error'
            }.get(status, status)
            self._status_text.configure(text=status_text)
            self._update_button_visibility()
            
        try:
            self.after(0, _update)
        except tk.TclError:
            pass

    def update_db_presets(self, presets: dict):
        self._db_presets = presets
        if hasattr(self, '_db_combo'):
            db_options = list(presets.keys()) if presets else [NO_DB_PRESET]
            self._db_combo.configure(values=db_options)
            self._db_combo.set(db_options[0] if presets else NO_DB_PRESET)

    def set_custom_command(self, cmd: str):
        """Set custom command (from persisted settings)."""
        if hasattr(self, '_cmd_entry') and cmd:
            self._cmd_entry.delete(0, "end")
            self._cmd_entry.insert(0, cmd)
            self._update_header_hints()

    def get_custom_command(self) -> str:
        """Get custom command if set."""
        if hasattr(self, '_cmd_entry'):
            return self._cmd_entry.get().strip()
        return ''

    def get_current_profile(self):
        if hasattr(self, '_config_combo'):
            val = self._config_combo.get()
            return val if val != "- Sin Seleccionar -" else ''
        elif hasattr(self, '_config_combos') and self._config_combos:
            res = {}
            for tf, combo in self._config_combos.items():
                v = combo.get()
                if v and v not in ('- Sin Seleccionar -', ''):
                    res[tf] = v
            return res
        return ''

    def get_branch(self) -> str:
        return getattr(self, '_current_branch', '')

    def get_name(self) -> str:
        return self._repo.name

    def get_repo_info(self):
        return self._repo

    def get_docker_compose_active(self) -> list:
        return list(self._active_compose_files)

    def get_docker_profile_services(self) -> dict:
        return dict(self._docker_profile_services)

    def set_docker_profile_services(self, services_map: dict):
        """Restore docker profile services selection from a loaded profile."""
        if not services_map:
            return
        resolved = {}
        for f, svc_list in services_map.items():
            # Match by full path or basename
            for repo_f in self._repo.docker_compose_files:
                if repo_f == f or os.path.basename(repo_f) == os.path.basename(f):
                    resolved[repo_f] = list(svc_list)
                    break
        self._docker_profile_services = resolved

    def set_docker_compose_active(self, active_files: list):
        """Apply active compose files from profile, modifying UI and stopping old ones."""
        old_active = self._active_compose_files.copy()
        
        # We need absolute paths, profile might just save basenames if we want it robust,
        # but here we expect full paths or we match by basename.
        new_active = set()
        for f in active_files:
            # Map basename back to absolute path in repo.docker_compose_files
            for repo_f in self._repo.docker_compose_files:
                if repo_f == f or os.path.basename(repo_f) == f or os.path.basename(repo_f) == os.path.basename(f):
                    new_active.add(repo_f)
                    break
                    
        self._active_compose_files = new_active
        
        # Stop ones that are no longer active
        to_stop = old_active - new_active
        if to_stop:
            def _stop_bg():
                from core.db_manager import docker_compose_down
                for f in to_stop:
                    if self._log: self._log(f"Deteniendo compose inactivo: {os.path.basename(f)}")
                    docker_compose_down(f, log=self._log)
            threading.Thread(target=_stop_bg, daemon=True).start()
            
        # Update UI borders
        for dc_file, btn in self._docker_compose_buttons.items():
            if dc_file in new_active:
                btn.configure(fg_color=theme.C.docker_active_fg, border_color=theme.C.docker_border_active)
                ToolTip(btn, "Haga clic para gestionar servicios (Activo en perfil)")
            else:
                btn.configure(fg_color=theme.C.docker_stopped_fg, border_color=theme.C.docker_border_stopped)
                ToolTip(btn, "Haga clic para gestionar servicios")

    def do_pull(self):
        self._pull()

    def do_start(self):
        self._start()

    def do_stop(self):
        self._stop()

    def get_status(self) -> str:
        return self._status
