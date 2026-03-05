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


class DevOpsManagerApp(ctk.CTk):
    """Main application window."""

    def __init__(self, workspace_dir: str = None):
        super().__init__()

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

        # Window config
        self.title("DevOps Manager")
        self.geometry("1300x900")
        self.minsize(1000, 650)

        # Theme (hardcoded dark)
        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme("blue")

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

        # Start background check loop for tray icon status
        self._check_tray_status()

    def _build_ui(self):
        """Build the main UI layout."""
        # ─── Top Bar ───
        topbar = ctk.CTkFrame(self, height=56, corner_radius=0,
                               fg_color="#0f0e26")
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        # Subtle bottom separator
        separator = ctk.CTkFrame(self, height=2, corner_radius=0,
                                  fg_color="#312e81")
        separator.pack(fill="x")

        # Logo / Title
        ctk.CTkLabel(
            topbar, text="🚀 DevOps Manager",
            font=(FONT_FAMILY, 22, "bold"),
            text_color="#e0e7ff"
        ).pack(side="left", padx=20)

        # Workspace path
        def open_workspace(event):
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

        path_label = ctk.CTkLabel(
            topbar, text=self._workspace_dir,
            font=("Consolas", 12),
            text_color="#6366f1",
            cursor="hand2"
        )
        path_label.pack(side="left", padx=10)
        path_label.bind("<Button-1>", open_workspace)
        ToolTip(path_label, "Abrir carpeta en el explorador")

        # Top-right buttons
        btn_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        btn_frame.pack(side="right", padx=15)

        configs_btn = ctk.CTkButton(
            btn_frame, text="💾 Configs", width=100, height=34,
            font=(FONT_FAMILY, 12),
            fg_color="#2e1065", hover_color="#6d28d9",
            border_width=1, border_color="#7c3aed",
            corner_radius=6,
            command=self._show_configs
        )
        configs_btn.pack(side="left", padx=3)
        ToolTip(configs_btn, "Gestionar configuraciones guardadas")

        clone_btn = ctk.CTkButton(
            btn_frame, text="➕ Clonar", width=95, height=34,
            font=(FONT_FAMILY, 12),
            fg_color="#172554", hover_color="#2563eb",
            border_width=1, border_color="#3b82f6",
            corner_radius=6,
            command=self._show_clone_dialog
        )
        clone_btn.pack(side="left", padx=3)
        ToolTip(clone_btn, "Clonar nuevo repositorio")

        rescan_btn = ctk.CTkButton(
            btn_frame, text="🔄 Rescan", width=95, height=34,
            font=(FONT_FAMILY, 12),
            fg_color="#4a3310", hover_color="#d97706",
            border_width=1, border_color="#f59e0b",
            corner_radius=6,
            command=self._scan_repos
        )
        rescan_btn.pack(side="left", padx=3)
        ToolTip(rescan_btn, "Re-escanear workspace")

        settings_btn = ctk.CTkButton(
            btn_frame, text="⚙", width=38, height=34,
            font=(FONT_FAMILY, 16),
            fg_color="#1e293b", hover_color="#475569",
            border_width=1, border_color="#64748b",
            corner_radius=6,
            command=self._show_settings
        )
        settings_btn.pack(side="left", padx=3)
        ToolTip(settings_btn, "Abrir configuración")

        log_btn = ctk.CTkButton(
            btn_frame, text="📜", width=38, height=34,
            font=(FONT_FAMILY, 16),
            fg_color="#1e293b", hover_color="#475569",
            border_width=1, border_color="#64748b",
            corner_radius=6,
            command=self._toggle_global_log
        )
        log_btn.pack(side="left", padx=3)
        ToolTip(log_btn, "Mostrar/Ocultar Log Global")

        # Global panel
        self._global_panel = GlobalPanel(
            self, db_presets=self._db_presets, log_callback=self._log
        )
        self._global_panel.pack(fill="x", padx=10, pady=(10, 6))

        # Scrollable cards area
        self._cards_scroll = ctk.CTkScrollableFrame(
            self, corner_radius=0,
            fg_color="transparent"
        )
        self._cards_scroll.pack(fill="both", expand=True, padx=10)

        # ─── Fix scroll tearing + overscroll ───
        canvas = self._cards_scroll._parent_canvas
        canvas.configure(yscrollincrement=20)

        def _on_mousewheel(event):
            """Smooth scroll with overscroll prevention."""
            # Only intercept scroll if hovering over the main cards area
            widget = self.winfo_containing(event.x_root, event.y_root)
            if not widget or not str(widget).startswith(str(self._cards_scroll)):
                return

            top, bottom = canvas.yview()
            # Content fits entirely — no scroll needed
            if top <= 0.0 and bottom >= 1.0:
                return "break"
            if event.delta:
                direction = -1 if event.delta > 0 else 1
                if direction < 0 and top <= 0.0:
                    return "break"
                if direction > 0 and bottom >= 1.0:
                    return "break"
                canvas.yview_scroll(direction * 3, "units")
            elif event.num == 4:
                if top <= 0.0:
                    return "break"
                canvas.yview_scroll(-3, "units")
            elif event.num == 5:
                if bottom >= 1.0:
                    return "break"
                canvas.yview_scroll(3, "units")
            return "break"

        canvas.bind("<MouseWheel>", _on_mousewheel)
        canvas.bind("<Button-4>", _on_mousewheel)
        canvas.bind("<Button-5>", _on_mousewheel)
        self._cards_scroll.bind_all("<MouseWheel>", _on_mousewheel)

        # Global log panel (hidden by default)
        self._global_log_frame = ctk.CTkFrame(self, fg_color="#0f0e26", height=150)
        self._global_log_frame.pack_propagate(False)
        
        log_header = ctk.CTkFrame(self._global_log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=(5, 0))
        
        ctk.CTkLabel(log_header, text="📜 Log Global", font=(FONT_FAMILY, 12, "bold"), text_color="#c7d2fe").pack(side="left")
        
        clear_btn = ctk.CTkButton(
            log_header, text="🗑 Limpiar", width=60, height=24,
            font=(FONT_FAMILY, 10),
            fg_color="#1e1b4b", hover_color="#312e81",
            border_width=1, border_color="#4338ca",
            command=self._clear_global_log
        )
        clear_btn.pack(side="right")
        
        detach_btn = ctk.CTkButton(
            log_header, text="🗗 Desacoplar", width=80, height=24,
            font=(FONT_FAMILY, 10),
            fg_color="#1e1b4b", hover_color="#312e81",
            border_width=1, border_color="#4338ca",
            command=self._detach_global_log
        )
        detach_btn.pack(side="right", padx=(0, 6))

        self._global_log_textbox = ctk.CTkTextbox(
            self._global_log_frame, font=("Consolas", 11),
            corner_radius=6, border_width=1,
            border_color="#3b3768", fg_color="#16132e",
            text_color="#e0e7ff", state="disabled"
        )
        self._global_log_textbox.pack(fill="both", expand=True, padx=10, pady=5)

        # Status bar
        self._statusbar = ctk.CTkLabel(
            self, text="Listo",
            font=(FONT_FAMILY, 11), text_color="#6366f1",
            anchor="w", height=24
        )
        self._statusbar.pack(fill="x", padx=15, pady=(0, 6))

        # Setup standard output redirection
        self._setup_global_log_redirect()

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

    def _setup_global_log_redirect(self):
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        redirector = StreamRedirector(self._log_global_stream)
        sys.stdout = redirector
        sys.stderr = redirector

    def _log_global_stream(self, string):
        if string:
            string = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', string)

        def _insert():
            # Embedded
            if hasattr(self, '_global_log_textbox') and self._global_log_textbox.winfo_exists():
                self._global_log_textbox.configure(state="normal")
                self._global_log_textbox.insert("end", string)
                
                content = self._global_log_textbox.get("1.0", "end")
                lines = content.splitlines()
                if len(lines) > 1000:
                    excess = len(lines) - 1000
                    self._global_log_textbox.delete("1.0", f"{excess + 1}.0")
                    
                self._global_log_textbox.see("end")
                self._global_log_textbox.configure(state="disabled")

            # Detached
            if getattr(self, '_detached_global_log_textbox', None) and self._detached_global_log_textbox.winfo_exists():
                self._detached_global_log_textbox.configure(state="normal")
                self._detached_global_log_textbox.insert("end", string)
                
                content = self._detached_global_log_textbox.get("1.0", "end")
                lines = content.splitlines()
                if len(lines) > 1000:
                    excess = len(lines) - 1000
                    self._detached_global_log_textbox.delete("1.0", f"{excess + 1}.0")
                    
                self._detached_global_log_textbox.see("end")
                self._detached_global_log_textbox.configure(state="disabled")

        try:
            self.after(0, _insert)
        except Exception:
            pass

    def _scan_repos(self):
        """Scan workspace for repositories."""
        self._log("Escaneando workspace...")
        self._statusbar.configure(text="Escaneando repos...")

        def _run():
            repos = detect_repos(self._workspace_dir)
            self._repos = repos

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
                on_edit_config=self._open_config_editor
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
            on_rescan=self._scan_repos
        )

    def _show_settings(self):
        """Show the settings dialog."""
        SettingsDialog(self, self._settings, self._save_settings)


    def _apply_config(self, profile_data: dict):
        """Apply a loaded configuration to all repos."""
        repos_config = profile_data.get('repos', {})
        for card in self._repo_cards:
            name = card.get_name()
            if name in repos_config:
                config = repos_config[name]
                # Apply branch
                branch = config.get('branch', '')
                if branch:
                    card.set_branch(branch)
                # Apply app profile
                profile = config.get('profile', '')
                if profile:
                    card.set_profile(profile)
                # Apply custom command
                custom_cmd = config.get('custom_command')
                if custom_cmd is not None:
                    card.set_custom_command(custom_cmd)
                # Apply java version
                java_version = config.get('java_version')
                if java_version is not None and hasattr(card, 'selected_java_var'):
                    card.selected_java_var.set(java_version)

        self._log("[config] Configuración aplicada a todos los repos")

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
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', CONFIG_FILE
        )
        config_path = os.path.normpath(config_path)

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log(f"Error guardando config: {e}")


        # Update DB presets across all components
        self._db_presets = settings.get('db_presets', {})
        self._global_panel.update_db_presets(self._db_presets)
        for card in self._repo_cards:
            card.update_db_presets(self._db_presets)
            
        # Update Java versions
        self._java_versions = settings.get('java_versions', {})
        for card in self._repo_cards:
            if hasattr(card, "update_java_versions"):
                card.update_java_versions(self._java_versions)

        # Rescan if workspace changed
        if settings.get('workspace_dir') and settings['workspace_dir'] != self._workspace_dir:
            self._workspace_dir = settings['workspace_dir']
            self._scan_repos()

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
        def _update():
            # Check if any repo is running or starting
            any_running = False
            for card in self._repo_cards:
                if card._status in ('running', 'starting'):
                    any_running = True
                    break
                    
            color = "green" if any_running else "red"
            icon_path = os.path.join(self._app_dir, f"icon_{color}.ico")
            
            if os.path.exists(icon_path):
                # Update main window icon if not withdrawn
                if self.state() != 'iconic':
                    try:
                        self.iconbitmap(icon_path)
                    except Exception:
                        pass
                
                # Update tray icon image if running
                if self._tray_icon:
                    try:
                        self._tray_icon.icon = Image.open(icon_path)
                    except Exception:
                        pass
                        
            # Loop every 2 seconds
            self.after(2000, self._check_tray_status)

        self.after(0, _update)

    def _on_close(self):
        """Handle window close."""
        if hasattr(self, '_original_stdout'):
            sys.stdout = self._original_stdout
        if hasattr(self, '_original_stderr'):
            sys.stderr = self._original_stderr

        self._service_launcher.stop_all(self._log)
        self._save_repo_state()
        self._save_settings(self._settings)
        self.destroy()
