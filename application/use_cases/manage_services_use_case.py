import os
from typing import Dict, Any, Callable
from domain.ports.event_bus import bus
from domain.models.repo_info import RepoInfo
from domain.models.running_service import RunningService
from infrastructure.process.process_manager import ProcessManager

class ManageServicesUseCase:
    """
    Coordinates the execution of services based on UI events.
    Decouples the GUI from the exact subprocess details.
    """
    def __init__(self, process_manager: ProcessManager, repos: list[RepoInfo]):
        self.process_manager = process_manager
        self.repos = {r.name: r for r in repos}
        self.log_callback = None
        
        bus.subscribe("REQUEST_START_SERVICE", self._on_start_request)
        bus.subscribe("REQUEST_STOP_SERVICE", self._on_stop_request)
        bus.subscribe("REQUEST_INSTALL_DEPENDENCIES", self._on_install_request)

    def update_repos(self, repos: list[RepoInfo]):
        """Update the list of known repos when a rescan occurs."""
        self.repos = {r.name: r for r in repos}
        
    def set_logger(self, log_callback: Callable[[str], None]):
        """Inject a global log callback."""
        self.log_callback = log_callback

    def _get_repo(self, name: str) -> RepoInfo:
        return self.repos.get(name)

    def _on_start_request(self, data: dict):
        name = data.get("name")
        custom_command = data.get("custom_command")
        profile = data.get("profile")
        java_home = data.get("java_home")
        
        repo = self._get_repo(name)
        if not repo:
            if self.log_callback:
                self.log_callback(f"[Error] Repo {name} not found.")
            return

        cmd = custom_command or repo.run_command
        if not cmd:
            if self.log_callback:
                self.log_callback(f"[Error] No start command defined for {name}.")
            return

        # Prepare cmd string natively
        if profile and repo.run_profile_flag:
            cmd += f" {repo.run_profile_flag}{profile}"

        # Build env (assuming simple string split for MVP)
        import shlex
        cmd_list = shlex.split(cmd) if os.name != 'nt' else cmd.split()
        
        env = None
        if java_home:
            from core.java_manager import build_java_env
            env = build_java_env(java_home)
            
        service = RunningService(
            name=name,
            repo_path=repo.path,
            profile=profile
        )

        self.process_manager.start_process(
            service=service,
            cmd=cmd_list,
            cwd=repo.path,
            env=env,
            log_callback=self.log_callback
        )

    def _on_stop_request(self, data: dict):
        name = data.get("name")
        self.process_manager.stop_process(name, log_callback=self.log_callback)

    def _on_install_request(self, data: dict):
        # We can implement install exactly like start, just listening to exit events.
        pass
