from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class RepoInfo:
    """Holds all detected metadata for a single repository."""
    name: str
    path: str
    repo_type: str

    # Spring profiles / Angular environments
    profiles: List[str] = field(default_factory=list)

    # Database info
    has_database: bool = False
    database_name: Optional[str] = None
    database_url: Optional[str] = None

    # Git info
    git_remote_url: Optional[str] = None
    current_branch: Optional[str] = None

    # Run command
    run_install_cmd: Optional[str] = None
    run_reinstall_cmd: Optional[str] = None
    run_command: Optional[str] = None
    run_profile_flag: Optional[str] = None

    # Config/environment files
    environment_files: List[str] = field(default_factory=list)
    env_default_dir: str = ""
    env_config_writer_type: str = "raw"
    env_pull_ignore_patterns: List[str] = field(default_factory=list)
    env_main_config_filename: str = ""

    # UI configuration mapped from yaml
    ui_config: dict = field(default_factory=dict)

    # Features supported (mapped from yaml)
    features: List[str] = field(default_factory=list)

    # Java version (for Spring Boot projects)
    java_version: Optional[str] = None

    # Server info (Spring Boot)
    server_port: Optional[int] = None
    context_path: Optional[str] = None

    # Log-based status detection patterns (regex)
    ready_pattern: Optional[str] = None
    error_pattern: Optional[str] = None

    # Seeds / Flyway migrations
    has_seeds: bool = False
    seed_dirs: List[str] = field(default_factory=list)

    # Docker Compose files
    docker_compose_files: List[str] = field(default_factory=list)

    # Optional metadata from custom configs
    detected_framework: str = "unknown"



