from dataclasses import dataclass
from typing import Optional
import subprocess
import threading

# Note: Keeping subprocess and threading here temporarily, but ideally
#       these should be abstracted behind ports (e.g., IProcessContext) in a pure domain.
#       For now, we just move the dataclass out of service_launcher.

@dataclass
class RunningService:
    """Tracks a running service process."""
    name: str
    repo_path: str
    process: Optional[subprocess.Popen] = None
    thread: Optional[threading.Thread] = None
    status: str = 'stopped'  # running, starting, stopped, error
    port: Optional[int] = None
    profile: Optional[str] = None
