"""
app.py — Main application window for DevOps Manager.
"""
import customtkinter as ctk
import os
import json
import sys
import threading
import pystray
import re
import ctypes
from PIL import Image
from pystray import MenuItem as item

class StreamRedirector:
    def __init__(self, callback):
        self.callback = callback

    def write(self, string):
        self.callback(string)

    def flush(self):
        pass

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.repo_card import RepoCard
from gui.global_panel import GlobalPanel
from gui.tooltip import ToolTip
from gui.dialogs import CloneDialog, ConfigEditorDialog, ProfileDialog, SettingsDialog
from core.repo_detector import detect_repos
from core.service_launcher import ServiceLauncher
from core.config_manager import load_db_presets


CONFIG_FILE = 'devops_manager_config.json'

# ── Font constants ──────────────────────────────────────────────
FONT_FAMILY = "Segoe UI"

# ── Profile constants ───────────────────────────────────────────
NO_PROFILE_TEXT = "- Sin Perfil -"
SAVE_PROFILE_TEXT = "💾 Guardar"
SAVE_NEW_PROFILE_TEXT = "💾 Guardar Nuevo"
SAVE_CHANGED_PROFILE_TEXT = "💾 Guardar*"

class DevOpsManagerApp(ctk.CTk):
    def __init__(self, workspace_dir: str = None, project_analyzer=None, process_manager=None):

        # Theme must be set BEFORE CTk.__init__
        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.project_analyzer = project_analyzer
        self.process_manager = process_manager

        # Set Windows AppUserModelID for proper taskbar icon grouping
        try:
            if sys.platform == "win32":
                myappid = 'boa.devopsmanager.app.1'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        # Determine workspace directory
        if workspace_dir:
            self._workspace_dir = workspace_dir
        else:
            self._workspace_dir = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )

        self._app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self._settings = self._load_settings()
        # Keep settings synced to prevent false change detection on close
        self._settings['workspace_dir'] = self._workspace_dir

        self._service_launcher = ServiceLauncher()
        self._db_presets = self._settings.get('db_presets', {})
        self._repo_cards = []
        self._repos = []
        self._current_profile_name = self._settings.get('last_profile', "")
        self._current_profile_data = {}

        # Window config
        self.title("DevOps Manager")
        self.geometry("1300x900")
        self.minsize(1000, 650)

        # Set Window icon
        icon_path = os.path.join(self._app_dir, "icon_red.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
            self.after(200, lambda: self.iconbitmap(icon_path))

        # Handle close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Setup Tray
        self._tray_icon = None
        self._init_tray()

        # Bind Unmap to catch minimize
        self.bind("<Unmap>", self._on_window_unmap)

        self._build_ui()
        self._scan_repos()
        self._load_initial_profile_data()

        # Start background check loop for tray icon status and profile changes
        self._check_tray_status()
        self._check_profile_changes_loop()
        self._check_tray_status()

    def _build_ui(self):
        """Build the main UI layout."""
        self._build_topbar()
        self._global_panel = GlobalPanel(
            self, db_presets=self._db_presets, log_callback=self._log
        )
        self._global_panel.pack(fill="x", padx=10, pady=(10, 6))
        self._setup_cards_scroll()
        self._build_global_log_panel()
        self._statusbar = ctk.CTkLabel(
            self, text="Listo",
            font=(FONT_FAMILY, 11), text_color="#6366f1",
            anchor="w", height=24
        )
        self._statusbar.pack(fill="x", padx=15, pady=(0, 6))
        self._setup_global_log_redirect()

    def _build_topbar(self):
        """Build the top bar with logo, path, and action buttons."""
        topbar = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color="#0f0e26")
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        ctk.CTkFrame(self, height=2, corner_radius=0, fg_color="#312e81").pack(fill="x")

        ctk.CTkLabel(
            topbar, text="🚀 DevOps Manager",
            font=(FONT_FAMILY, 22, "bold"), text_color="#e0e7ff"
        ).pack(side="left", padx=20)

        path_label = ctk.CTkLabel(
            topbar, text=self._workspace_dir,
            font=("Consolas", 12), text_color="#6366f1", cursor="hand2"
        )
        path_label.pack(side="left", padx=10)
        path_label.bind("<Button-1>", lambda e: self._open_workspace())
        ToolTip(path_label, "Abrir carpeta en el explorador")

        self._build_topbar_buttons(topbar)

    def _build_topbar_buttons(self, topbar):
        """Build the right-side action buttons in the top bar."""
        btn_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        btn_frame.pack(side="right", padx=15)

        btn_defs = [
            ("➕ Clonar",  95,  "#172554", "#2563eb", "#3b82f6", self._show_clone_dialog, "Clonar nuevo repositorio"),
            ("🔄 Rescan",  95,  "#4a3310", "#d97706", "#f59e0b", self._scan_repos, "Re-escanear workspace"),
            ("⚙",          38,  "#1e293b", "#475569", "#64748b", self._show_settings, "Abrir configuración"),
            ("📜",         38,  "#1e293b", "#475569", "#64748b", self._toggle_global_log, "Mostrar/Ocultar Log Global"),
        ]

        from core.profile_manager import list_profiles

        profiles = [NO_PROFILE_TEXT] + list_profiles()

        # Quick Save btn
        self._quick_save_btn = ctk.CTkButton(
            btn_frame, text="💾", width=38, height=34,
            font=(FONT_FAMILY, 16),
            fg_color="#7f1d1d", hover_color="#991b1b",
            border_width=1, border_color="#b91c1c",
            text_color="#facc15",
            corner_radius=6, command=self._save_current_profile
        )
        self._quick_save_btn.pack(side="left", padx=(0, 5))
        self._quick_save_btn.pack_forget() # Initially hidden
        ToolTip(self._quick_save_btn, "💾 Guardar cambios en el perfil actual")
        
        # Profile Dropdown
        self._profile_combo = ctk.CTkComboBox(
            btn_frame, values=profiles, width=160, height=34,
            font=(FONT_FAMILY, 12),
            corner_radius=6, border_color="#7c3aed", button_color="#7c3aed",
            command=self._on_profile_dropdown_change
        )
        self._profile_combo.pack(side="left", padx=(0, 10))
        if self._current_profile_name in profiles:
            self._profile_combo.set(self._current_profile_name)
        else:
            self._profile_combo.set(NO_PROFILE_TEXT)
            
        ToolTip(self._profile_combo, "Seleccionar Perfil de Workspace")
        
        # Gestionar Perfiles btn (Dynamic, to the right of the selector)
        self._save_profile_btn = ctk.CTkButton(
            btn_frame, text="👤", width=38, height=34,
            font=(FONT_FAMILY, 16),
            fg_color="#1e293b", hover_color="#475569",
            border_width=1, border_color="#64748b",
            corner_radius=6, command=self._show_configs
        )
        self._save_profile_btn.pack(side="left", padx=(0, 20))
        ToolTip(self._save_profile_btn, "Gestionar Perfiles")
        
        for text, width, fg, hover, border, cmd, tip in btn_defs:
            btn = ctk.CTkButton(
                btn_frame, text=text, width=width, height=34,
                font=(FONT_FAMILY, 12 if len(text) > 2 else 16),
                fg_color=fg, hover_color=hover,
                border_width=1, border_color=border,
                corner_radius=6, command=cmd
            )
            btn.pack(side="left", padx=3)
            ToolTip(btn, tip)

    def _setup_cards_scroll(self):
        """Setup the scrollable cards area with overscroll prevention."""
        self._cards_scroll = ctk.CTkScrollableFrame(
            self, corner_radius=0, fg_color="transparent"
        )
        self._cards_scroll.pack(fill="both", expand=True, padx=10)

        canvas = self._cards_scroll._parent_canvas
        canvas.configure(yscrollincrement=20)

        canvas.bind("<MouseWheel>", self._on_canvas_scroll)
        canvas.bind("<Button-4>", self._on_canvas_scroll)
        canvas.bind("<Button-5>", self._on_canvas_scroll)
        self._cards_scroll.bind_all("<MouseWheel>", self._on_canvas_scroll)

    def _on_canvas_scroll(self, event):
        """Smooth scroll handler with overscroll prevention."""
        canvas = self._cards_scroll._parent_canvas
        widget = self.winfo_containing(event.x_root, event.y_root)
        if not widget or not str(widget).startswith(str(self._cards_scroll)):
            return
        top, bottom = canvas.yview()
        if top <= 0.0 and bottom >= 1.0:
            return "break"
        units = self._get_scroll_units(event, top, bottom)
        if units:
            canvas.yview_scroll(units, "units")
        return "break"

    def _get_scroll_units(self, event, top: float, bottom: float):
        """Return scroll units to apply, or None if blocked by overscroll guard."""
        if event.delta:
            direction = -1 if event.delta > 0 else 1
            if (direction < 0 and top <= 0.0) or (direction > 0 and bottom >= 1.0):
                return None
            return direction * 3
        if event.num == 4:
            return None if top <= 0.0 else -3
        if event.num == 5:
            return None if bottom >= 1.0 else 3
        return None

    def _build_global_log_panel(self):
        """Build the global log panel (hidden by default)."""
        self._global_log_frame = ctk.CTkFrame(self, fg_color="#0f0e26", height=150)
        self._global_log_frame.pack_propagate(False)

        log_header = ctk.CTkFrame(self._global_log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=(5, 0))

        ctk.CTkLabel(log_header, text="📜 Log Global", font=(FONT_FAMILY, 12, "bold"), text_color="#c7d2fe").pack(side="left")

        btn_style = {"height": 24, "font": (FONT_FAMILY, 10), "fg_color": "#1e1b4b", "hover_color": "#312e81", "border_width": 1, "border_color": "#4338ca"}
        ctk.CTkButton(log_header, text="🗗 Desacoplar", width=80, command=self._detach_global_log, **btn_style).pack(side="right", padx=(0, 6))
        ctk.CTkButton(log_header, text="🗑 Limpiar", width=60, command=self._clear_global_log, **btn_style).pack(side="right")

        self._global_log_textbox = ctk.CTkTextbox(
            self._global_log_frame, font=("Consolas", 11),
            corner_radius=6, border_width=1,
            border_color="#3b3768", fg_color="#16132e",
            text_color="#e0e7ff", state="disabled"
        )
        self._global_log_textbox.pack(fill="both", expand=True, padx=10, pady=5)

    def _log(self, message: str):
        """Central log function."""
        print(message)
        if hasattr(self, '_statusbar') and len(message) < 100:
            self._statusbar.configure(text=message)

    def _toggle_global_log(self):
        if self._global_log_frame.winfo_ismapped():
            self._global_log_frame.pack_forget()
        else:
            self._global_log_frame.pack(fill="x", padx=10, pady=(5, 5), before=self._statusbar)

    def _clear_global_log(self):
        if hasattr(self, '_global_log_textbox'):
            self._global_log_textbox.configure(state="normal")
            self._global_log_textbox.delete("1.0", "end")
            self._global_log_textbox.configure(state="disabled")

        if getattr(self, '_detached_global_log_textbox', None) and self._detached_global_log_textbox.winfo_exists():
            self._detached_global_log_textbox.configure(state="normal")
            self._detached_global_log_textbox.delete("1.0", "end")
            self._detached_global_log_textbox.configure(state="disabled")

    def _detach_global_log(self):
        """Open the global logs in a separate detached window and hide the embedded one."""
        if getattr(self, '_detached_global_log_window', None) and self._detached_global_log_window.winfo_exists():
            self._detached_global_log_window.focus()
            return

        # Hide the embedded log
        if self._global_log_frame.winfo_ismapped():
            self._global_log_frame.pack_forget()
            
        self._detached_global_log_window = ctk.CTkToplevel(self)
        self._detached_global_log_window.title("Log Global - DevOps Manager")
        self._detached_global_log_window.geometry("800x600")
        
        # Bring window to front
        self.after(100, lambda: self._detached_global_log_window.lift())
        self.after(110, lambda: self._detached_global_log_window.focus_force())
        
        self._detached_global_log_textbox = ctk.CTkTextbox(
            self._detached_global_log_window, font=("Consolas", 12),
            corner_radius=0, border_width=0,
            fg_color="#0f0e26", text_color="#e0e7ff"
        )
        self._detached_global_log_textbox.pack(fill="both", expand=True)
        
        # Copy current content
        current_logs = self._global_log_textbox.get("1.0", "end")
        self._detached_global_log_textbox.insert("end", current_logs)
        self._detached_global_log_textbox.configure(state="disabled")
        self._detached_global_log_textbox.see("end")

    def _open_workspace(self):
        """Open the workspace directory in the system file explorer."""
        try:
            if sys.platform == 'win32':
                os.startfile(self._workspace_dir)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', self._workspace_dir])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', self._workspace_dir])
        except Exception as e:
            self._log(f"Error al abrir carpeta: {e}")

    def _setup_global_log_redirect(self):
        """Redirect stdout/stderr to the global log panel."""
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        redirector = StreamRedirector(self._log_global_stream)
        sys.stdout = redirector
        sys.stderr = redirector

    def _log_global_stream(self, string):
        if string:
            string = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', string)

        def _insert():
            self._insert_log_into_textbox(
                getattr(self, '_global_log_textbox', None), string, 1000
            )
            self._insert_log_into_textbox(
                getattr(self, '_detached_global_log_textbox', None), string, 1000
            )

        try:
            self.after(0, _insert)
        except Exception:
            pass

    def _insert_log_into_textbox(self, textbox, text: str, max_lines: int):
        """Thread-safe helper to insert text into a CTkTextbox, trimming to max_lines."""
        if not textbox or not textbox.winfo_exists():
            return
        textbox.configure(state="normal")
        textbox.insert("end", text)
        content = textbox.get("1.0", "end")
        lines = content.splitlines()
        if len(lines) > max_lines:
            excess = len(lines) - max_lines
            textbox.delete("1.0", f"{excess + 1}.0")
        textbox.see("end")
        textbox.configure(state="disabled")

    def _scan_repos(self):
        """Scan workspace for repositories."""
        self._log("Escaneando workspace...")
        self._statusbar.configure(text="Escaneando repos...")

        def _run():
            if self.project_analyzer:
                repos = self.project_analyzer.detect_repos(self._workspace_dir)
            else:
                repos = detect_repos(self._workspace_dir)
            self._repos = repos
            
            from application.use_cases.manage_services_use_case import ManageServicesUseCase
            if hasattr(self, '_manage_services_use_case'):
                self._manage_services_use_case.update_repos(repos)
            elif self.process_manager:
                self._manage_services_use_case = ManageServicesUseCase(self.process_manager, repos)
                self._manage_services_use_case.set_logger(self._log)

            def _update():
                self._build_cards(repos)
                self._statusbar.configure(
                    text=f"{len(repos)} repositorios detectados"
                )
                self._log(f"Detectados {len(repos)} repos: "
                         + ", ".join(r.name for r in repos))

            self.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _build_cards(self, repos: list):
        """Build repo cards in vertical list (horizontal cards)."""
        # Clear existing cards
        for widget in self._cards_scroll.winfo_children():
            widget.destroy()
        self._repo_cards = []

        # Restore persisted state
        repo_state = self._settings.get('repo_state', {})
        self._java_versions = self._settings.get('java_versions', {})

        # Single column list layout
        for idx, repo in enumerate(repos):
            card = RepoCard(
                self._cards_scroll, repo,
                self._service_launcher,
                db_presets=self._db_presets,
                java_versions=self._java_versions,
                log_callback=self._log,
                on_edit_config=self._open_config_editor,
                on_change_callback=self._check_profile_changes
            )
            card.pack(fill="x", padx=4, pady=3)
            self._repo_cards.append(card)

            # Restore per-repo state (selection, custom command)
            state = repo_state.get(repo.name, {})
            if 'selected' in state:
                card.set_selected(state['selected'])
            if state.get('custom_command'):
                card.set_custom_command(state['custom_command'])
            if state.get('java_version'):
                card.selected_java_var.set(state['java_version'])

            # Stagger branch loading
            if card._branch_load_id:
                card.after_cancel(card._branch_load_id)
            card._branch_load_id = card.after(300 * idx, card._refresh_branch)

        # Update global panel
        self._global_panel.set_cards(self._repo_cards)

    def _open_config_editor(self, filepath: str):
        """Open the config editor dialog for a file."""
        ConfigEditorDialog(self, filepath, self._log)

    def _show_clone_dialog(self):
        """Show the clone dialog."""
        CloneDialog(self, self._workspace_dir, self._log, self._scan_repos)

    def _show_configs(self):
        """Show the saved configurations dialog."""
        ProfileDialog(
            parent=self,
            workspace_dir=self._workspace_dir,
            repos=self._repos,
            repo_cards=self._repo_cards,
            db_presets=self._db_presets,
            log_callback=self._log,
            on_profile_loaded=self._apply_config,
            on_rescan=self._scan_repos,
            on_profiles_changed=self._refresh_profile_dropdown
        )

    def _refresh_profile_dropdown(self, auto_select_name=None):
        """Reload profile options into topbar dropdown after creation/deletion."""
        from core.profile_manager import list_profiles
        profiles = [NO_PROFILE_TEXT] + list_profiles()
        if hasattr(self, '_profile_combo'):
            self._profile_combo.configure(values=profiles)
            
            if auto_select_name and auto_select_name in profiles:
                self._profile_combo.set(auto_select_name)
                # Ensure the system selects and triggers it
                self._on_profile_dropdown_change(auto_select_name)
            elif self._current_profile_name in profiles:
                self._profile_combo.set(self._current_profile_name)
            else:
                self._profile_combo.set(NO_PROFILE_TEXT)

    def _load_initial_profile_data(self):
        """Loads cached profile data for change tracking on startup."""
        if self._current_profile_name and self._current_profile_name != NO_PROFILE_TEXT:
            from core.profile_manager import load_profile
            data = load_profile(self._current_profile_name)
            if data:
                self._current_profile_data = data
        
    def _on_profile_dropdown_change(self, selected_profile: str):
        if selected_profile == NO_PROFILE_TEXT:
            self._current_profile_name = ""
            self._current_profile_data = {}
            self._settings['last_profile'] = ""
            self._save_settings(self._settings)
            
            # Limpiar perfiles en cards
            for card in self._repo_cards:
                card.set_profile('- Sin Seleccionar -')
            return

        from core.profile_manager import load_profile
        data = load_profile(selected_profile)
        if not data:
            self._log(f"Error cargando perfil: {selected_profile}")
            return

        # Assign first, then apply -> to avoid false positive in change check
        self._current_profile_name = selected_profile
        self._current_profile_data = data
        self._settings['last_profile'] = selected_profile
        self._save_settings(self._settings)
        
        self._apply_config(data)

    def _save_current_profile(self):
        """Guards changes to current profile if exists, else opens Config manager."""
        if not self._current_profile_name or self._current_profile_name == NO_PROFILE_TEXT:
             # Despliega dialog si no hay uno seleccionado
             self._show_configs()
             return
             
        from core.profile_manager import build_profile_data, save_profile
        profile_data = build_profile_data(
            self._repo_cards,
            db_presets=self._db_presets,
            include_db_presets=True,
            include_config_files=True
        )
        
        save_profile(self._current_profile_name, profile_data)
        self._current_profile_data = profile_data
        
        self._quick_save_btn.pack_forget()
        self._save_profile_btn.configure(
            text="👤", fg_color="#1e293b", border_color="#64748b",
            hover_color="#475569", text_color="#e0e7ff"
        )
        self._log(f"✅ Perfil '{self._current_profile_name}' guardado correctamente")

    def _check_profile_changes_loop(self):
        """Loop to detect unsaved changes in current profile periodically."""
        self._check_profile_changes()
        self.after(3000, self._check_profile_changes_loop)

    def _check_profile_changes(self):
        """Compares UI state vs loaded profile data to highlight the profile btn."""
        if not hasattr(self, '_save_profile_btn'): return
        
        if not self._current_profile_name or self._current_profile_name == NO_PROFILE_TEXT:
            # No profile selected
            if self._save_profile_btn.cget("text") != "👤":
                self._save_profile_btn.configure(
                    text="👤", fg_color="#1e293b", hover_color="#475569", 
                    border_color="#64748b", text_color="#e0e7ff"
                )
            if self._quick_save_btn.winfo_ismapped():
                self._quick_save_btn.pack_forget()
            return

        # Check if changed
        has_changed = self._detect_unsaved_profile_changes()
        
        if has_changed:
            if not self._quick_save_btn.winfo_ismapped():
                self._quick_save_btn.configure(text="💾", fg_color="#7f1d1d", hover_color="#991b1b", border_color="#b91c1c", text_color="#facc15")
                self._quick_save_btn.pack(side="left", padx=(0, 5), before=self._profile_combo)
        else:
            if self._quick_save_btn.winfo_ismapped():
                 self._quick_save_btn.pack_forget()

    def _detect_unsaved_profile_changes(self) -> bool:
        """Returns True if current repo cards deviate from _current_profile_data."""
        if not self._current_profile_data: 
            return False
            
        from core.profile_manager import build_profile_data
        current_data = build_profile_data(
            self._repo_cards,
            db_presets=self._db_presets,
            include_db_presets=False,
            include_config_files=False # Heavy to compare, rely on memory branches/profiles
        )
        
        # Compare repos
        target_repos = self._current_profile_data.get('repos', {})
        current_repos = current_data.get('repos', {})
        
        # Check counts
        if len(target_repos) != len(current_repos):
             return True
             
        for r_name, t_cfg in target_repos.items():
            if r_name not in current_repos:
                return True
            c_cfg = current_repos[r_name]
            
            # Compare key fields
            if c_cfg.get('branch') != t_cfg.get('branch'): return True
            if c_cfg.get('profile') != t_cfg.get('profile'): return True
            if c_cfg.get('custom_command') != t_cfg.get('custom_command'): return True
            
        return False

    def _show_settings(self):
        """Show the settings dialog."""
        SettingsDialog(self, self._settings, self._save_settings)


    def _apply_config(self, profile_data: dict):
        """Apply a loaded configuration to all repos."""
        repos_config = profile_data.get('repos', {})
        for card in self._repo_cards:
            name = card.get_name()
            if name in repos_config:
                self._apply_config_to_card(card, repos_config[name])
        self._log("[config] Configuración aplicada a todos los repos")

    def _apply_config_to_card(self, card, config: dict):
        """Apply a single repo config to a card."""
        branch = config.get('branch', '')
        if branch:
            card.set_branch(branch)
        profile = config.get('profile', '')
        if profile:
            card.set_profile(profile)
        custom_cmd = config.get('custom_command')
        if custom_cmd is not None:
            card.set_custom_command(custom_cmd)
        java_version = config.get('java_version')
        if java_version is not None and hasattr(card, 'selected_java_var'):
            card.selected_java_var.set(java_version)

    def _load_settings(self) -> dict:
        """Load settings from config file."""
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', CONFIG_FILE
        )
        config_path = os.path.normpath(config_path)

        if os.path.isfile(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass

        return {
            'workspace_dir': self._workspace_dir if hasattr(self, '_workspace_dir') else '',
        }

    def _save_settings(self, settings: dict):
        """Save settings to config file."""
        self._settings = settings
        config_path = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', CONFIG_FILE
        ))
        try:
            existing = {}
            if os.path.isfile(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            
            # Prevent stale in-memory active_configs from overwriting fresh disk ones
            if 'active_configs' in existing:
                settings['active_configs'] = existing['active_configs']
            
            existing.update(settings)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log(f"Error guardando config: {e}")

        self._propagate_settings_to_cards(settings)

        if settings.get('workspace_dir') and settings['workspace_dir'] != self._workspace_dir:
            self._workspace_dir = settings['workspace_dir']
            self._scan_repos()

    def _propagate_settings_to_cards(self, settings: dict):
        """Propagate updated settings (DB presets, Java versions) to all repo cards."""
        self._db_presets = settings.get('db_presets', {})
        self._global_panel.update_db_presets(self._db_presets)
        for card in self._repo_cards:
            card.update_db_presets(self._db_presets)
        self._java_versions = settings.get('java_versions', {})
        for card in self._repo_cards:
            if hasattr(card, "update_java_versions"):
                card.update_java_versions(self._java_versions)

    def _save_repo_state(self):
        """Save per-repo state (selection, custom commands, java version) to settings."""
        state = {}
        for card in self._repo_cards:
            state[card.get_name()] = {
                'selected': card.is_selected(),
                'custom_command': card.get_custom_command(),
                'java_version': card.selected_java_var.get()
            }
        self._settings['repo_state'] = state

    def _init_tray(self):
        self._tray_icon = None

    def _on_window_unmap(self, event):
        # Only handle events from the main window itself, intercept minimize
        if event.widget != self:
            return

        if self.state() == 'iconic':
            self.withdraw()
            
            # Recreate the tray icon to avoid state issues
            any_running = False
            for card in getattr(self, '_repo_cards', []):
                if getattr(card, '_status', '') in ('running', 'starting'):
                    any_running = True
                    break
                    
            color = "green" if any_running else "red"
            icon_path = os.path.join(self._app_dir, f"icon_{color}.ico")
            
            if os.path.exists(icon_path):
                try:
                    image = Image.open(icon_path)
                except Exception:
                    image = Image.new('RGB', (64, 64), color='red')
            else:
                image = Image.new('RGB', (64, 64), color='red')

            menu = pystray.Menu(
                item('Mostrar', self._restore_window, default=True),
                item('Salir', self._quit_app)
            )
            self._tray_icon = pystray.Icon("devops_manager", image, "DevOps Manager", menu)
            
            # run_detached handles the background thread natively in pystray
            self._tray_icon.run_detached()

    def _restore_window(self, icon, item):
        if self._tray_icon:
            self._tray_icon.stop()
            self._tray_icon = None
        
        # Must schedule the UI update in the main thread
        def _show():
            self.deiconify()
            self.state('normal')
        self.after(0, _show)

    def _quit_app(self, icon, item):
        if self._tray_icon:
            self._tray_icon.stop()
        self.after(0, self._on_close)

    def _check_tray_status(self):
        self.after(0, self._do_update_tray_status)

    def _do_update_tray_status(self):
        """Update tray and window icon based on running services."""
        any_running = any(
            getattr(card, '_status', '') in ('running', 'starting')
            for card in self._repo_cards
        )
        color = "green" if any_running else "red"
        icon_path = os.path.join(self._app_dir, f"icon_{color}.ico")
        if os.path.exists(icon_path):
            if self.state() != 'iconic':
                try:
                    self.iconbitmap(icon_path)
                except Exception:
                    pass
            if self._tray_icon:
                try:
                    self._tray_icon.icon = Image.open(icon_path)
                except Exception:
                    pass
        self.after(2000, self._check_tray_status)

    def _on_close(self):
        """Handle window close."""
        try:
            if hasattr(self, '_original_stdout'):
                sys.stdout = self._original_stdout
            if hasattr(self, '_original_stderr'):
                sys.stderr = self._original_stderr

            if hasattr(self, '_tray_icon') and self._tray_icon is not None:
                try:
                    self._tray_icon.stop()
                except Exception:
                    pass

            if hasattr(self, '_service_launcher'):
                self._service_launcher.stop_all(self._log)
                
            self._save_repo_state()
            self._save_settings(self._settings)
        except Exception:
            pass
        finally:
            self.destroy()
            os._exit(0)

