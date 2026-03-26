"""_base.py — RepoCard composed from focused mixins."""
from __future__ import annotations
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
import customtkinter as ctk

from gui.repo_card._log import LogMixin
from gui.repo_card._git import GitMixin
from gui.repo_card._config import ConfigMixin
from gui.repo_card._docker import DockerMixin
from gui.repo_card._actions import ActionsMixin
from gui.repo_card._header import HeaderMixin
from gui.repo_card._expand_panel import ExpandPanelMixin
from gui.tooltip import ToolTip
from gui import theme
from gui.constants import GIT_BADGE_SEMAPHORE_COUNT

class RepoCard(
    HeaderMixin,
    ExpandPanelMixin,
    LogMixin,
    GitMixin,
    ConfigMixin,
    DockerMixin,
    ActionsMixin,
    ctk.CTkFrame,
):
    """Accordion repo card widget.

    All logic lives in focused mixins; this class owns __init__, destroy,
    and the public getter/setter API.
    """

    _GIT_BADGE_SEMAPHORE = threading.Semaphore(GIT_BADGE_SEMAPHORE_COUNT)

    def __init__(self, parent, repo_info, service_launcher,
                 java_versions=None, log_callback=None, on_edit_config=None, on_change_callback=None, **kwargs):
        super().__init__(parent, corner_radius=theme.G.corner_card, border_width=theme.G.border_width,
                         border_color=theme.C.card_border,
                         fg_color=theme.C.card, **kwargs)

        self._repo = repo_info
        self._launcher = service_launcher
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
        self._docker_status_cache: dict = {}        # dc_file -> (running, total)
        self._compose_status_thread_running = False
        self._compose_stop_event = threading.Event()
        self._badge_timer = None
        # Bounded pool for user-triggered actions (start/stop/pull/install/clean).
        # max_workers=3: handles the common case of concurrent ops without unbounded growth.
        self._action_pool = ThreadPoolExecutor(
            max_workers=3,
            thread_name_prefix=f'act-{repo_info.name[:12]}',
        )
        self._log_line_count = [0]          # mutable list ref for O(1) log trimming
        self._detached_log_line_count = [0]
        self._pre_panel_log_buffer: list = []   # log lines buffered before expand panel exists
        self._expand_panel_built = False
        self._pending_profile = None    # profile value set before expand panel exists
        self._pending_custom_command = ''  # custom command set before expand panel exists

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

        if getattr(self._repo, 'docker_compose_files', None):
            self.after(500, self._prefetch_docker_status)

    def destroy(self):
        """Cancel pending timers and stop background threads before destroying."""
        self._action_pool.shutdown(wait=False)
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

    # ── Public getters / setters ────────────────────────────────────────────

    def is_selected(self) -> bool:
        return self.selected_var.get()

    def set_selected(self, value: bool):
        self.selected_var.set(value)

    def set_branch(self, branch: str) -> bool:
        def _run():
            from core.git_manager import has_branch, get_current_branch
            if get_current_branch(self._repo.path) == branch:
                return  # Already on target branch — skip checkout and dirty trigger
            if has_branch(self._repo.path, branch):
                self._on_branch_change(branch)
        threading.Thread(target=_run, daemon=True).start()
        return True

    def set_profile(self, profile):
        self._pending_profile = profile  # always persist regardless of widget state
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

    def set_custom_command(self, cmd: str):
        """Set custom command (from persisted settings)."""
        self._pending_custom_command = cmd  # always persist regardless of widget state
        if hasattr(self, '_cmd_entry') and cmd:
            self._cmd_entry.delete(0, "end")
            self._cmd_entry.insert(0, cmd)
            self._update_header_hints()

    def get_custom_command(self) -> str:
        """Get custom command if set."""
        if hasattr(self, '_cmd_entry'):
            return self._cmd_entry.get().strip()
        return self._pending_custom_command

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
        # Expand panel not built yet — return the pending value set by set_profile()
        return self._pending_profile if self._pending_profile is not None else ''

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
                    if self._log:
                        self._log(f"Deteniendo compose inactivo: {os.path.basename(f)}")
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
