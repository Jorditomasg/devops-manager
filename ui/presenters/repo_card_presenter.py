"""
repo_card_presenter.py — Presenter for individual repository cards.
"""
from typing import Optional
from domain.models.repo_info import RepoInfo
from domain.ports.event_bus import bus

class RepoCardPresenter:
    def __init__(self, repo_info: RepoInfo, view=None):
        self.repo_info = repo_info
        self._view = view
        
    def attach_view(self, view):
        self._view = view
        # We could filter events to only this repo_info.name
        
    def on_start_clicked(self):
        """Handles the user clicking start on a repository."""
        # Dispatch a command or event to start this repo
        bus.publish("REQUEST_START_SERVICE", {"name": self.repo_info.name})

    def on_stop_clicked(self):
        """Handles the user clicking stop."""
        bus.publish("REQUEST_STOP_SERVICE", {"name": self.repo_info.name})
        
    def on_install_clicked(self, skip_if_installed=False):
        bus.publish("REQUEST_INSTALL_DEPENDENCIES", {
            "name": self.repo_info.name, 
            "skip_if_installed": skip_if_installed
        })
