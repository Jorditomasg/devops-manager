"""
process_manager.py — Universal, safe Process/Subprocess management.
Handles process creation, tracking, and clean process tree termination.
"""
import subprocess
import os
import signal
import logging
import threading
import atexit
import time
from typing import Optional, Callable, Dict
from domain.models.running_service import RunningService
from domain.exceptions import ProcessExecutionError
from domain.ports.event_bus import bus

LogCallback = Optional[Callable[[str], None]]

class ProcessManager:
    """
    Manages robust execution and termination of system processes.
    Subscribes to events or is called by applicaton services.
    Ensures no zombie processes are left on exit.
    """
    def __init__(self):
        self._services: Dict[str, RunningService] = {}
        self._lock = threading.Lock()
        atexit.register(self.stop_all)

    def register_service(self, service: RunningService):
        with self._lock:
            self._services[service.name] = service

    def get_service(self, name: str) -> Optional[RunningService]:
        with self._lock:
            return self._services.get(name)

    def is_running(self, name: str) -> bool:
        svc = self.get_service(name)
        if svc and svc.process:
            return svc.process.poll() is None
        return False

    def start_process(self, 
                     service: RunningService, 
                     cmd: list, 
                     cwd: str, 
                     env: Optional[dict] = None, 
                     log_callback: LogCallback = None) -> bool:
        """Starts a process asynchronously and streams its output securely."""
        if self.is_running(service.name):
            if log_callback:
                log_callback(f"[sys] {service.name} is already running.")
            return False

        self.register_service(service)
        service.status = 'starting'
        bus.publish("SERVICE_STATUS_CHANGED", {"name": service.name, "status": "starting"})

        thread = threading.Thread(
            target=self._process_run_loop, 
            args=(service, cmd, cwd, env, log_callback),
            daemon=True, 
            name=f"proc-{service.name}"
        )
        service.thread = thread
        thread.start()
        
        return True

    def _process_run_loop(self, service: RunningService, cmd: list, cwd: str, env: Optional[dict], log_callback: LogCallback):
        try:
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) if os.name == 'nt' else 0
            
            process = subprocess.Popen(
                cmd, cwd=cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                shell=(os.name == 'nt' and cmd[0] in ('npm', 'npx', 'mvn', 'mvnw.cmd')),
                creationflags=creationflags
            )
            
            service.process = process
            service.status = 'running'
            bus.publish("SERVICE_STATUS_CHANGED", {"name": service.name, "status": "running"})

            self._stream_process_output(process, service, log_callback)

            process.wait()
            service.status = 'stopped'
            bus.publish("SERVICE_STATUS_CHANGED", {"name": service.name, "status": "stopped", "exit_code": process.returncode})
            
            if log_callback:
                log_callback(f"[sys] {service.name} process exited (code {process.returncode})")

        except (subprocess.SubprocessError, OSError) as e:
            logging.error(f"Error in process {service.name}: {e}", exc_info=True)
            service.status = 'error'
            bus.publish("SERVICE_STATUS_CHANGED", {"name": service.name, "status": "error", "error": str(e)})
            if log_callback:
                log_callback(f"[sys] Error starting {service.name}: {e}")

    def _stream_process_output(self, process, service: RunningService, log_callback: LogCallback):
        for raw_line in iter(process.stdout.readline, b''):
            line = raw_line.decode('utf-8', errors='replace').strip()
            if line and log_callback:
                log_callback(f"[{service.name}] {line}")

    def stop_process(self, name: str, log_callback: LogCallback = None) -> bool:
        """Stops a process safely, cleaning up process trees."""
        svc = self.get_service(name)
        if not svc or not svc.process:
            if log_callback:
                log_callback(f"[sys] {name} is not running.")
            return False

        if log_callback:
            log_callback(f"[sys] Stopping {name}...")

        try:
            if os.name == 'nt':
                # Windows taskkill forcefully kills process tree
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(svc.process.pid)],
                    capture_output=True, timeout=10,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
            else:
                # Unix pgid term
                os.killpg(os.getpgid(svc.process.pid), signal.SIGTERM)

            svc.process.wait(timeout=5)
            svc.status = 'stopped'
            bus.publish("SERVICE_STATUS_CHANGED", {"name": name, "status": "stopped"})
            return True
            
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout stopping process {name}, force killing", exc_info=True)
            # Force kill if term failed or hung
            try:
                svc.process.kill()
            except OSError:
                pass
            svc.status = 'error'
            bus.publish("SERVICE_STATUS_CHANGED", {"name": name, "status": "error", "error": "Force killed on timeout."})
            return False
            
        except (subprocess.SubprocessError, OSError) as e:
            logging.error(f"Error stopping process {name}: {e}", exc_info=True)
            if log_callback:
                log_callback(f"[sys] Error stopping {name}: {e}")
            svc.status = 'error'
            bus.publish("SERVICE_STATUS_CHANGED", {"name": name, "status": "error", "error": str(e)})
            return False

    def stop_all(self):
        """Emergency cleanup method."""
        with self._lock:
            names = list(self._services.keys())
        for name in names:
            if self.is_running(name):
                self.stop_process(name)
