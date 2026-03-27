"""_docker.py — Docker Compose management mixin for RepoCard."""
from __future__ import annotations
import os
import threading
from gui.constants import DOCKER_POLL_MS
from gui import theme


class DockerMixin:
    """Mixin providing docker-compose profile management and status polling."""

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

    def _prefetch_docker_status(self):
        """Pre-fetch docker container status in background before the expand panel is built."""
        def _run():
            from core.db_manager import parse_compose_services, get_compose_service_status
            for dc_file in self._repo.docker_compose_files:
                try:
                    services = parse_compose_services(dc_file)
                    status_map = get_compose_service_status(dc_file)
                    running = sum(1 for s in status_map.values() if s == "running")
                    self._docker_status_cache[dc_file] = (running, len(services))
                except Exception:
                    pass
            # If the expand panel was already built while we were fetching, update buttons now
            if self._expand_panel_built and self._docker_compose_buttons:
                self.after(0, self._apply_cached_docker_status)
        threading.Thread(target=_run, daemon=True).start()

    def _apply_cached_docker_status(self):
        """Apply cached docker status to already-built buttons (main thread)."""
        for dc_file, btn in self._docker_compose_buttons.items():
            if dc_file in self._docker_status_cache:
                running, total = self._docker_status_cache[dc_file]
                dc_name = self._format_compose_name(os.path.basename(dc_file))
                text = f"🐳 {dc_name.title()} [{running}/{total}]"
                self._update_compose_btn(btn, text, running, dc_file)

    def _update_compose_counts_now(self):
        """Trigger an immediate background poll of all docker compose file statuses."""
        if not self._expand_panel_built or not self._docker_compose_buttons:
            return
        threading.Thread(
            target=self._poll_compose_status,
            args=(self._compose_stop_event, DOCKER_POLL_MS // 1000),
            daemon=True,
        ).start()

    def _poll_compose_status(self, event: threading.Event, timeout: int):
        """Poll docker container status for all active compose files once."""
        from core.db_manager import parse_compose_services, get_compose_service_status
        total_running = 0
        for dc_file, btn in self._docker_compose_buttons.items():
            try:
                running = self._poll_single_compose_file(dc_file, btn, parse_compose_services, get_compose_service_status)
                if dc_file in self._active_compose_files:
                    total_running += running
            except Exception:
                pass
        if self._active_compose_files:
            self.after(0, lambda r=total_running: self._update_docker_global_status(r))

    def _poll_single_compose_file(self, dc_file, btn, parse_fn, status_fn) -> int:
        """Poll one compose file, schedule its button update only if status changed."""
        services = parse_fn(dc_file)
        status_map = status_fn(dc_file)
        running = sum(1 for s in status_map.values() if s == "running")
        new_status = (running, len(services))
        prev_status = self._docker_status_cache.get(dc_file)
        self._docker_status_cache[dc_file] = new_status
        # Only update UI when the counts actually changed
        if prev_status != new_status:
            dc_name = self._format_compose_name(os.path.basename(dc_file))
            text = f"🐳 {dc_name.title()} [{running}/{len(services)}]"
            self.after(0, lambda b=btn, t=text, r=running, f=dc_file: self._update_compose_btn(b, t, r, f))
        return running

    def _format_compose_name(self, basename: str) -> str:
        """Shorten a docker-compose filename to a display name."""
        if basename == 'docker-compose.yml':
            return 'docker-compose'
        if basename.startswith('docker-compose.'):
            return basename.replace('docker-compose.', '').replace('.yml', '')
        return basename

    def _update_compose_btn(self, btn, text: str, running: int, dc_file: str) -> None:
        """Update a compose button's text and border color (main thread)."""
        if not btn.winfo_exists():
            return
        btn.configure(text=text)
        if running > 0:
            btn.configure(border_color=theme.C.docker_border_running)
        elif dc_file in self._active_compose_files:
            btn.configure(border_color=theme.C.docker_border_active)
        else:
            btn.configure(border_color=theme.C.docker_border_stopped)

    def _update_docker_global_status(self, total_running: int) -> None:
        """Update the repo card status label based on running docker services."""
        if not self.winfo_exists():
            return
        # Cancel any pending log-flash revert so it doesn't override the status color
        if hasattr(self, '_log_flash_timer') and self._log_flash_timer:
            self.after_cancel(self._log_flash_timer)
            self._log_flash_timer = None
        if total_running > 0:
            self._status_label.configure(text="🔴", text_color=theme.C.status_running)
            self._status_text.configure(text=f"Ejecutando ({total_running} servicios)", text_color=theme.C.status_running)
            self._status = "running"
        else:
            self._status_label.configure(text="🔴", text_color=theme.C.status_stopped)
            self._status_text.configure(text="Detenido", text_color=theme.C.text_placeholder)
            self._status = "stopped"
        self._update_button_visibility()

    def _start_compose_status_thread(self):
        """Background thread to poll docker container status for active compose files."""
        def _loop():
            while self._compose_status_thread_running and self.winfo_exists():
                self._poll_compose_status(self._compose_stop_event, DOCKER_POLL_MS // 1000)
                self._compose_stop_event.wait(timeout=DOCKER_POLL_MS // 1000)
                if self._compose_stop_event.is_set():
                    break

        threading.Thread(target=_loop, daemon=True).start()

    def _start_docker_services(self):
        """Start active docker-compose services.
        Falls back to all repo compose files if none are explicitly active."""
        def _run():
            from core.db_manager import docker_compose_up
            files_to_start = self._active_compose_files or set(getattr(self._repo, 'docker_compose_files', []))
            if not files_to_start:
                if self._log:
                    self._log(f"[{self._repo.name}] ⚠ No hay ficheros docker-compose configurados.")
                return
            for dc_file in files_to_start:
                svcs = self._docker_profile_services.get(dc_file, [])
                if svcs:
                    docker_compose_up(dc_file, services=svcs, log=self._log)
                else:
                    docker_compose_up(dc_file, log=self._log)
            # Poll immediately and again at 3 s / 7 s to catch containers reaching 'running'
            self.after(0, self._update_compose_counts_now)
            self.after(3000, self._update_compose_counts_now)
            self.after(7000, self._update_compose_counts_now)
        threading.Thread(target=_run, daemon=True).start()
