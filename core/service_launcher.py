"""
service_launcher.py — Start/stop/restart services (Spring Boot, Angular, Docker).
"""
from __future__ import annotations
import subprocess
import os
import signal
import threading
from typing import Optional, Callable
from dataclasses import dataclass, field

LogCallback = Optional[Callable[[str], None]]


@dataclass
class RunningService:
    """Tracks a running service process."""
    name: str
    repo_path: str
    process: Optional[subprocess.Popen] = None
    thread: Optional[threading.Thread] = None
    status: str = 'stopped'  # stopped, starting, running, error
    port: Optional[int] = None
    profile: Optional[str] = None


class ServiceLauncher:
    """Manages starting/stopping of all services."""

    def __init__(self):
        self._services: dict[str, RunningService] = {}
        self._lock = threading.Lock()

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

    def start_spring_boot(self, name: str, repo_path: str, profile: str = 'default',
                          port: int = None, log: LogCallback = None,
                          status_callback: Callable = None) -> bool:
        """Start a Spring Boot service using mvnw."""
        if self.is_running(name):
            if log:
                log(f"[svc] {name} is already running")
            return False

        mvnw = os.path.join(repo_path, 'mvnw.cmd' if os.name == 'nt' else 'mvnw')
        if not os.path.isfile(mvnw):
            mvnw = 'mvn'

        cmd = [mvnw, 'spring-boot:run']
        if profile and profile != 'default':
            cmd.append(f'-Dspring-boot.run.profiles={profile}')

        svc = RunningService(name=name, repo_path=repo_path, port=port,
                             profile=profile, status='starting')
        self._services[name] = svc

        if log:
            log(f"[svc] Starting {name} (profile: {profile})...")

        if status_callback:
            status_callback(name, 'starting')

        def _run():
            try:
                process = subprocess.Popen(
                    cmd, cwd=repo_path,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
                )
                svc.process = process
                svc.status = 'running'

                if status_callback:
                    status_callback(name, 'running')

                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    line = line.strip()
                    if log:
                        log(f"[{name}] {line}")
                    # Detect startup
                    if 'Started ' in line and ' in ' in line:
                        svc.status = 'running'
                        if log:
                            log(f"[svc] ✅ {name} started successfully on port {port or '?'}")
                        if status_callback:
                            status_callback(name, 'running')

                process.wait()
                svc.status = 'stopped'
                if status_callback:
                    status_callback(name, 'stopped')
                if log:
                    log(f"[svc] {name} stopped (exit code: {process.returncode})")
            except Exception as e:
                svc.status = 'error'
                if status_callback:
                    status_callback(name, 'error')
                if log:
                    log(f"[svc] {name} error: {e}")

        thread = threading.Thread(target=_run, daemon=True, name=f'svc-{name}')
        svc.thread = thread
        thread.start()
        return True

    def start_angular(self, name: str, repo_path: str, configuration: str = '',
                      log: LogCallback = None,
                      status_callback: Callable = None) -> bool:
        """Start an Angular/Nx project."""
        if self.is_running(name):
            if log:
                log(f"[svc] {name} is already running")
            return False

        # Detect Nx vs plain Angular
        has_nx = os.path.isfile(os.path.join(repo_path, 'nx.json'))
        if has_nx:
            apps_dir = os.path.join(repo_path, 'apps')
            app_names = []
            if os.path.isdir(apps_dir):
                app_names = [d for d in os.listdir(apps_dir)
                             if os.path.isdir(os.path.join(apps_dir, d)) and not d.startswith('.')]
            main_app = app_names[0] if app_names else 'app'
            cmd = ['npx', 'nx', 'serve', main_app]
        else:
            cmd = ['npx', 'ng', 'serve']

        if configuration and configuration != 'default':
            cmd.extend([f'--configuration={configuration}'])

        svc = RunningService(name=name, repo_path=repo_path, port=4200,
                             profile=configuration, status='starting')
        self._services[name] = svc

        if log:
            log(f"[svc] Starting {name} (config: {configuration or 'default'})...")

        if status_callback:
            status_callback(name, 'starting')

        def _run():
            try:
                process = subprocess.Popen(
                    cmd, cwd=repo_path,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, shell=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
                )
                svc.process = process
                svc.status = 'running'

                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    line = line.strip()
                    if log:
                        log(f"[{name}] {line}")
                    if 'Compiled successfully' in line or 'compiled successfully' in line.lower():
                        svc.status = 'running'
                        if log:
                            log(f"[svc] ✅ {name} compiled successfully on :4200")
                        if status_callback:
                            status_callback(name, 'running')

                process.wait()
                svc.status = 'stopped'
                if status_callback:
                    status_callback(name, 'stopped')
                if log:
                    log(f"[svc] {name} stopped")
            except Exception as e:
                svc.status = 'error'
                if status_callback:
                    status_callback(name, 'error')
                if log:
                    log(f"[svc] {name} error: {e}")

        thread = threading.Thread(target=_run, daemon=True, name=f'svc-{name}')
        svc.thread = thread
        thread.start()
        return True

    def start_maven_install(self, name: str, repo_path: str,
                            log: LogCallback = None,
                            status_callback: Callable = None) -> bool:
        """Run mvn install for a library project."""
        if self.is_running(name):
            if log:
                log(f"[svc] {name} is already running")
            return False

        mvnw = os.path.join(repo_path, 'mvnw.cmd' if os.name == 'nt' else 'mvnw')
        if not os.path.isfile(mvnw):
            mvnw = 'mvn'

        cmd = [mvnw, 'install', '-DskipTests']

        svc = RunningService(name=name, repo_path=repo_path, status='starting')
        self._services[name] = svc

        if log:
            log(f"[svc] Building {name} (mvn install)...")

        if status_callback:
            status_callback(name, 'starting')

        def _run():
            try:
                process = subprocess.Popen(
                    cmd, cwd=repo_path,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1
                )
                svc.process = process

                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    line = line.strip()
                    if log:
                        log(f"[{name}] {line}")
                    if 'BUILD SUCCESS' in line:
                        if log:
                            log(f"[svc] ✅ {name} built successfully")

                process.wait()
                svc.status = 'stopped'
                if status_callback:
                    status_callback(name, 'stopped')
                if log:
                    log(f"[svc] {name} build finished (exit code: {process.returncode})")
            except Exception as e:
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
                    capture_output=True, timeout=15
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
        except Exception as e:
            # Force kill
            try:
                svc.process.kill()
            except Exception:
                pass
            svc.status = 'stopped'
            if status_callback:
                status_callback(name, 'stopped')
            if log:
                log(f"[svc] {name} force-stopped: {e}")
            return True

    def restart_service(self, name: str, repo_path: str, repo_type: str,
                        profile: str = '', port: int = None,
                        log: LogCallback = None,
                        status_callback: Callable = None) -> bool:
        """Restart a service (stop then start)."""
        self.stop_service(name, log, status_callback)

        import time
        time.sleep(1)

        if repo_type == 'spring-boot':
            return self.start_spring_boot(name, repo_path, profile, port, log, status_callback)
        elif repo_type == 'angular':
            return self.start_angular(name, repo_path, profile, log, status_callback)
        elif repo_type == 'maven-lib':
            return self.start_maven_install(name, repo_path, log, status_callback)
        return False

    def stop_all(self, log: LogCallback = None,
                 status_callback: Callable = None):
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
