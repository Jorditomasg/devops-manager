from typing import Callable
from domain.models.repo_info import RepoInfo
from infrastructure.process.process_manager import ProcessManager


class ManageServicesUseCase:
    """
    Tracks known repos and exposes a shared logger to infrastructure.
    GUI calls service operations directly; this class provides the data bridge.
    """
    def __init__(self, process_manager: ProcessManager, repos: list[RepoInfo]):
        self.process_manager = process_manager
        self.repos = {r.name: r for r in repos}
        self.log_callback = None

    def update_repos(self, repos: list[RepoInfo]):
        """Update the list of known repos when a rescan occurs."""
        self.repos = {r.name: r for r in repos}

    def set_logger(self, log_callback: Callable[[str], None]):
        """Inject a global log callback."""
        self.log_callback = log_callback
