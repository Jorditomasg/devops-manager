"""
repo_card.py — Accordion-style repo card widget for the main dashboard.
Collapsed: compact bar with checkbox + name + branch/profile hint + status + action buttons.
Expanded: reveals branch selector, profile/BD selectors, npm ci/mvn install, custom command.
"""
import customtkinter as ctk
import threading
import webbrowser
import os
import subprocess
import re
from datetime import datetime

from gui.tooltip import ToolTip


# ── Font constants ──────────────────────────────────────────────
FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"

# ── String constants ────────────────────────────────────────────
NO_DB_PRESET = "(Sin presets BD)"
NPM_INSTALL_OK = "📦 npm install ✓"
NPM_INSTALL_FAIL = "📦 npm install ✗"
NPM_INSTALL_RUN = "⏳ Instalando..."
MVN_INSTALL_OK = "🔧 mvn install ✓"
MVN_INSTALL_FAIL = "🔧 mvn install ✗"
MVN_INSTALL_RUN = "⏳ Compilando..."
BTN_CLICK = "<Button-1>"
BTN_CONFIG_TEXT = "⚙ Config"
BTN_CONFIG_TOOLTIP = "Editar configuración"

COLORS = {
    'running': '#22c55e',
    'starting': '#f59e0b',
    'stopped': '#6b7280',
    'error': '#ef4444',
    'spring-boot': '#22c55e',
    'angular': '#ef4444',
    'docker-infra': '#3b82f6',
    'maven-lib': '#a855f7',
}

TYPE_ICONS = {
    'spring-boot': '🍃',
    'angular': '🅰',
    'docker-infra': '🐳',
    'maven-lib': '📦',
}

STATUS_ICONS = {
    'running': '#22c55e', # Green
    'starting': '#eab308', # Yellow
    'stopped': '#6b7280', # Gray
    'error': '#ef4444', # Red
    'logging': '#f97316', # Orange
}

# ── Card colors ─────────────────────────────────────────────────
CARD_BG = "#16132e"
CARD_HOVER = "#1c1940"
CARD_BORDER = "#3b3768"
EXPAND_BG = "#120f28"


class RepoCard(ctk.CTkFrame):
    """Accordion repo card — collapsed bar + expandable details."""

    def __init__(self, parent, repo_info, service_launcher, db_presets=None,
                 java_versions=None, log_callback=None, on_edit_config=None, **kwargs):
        super().__init__(parent, corner_radius=10, border_width=1,
                         border_color=CARD_BORDER,
                         fg_color=CARD_BG, **kwargs)

        self._repo = repo_info
        self._launcher = service_launcher
        self._db_presets = db_presets or {}
        self._java_versions = java_versions or {}
        self._log = self._repo_log
        self._global_log = log_callback
        self._on_edit_config = on_edit_config
        self._status = 'stopped'
        self._branches_cache = []
        self._branch_load_id = None
        self._expanded = False
        self._is_installing = False
        self.selected_var = ctk.BooleanVar(value=True)
        self.selected_java_var = ctk.StringVar(value="Sistema (Por Defecto)")

        self._build_header()
        self._build_expand_panel()
        self._expand_panel.pack_forget()

        self._header.bind("<Enter>", self._on_hover_enter)
        self._header.bind("<Leave>", self._on_hover_leave)
        self._branch_load_id = self.after(200, self._refresh_branch)
        self._badge_timer = self.after(3000, self._refresh_badge_loop)
    
    def get_config_key(self, target_file: str) -> str:
        """Get the unique config key for a specific module's target file."""
        import os
        repo_path = self._repo.path
        if not target_file or not os.path.exists(target_file):
            return self._repo.name
        
        rel_path = os.path.relpath(target_file, repo_path).replace('\\', '/')
        parts = rel_path.split('/')
        if 'src' in parts:
            idx = parts.index('src')
            mod_name = parts[idx-1] if idx > 0 else 'App'
        else:
            mod_name = parts[0] if len(parts) > 1 else 'App'
            
        return f"{self._repo.name}::{mod_name}"

    def _refresh_badge_loop(self):
        """Periodically refresh the unsigned changes badge."""
        self._refresh_badge()
        self._badge_timer = self.after(10000, self._refresh_badge_loop)

    def _refresh_badge(self):
        """Count modified files and update the badge label."""
        def _run():
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
        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _on_hover_enter(self, event=None):
        self._header.configure(fg_color=CARD_HOVER)

    def _on_hover_leave(self, event=None):
        self._header.configure(fg_color="transparent")

    # ─── HEADER (always visible, compact) ────────────────────────

    def _build_header(self):
        """Build the collapsed header bar."""
        repo = self._repo
        type_color = COLORS.get(repo.repo_type, '#888')

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
            font=(FONT_FAMILY, 15), width=30,
            text_color=STATUS_ICONS.get('stopped', '#6b7280')
        )
        self._status_label.pack(side="left", padx=(0, 6))
        self._status_label.bind(BTN_CLICK, self._toggle_expand)

        # Type badge
        ctk.CTkLabel(
            self._header,
            text=f" {repo.repo_type.replace('-', ' ').title()} ",
            font=(FONT_FAMILY, 10, "bold"),
            text_color="#fff", fg_color=type_color,
            corner_radius=4, height=18
        ).pack(side="left", padx=(0, 8))

        # Name
        name_label = ctk.CTkLabel(
            self._header, text=f"{TYPE_ICONS.get(repo.repo_type, '📁')} {repo.name}",
            font=(FONT_FAMILY, 14, "bold"), anchor="w",
            text_color="#e0e7ff"
        )
        name_label.pack(side="left")
        name_label.bind(BTN_CLICK, self._toggle_expand)
        if repo.git_remote_url:
            ToolTip(name_label, "🔗 Clic derecho: abrir repositorio")
            name_label.bind("<Button-3>", lambda e: webbrowser.open(repo.git_remote_url))

        # Unsaved changes badge
        self._changes_count_label = ctk.CTkLabel(
            self._header, text="",
            font=(FONT_FAMILY, 11, "bold"), text_color="#facc15"
        )
        self._changes_count_label.pack(side="left", padx=(4, 4))
        ToolTip(self._changes_count_label, "Ficheros modificados sin guardar en el directorio vinculados al repo.")

        # Branch + profile hints (grey, right of name)
        self._branch_hint = ctk.CTkLabel(
            self._header, text="",
            font=(FONT_MONO, 10), text_color="#6b7280", anchor="w"
        )
        self._branch_hint.pack(side="left", padx=(6, 0), fill="x", expand=True)
        self._branch_hint.bind(BTN_CLICK, self._toggle_expand)

        # Status text
        self._status_text = ctk.CTkLabel(
            self._header, text="Detenido",
            font=(FONT_FAMILY, 12), text_color="#94a3b8"
        )
        self._status_text.pack(side="left", padx=(0, 4))

        if repo.server_port:
            ctk.CTkLabel(
                self._header, text=f":{repo.server_port}",
                font=(FONT_MONO, 11, "bold"), text_color="#6366f1"
            ).pack(side="left", padx=(0, 8))

        # Main action buttons
        self._action_btns_frame = ctk.CTkFrame(self._header, fg_color="transparent")
        self._action_btns_frame.pack(side="left", padx=(0, 4))

        btn_style = {"height": 28, "font": (FONT_FAMILY, 13), "corner_radius": 6,
                     "border_width": 1}

        self._start_btn = ctk.CTkButton(
            self._action_btns_frame, text="▶", width=32,
            fg_color="#144d28", hover_color="#16a34a",
            border_color="#22c55e",
            command=self._start, **btn_style
        )
        ToolTip(self._start_btn, "Iniciar servicio")

        self._stop_btn = ctk.CTkButton(
            self._action_btns_frame, text="⬛", width=32,
            fg_color="#4c1616", hover_color="#dc2626",
            border_color="#ef4444",
            command=self._stop, **btn_style
        )
        ToolTip(self._stop_btn, "Detener servicio")

        self._restart_btn = ctk.CTkButton(
            self._action_btns_frame, text="🔄", width=32,
            fg_color="#4a3310", hover_color="#d97706",
            border_color="#f59e0b",
            command=self._restart, **btn_style
        )
        ToolTip(self._restart_btn, "Reiniciar servicio")

        self._update_button_visibility()

        # Expand toggle
        self._toggle_btn = ctk.CTkButton(
            self._header, text="▼", width=28, height=28,
            font=(FONT_FAMILY, 11),
            fg_color="transparent", hover_color="#312e81",
            text_color="#818cf8",
            border_width=1, border_color="#4338ca",
            corner_radius=6, command=self._toggle_expand
        )
        self._toggle_btn.pack(side="right", padx=(4, 2))
        ToolTip(self._toggle_btn, "Expandir / Colapsar opciones")

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
        if hasattr(self, '_npm_install_btn'):
            if is_running:
                self._npm_install_btn.configure(state="disabled")
            elif not is_installing:
                self._npm_install_btn.configure(state="normal")
                
        if hasattr(self, '_mvn_install_btn'):
            if is_running:
                self._mvn_install_btn.configure(state="disabled")
            elif not is_installing:
                self._mvn_install_btn.configure(state="normal")

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
        # Custom command
        if hasattr(self, '_cmd_entry'):
            cmd = self._cmd_entry.get().strip()
            if cmd:
                parts.append(f"$ {cmd}")
            elif self._repo.run_command:
                parts.append(f"$ {self._repo.run_command}")
        elif self._repo.run_command:
            parts.append(f"$ {self._repo.run_command}")

        is_installed = False
        if self._repo.repo_type == 'angular':
            is_installed = os.path.isdir(os.path.join(self._repo.path, 'node_modules'))
        elif self._repo.repo_type in ('spring-boot', 'maven-lib'):
            is_installed = os.path.isdir(os.path.join(self._repo.path, 'target'))
        else:
            is_installed = True

        if not is_installed:
            parts.insert(0, "❌ Faltan deps")

        self._branch_hint.configure(text="   ".join(parts))

    def install_dependencies(self, skip_if_installed=False):
        """Method to trigger dependency installation (NPM or Maven)."""
        repo = self._repo
        
        if repo.repo_type == 'angular':
            has_node_modules = os.path.isdir(os.path.join(repo.path, 'node_modules'))
            if skip_if_installed and has_node_modules:
                return
            self._run_npm_install()
        elif repo.repo_type in ('spring-boot', 'maven-lib'):
            has_target = os.path.isdir(os.path.join(repo.path, 'target'))
            if skip_if_installed and has_target:
                return
            self._run_mvn_install()

    # ─── EXPAND PANEL ────────────────────────────────────────────

    def _build_expand_panel(self):
        """Build the expandable details panel."""
        repo = self._repo

        # corner_radius para encajar bien sin tapar las esquinas del padre
        self._expand_panel = ctk.CTkFrame(self, fg_color=EXPAND_BG, corner_radius=8)

        ctk.CTkFrame(self._expand_panel, height=1, fg_color="#312e81").pack(fill="x", padx=10)

        content = ctk.CTkFrame(self._expand_panel, fg_color="transparent")
        content.pack(fill="x", padx=14, pady=6)

        # Row 1: Branch + secondary buttons
        self._build_branch_row(content, repo)
        # Row 2: Conditional selectors
        self._build_selector_row(content, repo)
        # Row 3: Custom start command
        self._build_command_row(content, repo)
        # Row 4: Logs
        self._build_log_row(content)

    def _build_log_row(self, content):
        """Build the repository log console."""
        self._log_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._log_frame.pack(fill="x", pady=(8, 0))

        header = ctk.CTkFrame(self._log_frame, fg_color="transparent")
        header.pack(fill="x")
        
        ctk.CTkLabel(header, text="📋 Logs del Repositorio", font=(FONT_FAMILY, 12, "bold"), text_color="#c7d2fe").pack(side="left")
        
        clear_btn = ctk.CTkButton(
            header, text="🗑 Limpiar", width=60, height=24,
            font=(FONT_FAMILY, 10),
            fg_color="#1e1b4b", hover_color="#312e81",
            border_width=1, border_color="#4338ca",
            command=self._clear_logs
        )
        clear_btn.pack(side="right")
        
        detach_btn = ctk.CTkButton(
            header, text="🗗 Desacoplar", width=80, height=24,
            font=(FONT_FAMILY, 10),
            fg_color="#1e1b4b", hover_color="#312e81",
            border_width=1, border_color="#4338ca",
            command=self._detach_logs
        )
        detach_btn.pack(side="right", padx=(0, 6))
        
        self._log_textbox = ctk.CTkTextbox(
            self._log_frame, height=120, font=(FONT_MONO, 11),
            corner_radius=6, border_width=1,
            border_color="#3b3768", fg_color="#0f0e26",
            text_color="#e0e7ff", state="disabled"
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
        
        # Bring window to front
        self.after(100, lambda: self._detached_log_window.lift())
        self.after(110, lambda: self._detached_log_window.focus_force())
        
        self._detached_log_textbox = ctk.CTkTextbox(
            self._detached_log_window, font=(FONT_MONO, 12),
            corner_radius=0, border_width=0,
            fg_color="#0f0e26", text_color="#e0e7ff"
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

                # Trim old lines
                content = self._log_textbox.get("1.0", "end")
                lines = content.splitlines()
                if len(lines) > 500:
                    excess = len(lines) - 500
                    self._log_textbox.delete("1.0", f"{excess + 1}.0")

                self._log_textbox.see("end")
                self._log_textbox.configure(state="disabled")
                
            if getattr(self, '_detached_log_textbox', None) and self._detached_log_textbox.winfo_exists():
                self._detached_log_textbox.configure(state="normal")
                self._detached_log_textbox.insert("end", line)
                
                content = self._detached_log_textbox.get("1.0", "end")
                lines = content.splitlines()
                if len(lines) > 500:
                    excess = len(lines) - 500
                    self._detached_log_textbox.delete("1.0", f"{excess + 1}.0")
                    
                self._detached_log_textbox.see("end")
                self._detached_log_textbox.configure(state="disabled")
            
            self._flash_log_icon()

        try:
            self.after(0, _insert)
        except Exception:
            pass

    def _flash_log_icon(self):
        """Temporarily change the status icon color to orange when a log is received."""
        if not hasattr(self, '_status_label'):
            return
            
        self._status_label.configure(text="🔴", text_color=STATUS_ICONS.get('logging', '#f97316'))

        def _revert():
            if hasattr(self, '_status_label') and hasattr(self, '_status'):
                self._status_label.configure(text="🔴", text_color=STATUS_ICONS.get(self._status, '#6b7280'))
            self._log_flash_timer = None

        self._log_flash_timer = self.after(3000, _revert)

    def _build_branch_row(self, content, repo):
        """Build branch + secondary buttons row."""
        row1 = ctk.CTkFrame(content, fg_color="transparent")
        row1.pack(fill="x")

        ctk.CTkLabel(row1, text="Rama:", font=(FONT_FAMILY, 13),
                     text_color="#c7d2fe", width=50, anchor="e").pack(side="left")

        self._branch_combo = ctk.CTkComboBox(
            row1, values=["cargando..."],
            width=180, height=28, font=(FONT_FAMILY, 12),
            corner_radius=6, fg_color="#1e1b4b",
            border_color="#4338ca", button_color="#4338ca",
            command=self._on_branch_change
        )
        self._branch_combo.pack(side="left", padx=(6, 4))

        def _on_branch_type(event):
            text = self._branch_combo.get().lower()
            filtered = [b for b in self._branches_cache if text in b.lower()]
            self._branch_combo.configure(values=filtered if filtered else self._branches_cache)
        
        self._branch_combo.bind("<KeyRelease>", _on_branch_type)

        search_btn = ctk.CTkButton(
            row1, text="🔍", width=28, height=28,
            fg_color="#1e1b4b", hover_color="#312e81",
            border_width=1, border_color="#4338ca",
            corner_radius=6, command=self._fetch_branches
        )
        search_btn.pack(side="left", padx=(0, 10))
        ToolTip(search_btn, "Buscar ramas remotas (fetch)")

        sec_btn_style = {"height": 28, "font": (FONT_FAMILY, 12), "corner_radius": 6,
                         "border_width": 1}

        # Pull
        self._pull_btn = ctk.CTkButton(
            row1, text="⬇ Pull", width=65,
            fg_color="#172554", hover_color="#2563eb",
            border_color="#3b82f6",
            command=self._pull, **sec_btn_style
        )
        self._pull_btn.pack(side="left", padx=(0, 3))
        ToolTip(self._pull_btn, "Descargar cambios (git pull)")

        # Clean
        self._clean_btn = ctk.CTkButton(
            row1, text="🧹 Limpiar", width=80,
            fg_color="#4c1d95", hover_color="#6d28d9",
            border_color="#7c3aed",
            command=self._clean_repo, **sec_btn_style
        )
        self._clean_btn.pack(side="left", padx=(0, 3))
        ToolTip(self._clean_btn, "Limpiar ficheros no commiteados y reestablecer cambios")

        # Config
        if not ((repo.repo_type == 'spring-boot' and repo.profiles) or (repo.repo_type == 'angular' and repo.profiles)):
            edit_btn = ctk.CTkButton(
                row1, text=BTN_CONFIG_TEXT, width=80,
                fg_color="#1e293b", hover_color="#475569",
                border_color="#64748b",
                command=self._edit_config, **sec_btn_style
            )
            edit_btn.pack(side="left")
            ToolTip(edit_btn, BTN_CONFIG_TOOLTIP)

        # Right-aligned frame for install buttons
        self.right_frame = ctk.CTkFrame(row1, fg_color="transparent")
        self.right_frame.pack(side="right", fill="y", padx=(10, 0))
        self.btn_style = sec_btn_style # Store for reuse

        # npm ci for Angular
        if repo.repo_type == 'angular':
            self._build_npm_install_btn(self.right_frame, self.btn_style)

        # mvn install for Spring Boot / Maven lib
        if repo.repo_type in ('spring-boot', 'maven-lib'):
            self._build_mvn_install_btn(self.right_frame, self.btn_style)

        # Seed
        if repo.has_seeds or (repo.repo_type == 'docker-infra' and repo.has_database):
            seed_btn = ctk.CTkButton(
                row1, text="🌱 Seed", width=70,
                fg_color="#2e1065", hover_color="#9333ea",
                border_color="#a855f7",
                command=self._seed, **sec_btn_style
            )
            seed_btn.pack(side="left", padx=(0, 3))
            ToolTip(seed_btn, "Ejecutar seeds de BD")

    def _build_npm_install_btn(self, parent, style):
        """Build the npm install button."""
        has_node_modules = os.path.isdir(os.path.join(self._repo.path, 'node_modules'))
        
        btn_text = "📦 npm i"
        if has_node_modules:
            btn_text = "📦 npm i ✓"
            fg_color = "#334155"
            border_color = "#64748b"
            hover_color = "#475569"
        else:
            fg_color = "#7f1d1d" 
            border_color = "#b91c1c"
            hover_color = "#991b1b"

        self._npm_install_btn = ctk.CTkButton(
            parent, text=btn_text, width=100,
            fg_color=fg_color, hover_color=hover_color,
            border_color=border_color,
            command=self._run_npm_install, **style
        )
        self._npm_install_btn.pack(side="left", padx=(0, 6))
        
        tooltip_text = f"Instalar dependencias (npm i)"
        if not has_node_modules:
            tooltip_text += " — node_modules no encontrado!"
            
        self._npm_install_tooltip = ToolTip(
            self._npm_install_btn,
            tooltip_text
        )

    def _build_mvn_install_btn(self, parent, style):
        """Build the mvn install button."""
        has_target = os.path.isdir(os.path.join(self._repo.path, 'target'))
        
        btn_text = "🔧 mvn inst"
        if has_target:
            btn_text = "🔧 mvn inst ✓"
            fg_color = "#334155"
            border_color = "#64748b"
            hover_color = "#475569"
        else:
            fg_color = "#7f1d1d" 
            border_color = "#b91c1c"
            hover_color = "#991b1b"

        self._mvn_install_btn = ctk.CTkButton(
            parent, text=btn_text, width=100,
            fg_color=fg_color, hover_color=hover_color,
            border_color=border_color,
            command=self._run_mvn_install, **style
        )
        self._mvn_install_btn.pack(side="left", padx=(0, 6))
        self._mvn_install_tooltip = ToolTip(
            self._mvn_install_btn,
            "Compilar e instalar dependencias (mvn install -DskipTests)"
        )

    def _build_selector_row(self, content, repo):
        """Build conditional selector row (profile, DB, env, docker)."""
        row2 = ctk.CTkFrame(content, fg_color="transparent")
        has_row2 = False

        combo_style = {"height": 28, "font": (FONT_FAMILY, 12), "corner_radius": 6,
                       "fg_color": "#1e1b4b", "border_color": "#4338ca",
                       "button_color": "#4338ca"}

        sec_btn_style = {"height": 28, "font": (FONT_FAMILY, 12), "corner_radius": 6,
                         "border_width": 1}

        if repo.repo_type in ('spring-boot', 'angular') and repo.environment_files:
            has_row2 = True
            from core.config_manager import load_repo_configs
            
            target_files = []
            if repo.repo_type == 'angular':
                target_files = sorted(list({f for f in repo.environment_files if os.path.basename(f) == 'environment.ts'}))
                if not target_files and repo.environment_files:
                    dirs = {os.path.dirname(f) for f in repo.environment_files}
                    for d in dirs:
                        env_files_in_dir = [f for f in repo.environment_files if os.path.dirname(f) == d]
                        if env_files_in_dir:
                            target_files.append(sorted(env_files_in_dir)[0])
            elif repo.repo_type == 'spring-boot':
                target_files = sorted(list({f for f in repo.environment_files if os.path.basename(f) in ('application.yml', 'application.yaml', 'application.properties')}))
            
            if not target_files:
                if repo.repo_type == 'spring-boot':
                    target_files = [os.path.join(repo.path, 'src', 'main', 'resources', 'application.yml')]
                else:
                    if repo.environment_files:
                        target_files = [repo.environment_files[0]]
            
            target_files = sorted(list(set(target_files)))
            self._config_combos = {} 
            
            # Use a vertical frame to stack them
            selectors_container = ctk.CTkFrame(row2, fg_color="transparent")
            selectors_container.pack(side="left", padx=0, expand=True, fill="both")
            
            for target_file in target_files:
                rel_path = os.path.relpath(target_file, repo.path).replace('\\', '/')
                parts = rel_path.split('/')
                if 'src' in parts:
                    idx = parts.index('src')
                    mod_name = parts[idx-1] if idx > 0 else 'App'
                else:
                    mod_name = parts[0] if len(parts) > 1 else 'App'
                
                sel_frame = ctk.CTkFrame(selectors_container, fg_color="transparent")
                sel_frame.pack(side="top", pady=2, anchor="w")
                
                config_key = self.get_config_key(target_file)
                configs = load_repo_configs(config_key)
                
                # Check for legacy configs stored on the old main repo name
                legacy_configs = load_repo_configs(repo.name)
                # If the submodule logic doesn't have anything, auto-feed from global name to assist migration
                if not configs and legacy_configs:
                    configs = legacy_configs
                    
                opts = ["- Sin Seleccionar -"] + list(configs.keys())
                
                lbl_text = f"App ({mod_name}):" if repo.repo_type == 'spring-boot' else f"Env ({mod_name}):"
                if len(target_files) == 1:
                    lbl_text = "App:" if repo.repo_type == 'spring-boot' else "Env:"
                    
                ctk.CTkLabel(sel_frame, text=lbl_text, font=(FONT_FAMILY, 13),
                             text_color="#c7d2fe", anchor="w").pack(side="left")
                             
                combo = ctk.CTkComboBox(
                    sel_frame, values=opts, width=130,
                    command=lambda val, tf=target_file: self._on_config_change(val, tf), **combo_style
                )
                combo.pack(side="left", padx=(6, 0))
                combo.set("- Sin Seleccionar -")
                self._config_combos[target_file] = combo
                
                edit_btn = ctk.CTkButton(
                    sel_frame, text="⚙️", width=35,
                    fg_color="#1e293b", hover_color="#475569",
                    border_color="#64748b",
                    command=lambda tf=target_file: self._open_config_manager(tf), **sec_btn_style
                )
                edit_btn.pack(side="left", padx=(6, 12))
                ToolTip(edit_btn, f"Gestor de configuraciones ({lbl_text})")

        if repo.has_database and repo.repo_type == 'spring-boot':
            has_row2 = True
            ctk.CTkLabel(row2, text="BD:", font=(FONT_FAMILY, 13),
                         text_color="#c7d2fe", width=35, anchor="e").pack(side="left")
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

        if repo.repo_type == 'docker-infra' and repo.docker_compose_files:
            self._docker_checkboxes = {}
            for dc_file in repo.docker_compose_files:
                dc_name = os.path.basename(dc_file).replace('docker-compose.', '').replace('.yml', '')
                if dc_name == 'all':
                    continue
                has_row2 = True
                var = ctk.BooleanVar(value=False)
                self._docker_checkboxes[dc_file] = var
                ctk.CTkCheckBox(
                    row2, text=dc_name.title(),
                    font=(FONT_FAMILY, 12), variable=var,
                    checkbox_width=18, checkbox_height=18,
                    text_color="#c7d2fe"
                ).pack(side="left", padx=(0, 6))

        if has_row2:
            row2.pack(fill="x", pady=(4, 0))

        row_java = ctk.CTkFrame(content, fg_color="transparent")
        has_row_java = False

        if repo.repo_type in ('spring-boot', 'maven-lib'):
            has_row_java = True
            ctk.CTkLabel(row_java, text="Java:", font=(FONT_FAMILY, 13),
                         text_color="#c7d2fe", width=50, anchor="e").pack(side="left")
            java_options = ["Sistema (Por Defecto)"] + list(self._java_versions.keys())
            self._java_combo = ctk.CTkComboBox(
                row_java, values=java_options, width=150,
                variable=self.selected_java_var, **combo_style
            )
            self._java_combo.pack(side="left", padx=(6, 12))

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

        ctk.CTkLabel(row3, text="Cmd:", font=(FONT_FAMILY, 13),
                     text_color="#c7d2fe", width=50, anchor="e").pack(side="left")

        self._cmd_entry = ctk.CTkEntry(
            row3, height=28, font=(FONT_MONO, 11),
            corner_radius=6, fg_color="#1e1b4b",
            border_color="#4338ca",
            placeholder_text=repo.run_command or "comando de inicio"
        )
        self._cmd_entry.pack(side="left", padx=(6, 4), fill="x", expand=True)
        ToolTip(self._cmd_entry,
                "Comando de inicio personalizado. Dejar vacío para usar el por defecto.\n"
                f"Por defecto: {repo.run_command or 'N/A'}")

        # Update header hints when command changes
        self._cmd_entry.bind("<FocusOut>", lambda e: self._update_header_hints())

    # ─── Toggle expand ───────────────────────────────────────────

    def _toggle_expand(self, event=None):
        """Toggle expanded/collapsed state."""
        self._expanded = not self._expanded
        if self._expanded:
            self._expand_panel.pack(fill="x", padx=3, pady=(0, 3), after=self._header)
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
                    if hasattr(self, '_branch_combo'):
                        self._branch_combo.set(branch)
                    self._update_header_hints()
                    self._check_pull_status()
                    self._refresh_badge()
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

    def _on_config_change(self, config_name: str, target_file: str = None):
        """Handle env/app change and overwrite target config file."""
        from tkinter import messagebox
        from core.config_manager import load_repo_configs, write_angular_environment_raw, write_config_file_raw
        
        repo = self._repo
        
        if not target_file:
            if repo.repo_type == 'angular':
                # Search for environment.ts
                for ef in repo.environment_files:
                    if os.path.basename(ef) == 'environment.ts':
                        target_file = ef
                        break
                if not target_file and repo.environment_files:
                    target_file = os.path.join(os.path.dirname(repo.environment_files[0]), 'environment.ts')
            elif repo.repo_type == 'spring-boot':
                target_file = os.path.join(repo.path, 'src', 'main', 'resources', 'application.yml')

        config_key = self.get_config_key(target_file)
        
        if config_name == "- Sin Seleccionar -":
            if self._log:
                self._log(f"[{self._repo.name}] Configuración deseleccionada. Restaurando configuración original.")
            if target_file and os.path.isfile(target_file):
                import subprocess
                subprocess.run(['git', 'checkout', '--', target_file], cwd=repo.path, capture_output=True)
            self._update_header_hints()
            return

        configs = load_repo_configs(config_key)
        
        # Check legacy keys
        if not configs:
            legacy_configs = load_repo_configs(repo.name)
            if legacy_configs:
                configs = legacy_configs
                
        config_data = configs.get(config_name)
        
        if not config_data:
            if self._log:
                self._log(f"[{self._repo.name}] La configuración '{config_name}' no se encontró.")
            return

        res = False
        if repo.repo_type == 'angular':
            import json
            if isinstance(config_data, dict):
                content = "\n".join([f"export const environment = {json.dumps(config_data, indent=2)};", ""])
            else:
                content = str(config_data)
            res = write_angular_environment_raw(target_file, content)
        elif repo.repo_type == 'spring-boot':
            config_str = str(config_data)
            # Detect if it's properties or yaml based on first few lines
            is_props = "=" in config_str.split("\n", 3)[0] or "=" in config_str
            if is_props and not config_str.startswith("spring:") and not config_str.startswith("server:"):
                target_file = target_file.replace('.yml', '.properties')
            else:
                target_file = target_file.replace('.properties', '.yml')
                
            # Remove the opposite file to avoid Spring Boot loading both and conflicting
            opposite_file = target_file.replace('.properties', '.yml') if target_file.endswith('.properties') else target_file.replace('.yml', '.properties')
            if os.path.exists(opposite_file):
                try:
                    os.remove(opposite_file)
                except Exception:
                    pass
            
            # Also clean up the opposite file from target/classes if it exists
            target_classes_dir = os.path.join(repo.path, 'target', 'classes')
            opposite_basename = os.path.basename(opposite_file)
            target_classes_file = os.path.join(target_classes_dir, opposite_basename)
            if os.path.exists(target_classes_file):
                try:
                    os.remove(target_classes_file)
                except Exception:
                    pass
                    
            res = write_config_file_raw(target_file, config_data)

        if res:
            if self._log:
                self._log(f"[{self._repo.name}] Configuración '{config_name}' aplicada.")
        else:
            messagebox.showerror("Error", f"No se pudo escribir en '{target_file}'")
            
        self._update_header_hints()

    def _open_config_manager(self, target_file: str = None):
        """Open the RepoConfigManagerDialog for this repository."""
        from gui.dialogs import RepoConfigManagerDialog
        
        config_key = self.get_config_key(target_file) if target_file else self._repo.name
        
        def _on_configs_updated():
            from core.config_manager import load_repo_configs
            configs = load_repo_configs(config_key)
            opts = ["- Sin Seleccionar -"] + list(configs.keys())
            if hasattr(self, '_config_combos'):
                combo = self._config_combos.get(target_file)
                if combo:
                    combo.configure(values=opts)
                    curr = combo.get()
                    if curr not in opts:
                        combo.set("- Sin Seleccionar -")
                self._update_header_hints()
            elif hasattr(self, '_config_combo'):
                self._config_combo.configure(values=opts)
                curr = self._config_combo.get()
                if curr not in opts:
                    self._config_combo.set("- Sin Seleccionar -")
                    self._update_header_hints()
                    
        RepoConfigManagerDialog(
            self.winfo_toplevel(), 
            repo=self._repo, 
            config_key=config_key,
            log_callback=self._log,
            on_close_callback=_on_configs_updated
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
            resources_dir = os.path.join(self._repo.path, 'src', 'main', 'resources')
            success = set_spring_db_preset(resources_dir, active_profile, preset)
            if self._log:
                msg = f"BD cambiada a: {preset_name}" if success else "Error al cambiar BD"
                self._log(f"[{self._repo.name}] {msg}")

        threading.Thread(target=_run, daemon=True).start()

    # ─── npm install ─────────────────────────────────────────────

    def _run_npm_install(self):
        """Run npm install to install dependencies."""
        from tkinter import messagebox
        if hasattr(self, '_npm_install_btn') and self._npm_install_btn.cget("text") in (NPM_INSTALL_OK, NPM_INSTALL_FAIL):
            if not messagebox.askyesno("Reinstalar", "¿Estás seguro de que deseas volver a instalar dependencias?"):
                return
                
        repo = self._repo
        cmd_args = ['npm', 'install', '--yes', '--legacy-peer-deps']
        cmd_str = ' '.join(cmd_args)
        
        if self._log:
            self._log(f"Running {cmd_str}...")
        self._npm_install_btn.configure(text=NPM_INSTALL_RUN, state="disabled")
        self._is_installing = True
        self._update_button_visibility()

        def _run():
            try:
                process = subprocess.Popen(
                    cmd_args, cwd=repo.path,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, shell=True,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
                )
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    if self._log:
                        self._log(line.strip())
                process.wait()

                def _done():
                    self._is_installing = False
                    if os.path.isdir(os.path.join(self._repo.path, 'node_modules')):
                        self._npm_install_btn.configure(
                            text="📦 npm i ✓", fg_color="#334155", border_color="#64748b", hover_color="#475569"
                        )
                        if self._log:
                            self._log(f"[{self._repo.name}] npm install finalizado ✓")
                    else:
                        self._npm_install_btn.configure(
                            text="📦 npm i", fg_color="#7f1d1d", border_color="#b91c1c", hover_color="#991b1b"
                        )
                        if self._log:
                            self._log(f"[{self._repo.name}] Fallo al instalar NPM. node_modules no encontrado.")
                    self._update_button_visibility()
                self.after(0, _done)
            except Exception as e:
                if self._log:
                    self._log(f"Error {cmd_str}: {e}")
                def _err():
                    self._is_installing = False
                    self._npm_install_btn.configure(text=NPM_INSTALL_FAIL, state="normal")
                    self._update_button_visibility()
                self.after(0, _err)

        threading.Thread(target=_run, daemon=True).start()

    # ─── mvn install ─────────────────────────────────────────────

    def _run_mvn_install(self):
        """Run mvn install -DskipTests for Java projects using specified Java version."""
        from tkinter import messagebox
        if hasattr(self, '_mvn_install_btn') and self._mvn_install_btn.cget("text") in (MVN_INSTALL_OK, MVN_INSTALL_FAIL):
            if not messagebox.askyesno("Reinstalar", "¿Estás seguro de que deseas volver a compilar (mvn install)?"):
                return
                
        repo = self._repo
        if self._log:
            self._log(f"Running mvn install -DskipTests...")
        self._mvn_install_btn.configure(text=MVN_INSTALL_RUN, state="disabled")
        self._is_installing = True
        self._update_button_visibility()

        mvnw = os.path.join(repo.path, 'mvnw.cmd' if os.name == 'nt' else 'mvnw')
        if not os.path.isfile(mvnw):
            mvnw = 'mvn'
        cmd = [mvnw, 'install', '-DskipTests', '--batch-mode']
        
        # Build environment with specific JAVA_HOME
        from core.java_manager import build_java_env
        java_choice = self.selected_java_var.get()
        java_home = self._java_versions.get(java_choice, "")
        env = build_java_env(java_home)
        
        if java_home and self._log:
            self._log(f"Usando JAVA_HOME: {java_home}")

        def _run():
            try:
                process = subprocess.Popen(
                    cmd, cwd=repo.path, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
                )
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    if self._log:
                        self._log(line.strip())
                process.wait()

                def _done():
                    self._is_installing = False
                    if os.path.isdir(os.path.join(self._repo.path, 'target')):
                        self._mvn_install_btn.configure(
                            text="🔧 mvn inst ✓", fg_color="#334155", border_color="#64748b", hover_color="#475569"
                        )
                        if self._log:
                            self._log(f"[{self._repo.name}] mvn install finalizado ✓")
                    else:
                        self._mvn_install_btn.configure(
                            text="🔧 mvn inst", fg_color="#7f1d1d", border_color="#b91c1c", hover_color="#991b1b"
                        )
                        if self._log:
                            self._log(f"[{self._repo.name}] Fallo al empaquetar con Maven. target no encontrado.")
                    self._update_button_visibility()
                self.after(0, _done)
            except Exception as e:
                if self._log:
                    self._log(f"Error mvn install: {e}")
                def _err():
                    self._is_installing = False
                    self._mvn_install_btn.configure(text=MVN_INSTALL_FAIL, state="normal")
                    self._update_button_visibility()
                self.after(0, _err)

        threading.Thread(target=_run, daemon=True).start()

    # ─── Start / Stop / Restart ──────────────────────────────────

    def _get_start_command(self):
        """Get the start command — custom or default."""
        if hasattr(self, '_cmd_entry'):
            custom = self._cmd_entry.get().strip()
            if custom:
                return custom
        return self._repo.run_command or ''

    def _start(self):
        """Start the service."""
        repo = self._repo

        if repo.repo_type == 'docker-infra':
            self._start_docker_services()
            return

        # Angular: auto-npm-ci if node_modules missing
        if repo.repo_type == 'angular':
            if not os.path.isdir(os.path.join(repo.path, 'node_modules')):
                if self._log:
                    self._log(f"[{repo.name}] ⚠ node_modules no encontrado, ejecutando npm ci primero...")
                self._npm_ci_then_start()
                return

        # Check for custom command
        custom_cmd = self._get_start_command()
        if custom_cmd and custom_cmd != repo.run_command:
            self._start_custom(custom_cmd)
            return

        self._do_start()

    def _start_custom(self, cmd_str: str):
        """Start with a custom command."""
        repo = self._repo
        if self._log:
            self._log(f"Ejecutando: {cmd_str}")

        self._update_status(repo.name, 'starting')

        def _run():
            try:
                process = subprocess.Popen(
                    cmd_str, cwd=repo.path, shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    creationflags=(getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)) if os.name == 'nt' else 0
                )
                self._update_status(repo.name, 'running')

                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    if self._log:
                        self._log(line.strip())

                process.wait()
                self._update_status(repo.name, 'stopped')
            except Exception as e:
                self._update_status(repo.name, 'error')
                if self._log:
                    self._log(f"Error: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _npm_ci_then_start(self):
        """Run npm ci then start the service."""
        repo = self._repo
        if hasattr(self, '_npm_ci_btn'):
            self._npm_ci_btn.configure(text=NPM_INSTALL_RUN, state="disabled") # Changed from NPM_CI_RUN
        self._is_installing = True
        self._update_button_visibility()

        def _run():
            try:
                process = subprocess.Popen(
                    ['npm', 'ci'], cwd=repo.path,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, shell=True
                )
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    if self._log:
                        self._log(line.strip())
                process.wait()

                def _after():
                    self._is_installing = False
                    self._update_button_visibility()
                    if os.path.isdir(os.path.join(self._repo.path, 'node_modules')):
                        self._npm_install_btn.configure(
                            text="📦 npm i ✓", fg_color="#334155", border_color="#64748b", hover_color="#475569"
                        )
                        if self._log:
                            self._log(f"[{self._repo.name}] npm install finalizado ✓")
                        self._do_start()
                    else:
                            self._npm_ci_btn.configure(text=NPM_CI_FAIL, state="normal")
                self.after(0, _after)
            except Exception as e:
                if self._log:
                    self._log(f"Error: {e}")
                def _err():
                    self._is_installing = False
                    self._update_button_visibility()
                self.after(0, _err)

        threading.Thread(target=_run, daemon=True).start()

    def _do_start(self):
        """Actually start the service."""
        repo = self._repo

        def _run():
            profile = ''
            if hasattr(self, '_profile_combo'):
                profile = self._profile_combo.get()
            elif hasattr(self, '_env_combo'):
                profile = self._env_combo.get()

            if repo.repo_type == 'spring-boot':
                self._launcher.start_spring_boot(
                    repo.name, repo.path, profile, repo.server_port,
                    self._log, self._update_status
                )
            elif repo.repo_type == 'angular':
                self._launcher.start_angular(
                    repo.name, repo.path, profile,
                    self._log, self._update_status
                )
            elif repo.repo_type == 'maven-lib':
                self._launcher.start_maven_install(
                    repo.name, repo.path,
                    self._log, self._update_status
                )

        threading.Thread(target=_run, daemon=True).start()

    def _start_docker_services(self):
        """Start selected docker-compose services."""
        def _run():
            from core.db_manager import docker_compose_up
            if hasattr(self, '_docker_checkboxes'):
                for dc_file, var in self._docker_checkboxes.items():
                    if var.get():
                        docker_compose_up(dc_file, log=self._log)
        threading.Thread(target=_run, daemon=True).start()

    def _stop(self):
        """Stop the service."""
        repo = self._repo
        if repo.repo_type == 'docker-infra':
            self._stop_docker_services()
            return

        def _run():
            self._launcher.stop_service(repo.name, self._log, self._update_status)
        threading.Thread(target=_run, daemon=True).start()

    def _stop_docker_services(self):
        """Stop selected docker-compose services."""
        def _run():
            from core.db_manager import docker_compose_down
            if hasattr(self, '_docker_checkboxes'):
                for dc_file, var in self._docker_checkboxes.items():
                    if var.get():
                        docker_compose_down(dc_file, log=self._log)
        threading.Thread(target=_run, daemon=True).start()

    def _restart(self):
        """Restart the service."""
        repo = self._repo
        if repo.repo_type == 'docker-infra':
            self._stop_docker_services()
            self.after(2000, self._start_docker_services)
            return

        def _run():
            profile = ''
            if hasattr(self, '_profile_combo'):
                profile = self._profile_combo.get()
            elif hasattr(self, '_env_combo'):
                profile = self._env_combo.get()

            self._launcher.restart_service(
                repo.name, repo.path, repo.repo_type,
                profile, repo.server_port,
                self._log, self._update_status
            )
        threading.Thread(target=_run, daemon=True).start()

    def _pull(self):
        """Pull latest changes."""
        def _run():
            from core.git_manager import get_local_changes, get_commits_behind, get_current_branch, pull
            from tkinter import messagebox
            
            ignore = ['application.yml', 'environment.ts']
            
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
                            self._pull_btn.configure(text=f"⬇ Pull ({commits})", fg_color="#1d4ed8")
                        else:
                            self._pull_btn.configure(text="⬇ Pull", fg_color="#172554")
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
        files = []
        if repo.repo_type in ('spring-boot', 'maven-lib'):
            resources_dir = os.path.join(repo.path, 'src', 'main', 'resources')
            if os.path.isdir(resources_dir):
                for f in sorted(os.listdir(resources_dir)):
                    if f.startswith('application') and f.endswith('.yml'):
                        files.append(os.path.join(resources_dir, f))
        elif repo.repo_type == 'angular':
            files = repo.environment_files
        elif repo.repo_type == 'docker-infra':
            files = repo.docker_compose_files
        return files

    def _show_file_selector(self, files: list):
        """Show a popup to select which config file to edit."""
        popup = ctk.CTkToplevel(self)
        popup.title("Seleccionar archivo")
        popup.geometry("400x300")
        popup.transient(self)
        popup.grab_set()

        ctk.CTkLabel(popup, text="Seleccionar archivo para editar:",
                     font=(FONT_FAMILY, 12, "bold")).pack(pady=(15, 10))

        scroll = ctk.CTkScrollableFrame(popup)
        scroll.pack(fill="both", expand=True, padx=15, pady=5)

        for f in files:
            btn = ctk.CTkButton(
                scroll, text=os.path.basename(f),
                font=(FONT_FAMILY, 11), height=32,
                fg_color="transparent",
                text_color=("#333", "#ddd"),
                hover_color=("#E3F2FD", "#1a2332"),
                anchor="w",
                command=lambda fp=f: (popup.destroy(),
                                      self._on_edit_config(fp) if self._on_edit_config else None)
            )
            btn.pack(fill="x", padx=5, pady=2)

    def _update_status(self, name: str, status: str):
        """Update the status display."""
        self._status = status

        def _update():
            color = STATUS_ICONS.get(status, '#ef4444')
            if status == 'logging':
                color = STATUS_ICONS.get('logging', '#f97316')
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

        try:
            self.after(0, _update)
        except Exception:
            pass

    # ─── Public API ──────────────────────────────────────────────

    def is_selected(self) -> bool:
        return self.selected_var.get()

    def set_selected(self, value: bool):
        self.selected_var.set(value)

    def set_branch(self, branch: str) -> bool:
        from core.git_manager import has_branch
        if has_branch(self._repo.path, branch):
            self._on_branch_change(branch)
            return True
        return False

    def set_db_preset(self, preset_name: str):
        if hasattr(self, '_db_combo'):
            self._db_combo.set(preset_name)
            self._on_db_change(preset_name)

    def set_profile(self, profile: str):
        if hasattr(self, '_config_combo'):
            self._config_combo.set(profile)
            self._update_header_hints()
            self._on_config_change(profile)

    def _start(self):
        """Start the service."""
        java_choice = self.selected_java_var.get()
        java_home = self._java_versions.get(java_choice, "")
        
        if self._repo.repo_type == 'spring-boot':
            profile = getattr(self, '_profile_combo', None)
            active_profile = profile.get() if profile else 'default'
            self._launcher.start_spring_boot(
                self._repo.name, self._repo.path, active_profile,
                self._repo.server_port, self._log, self._on_status_change, java_home=java_home
            )
        elif self._repo.repo_type == 'angular':
            env = getattr(self, '_env_combo', None)
            active_env = env.get() if env else ''
            self._launcher.start_angular(
                self._repo.name, self._repo.path, active_env,
                self._log, self._on_status_change
            )
        elif self._repo.repo_type == 'maven-lib':
            self._launcher.start_maven_install(
                self._repo.name, self._repo.path, self._log, self._on_status_change, java_home=java_home
            )
        elif self._repo.repo_type == 'docker-infra':
            pass # We don't have start for docker-infra directly yet

    def _stop(self):
        """Stop the service."""
        self._launcher.stop_service(self._repo.name, self._log, self._on_status_change)

    def _restart(self):
        """Restart the service."""
        java_choice = self.selected_java_var.get()
        java_home = self._java_versions.get(java_choice, "")
        
        profile = ''
        if getattr(self, '_profile_combo', None):
            profile = self._profile_combo.get()
        elif getattr(self, '_env_combo', None):
            profile = self._env_combo.get()

        self._launcher.restart_service(
            self._repo.name, self._repo.path, self._repo.repo_type,
            profile, self._repo.server_port, self._log, self._on_status_change, java_home=java_home
        )

    def _on_status_change(self, name: str, status: str):
        """Callback from ServiceLauncher when status changes."""
        if name != self._repo.name:
            return

        self._status = status
        
        def _update():
            # Basic info updater that was decoupled
            color = STATUS_ICONS.get(status, '#ef4444')
            if status == 'logging':
                color = STATUS_ICONS.get('logging', '#f97316')
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
        except Exception:
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

    def get_current_profile(self) -> str:
        if hasattr(self, '_config_combo'):
            val = self._config_combo.get()
            return val if val != "- Sin Seleccionar -" else ''
        return ''

    def get_name(self) -> str:
        return self._repo.name

    def get_repo_info(self):
        return self._repo

    def do_pull(self):
        self._pull()

    def do_start(self):
        self._start()

    def do_stop(self):
        self._stop()

    def get_status(self) -> str:
        return self._status
