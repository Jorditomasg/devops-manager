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
import re
import queue
import ctypes

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
from core.i18n import t
from core.service_launcher import ServiceLauncher


CONFIG_FILE = 'devops_manager_config.json'


class DevOpsManagerApp(ProfileManagerMixin, ctk.CTk):
    def __init__(self, workspace_dir: str = None, project_analyzer=None, process_manager=None):

        # Theme must be set BEFORE CTk.__init__
        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.attributes('-alpha', 0.0)  # invisible until UI is fully built — avoids white-flash

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

        from core.config_manager import get_active_group
        active_group = get_active_group()
        self._active_group_name = active_group if active_group else "Default"

        # Per-group last profile — with fallback to legacy last_profile for Default group
        lpg = self._settings.get('last_profile_by_group', {})
        if self._active_group_name not in lpg:
            # Migrate legacy last_profile for Default group
            legacy = self._settings.get('last_profile', '')
            lpg[self._active_group_name] = legacy
            self._settings['last_profile_by_group'] = lpg
        self._current_profile_name = lpg.get(self._active_group_name, '')

        self._service_launcher = ServiceLauncher()
        self._repo_cards = []
        self._repos = []
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

        # Show window now that UI is fully constructed (eliminates white-flash)
        self.update_idletasks()
        self.attributes('-alpha', 1.0)

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
        self._global_log_buffer: list = []
        self._global_log_queue: queue.Queue = queue.Queue()
        self._log_line_counts: dict = {}
        self._statusbar = ctk.CTkLabel(
            self, text=t("label.ready"),
            font=theme.font("md"), text_color=theme.C.text_accent,
            anchor="w", height=24
        )
        self._statusbar.pack(fill="x", padx=15, pady=(0, 6))
        self._setup_global_log_redirect()
        self._poll_global_log()

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
        self._path_tooltip = ToolTip(self._path_label, t("tooltip.workspace_dir", path=self._workspace_dir))

        # Group selector area — shown in topbar when >1 group exists (replaces path label)
        self._group_area = ctk.CTkFrame(topbar, fg_color="transparent")
        # (packed/unpacked dynamically by _update_topbar_group_ui)

        ctk.CTkLabel(
            self._group_area, text=t("label.group"),
            font=theme.font("base"), text_color=theme.C.text_accent
        ).pack(side="left", padx=(0, 6))

        self._topbar_group_combo = ctk.CTkComboBox(
            self._group_area, values=[""], width=200, state="readonly",
            command=self._on_group_changed,
            **theme.combo_style()
        )
        self._topbar_group_combo.pack(side="left", padx=(0, 4))

        _gear_btn = ctk.CTkButton(
            self._group_area, text="⚙", width=32,
            command=self._open_groups_dialog_topbar,
            **theme.btn_style("neutral", height="md", font_size="base")
        )
        _gear_btn.pack(side="left")
        ToolTip(_gear_btn, t("tooltip.manage_groups"))

    def _build_topbar_buttons(self, topbar):
        """Build the right-side action buttons in the top bar."""
        btn_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        btn_frame.pack(side="right", padx=15)

        btn_defs = [
            (t("btn.clone"),  95, "blue",    self._show_clone_dialog,   t("tooltip.clone_btn")),
            (t("btn.rescan"), 95, "warning", self._scan_repos,           t("tooltip.rescan_btn")),
            ("⚙",          38, "neutral", self._show_settings,        t("tooltip.settings_btn")),
            ("📋",         38, "neutral", self._detach_global_log,    t("tooltip.global_log_btn")),
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
            self._profile_combo.set(t("label.no_profile"))
            
        ToolTip(self._profile_combo, t("tooltip.profile_selector"))
        
        # Gestionar Perfiles btn (Dynamic, to the right of the selector)
        self._save_profile_btn = ctk.CTkButton(
            btn_frame, text="👤", width=38,
            command=self._show_configs,
            **theme.btn_style("neutral", height="lg", font_size="h2")
        )
        self._save_profile_btn.pack(side="left", padx=(0, 20))
        ToolTip(self._save_profile_btn, t("tooltip.manage_profiles"))

        for text, width, variant, cmd, tip in btn_defs:
            font_size = "base" if len(text) > 2 else "h2"
            s = theme.btn_style(variant, height="lg")
            s["font"] = theme.font(font_size)
            btn = ctk.CTkButton(btn_frame, text=text, width=width, command=cmd, **s)
            btn.pack(side="left", padx=3)
            ToolTip(btn, tip)

    def _open_groups_dialog_topbar(self):
        from gui.dialogs.workspace_groups import WorkspaceGroupsDialog
        WorkspaceGroupsDialog(self, on_groups_changed=self._on_groups_updated_topbar)

    def _on_groups_updated_topbar(self, groups):
        from core.config_manager import get_active_group, set_active_group
        self._update_topbar_group_ui(groups)
        active = self._topbar_group_combo.get() if hasattr(self, '_topbar_group_combo') else ""
        names = [g["name"] for g in groups]
        if active not in names and names:
            active = names[0]
            set_active_group(active)
        if active:
            self._on_group_changed(active)

    def _update_topbar_group_ui(self, groups: list):
        """Show group combo in topbar when >1 group or active group has >1 path."""
        names = [g["name"] for g in groups]
        active = self._active_group_name if self._active_group_name in names else (names[0] if names else "")
        active_group = next((g for g in groups if g["name"] == active), None)
        active_paths = len(active_group.get("paths", [])) if active_group else 0
        if len(names) > 1 or active_paths > 1:
            self._path_label.pack_forget()
            self._topbar_group_combo.configure(values=names)
            self._topbar_group_combo.set(active)
            if not self._group_area.winfo_ismapped():
                self._group_area.pack(side="left", padx=(10, 0), fill="x", expand=True)
        else:
            self._group_area.pack_forget()
            if not self._path_label.winfo_ismapped():
                self._path_label.pack(side="left", padx=10, fill="x", expand=True)

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

    def _clear_global_log(self):
        self._global_log_buffer.clear()
        self._log_line_counts.clear()
        if getattr(self, '_detached_global_log_textbox', None) and self._detached_global_log_textbox.winfo_exists():
            self._detached_global_log_textbox.configure(state="normal")
            self._detached_global_log_textbox.delete("1.0", "end")
            self._detached_global_log_textbox.configure(state="disabled")

    def _detach_global_log(self):
        """Open the global log in a separate floating window."""
        if getattr(self, '_detached_global_log_window', None) and self._detached_global_log_window.winfo_exists():
            self._detached_global_log_window.focus()
            return

        self._detached_global_log_window = ctk.CTkToplevel(self)
        self._detached_global_log_window.title(t("dialog.global_log.title"))
        self._detached_global_log_window.geometry("800x600")

        # Set window icon matching the current app icon color
        try:
            color = getattr(self, '_current_icon_color', 'red')
            _icon_path = os.path.join(self._icons_dir, f"icon_{color}.ico")
            if os.path.exists(_icon_path):
                self._detached_global_log_window.after(200, lambda p=_icon_path: self._detached_global_log_window.iconbitmap(p))
        except Exception:
            pass

        # Bring window to front
        self.after(100, lambda: self._detached_global_log_window.lift())
        self.after(110, lambda: self._detached_global_log_window.focus_force())
        
        header = ctk.CTkFrame(self._detached_global_log_window, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(6, 0))
        log_btn_s = theme.btn_style("log_action", height="sm", font_size="sm")
        ctk.CTkButton(
            header, text=t("btn.clear_log"), width=60,
            command=self._clear_global_log,
            **log_btn_s
        ).pack(side="left")

        self._detached_global_log_textbox = ctk.CTkTextbox(
            self._detached_global_log_window,
            **theme.log_textbox_style(detached=True)
        )
        self._detached_global_log_textbox.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        
        # Flush pending items so the buffer is up to date, then seed the window
        self._drain_global_log_queue()
        if self._global_log_buffer:
            self._detached_global_log_textbox.configure(state="normal")
            self._detached_global_log_textbox.insert("end", "".join(self._global_log_buffer))
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
        if string:
            self._global_log_queue.put(string)

    def _drain_global_log_queue(self):
        """Drain all pending items from the thread-safe queue into the log textboxes.
        Safe to call from the main thread at any time (e.g. before copying content)."""
        items = []
        try:
            while True:
                items.append(self._global_log_queue.get_nowait())
        except queue.Empty:
            pass
        if not items:
            return
        text = ''.join(items)
        self._global_log_buffer.append(text)
        self._insert_log_into_textbox(getattr(self, '_detached_global_log_textbox', None), text, 1000)

    def _poll_global_log(self):
        """Periodic timer (50 ms) that drains the log queue on the main thread."""
        self._drain_global_log_queue()
        try:
            self.after(100, self._poll_global_log)
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

    def _scan_repos(self, _after_scan=None):
        """Scan workspace for repositories, using workspace groups when available."""
        from core.config_manager import get_workspace_groups, get_active_group, set_workspace_groups
        groups = get_workspace_groups()
        active = get_active_group()

        # Migration: persist default group if it wasn't stored yet
        from core.config_manager import _load_config_cached, get_config_path
        if "workspace_groups" not in _load_config_cached(get_config_path()):
            set_workspace_groups(groups)

        group = next((g for g in groups if g["name"] == active), None)
        if group and group.get("paths"):
            paths = group["paths"]
        else:
            # Fallback: use first group or single workspace_dir
            paths = groups[0]["paths"] if groups and groups[0].get("paths") else [self._workspace_dir]

        self._scan_repos_for_group(paths, _after_scan=_after_scan)

    def _scan_repos_for_group(self, paths: list, _after_scan=None):
        """Scan repos across a list of paths and rebuild the UI."""
        self._log(t("log.scanning"))
        self._statusbar.configure(text=t("label.scanning_status"))

        def _run():
            if self.project_analyzer:
                repos = self.project_analyzer.detect_repos_for_group(paths)
            else:
                # Fallback: use legacy detect_repos for each path and deduplicate
                seen = set()
                repos = []
                for p in paths:
                    for r in detect_repos(p):
                        if r.path not in seen:
                            seen.add(r.path)
                            repos.append(r)
                repos.sort(key=lambda r: r.name.lower())
            self._repos = repos

            from application.use_cases.manage_services_use_case import ManageServicesUseCase
            if hasattr(self, '_manage_services_use_case'):
                self._manage_services_use_case.update_repos(repos)
            elif self.process_manager:
                self._manage_services_use_case = ManageServicesUseCase(self.process_manager, repos)
                self._manage_services_use_case.set_logger(self._log)

            def _update():
                self._build_cards(repos)
                self._statusbar.configure(text=t("label.ready"))
                self._log(t("log.repos_detected", count=len(repos), names=", ".join(r.name for r in repos)))
                if _after_scan:
                    _after_scan()

            self.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _on_group_changed(self, group_name: str):
        """Called when the user selects a different group in the topbar combo."""
        from core.config_manager import set_active_group, get_workspace_groups
        set_active_group(group_name)
        self._active_group_name = group_name
        groups = get_workspace_groups()
        group = next((g for g in groups if g["name"] == group_name), None)
        if group:
            self._scan_repos_for_group(group["paths"], _after_scan=self._reload_profiles_for_group)

    def _reload_profiles_for_group(self):
        """After group switch: load last profile for new group and refresh dropdown."""
        lpg = self._settings.get('last_profile_by_group', {})
        last = lpg.get(self._active_group_name, '')
        self._current_profile_name = last
        self._current_profile_data = {}
        self._refresh_profile_dropdown()
        if last:
            from core.profile_manager import load_profile
            data = load_profile(last, group_name=self._active_group_name)
            if data:
                self._current_profile_data = data
                self._apply_config(data, _skip_dirty_check=True)

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

            # Stagger branch loading (30ms apart)
            if card._branch_load_id:
                card.after_cancel(card._branch_load_id)
            card._branch_load_id = card.after(30 * idx, card._refresh_branch)

            # Stagger badge refresh (500ms apart, starting at 3s) so all N cards
            # don't saturate the git semaphore simultaneously on startup.
            if card._badge_timer:
                card.after_cancel(card._badge_timer)
            card._badge_timer = card.after(3000 + 500 * idx, card._refresh_badge_loop)

        # Update global panel cards and topbar group selector
        self._global_panel.set_cards(self._repo_cards)
        from core.config_manager import get_workspace_groups
        self._update_topbar_group_ui(get_workspace_groups())

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
            on_rescan=lambda: self._scan_repos(),
            on_profiles_changed=self._refresh_profile_dropdown
        )

    def _show_settings(self):
        """Show the settings dialog."""
        SettingsDialog(self, self._settings, self._save_settings,
                       on_groups_changed=self._on_groups_updated_topbar)


    def _load_settings(self) -> dict:
        """Load settings from config file (uses in-memory cache)."""
        from core.config_manager import _load_config_cached, get_config_path
        data = _load_config_cached(get_config_path())
        if data:
            return data
        return {
            'workspace_dir': self._workspace_dir if hasattr(self, '_workspace_dir') else '',
        }

    def _save_settings(self, settings: dict):
        """Save settings to config file and invalidate the in-memory cache."""
        from core.config_manager import _load_config_cached, _invalidate_config_cache, get_config_path
        self._settings = settings
        config_path = get_config_path()
        try:
            existing = dict(_load_config_cached(config_path))

            # Prevent stale in-memory from overwriting fresh disk ones
            if 'active_configs' in existing:
                settings['active_configs'] = existing['active_configs']
            if 'repo_configs' in existing:
                settings['repo_configs'] = existing['repo_configs']
            existing.update(settings)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            _invalidate_config_cache(config_path)
        except Exception as e:
            logging.error(f"Error guardando config: {e}", exc_info=True)
            self._log(f"Error guardando config: {e}")

        self._propagate_settings_to_cards(settings)

        if settings.get('workspace_dir') and settings['workspace_dir'] != self._workspace_dir:
            self._workspace_dir = settings['workspace_dir']
            self._update_path_label()
            self._path_tooltip.update_text(t("tooltip.workspace_dir", path=self._workspace_dir))
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
        from PIL import Image
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

        if self.state() == 'iconic' and self._settings.get('minimize_to_tray', True):
            self.withdraw()
            
            # Recreate the tray icon to avoid state issues
            any_running = False
            for card in getattr(self, '_repo_cards', []):
                if getattr(card, '_status', '') in ('running', 'starting'):
                    any_running = True
                    break
                    
            from PIL import Image
            import pystray
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
                for child in self.winfo_children():
                    if isinstance(child, ctk.CTkToplevel) and child.winfo_exists():
                        try:
                            child.iconbitmap(win_icon_path)
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
        import pystray
        from pystray import MenuItem as item
        running = [c for c in self._repo_cards if getattr(c, '_status', '') in ('running', 'starting')]
        selected = [c for c in self._repo_cards if c.is_selected()]
        items = []
        if selected:
            items.append(item(t("tray.start_selected", count=len(selected)), self._tray_start_selected))
        if running:
            items.append(item(t("tray.stop_running", count=len(running)), self._tray_stop_running))
        if running:
            items.append(pystray.Menu.SEPARATOR)
            for card in running:
                name = card.get_name()
                status = getattr(card, '_status', '')
                status_label = t("label.tray.starting") if status == 'starting' else t("label.tray.running")
                label = f'{name} - {status_label}'
                items.append(item(label, None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        items.append(item(t("tray.show"), self._restore_window, default=True))
        items.append(item(t("tray.quit"), self._quit_app))
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
        """Handle window close — show confirmation if services are running."""
        running_count = sum(
            1 for card in self._repo_cards
            if getattr(card, '_status', '') in ('running', 'starting')
        )
        if running_count:
            from gui.dialogs import ConfirmCloseDialog
            dlg = ConfirmCloseDialog(self, running_count)
            self.wait_window(dlg)
            if not dlg.confirmed:
                return

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

