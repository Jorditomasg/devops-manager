"""
service_launcher.py — Start/stop/restart services (Spring Boot, Angular, Docker).
"""
from __future__ import annotations
import subprocess
import os
import signal
import logging
import threading
import atexit
from domain.models.running_service import RunningService
from typing import Optional, Callable
from dataclasses import dataclass, field

LogCallback = Optional[Callable[[str], None]]


class ServiceLauncher:
    """Manages starting/stopping of all services."""

    def __init__(self):
        self._services: dict[str, RunningService] = {}
        self._lock = threading.Lock()
        atexit.register(self.stop_all)

    def get_service(self, name: str) -> Optional[RunningService]:
        """Get a running service by name."""
        return self._services.get(name)

    def get_all_services(self) -> dict[str, RunningService]:
        """Get all tracked services."""
        return dict(self._services)

    def is_running(self, name: str) -> bool:
        """Check if a service is running."""
        svc = self._services.get(name)
        if svc and svc.process:
            return svc.process.poll() is None
        return False


    def start_generic_install(self, name: str, repo_path: str, cmd_str: str,
                              log: LogCallback = None,
                              status_callback: Callable = None, java_home: str = "") -> bool:
        """Run a generic install command as a service (blocking or long-running)."""
        if self.is_running(name):
            return False

        if not cmd_str:
            if log:
                log(f"[svc] No install command defined for {name}")
            return False

        if not os.path.isdir(repo_path):
            if log:
                log(f"[svc] {name}: repo path is not a valid directory: {repo_path}")
            return False

        # Build environment - only use JAVA_HOME if supplied
        env = None
        if java_home:
            from core.java_manager import build_java_env
            env = build_java_env(java_home)

        svc = RunningService(name=name, repo_path=repo_path, port=0, status='starting')
        self._services[name] = svc

        if log:
            log(f"[svc] Running installation for {name}: {cmd_str}")
            if java_home:
                log(f"[svc] Using JAVA_HOME: {java_home}")
        if status_callback:
            status_callback(name, 'starting')

        def _run():
            try:
                use_shell = True
                process = subprocess.Popen(
                    cmd_str, cwd=repo_path, env=env, shell=use_shell,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    creationflags=(getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)) if os.name == 'nt' else 0
                )
                svc.process = process

                for raw_line in iter(process.stdout.readline, b''):
                    line = raw_line.decode('utf-8', errors='replace').strip()
                    if line and log:
                        log(line)

                try:
                    process.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    if log:
                        log(f"[svc] ⚠️ {name} install timed out after 10 min, killing process")
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except OSError:
                        pass
                svc.status = 'stopped'
                if status_callback:
                    status_callback(name, 'stopped')
                if log:
                    if process.returncode == 0:
                        log(f"[svc] ✅ {name} installed successfully")
                    else:
                        log(f"[svc] {name} installation finished with exit code: {process.returncode}")
            except (subprocess.SubprocessError, OSError) as e:
                logging.error(f"System error starting service {name}: {e}", exc_info=True)
                svc.status = 'error'
                if status_callback:
                    status_callback(name, 'error')
                if log:
                    log(f"[svc] {name} system error: {e}")
            except Exception as e:
                logging.error(f"Unexpected error starting service {name}: {e}", exc_info=True)
                svc.status = 'error'
                if status_callback:
                    status_callback(name, 'error')
                if log:
                    log(f"[svc] {name} error: {e}")

        thread = threading.Thread(target=_run, daemon=True, name=f'svc-{name}')
        svc.thread = thread
        thread.start()
        return True

    def stop_service(self, name: str, log: LogCallback = None,
                     status_callback: Callable = None) -> bool:
        """Stop a running service."""
        svc = self._services.get(name)
        if not svc or not svc.process:
            if log:
                log(f"[svc] {name} is not running")
            return False

        try:
            if log:
                log(f"[svc] Stopping {name}...")

            if os.name == 'nt':
                # Windows: use taskkill to kill the entire process tree
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(svc.process.pid)],
                    capture_output=True, timeout=15,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
            else:
                os.killpg(os.getpgid(svc.process.pid), signal.SIGTERM)

            svc.process.wait(timeout=10)
            svc.status = 'stopped'
            if status_callback:
                status_callback(name, 'stopped')
            if log:
                log(f"[svc] {name} stopped")
            return True
        except (subprocess.SubprocessError, OSError) as e:
            logging.error(f"System error stopping service {name}: {e}", exc_info=True)
            # Force kill
            try:
                svc.process.kill()
            except OSError:
                pass
            svc.status = 'stopped'
            if status_callback:
                status_callback(name, 'stopped')
            if log:
                log(f"[svc] {name} force-stopped: {e}")
            return True


    def stop_all(self, log: LogCallback = None,
                 status_callback: Callable = None) -> None:
        """Stop all running services."""
        for name in list(self._services.keys()):
            if self.is_running(name):
                self.stop_service(name, log, status_callback)

    def get_status(self, name: str) -> str:
        """Get the status of a service."""
        svc = self._services.get(name)
        if not svc:
            return 'stopped'
        if svc.process and svc.process.poll() is None:
            return svc.status
        return 'stopped'
