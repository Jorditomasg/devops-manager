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
NPM_CI_OK = "📦 npm ci ✓"
NPM_CI_FAIL = "📦 npm ci ✗"
NPM_CI_RUN = "⏳ Instalando..."
MVN_INSTALL_OK = "🔧 mvn install ✓"
MVN_INSTALL_FAIL = "🔧 mvn install ✗"
MVN_INSTALL_RUN = "⏳ Compilando..."
BTN_CLICK = "<Button-1>"

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
    'running': '🟢',
    'starting': '🟡',
    'stopped': '🔴',
    'error': '🔴',
    'logging': '🟠',
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
            self._header, text=STATUS_ICONS.get('stopped', '⚪'),
            font=(FONT_FAMILY, 15), width=20
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
        if hasattr(self, '_npm_ci_btn'):
            if is_running:
                self._npm_ci_btn.configure(state="disabled")
            elif not is_installing:
                self._npm_ci_btn.configure(state="normal")
                
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

    def install_dependencies(self):
        """Public method to install dependencies (npm ci or mvn install)."""
        if self._repo.repo_type == 'angular':
            if hasattr(self, '_npm_ci_btn') and self._npm_ci_btn.cget("state") != "disabled":
                self._run_npm_ci()
        elif self._repo.repo_type in ('spring-boot', 'maven-lib'):
            if hasattr(self, '_mvn_install_btn') and self._mvn_install_btn.cget("state") != "disabled":
                self._run_mvn_install()

    # ─── EXPAND PANEL ────────────────────────────────────────────

    def _build_expand_panel(self):
        """Build the expandable details panel."""
        repo = self._repo

        self._expand_panel = ctk.CTkFrame(self, fg_color=EXPAND_BG, corner_radius=0)

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
        # Save log_frame as an instance variable to hide/show it dynamically
        self._log_frame = ctk.CTkFrame(content, fg_color="transparent")
        # Do not pack initially to hide it when empty

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
        if hasattr(self, '_log_frame'):
            self._log_frame.pack_forget()

    def _detach_logs(self):
        """Open the logs in a separate detached window."""
        # Prevent multiple detached windows
        if getattr(self, '_detached_log_window', None) and self._detached_log_window.winfo_exists():
            self._detached_log_window.focus()
            return
            
        self._detached_log_window = ctk.CTkToplevel(self)
        self._detached_log_window.title(f"Logs - {self._repo.name}")
        self._detached_log_window.geometry("800x600")
        
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
            # Show the log frame if it's hidden and this is the first log
            if not getattr(self, '_has_logs', False):
                self._has_logs = True
                if hasattr(self, '_log_frame'):
                    self._log_frame.pack(fill="x", pady=(8, 0))

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
        """Temporarily change the status icon to 🟠 when a log is received."""
        if not hasattr(self, '_status_label'):
            return
            
        self._status_label.configure(text=STATUS_ICONS.get('logging', '🟠'))

        if getattr(self, '_log_flash_timer', None):
            self.after_cancel(self._log_flash_timer)

        def _revert():
            if hasattr(self, '_status_label') and hasattr(self, '_status'):
                self._status_label.configure(text=STATUS_ICONS.get(self._status, '⚪'))
            self._log_flash_timer = None

        self._log_flash_timer = self.after(300, _revert)

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
        pull_btn = ctk.CTkButton(
            row1, text="⬇ Pull", width=65,
            fg_color="#172554", hover_color="#2563eb",
            border_color="#3b82f6",
            command=self._pull, **sec_btn_style
        )
        pull_btn.pack(side="left", padx=(0, 3))
        ToolTip(pull_btn, "Descargar cambios (git pull)")

        # npm ci for Angular
        if repo.repo_type == 'angular':
            self._build_npm_ci_btn(row1, sec_btn_style)

        # mvn install for Spring Boot / Maven lib
        if repo.repo_type in ('spring-boot', 'maven-lib'):
            self._build_mvn_install_btn(row1, sec_btn_style)

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

        # Config
        edit_btn = ctk.CTkButton(
            row1, text="⚙ Config", width=80,
            fg_color="#1e293b", hover_color="#475569",
            border_color="#64748b",
            command=self._edit_config, **sec_btn_style
        )
        edit_btn.pack(side="left")
        ToolTip(edit_btn, "Editar configuración")

    def _build_npm_ci_btn(self, parent, style):
        """Build the npm ci button."""
        has_nm = os.path.isdir(os.path.join(self._repo.path, 'node_modules'))
        has_lock = os.path.isfile(os.path.join(self._repo.path, 'package-lock.json')) or \
                   os.path.isfile(os.path.join(self._repo.path, 'npm-shrinkwrap.json'))
        
        btn_text = "📦 npm ci" if has_lock else "📦 npm i"
        
        self._npm_ci_btn = ctk.CTkButton(
            parent, text=NPM_CI_OK if has_nm else btn_text,
            width=90,
            fg_color="#1e293b" if has_nm else "#4c1616",
            hover_color="#475569" if has_nm else "#dc2626",
            border_color="#64748b" if has_nm else "#ef4444",
            command=self._run_npm_ci, **style
        )
        self._npm_ci_btn.pack(side="left", padx=(0, 3))
        
        tooltip_text = f"Instalar dependencias ({'npm ci' if has_lock else 'npm i'})"
        if not has_nm:
            tooltip_text += " — node_modules no encontrado!"
            
        self._npm_ci_tooltip = ToolTip(
            self._npm_ci_btn,
            tooltip_text
        )

    def _build_mvn_install_btn(self, parent, style):
        """Build the mvn install button."""
        self._mvn_install_btn = ctk.CTkButton(
            parent, text="🔧 mvn install", width=110,
            fg_color="#1e293b", hover_color="#475569",
            border_color="#64748b",
            command=self._run_mvn_install, **style
        )
        self._mvn_install_btn.pack(side="left", padx=(0, 3))
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

        if repo.repo_type == 'spring-boot' and repo.profiles:
            has_row2 = True
            ctk.CTkLabel(row2, text="App:", font=(FONT_FAMILY, 13),
                         text_color="#c7d2fe", width=50, anchor="e").pack(side="left")
            self._profile_combo = ctk.CTkComboBox(
                row2, values=repo.profiles, width=130,
                command=self._on_profile_change, **combo_style
            )
            self._profile_combo.pack(side="left", padx=(6, 12))
            if 'local' in repo.profiles:
                self._profile_combo.set('local')
            elif repo.profiles:
                self._profile_combo.set(repo.profiles[0])

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

        if repo.repo_type == 'angular' and repo.profiles:
            has_row2 = True
            ctk.CTkLabel(row2, text="Env:", font=(FONT_FAMILY, 13),
                         text_color="#c7d2fe", width=50, anchor="e").pack(side="left")
            self._env_combo = ctk.CTkComboBox(
                row2, values=repo.profiles, width=130,
                command=self._on_env_change, **combo_style
            )
            self._env_combo.pack(side="left", padx=(6, 0))
            if 'local' in repo.profiles:
                self._env_combo.set('local')
            elif repo.profiles:
                self._env_combo.set(repo.profiles[0])

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
            self._expand_panel.pack(fill="x", after=self._header)
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
                    self._branch_combo.configure(values=branches)
                self._branch_combo.set(current)
                self._update_header_hints()
            self.after(0, _update)

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
        def _run():
            from core.git_manager import checkout
            success, _ = checkout(self._repo.path, branch, self._log)
            if success:
                def _update():
                    self._branch_combo.set(branch)
                    self._update_header_hints()
                self.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _on_profile_change(self, profile: str):
        """Handle app profile change."""
        self._update_header_hints()
        if self._log:
            self._log(f"[{self._repo.name}] App profile cambiado a: {profile}")

    def _on_env_change(self, env: str):
        """Handle env change."""
        self._update_header_hints()
        if self._log:
            self._log(f"[{self._repo.name}] Env cambiado a: {env}")

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

    # ─── npm ci ──────────────────────────────────────────────────

    def _run_npm_ci(self):
        """Run npm ci or npm i to install dependencies."""
        repo = self._repo
        has_lock = os.path.isfile(os.path.join(repo.path, 'package-lock.json')) or \
                   os.path.isfile(os.path.join(repo.path, 'npm-shrinkwrap.json'))
        cmd_args = ['npm', 'ci', '--yes', '--legacy-peer-deps'] if has_lock else ['npm', 'install', '--yes', '--legacy-peer-deps']
        cmd_str = ' '.join(cmd_args)
        
        if self._log:
            self._log(f"Running {cmd_str}...")
        self._npm_ci_btn.configure(text=NPM_CI_RUN, state="disabled")
        self._is_installing = True
        self._update_button_visibility()

        def _run():
            try:
                process = subprocess.Popen(
                    cmd_args, cwd=repo.path,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, shell=True
                )
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    if self._log:
                        self._log(line.strip())
                process.wait()

                def _done():
                    self._is_installing = False
                    if process.returncode == 0:
                        if self._log:
                            self._log(f"✅ {cmd_str} completado")
                        self._npm_ci_btn.configure(
                            text=NPM_CI_OK, state="normal",
                            fg_color="#1e293b", border_color="#64748b"
                        )
                        self._npm_ci_tooltip.update_text(f"Instalación completada ({cmd_str})")
                        self._update_header_hints()
                    else:
                        if self._log:
                            self._log(f"❌ {cmd_str} falló (exit: {process.returncode})")
                        self._npm_ci_btn.configure(
                            text=NPM_CI_FAIL, state="normal",
                            fg_color="#4c1616", border_color="#ef4444"
                        )
                    self._update_button_visibility()
                self.after(0, _done)
            except Exception as e:
                if self._log:
                    self._log(f"Error {cmd_str}: {e}")
                def _err():
                    self._is_installing = False
                    self._npm_ci_btn.configure(text=NPM_CI_FAIL, state="normal")
                    self._update_button_visibility()
                self.after(0, _err)

        threading.Thread(target=_run, daemon=True).start()

    # ─── mvn install ─────────────────────────────────────────────

    def _run_mvn_install(self):
        """Run mvn install -DskipTests for Java projects using specified Java version."""
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
                    text=True, bufsize=1
                )
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    if self._log:
                        self._log(line.strip())
                process.wait()

                def _done():
                    self._is_installing = False
                    if process.returncode == 0:
                        if self._log:
                            self._log(f"✅ mvn install completado")
                        self._mvn_install_btn.configure(
                            text=MVN_INSTALL_OK, state="normal",
                            fg_color="#144d28", border_color="#22c55e"
                        )
                        self._update_header_hints()
                    else:
                        if self._log:
                            self._log(f"❌ mvn install falló (exit: {process.returncode})")
                        self._mvn_install_btn.configure(
                            text=MVN_INSTALL_FAIL, state="normal",
                            fg_color="#4c1616", border_color="#ef4444"
                        )
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
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
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
            self._npm_ci_btn.configure(text=NPM_CI_RUN, state="disabled")
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
                    if process.returncode == 0:
                        if self._log:
                            self._log(f"✅ npm ci completado, iniciando...")
                        if hasattr(self, '_npm_ci_btn'):
                            self._npm_ci_btn.configure(
                                text=NPM_CI_OK, state="normal",
                                fg_color="#1e293b", border_color="#64748b"
                            )
                            self._npm_ci_tooltip.update_text("Instalar dependencias (npm ci)")
                        self._do_start()
                    else:
                        if self._log:
                            self._log(f"❌ npm ci falló, no se puede iniciar")
                        if hasattr(self, '_npm_ci_btn'):
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
            from core.git_manager import pull
            pull(self._repo.path, self._log)
            self._refresh_branch()
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
            self._status_label.configure(text=STATUS_ICONS.get(status, '⚪'))
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
        if hasattr(self, '_profile_combo') and profile in self._repo.profiles:
            self._profile_combo.set(profile)
            self._update_header_hints()

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
            self._status_label.configure(text=STATUS_ICONS.get(status, '⚪'))
            
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
        if hasattr(self, '_profile_combo'):
            return self._profile_combo.get()
        if hasattr(self, '_env_combo'):
            return self._env_combo.get()
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
