"""
app.py — Main application window for DevOps Manager.
"""
import customtkinter as ctk
import tkinter as tk
import os
import json
import sys
import logging
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
from gui import theme
from gui.app_profile import ProfileManagerMixin
from core.repo_detector import detect_repos
from core.service_launcher import ServiceLauncher


CONFIG_FILE = 'devops_manager_config.json'

# ── Profile constants ───────────────────────────────────────────
NO_PROFILE_TEXT = "- Sin Perfil -"
SAVE_PROFILE_TEXT = "💾 Guardar"
SAVE_NEW_PROFILE_TEXT = "💾 Guardar Nuevo"
SAVE_CHANGED_PROFILE_TEXT = "💾 Guardar*"

class DevOpsManagerApp(ProfileManagerMixin, ctk.CTk):
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
        except (AttributeError, OSError):
            pass

        # Determine workspace directory
        if workspace_dir:
            self._workspace_dir = workspace_dir
        else:
            self._workspace_dir = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )

        self._app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._icons_dir = os.path.join(self._app_dir, "assets", "icons")

        self._settings = self._load_settings()
        # Keep settings synced to prevent false change detection on close
        self._settings['workspace_dir'] = self._workspace_dir

        self._service_launcher = ServiceLauncher()
        self._repo_cards = []
        self._repos = []
        self._current_profile_name = self._settings.get('last_profile', "")
        self._current_profile_data = {}
        self._pending_profile_check = None
        self._applying_profile = False

        # Window config
        self.title("DevOps Manager")
        self.geometry("1300x900")
        self.minsize(1000, 650)

        # Set Window icon
        icon_path = os.path.join(self._icons_dir, "icon_red.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
            self.after(200, lambda: self.iconbitmap(icon_path))
        self._current_icon_color = "red"

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

        # Start background check loop for tray icon status
        self._check_tray_status()
        # Profile changes are detected reactively via on_change_callback on each card

    def _build_ui(self):
        """Build the main UI layout."""
        self._build_topbar()
        self._global_panel = GlobalPanel(
            self, log_callback=self._log
        )
        self._global_panel.pack(fill="x", padx=10, pady=(10, 6))
        self._setup_cards_scroll()
        self._build_global_log_panel()
        self._statusbar = ctk.CTkLabel(
            self, text="Listo",
            font=theme.font("md"), text_color=theme.C.text_accent,
            anchor="w", height=24
        )
        self._statusbar.pack(fill="x", padx=15, pady=(0, 6))
        self._setup_global_log_redirect()

    def _build_topbar(self):
        """Build the top bar with logo, path, and action buttons."""
        topbar = ctk.CTkFrame(self, height=theme.G.topbar_height, corner_radius=0, fg_color=theme.C.app)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        ctk.CTkFrame(self, height=2, corner_radius=0, fg_color=theme.C.divider).pack(fill="x")

        # Right buttons must be packed first to reserve their space before the
        # path label fills the remainder — prevents buttons being pushed off screen.
        self._build_topbar_buttons(topbar)

        ctk.CTkLabel(
            topbar, text="🚀 DevOps Manager",
            font=theme.font("h1", bold=True), text_color=theme.C.text_primary
        ).pack(side="left", padx=20)

        self._path_label = ctk.CTkLabel(
            topbar, text=self._workspace_dir,
            font=theme.font("base", mono=True), text_color=theme.C.text_accent,
            cursor="hand2", anchor="w"
        )
        self._path_label.pack(side="left", padx=10, fill="x", expand=True)
        self._path_label.bind("<Button-1>", lambda e: self._open_workspace())
        self._path_label.bind("<Configure>", self._update_path_label)
        ToolTip(self._path_label, f"📁 {self._workspace_dir}\nAbrir en el explorador")

    def _build_topbar_buttons(self, topbar):
        """Build the right-side action buttons in the top bar."""
        btn_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        btn_frame.pack(side="right", padx=15)

        btn_defs = [
            ("➕ Clonar",  95, "blue",    self._show_clone_dialog,   "Clonar nuevo repositorio"),
            ("🔄 Rescan",  95, "warning", self._scan_repos,           "Re-escanear workspace"),
            ("⚙",          38, "neutral", self._show_settings,        "Abrir configuración"),
            ("📜",         38, "neutral", self._detach_global_log,    "Abrir Log Global en Ventana"),
        ]

        profiles = self._profile_dropdown_values()

        # Profile Dropdown
        combo_kw = theme.combo_style(height="lg")
        combo_kw["border_color"] = theme.C.profile_accent
        combo_kw["button_color"] = theme.C.profile_accent
        self._profile_combo = ctk.CTkComboBox(
            btn_frame, values=profiles, width=160,
            command=self._on_profile_dropdown_change,
            **combo_kw
        )
        self._profile_combo.pack(side="left", padx=(0, 10))
        if self._current_profile_name in profiles:
            self._profile_combo.set(self._current_profile_name)
        else:
            self._profile_combo.set(NO_PROFILE_TEXT)
            
        ToolTip(self._profile_combo, "Seleccionar Perfil de Workspace")
        
        # Gestionar Perfiles btn (Dynamic, to the right of the selector)
        self._save_profile_btn = ctk.CTkButton(
            btn_frame, text="👤", width=38,
            command=self._show_configs,
            **theme.btn_style("neutral", height="lg", font_size="h2")
        )
        self._save_profile_btn.pack(side="left", padx=(0, 20))
        ToolTip(self._save_profile_btn, "Gestionar Perfiles")

        for text, width, variant, cmd, tip in btn_defs:
            font_size = "base" if len(text) > 2 else "h2"
            s = theme.btn_style(variant, height="lg")
            s["font"] = theme.font(font_size)
            btn = ctk.CTkButton(btn_frame, text=text, width=width, command=cmd, **s)
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
        self._global_log_frame = ctk.CTkFrame(self, fg_color=theme.C.app, height=150)
        self._global_log_frame.pack_propagate(False)

        log_header = ctk.CTkFrame(self._global_log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=(5, 0))

        ctk.CTkLabel(log_header, text="📜 Log Global", font=theme.font("base", bold=True), text_color=theme.C.text_secondary).pack(side="left")

        log_btn_s = theme.btn_style("log_action", height="sm", font_size="sm")
        ctk.CTkButton(log_header, text="🗗 Desacoplar", width=80, command=self._detach_global_log, **log_btn_s).pack(side="right", padx=(0, 6))
        ctk.CTkButton(log_header, text="🗑 Limpiar", width=60, command=self._clear_global_log, **log_btn_s).pack(side="right")

        self._global_log_textbox = ctk.CTkTextbox(
            self._global_log_frame, state="disabled",
            **theme.log_textbox_style()
        )
        self._global_log_textbox.pack(fill="both", expand=True, padx=10, pady=5)
        self._log_line_counts: dict = {}

    def _log(self, message: str):
        """Central log function."""
        print(message)
        if hasattr(self, '_statusbar') and len(message) < 100:
            def _update_statusbar():
                try:
                    self._statusbar.configure(text=message)
                except Exception:
                    pass
            try:
                self.after(0, _update_statusbar)
            except Exception:
                pass

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
        
        header = ctk.CTkFrame(self._detached_global_log_window, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(6, 0))
        log_btn_s = theme.btn_style("log_action", height="sm", font_size="sm")
        ctk.CTkButton(
            header, text="🗑 Limpiar", width=60,
            command=self._clear_global_log,
            **log_btn_s
        ).pack(side="left")

        self._detached_global_log_textbox = ctk.CTkTextbox(
            self._detached_global_log_window,
            **theme.log_textbox_style(detached=True)
        )
        self._detached_global_log_textbox.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        
        # Copy current content
        current_logs = self._global_log_textbox.get("1.0", "end")
        self._detached_global_log_textbox.insert("end", current_logs)
        self._detached_global_log_textbox.configure(state="disabled")
        self._detached_global_log_textbox.see("end")

    def _update_path_label(self, event=None):
        """Truncate workspace path with ellipsis to fit available label width."""
        if getattr(self, '_updating_path_label', False):
            return
        if not hasattr(self, '_path_label'):
            return
        available_w = self._path_label.winfo_width()
        if available_w <= 1:
            return
        full_text = self._workspace_dir
        self._updating_path_label = True
        try:
            import tkinter.font as tkfont
            f = tkfont.Font(font=theme.font("base", mono=True))
            if f.measure(full_text) <= available_w - 10:
                self._path_label.configure(text=full_text)
                return
            ellipsis = "..."
            ell_w = f.measure(ellipsis)
            for i in range(len(full_text), 0, -1):
                if f.measure(full_text[:i]) + ell_w <= available_w - 10:
                    self._path_label.configure(text=full_text[:i] + ellipsis)
                    return
            self._path_label.configure(text=ellipsis)
        except Exception:
            pass
        finally:
            self._updating_path_label = False

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
            logging.error(f"Error al abrir carpeta: {e}", exc_info=True)
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
        except tk.TclError:
            pass

    def _insert_log_into_textbox(self, textbox, text: str, max_lines: int):
        """Thread-safe helper to insert text into a CTkTextbox, trimming to max_lines."""
        if not textbox or not textbox.winfo_exists():
            return
        textbox.configure(state="normal")
        textbox.insert("end", text)
        count = self._log_line_counts.get(id(textbox), 0) + 1
        if count > max_lines:
            excess = count - max_lines
            textbox.delete("1.0", f"{excess + 1}.0")
            count = max_lines
        self._log_line_counts[id(textbox)] = count
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
            card._branch_load_id = card.after(30 * idx, card._refresh_branch)

        # Update global panel
        self._global_panel.set_cards(self._repo_cards)

        # Re-apply active profile after (re)building cards.
        # _skip_dirty_check=True because branches are still loading async at this point;
        # the per-card _trigger_change_callback will fire once they settle.
        if self._current_profile_data:
            self._apply_config(self._current_profile_data, _skip_dirty_check=True)

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
            log_callback=self._log,
            on_profile_loaded=self._apply_config,
            on_rescan=self._scan_repos,
            on_profiles_changed=self._refresh_profile_dropdown
        )

    def _show_settings(self):
        """Show the settings dialog."""
        SettingsDialog(self, self._settings, self._save_settings)


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
            except (json.JSONDecodeError, OSError):
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
            
            # Prevent stale in-memory from overwriting fresh disk ones
            if 'active_configs' in existing:
                settings['active_configs'] = existing['active_configs']
            if 'repo_configs' in existing:
                settings['repo_configs'] = existing['repo_configs']
            existing.update(settings)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Error guardando config: {e}", exc_info=True)
            self._log(f"Error guardando config: {e}")

        self._propagate_settings_to_cards(settings)

        if settings.get('workspace_dir') and settings['workspace_dir'] != self._workspace_dir:
            self._workspace_dir = settings['workspace_dir']
            self._scan_repos()

    def _propagate_settings_to_cards(self, settings: dict):
        """Propagate updated settings (Java versions) to all repo cards."""
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
        self._tray_icon_images = {}
        for color in ("red", "green"):
            icon_path = os.path.join(self._icons_dir, f"icon_{color}.ico")
            try:
                img = Image.open(icon_path) if os.path.exists(icon_path) else Image.new('RGB', (64, 64), color=color)
            except Exception:
                img = Image.new('RGB', (64, 64), color=color)
            self._tray_icon_images[color] = img

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
            image = self._tray_icon_images.get(color, Image.new('RGB', (64, 64), color='red'))

            menu = pystray.Menu(self._build_tray_menu)
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
            self.attributes('-alpha', 1.0)
            self.state('normal')
            self.lift()
            self.focus_force()
        self.after(0, _show)

    def _quit_app(self, icon, item):
        if self._tray_icon:
            self._tray_icon.stop()
        self.after(0, self._on_close)

    def _check_tray_status(self):
        self.after(0, self._do_update_tray_status)

    def _do_update_tray_status(self):
        """Update tray icon color and tooltip based on running services."""
        running = [
            card for card in self._repo_cards
            if getattr(card, '_status', '') in ('running', 'starting')
        ]
        color = "green" if running else "red"
        if color != self._current_icon_color:
            self._current_icon_color = color
            win_icon_path = os.path.join(self._icons_dir, f"icon_{color}.ico")
            if os.path.exists(win_icon_path):
                try:
                    self.iconbitmap(win_icon_path)
                except Exception:
                    pass
        if self._tray_icon:
            img = self._tray_icon_images.get(color)
            if img:
                try:
                    self._tray_icon.icon = img
                except (OSError, ValueError):
                    pass
            try:
                self._tray_icon.title = f"DevOps Manager — {len(running)}/{len(self._repo_cards)} corriendo"
            except (OSError, ValueError):
                pass
        self.after(5000, self._check_tray_status)

    def _build_tray_menu(self):
        """Build the tray context menu dynamically at open time."""
        running = [c for c in self._repo_cards if getattr(c, '_status', '') in ('running', 'starting')]
        selected = [c for c in self._repo_cards if c.is_selected()]
        items = []
        if selected:
            items.append(item(f'▶  Iniciar seleccionados ({len(selected)})', self._tray_start_selected))
        if running:
            items.append(item(f'■  Parar todos corriendo ({len(running)})', self._tray_stop_running))
        if running:
            items.append(pystray.Menu.SEPARATOR)
            for card in running:
                name = card.get_name()
                status = getattr(card, '_status', '')
                label = f'● {name}' + (' (arrancando)' if status == 'starting' else '')
                items.append(item(label, None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        items.append(item('Mostrar', self._restore_window, default=True))
        items.append(item('Salir', self._quit_app))
        return items

    def _tray_start_selected(self, icon, menu_item):
        self.after(0, self._do_tray_start_selected)

    def _do_tray_start_selected(self):
        for card in list(self._repo_cards):
            if card.is_selected():
                card.do_start()

    def _tray_stop_running(self, icon, menu_item):
        self.after(0, self._do_tray_stop_running)

    def _do_tray_stop_running(self):
        for card in list(self._repo_cards):
            if getattr(card, '_status', '') in ('running', 'starting'):
                card.do_stop()

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
                except (RuntimeError, AttributeError):
                    pass

            if hasattr(self, '_service_launcher'):
                self._service_launcher.stop_all(self._log)
                
            self._save_repo_state()
            self._save_settings(self._settings)
        except Exception as e:
            logging.error(f"Error durante el cierre de la aplicación: {e}", exc_info=True)
        finally:
            self.destroy()
            os._exit(0)

