"""
repo_detector.py — Auto-detect repositories and classify them.
"""
from __future__ import annotations
import os
import re
import yaml
import subprocess
from domain.models.repo_info import RepoInfo
from dataclasses import dataclass, field
from typing import Optional

MVNW_CMD_WINDOWS = 'mvnw.cmd'
CONFIG_FLAG = '--configuration='


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
    """Classify a repo based on its contents using YAML configs."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_dir = os.path.join(base_dir, 'config')
    
    from application.services.project_analyzer import ProjectAnalyzerService
    analyzer = ProjectAnalyzerService(config_dir=config_dir)
    
    files_in_root = set()
    for item in os.listdir(path):
        if os.path.isfile(os.path.join(path, item)):
            files_in_root.add(item)
            
    matched_repo = None
    for r_type in analyzer.repo_types:
        if analyzer._matches_definition(r_type, files_in_root, path):
            matched_repo = analyzer._build_repo_info(name, path, r_type)
            break
            
    if not matched_repo:
        return None

    # Ahora hacemos extracciones específicas si corresponde
    repo = matched_repo
    
    # Extracciones configurables basadas en características (features)
    if 'java_version' in repo.features:
        repo.java_version = _extract_java_version_from_pom(path)
        
    main_spring_config = next((f for f in repo.environment_files if os.path.basename(f) in ['application.yml', 'application.yaml', 'application.properties']), None)
    if main_spring_config:
        # Extraer perfiles de Spring si hay un directorio por defecto
        default_env_dir = getattr(repo, 'env_default_dir', '')
        if default_env_dir:
            resources_dir = os.path.join(path, default_env_dir)
            if not repo.profiles:  
                repo.profiles = _detect_spring_profiles(resources_dir)
                
        try:
            if main_spring_config.endswith('.properties'):
                _extract_spring_info_from_props(repo, main_spring_config)
            else:
                with open(main_spring_config, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                _extract_spring_db_info(repo, config)
                _extract_spring_server_info(repo, config)
        except Exception:
            pass

    if 'docker_checkboxes' in repo.features:
        dc_files = _find_docker_compose_files(path)
        if dc_files:
            repo.docker_compose_files = dc_files

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

def _extract_java_version_from_pom(path: str) -> Optional[str]:
    """Extract java.version or maven.compiler.source from pom.xml."""
    pom_path = os.path.join(path, 'pom.xml')
    if not os.path.isfile(pom_path):
        return None
    try:
        with open(pom_path, 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r'<java\.version>([^<]+)</java\.version>', content)
            if match:
                return match.group(1).strip()
            match = re.search(r'<maven\.compiler\.source>([^<]+)</maven\.compiler\.source>', content)
            if match:
                return match.group(1).strip()
    except Exception:
        pass
    return None
