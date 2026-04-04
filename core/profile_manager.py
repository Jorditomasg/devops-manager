"""
profile_manager.py — Save/load/export/import workspace profiles (JSON config files).
A profile stores: per-repo URL, branch, profile, custom command, config file contents.
Optionally includes global DB presets.
"""
from __future__ import annotations
import json
import os
import re
from datetime import datetime
from typing import Optional


PROFILES_DIR_NAME = '.devops-profiles'


def _sanitize_group_name(name: str) -> str:
    """Convert group name to a safe directory name."""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip('._') or 'default'


def get_profiles_dir(group_name: str = None) -> str:
    """Get or create the profiles directory for a group.
    'Default' and None both map to the root .devops-profiles/ dir (backwards compat).
    All other group names get their own subdirectory.
    """
    devops_manager_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = os.path.join(devops_manager_dir, PROFILES_DIR_NAME)
    if not group_name or group_name == "Default":
        d = base
    else:
        d = os.path.join(base, _sanitize_group_name(group_name))
    os.makedirs(d, exist_ok=True)
    return d


def save_profile(profile_name: str, config: dict, group_name: str = None) -> str:
    """Save a profile to the profiles directory."""
    profiles_dir = get_profiles_dir(group_name)
    filepath = os.path.join(profiles_dir, f'{profile_name}.json')

    config['name'] = profile_name
    config['created'] = datetime.now().isoformat()

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return filepath


def load_profile(profile_name: str, group_name: str = None) -> Optional[dict]:
    """Load a profile from the profiles directory."""
    profiles_dir = get_profiles_dir(group_name)
    filepath = os.path.join(profiles_dir, f'{profile_name}.json')

    if not os.path.isfile(filepath):
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def list_profiles(group_name: str = None) -> list:
    """List all available profile names.

    Backward-compat: if a custom group has no profiles yet, fall back to the
    root profiles directory so profiles saved before the groups feature was
    introduced are still visible.
    """
    profiles_dir = get_profiles_dir(group_name)
    profiles = []
    if os.path.isdir(profiles_dir):
        profiles = [f[:-5] for f in os.listdir(profiles_dir) if f.endswith('.json')]

    if not profiles and group_name and group_name != "Default":
        root_dir = get_profiles_dir(None)
        if os.path.isdir(root_dir):
            profiles = [f[:-5] for f in os.listdir(root_dir) if f.endswith('.json')]

    return sorted(profiles)


def delete_profile(profile_name: str, group_name: str = None) -> bool:
    """Delete a profile."""
    profiles_dir = get_profiles_dir(group_name)
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
        'branch': card.get_branch() if card.get_branch_in_profile() else None,
        'type': repo.repo_type,
        'profile': card.get_current_profile(),
        'custom_command': card.get_custom_command(),
        'java_version': card.selected_java_var.get() if hasattr(card, 'selected_java_var') else "Sistema (Por Defecto)",
        'selected': card.is_selected(),
    }

    if hasattr(card, 'get_docker_compose_active'):
        repo_data['docker_compose_active'] = card.get_docker_compose_active()

    if hasattr(card, 'get_docker_profile_services'):
        repo_data['docker_profile_services'] = card.get_docker_profile_services()

    if include_config_files:
        repo_data['config_files'] = _capture_config_files(repo)
        repo_data['saved_environments'] = _capture_saved_environments(repo)

    return repo.name, repo_data


def _capture_saved_environments(repo) -> dict:
    """Capture alternative environments stored in config manager."""
    from core.config_manager import load_repo_configs
    envs_by_file = {}
    for target_file in getattr(repo, 'environment_files', []):
        try:
            if hasattr(repo, 'path') and repo.path:
                rel_path = os.path.relpath(target_file, repo.path).replace(os.sep, '/')
                dir_path = '/'.join(rel_path.split('/')[:-1])
                if not dir_path or dir_path == '.':
                    dir_path = 'root'
                config_key = f"{repo.name}::{dir_path}"
                configs = load_repo_configs(config_key)
                if configs:
                    envs_by_file[rel_path] = configs
        except ValueError:
            pass
    return envs_by_file


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
    if not config_files:
        return

    for rel_dir, files in config_files.items():
        if not isinstance(files, dict):
            continue

        dir_path = os.path.join(repo_path, os.path.normpath(rel_dir)) if rel_dir else repo_path
        os.makedirs(dir_path, exist_ok=True)

        for fname, content in files.items():
            fpath = os.path.join(dir_path, fname)
            try:
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(content)
            except OSError:
                pass


def apply_saved_environments(repo_name: str, saved_environments: dict) -> dict:
    """Merge alternative environments from a profile into config manager.

    Returns a dict of renames per config_key:
    { "repo::module": {"original_name": "repetido1", ...}, ... }
    """
    from core.config_manager import merge_repo_configs
    all_renames: dict = {}
    if not saved_environments:
        return all_renames
    for rel_path, configs_dict in saved_environments.items():
        if not isinstance(configs_dict, dict):
            continue
        dir_path = '/'.join(rel_path.split('/')[:-1])
        if not dir_path or dir_path == '.':
            dir_path = 'root'
        config_key = f"{repo_name}::{dir_path}"
        renames = merge_repo_configs(config_key, configs_dict)
        if renames:
            all_renames[config_key] = renames
    return all_renames


def _derive_profile_name_from_filename(filename: str) -> str:
    """Heuristically derive a profile/environment name from a config filename.

    Examples:
      application.yml          → default
      application-local.yml   → local
      application-dev.yml     → dev
      environment.ts           → default
      environment.local.ts     → local
      .env                     → default
      .env.local               → local
    """
    import re
    base = filename
    # Strip common extensions
    for ext in ('.yml', '.yaml', '.ts', '.js', '.properties', '.json'):
        if base.lower().endswith(ext):
            base = base[:-len(ext)]
            break
    # Strip leading dot
    if base.startswith('.'):
        base = base[1:]

    # Known prefixes: everything after the prefix separator is the profile name
    for prefix in ('application-', 'application.', 'environment.', 'environment-', 'env-', 'env.'):
        if base.lower().startswith(prefix):
            rest = base[len(prefix):]
            return rest if rest else 'default'

    # If base equals a known base name, it is the default
    if base.lower() in ('application', 'environment', 'env'):
        return 'default'

    return 'default'


def apply_config_files_to_repo_configs(repo_name: str, config_files: dict) -> dict:
    """Save config_files entries as repo_configs, merging with existing data.

    config_files format: { rel_dir: { filename: content } }

    For each directory, derive a profile name from each filename and merge
    into repo_configs using the same smart merge logic (rename on conflict).

    Returns a dict of renames per config_key:
    { "repo::module": {"original_name": "repetido1", ...}, ... }
    """
    from core.config_manager import merge_repo_configs
    all_renames: dict = {}
    if not config_files:
        return all_renames
    for rel_dir, files in config_files.items():
        if not isinstance(files, dict):
            continue
        module = rel_dir if rel_dir else 'root'
        config_key = f"{repo_name}::{module}"
        configs_dict = {
            _derive_profile_name_from_filename(fname): content
            for fname, content in files.items()
            if isinstance(content, str)
        }
        if not configs_dict:
            continue
        renames = merge_repo_configs(config_key, configs_dict)
        if renames:
            all_renames[config_key] = renames
    return all_renames


def update_active_configs_for_renames(renames_by_key: dict, config_path: str = ''):
    """Update active_configs entries when config names were renamed during import.

    renames_by_key: { "repo::module": {"original_name": "repetido1"}, ... }
    If active_configs["repo::module"] == "original_name", update it to "repetido1".
    """
    from core.config_manager import get_config_path, _invalidate_config_cache
    import json
    if not renames_by_key:
        return
    if not config_path:
        config_path = get_config_path()
    try:
        if not os.path.isfile(config_path):
            return
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        active = config.get('active_configs', {})
        changed = False
        for config_key, renames in renames_by_key.items():
            current_active = active.get(config_key)
            if current_active and current_active in renames:
                active[config_key] = renames[current_active]
                changed = True
        if changed:
            config['active_configs'] = active
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            _invalidate_config_cache(config_path)
    except (OSError, json.JSONDecodeError):
        pass
