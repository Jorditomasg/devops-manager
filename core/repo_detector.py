"""
repo_detector.py — Auto-detect repositories and classify them.
"""
from __future__ import annotations
import os
import re
import yaml
import subprocess
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RepoInfo:
    """Holds all detected metadata for a single repository."""
    name: str
    path: str
    repo_type: str  # 'spring-boot', 'angular', 'docker-infra', 'maven-lib'
    profiles: list = field(default_factory=list)
    has_database: bool = False
    database_name: Optional[str] = None
    database_url: Optional[str] = None
    has_seeds: bool = False
    seed_dirs: list = field(default_factory=list)
    docker_compose_files: list = field(default_factory=list)
    server_port: Optional[int] = None
    context_path: Optional[str] = None
    git_remote_url: Optional[str] = None
    current_branch: Optional[str] = None
    run_command: Optional[str] = None
    run_profile_flag: Optional[str] = None
    environment_files: list = field(default_factory=list)


def detect_repos(workspace_dir: str) -> list[RepoInfo]:
    """Scan workspace_dir for subdirectories that are git repos and classify them."""
    repos = []
    if not os.path.isdir(workspace_dir):
        return repos

    for entry in sorted(os.listdir(workspace_dir)):
        full_path = os.path.join(workspace_dir, entry)
        if not os.path.isdir(full_path):
            continue
        if entry.startswith('.') or entry == 'node_modules':
            continue

        git_dir = os.path.join(full_path, '.git')
        if not os.path.isdir(git_dir):
            # Check for docker-compose files even without .git
            dc_files = _find_docker_compose_files(full_path)
            if dc_files:
                repo = _build_docker_infra_repo(entry, full_path, dc_files)
                repos.append(repo)
            continue

        repo = _classify_repo(entry, full_path)
        if repo:
            repos.append(repo)

    return repos


def _classify_repo(name: str, path: str) -> Optional[RepoInfo]:
    """Classify a repo based on its contents."""
    has_pom = os.path.isfile(os.path.join(path, 'pom.xml'))
    has_package_json = os.path.isfile(os.path.join(path, 'package.json'))
    has_nx = os.path.isfile(os.path.join(path, 'nx.json'))
    has_angular = os.path.isfile(os.path.join(path, 'angular.json'))
    dc_files = _find_docker_compose_files(path)

    # Angular / Nx project
    if has_package_json and (has_nx or has_angular):
        return _build_angular_repo(name, path)

    # Spring Boot project
    if has_pom:
        resources_dir = os.path.join(path, 'src', 'main', 'resources')
        app_yml = os.path.join(resources_dir, 'application.yml')
        app_yaml = os.path.join(resources_dir, 'application.yaml')
        app_properties = os.path.join(resources_dir, 'application.properties')
        
        main_config_file = None
        if os.path.isfile(app_yml):
            main_config_file = app_yml
        elif os.path.isfile(app_yaml):
            main_config_file = app_yaml
        elif os.path.isfile(app_properties):
            main_config_file = app_properties
            
        if main_config_file:
            return _build_spring_boot_repo(name, path, resources_dir, main_config_file)
        else:
            # Maven library (no application config with server config)
            return _build_maven_lib_repo(name, path)

    # Docker infra project (has docker-compose but no pom/package.json)
    if dc_files:
        return _build_docker_infra_repo(name, path, dc_files)

    return None


def _build_spring_boot_repo(name: str, path: str, resources_dir: str, main_config_file: str) -> RepoInfo:
    """Build RepoInfo for a Spring Boot project."""
    repo = RepoInfo(name=name, path=path, repo_type='spring-boot')

    # Detect profiles
    repo.profiles = _detect_spring_profiles(resources_dir)

    # Parse main config for DB and port info
    try:
        if main_config_file.endswith('.properties'):
            _extract_spring_info_from_props(repo, main_config_file)
        else:
            with open(main_config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            _extract_spring_db_info(repo, config)
            _extract_spring_server_info(repo, config)
    except Exception:
        pass

    # Detect seeds (flyway dirs)
    repo.has_seeds, repo.seed_dirs = _detect_seeds(path)

    # Docker compose files
    repo.docker_compose_files = _find_docker_compose_files(path)

    # Git remote
    repo.git_remote_url = _get_git_remote(path)

    # Run command
    mvnw = 'mvnw.cmd' if os.name == 'nt' else './mvnw'
    if os.path.isfile(os.path.join(path, 'mvnw.cmd' if os.name == 'nt' else 'mvnw')):
        repo.run_command = f'{mvnw} spring-boot:run'
        repo.run_profile_flag = '-Dspring-boot.run.profiles='
    else:
        repo.run_command = 'mvn spring-boot:run'
        repo.run_profile_flag = '-Dspring-boot.run.profiles='

    return repo


def _build_angular_repo(name: str, path: str) -> RepoInfo:
    """Build RepoInfo for an Angular/Nx project."""
    repo = RepoInfo(name=name, path=path, repo_type='angular')

    # Detect environment files
    env_files = []
    for root, dirs, files in os.walk(path):
        # Skip node_modules
        dirs[:] = [d for d in dirs if d != 'node_modules' and d != '.git']
        for f in files:
            if f.startswith('environment') and f.endswith('.ts'):
                env_files.append(os.path.join(root, f))
    repo.environment_files = env_files

    # Extract profile names from environment files
    profiles = []
    for ef in env_files:
        fname = os.path.basename(ef)
        # environment.local.ts -> local, environment.ts -> default
        match = re.match(r'environment\.?(.*)\.ts', fname)
        if match:
            prof = match.group(1)
            profiles.append(prof if prof else 'default')
    repo.profiles = profiles

    # Git remote
    repo.git_remote_url = _get_git_remote(path)

    # Detect if Nx monorepo
    has_nx = os.path.isfile(os.path.join(path, 'nx.json'))
    if has_nx:
        # Try to find the main app name from nx.json or apps/
        apps_dir = os.path.join(path, 'apps')
        if os.path.isdir(apps_dir):
            app_names = [d for d in os.listdir(apps_dir)
                         if os.path.isdir(os.path.join(apps_dir, d)) and not d.startswith('.')]
            if app_names:
                main_app = app_names[0]
                repo.run_command = f'npx nx serve {main_app}'
                repo.run_profile_flag = '--configuration='
            else:
                repo.run_command = 'npx nx serve'
                repo.run_profile_flag = '--configuration='
        else:
            repo.run_command = 'npx nx serve'
            repo.run_profile_flag = '--configuration='
    else:
        repo.run_command = 'ng serve'
        repo.run_profile_flag = '--configuration='

    return repo


def _build_maven_lib_repo(name: str, path: str) -> RepoInfo:
    """Build RepoInfo for a Maven library (no runnable server)."""
    repo = RepoInfo(name=name, path=path, repo_type='maven-lib')
    repo.git_remote_url = _get_git_remote(path)

    mvnw = 'mvnw.cmd' if os.name == 'nt' else './mvnw'
    if os.path.isfile(os.path.join(path, 'mvnw.cmd' if os.name == 'nt' else 'mvnw')):
        repo.run_command = f'{mvnw} install -DskipTests'
    else:
        repo.run_command = 'mvn install -DskipTests'

    # Detect profiles (may have application-local.yml for tests)
    resources_dir = os.path.join(path, 'src', 'main', 'resources')
    if os.path.isdir(resources_dir):
        repo.profiles = _detect_spring_profiles(resources_dir)

    return repo


def _build_docker_infra_repo(name: str, path: str, dc_files: list) -> RepoInfo:
    """Build RepoInfo for a Docker infrastructure project."""
    repo = RepoInfo(name=name, path=path, repo_type='docker-infra')
    repo.docker_compose_files = dc_files
    repo.git_remote_url = _get_git_remote(path)

    # Detect seeds
    repo.has_seeds, repo.seed_dirs = _detect_seeds(path)

    # Check for init.sql or flyway
    db_dir = os.path.join(path, 'db')
    if os.path.isdir(db_dir):
        repo.has_database = True

    return repo


def _detect_spring_profiles(resources_dir: str) -> list:
    """Detect available Spring profiles from application config files."""
    profiles = []
    if not os.path.isdir(resources_dir):
        return profiles
    for f in os.listdir(resources_dir):
        match = re.match(r'application-(.+)\.(yml|yaml|properties)$', f)
        if match:
            p = match.group(1)
            if p not in profiles:
                profiles.append(p)
    # Add default profile
    has_default = any(os.path.isfile(os.path.join(resources_dir, f)) 
                      for f in ['application.yml', 'application.yaml', 'application.properties'])
    if has_default:
        profiles.insert(0, 'default')
    return profiles


def _extract_spring_db_info(repo: RepoInfo, config: dict):
    """Extract database connection info from parsed YAML config."""
    spring = config.get('spring', {}) or {}
    datasource = spring.get('datasource', {}) or {}
    url = datasource.get('url', '')
    if url:
        repo.has_database = True
        repo.database_url = url
        # Extract DB name from JDBC URL
        match = re.search(r'/([^/?]+)(\?|$)', url)
        if match:
            repo.database_name = match.group(1)


def _extract_spring_server_info(repo: RepoInfo, config: dict):
    """Extract server port and context path from parsed YAML config."""
    server = config.get('server', {}) or {}
    port = server.get('port')
    if port:
        repo.server_port = int(port)
    servlet = server.get('servlet', {}) or {}
    ctx = servlet.get('context-path', '')
    if ctx:
        repo.context_path = ctx


def _extract_spring_info_from_props(repo: RepoInfo, props_file: str):
    """Extract database and server info from a properties file."""
    try:
        with open(props_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key, val = key.strip(), val.strip()
                
                if key == 'spring.datasource.url':
                    repo.has_database = True
                    repo.database_url = val
                    match = re.search(r'/([^/?]+)(\?|$)', val)
                    if match:
                        repo.database_name = match.group(1)
                elif key == 'server.port':
                    repo.server_port = int(val)
                elif key == 'server.servlet.context-path':
                    repo.context_path = val
    except Exception:
        pass


def _detect_seeds(path: str) -> tuple:
    """Detect if the repo has Flyway migration seeds."""
    seed_dirs = []
    db_dir = os.path.join(path, 'db')
    if os.path.isdir(db_dir):
        for entry in os.listdir(db_dir):
            full = os.path.join(db_dir, entry)
            if os.path.isdir(full) and entry.startswith('flyway'):
                migration_dir = os.path.join(full, 'migration')
                if os.path.isdir(migration_dir):
                    seed_dirs.append(full)
    return (len(seed_dirs) > 0, seed_dirs)


def _find_docker_compose_files(path: str) -> list:
    """Find all docker-compose*.yml files in a directory (non-recursive)."""
    files = []
    for f in os.listdir(path):
        if f.startswith('docker-compose') and f.endswith('.yml'):
            files.append(os.path.join(path, f))
    return sorted(files)


def _get_git_remote(path: str) -> Optional[str]:
    """Get the remote origin URL for a git repo."""
    try:
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, cwd=path, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None
