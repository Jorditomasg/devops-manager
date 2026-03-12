"""
main_window_presenter.py — Presenter for the main application window.
"""
from domain.ports.event_bus import bus

class MainWindowPresenter:
    """Handles UI actions and events for the main application window (MVP pattern)."""

    def __init__(self, view=None):
        self._view = view
        
    def attach_view(self, view):
        """Attach the view and subscribe to application-level events."""
        self._view = view
        self._subscribe_to_events()
        
    def _subscribe_to_events(self):
        bus.subscribe("SERVICE_STATUS_CHANGED", self._on_service_status_changed)
        
    def _on_service_status_changed(self, event_data: dict):
        """Forward service status changes to the view thread-safely."""
        if not self._view:
            return
        name = event_data.get("name")
        status = event_data.get("status")
        self._view.after(0, lambda: self._update_view_status(name, status))

    def _update_view_status(self, name: str, status: str):
        """Called on the UI thread to update status for a given service."""
        if hasattr(self._view, 'update_repo_status'):
            self._view.update_repo_status(name, status)

    def scan_workspace(self, workspace_dir: str):
        """Dispatch a workspace scan. Delegates to a Use Case in the future."""
        bus.publish("REQUEST_SCAN_WORKSPACE", {"workspace_dir": workspace_dir})
