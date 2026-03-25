"""
profile_manager.py — Save/load/export/import workspace profiles (JSON config files).
A profile stores: per-repo URL, branch, profile, custom command, config file contents.
Optionally includes global DB presets.
"""
from __future__ import annotations
import json
import os
import shutil
from datetime import datetime
from typing import Optional


PROFILES_DIR_NAME = '.devops-profiles'


def get_profiles_dir() -> str:
    """Get or create the profiles directory within the devops-manager repository."""
    # os.path.abspath(__file__) -> .../devops-manager/core/profile_manager.py
    # dirname -> .../devops-manager/core
    # dirname -> .../devops-manager
    devops_manager_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(devops_manager_dir, PROFILES_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def save_profile(profile_name: str, config: dict) -> str:
    """Save a profile to the profiles directory."""
    profiles_dir = get_profiles_dir()
    filepath = os.path.join(profiles_dir, f'{profile_name}.json')

    config['name'] = profile_name
    config['created'] = datetime.now().isoformat()

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return filepath


def load_profile(profile_name: str) -> Optional[dict]:
    """Load a profile from the profiles directory."""
    profiles_dir = get_profiles_dir()
    filepath = os.path.join(profiles_dir, f'{profile_name}.json')

    if not os.path.isfile(filepath):
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def list_profiles() -> list:
    """List all available profile names."""
    profiles_dir = get_profiles_dir()
    if not os.path.isdir(profiles_dir):
        return []

    profiles = []
    for f in os.listdir(profiles_dir):
        if f.endswith('.json'):
            profiles.append(f[:-5])
    return sorted(profiles)


def delete_profile(profile_name: str) -> bool:
    """Delete a profile."""
    profiles_dir = get_profiles_dir()
    filepath = os.path.join(profiles_dir, f'{profile_name}.json')
    try:
        os.remove(filepath)
        return True
    except OSError:
        return False


def export_profile_to_file(profile_data: dict, filepath_dest: str) -> bool:
    """Export a profile dict directly to a file."""
    try:
        with open(filepath_dest, 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, indent=2, ensure_ascii=False)
        return True
    except (OSError, TypeError):
        return False


def import_profile_from_file(filepath: str) -> Optional[dict]:
    """Import a profile from an external JSON file (just reads it)."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if 'repos' not in data:
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None


def get_missing_repos(workspace_dir: str, profile_data: dict) -> list:
    """Check which repos from a profile are missing in the workspace."""
    missing = []
    repos = profile_data.get('repos', {})
    for repo_name, repo_config in repos.items():
        expected_path = os.path.join(workspace_dir, repo_name)
        if not os.path.isdir(expected_path):
            missing.append({
                'name': repo_name,
                'git_url': repo_config.get('git_url', ''),
                'branch': repo_config.get('branch', 'main'),
            })
    return missing


def build_profile_data(repo_cards, include_config_files=False) -> dict:
    """Build a complete profile dict from current repo card states.

    Args:
        repo_cards: list of RepoCard widgets
        include_config_files: whether to capture config file contents
    """
    from core.git_manager import get_current_branch

    profile = {}

    repos = {}
    for card in repo_cards:
        repo_name, repo_data = _build_single_repo_profile(card, include_config_files)
        repos[repo_name] = repo_data

    profile['repos'] = repos
    return profile


def _build_single_repo_profile(card, include_config_files: bool) -> tuple[str, dict]:
    """Build profile dict for a single RepoCard."""
    repo = card.get_repo_info()
    repo_data = {
        'git_url': repo.git_remote_url or '',
        'branch': card.get_branch(),
        'type': repo.repo_type,
        'profile': card.get_current_profile(),
        'custom_command': card.get_custom_command(),
        'java_version': card.selected_java_var.get() if hasattr(card, 'selected_java_var') else "Sistema (Por Defecto)",
    }

    if hasattr(card, 'get_docker_compose_active'):
        repo_data['docker_compose_active'] = card.get_docker_compose_active()

    if hasattr(card, 'get_docker_profile_services'):
        repo_data['docker_profile_services'] = card.get_docker_profile_services()

    if include_config_files:
        repo_data['config_files'] = _capture_config_files(repo)

    return repo.name, repo_data


def _capture_config_files(repo) -> dict:
    """Read and capture the content of all config files for a repo."""
    files_by_dir = {}
    for ef in getattr(repo, 'environment_files', []):
        if not os.path.isfile(ef):
            continue
        fname = os.path.basename(ef)
        try:
            if hasattr(repo, 'path') and repo.path:
                rel_dir = os.path.relpath(os.path.dirname(ef), repo.path)
                rel_dir = rel_dir.replace(os.sep, '/')
                if rel_dir == '.':
                    rel_dir = ""
            else:
                rel_dir = ""
        except ValueError:
            rel_dir = ""

        try:
            with open(ef, 'r', encoding='utf-8') as fh:
                if rel_dir not in files_by_dir:
                    files_by_dir[rel_dir] = {}
                files_by_dir[rel_dir][fname] = fh.read()
        except OSError:
            pass
    return files_by_dir


def apply_config_files(repo_path: str, repo_type: str, config_files: dict, target_env=None):
    """Overwrite config files in a repo from saved profile data."""
    from core.config_manager import backup_file

    if not config_files:
        return

    # Check if this uses the new directory-based format (dict of dicts)
    is_new_format = any(isinstance(v, dict) for v in config_files.values())

    if is_new_format:
        for rel_dir, files in config_files.items():
            if not isinstance(files, dict):
                continue

            dir_path = os.path.join(repo_path, os.path.normpath(rel_dir)) if rel_dir else repo_path
            os.makedirs(dir_path, exist_ok=True)

            for fname, content in files.items():
                fpath = os.path.join(dir_path, fname)
                if os.path.isfile(fpath):
                    backup_file(fpath)
                try:
                    with open(fpath, 'w', encoding='utf-8') as f:
                        f.write(content)
                except OSError:
                    pass
    else:
        # Legacy flat structural support
        basenames = {os.path.basename(k) for k in config_files.keys()}
        file_locations = _find_existing_config_files(repo_path, basenames)

        for path_key, content in config_files.items():
            local_path_key = os.path.normpath(path_key)
            fpath = os.path.join(repo_path, local_path_key)

            if not os.path.isfile(fpath):
                basename = os.path.basename(path_key)
                if basename in file_locations:
                    fpath = file_locations[basename]

            if os.path.isfile(fpath):
                backup_file(fpath)

            try:
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(content)
            except OSError:
                pass


def _find_existing_config_files(repo_path: str, target_files: set) -> dict:
    """Helper purely for walking the directory to find existing config files."""
    file_locations = {}
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', 'dist', 'target')]
        for fname in target_files:
            if fname in files:
                file_locations[fname] = os.path.join(root, fname)
    return file_locations
