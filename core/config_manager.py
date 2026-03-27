"""
config_manager.py — Read/write application.yml and environment.ts config files.
"""
import os
import re
import json
import yaml
from typing import Optional


# ─── JSON config in-memory cache (mtime-based invalidation) ─────────────────

_CONFIG_CACHE: dict = {}
_CONFIG_CACHE_MTIME: dict = {}
_CONFIG_CACHE_LOCK = __import__('threading').RLock()   # guards both dicts for concurrent access
_CONFIG_CACHE_MAX = 30   # discard oldest entry when over this limit


def _load_config_cached(config_path: str) -> dict:
    """Return the parsed JSON for config_path, using a cached copy when the file
    has not changed since last read.  Thread-safe via RLock."""
    try:
        mtime = os.path.getmtime(config_path)
        with _CONFIG_CACHE_LOCK:
            if (config_path in _CONFIG_CACHE
                    and _CONFIG_CACHE_MTIME.get(config_path) == mtime):
                return _CONFIG_CACHE[config_path]
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        with _CONFIG_CACHE_LOCK:
            if len(_CONFIG_CACHE) >= _CONFIG_CACHE_MAX:
                oldest = next(iter(_CONFIG_CACHE))
                _CONFIG_CACHE.pop(oldest, None)
                _CONFIG_CACHE_MTIME.pop(oldest, None)
            _CONFIG_CACHE[config_path] = data
            _CONFIG_CACHE_MTIME[config_path] = mtime
        return data
    except (OSError, json.JSONDecodeError):
        return {}


def _invalidate_config_cache(config_path: str) -> None:
    """Bust the cache entry after a write so the next read goes to disk."""
    with _CONFIG_CACHE_LOCK:
        _CONFIG_CACHE.pop(config_path, None)
        _CONFIG_CACHE_MTIME.pop(config_path, None)


# ─── Config Path ────────────────────────────────────────────────────────────

def get_config_path() -> str:
    """Get the path to the main config file."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'devops_manager_config.json'
    )


# ─── Spring Boot Config ─────────────────────────────────────────────────────

def read_spring_config(resources_dir: str, profile: str = 'default') -> dict:
    """Read a Spring Boot application.yml or application-{profile}.yml."""
    if profile == 'default':
        filepath = os.path.join(resources_dir, 'application.yml')
    else:
        filepath = os.path.join(resources_dir, f'application-{profile}.yml')

    if not os.path.isfile(filepath):
        return {}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}


def write_spring_config(resources_dir: str, profile: str, config: dict) -> bool:
    """Write a Spring Boot config back to YAML, with backup."""
    if profile == 'default':
        filepath = os.path.join(resources_dir, 'application.yml')
    else:
        filepath = os.path.join(resources_dir, f'application-{profile}.yml')

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True
    except (OSError, yaml.YAMLError):
        return False


def get_active_spring_profile(repo_path: str) -> str:
    """Try to determine the active Spring profile for a repo."""
    resources_dir = os.path.join(repo_path, 'src', 'main', 'resources')
    config = read_spring_config(resources_dir, 'default')
    spring = config.get('spring', {}) or {}
    profiles = spring.get('profiles', {}) or {}
    active = profiles.get('active', '')
    return active if active else 'default'


# ─── Angular Environment Files ──────────────────────────────────────────────

def read_angular_environment(env_file: str) -> dict:
    """Parse an Angular environment.ts file into a dict of key-value pairs."""
    if not os.path.isfile(env_file):
        return {}

    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            content = f.read()

        result = {}
        # Match key: 'value' or key: "value" or key: value patterns
        pattern = r"(\w+)\s*:\s*['\"]?(.*?)['\"]?\s*[,}]"
        for match in re.finditer(pattern, content):
            key = match.group(1)
            value = match.group(2)
            result[key] = value
        return result
    except OSError:
        return {}


def read_angular_environment_raw(env_file: str) -> str:
    """Read raw content of an Angular environment file."""
    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


def write_angular_environment_raw(env_file: str, content: str) -> bool:
    """Write raw content to an Angular environment file."""
    try:
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except OSError:
        return False


def read_config_file_raw(filepath: str) -> str:
    """Read any config file as raw text."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


def write_config_file_raw(filepath: str, content: str) -> bool:
    """Write any config file as raw text."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except OSError:
        return False

# ─── Repo Configs (Env/App) ─────────────────────────────────────────────────
#
# Storage format:
#   repo_configs = {
#       "repo-name": {
#           "module-key": { "config-name": "content..." }
#       }
#   }
# config_key is always "repo-name::module-key" (produced by RepoCard.get_config_key).


def load_repo_configs(config_key: str, config_path: str = '') -> dict:
    """Load the custom environments/profiles for a specific config key.
    config_key is 'repo-name::module-key'.
    Returns a dict like: { 'dev': 'content...', 'prod': '...' }
    """
    if not config_path:
        config_path = get_config_path()
    repo_configs = _load_config_cached(config_path).get('repo_configs', {})
    if '::' in config_key:
        repo, module = config_key.split('::', 1)
        return repo_configs.get(repo, {}).get(module, {})
    return repo_configs.get(config_key, {})


def save_repo_configs(config_key: str, configs_dict: dict, config_path: str = ''):
    """Save the custom environments/profiles under the nested format:
       repo_configs[repo][module] = configs_dict
    config_key is 'repo-name::module-key'.
    """
    if not config_path:
        config_path = get_config_path()
    try:
        if os.path.isfile(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}

        if 'repo_configs' not in config:
            config['repo_configs'] = {}

        if '::' in config_key:
            repo, module = config_key.split('::', 1)
            if repo not in config['repo_configs'] or not isinstance(config['repo_configs'][repo], dict):
                config['repo_configs'][repo] = {}
            config['repo_configs'][repo][module] = configs_dict
        else:
            config['repo_configs'][config_key] = configs_dict

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        _invalidate_config_cache(config_path)
    except (OSError, json.JSONDecodeError):
        pass


def merge_repo_configs(config_key: str, configs_dict: dict, config_path: str = '') -> dict:
    """Merge configs_dict into existing repo_configs with smart conflict resolution.

    For each config name in configs_dict:
    - Not present in existing → add it directly.
    - Present with identical content → skip (no duplicate).
    - Present with different content → add with a unique name 'repetido1', 'repetido2', etc.

    config_key is 'repo-name::module-key'.
    Returns a dict of renames: {original_name: new_name} for any conflicts resolved by renaming.
    """
    if not config_path:
        config_path = get_config_path()
    renames: dict = {}
    try:
        if os.path.isfile(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}

        if 'repo_configs' not in config:
            config['repo_configs'] = {}

        def _merge(existing: dict, incoming: dict) -> dict:
            merged = dict(existing)
            for name, content in incoming.items():
                if name not in merged:
                    merged[name] = content
                elif merged[name] == content:
                    pass  # identical content – skip
                else:
                    i = 1
                    while True:
                        candidate = f"repetido{i}"
                        if candidate not in merged:
                            merged[candidate] = content
                            renames[name] = candidate
                            break
                        i += 1
            return merged

        if '::' in config_key:
            repo, module = config_key.split('::', 1)
            if repo not in config['repo_configs'] or not isinstance(config['repo_configs'][repo], dict):
                config['repo_configs'][repo] = {}
            existing = config['repo_configs'][repo].get(module, {})
            config['repo_configs'][repo][module] = _merge(existing, configs_dict)
        else:
            existing = config['repo_configs'].get(config_key, {})
            config['repo_configs'][config_key] = _merge(existing, configs_dict)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        _invalidate_config_cache(config_path)
    except (OSError, json.JSONDecodeError):
        pass
    return renames


def _profile_name_from_file(basename: str, env_patterns: list) -> str:
    """Derive a profile/environment name from a filename using config-driven glob patterns.

    For each pattern we strip the wildcard parts to find what the basename
    adds on top of the fixed prefix/suffix, e.g.:
      pattern "application*.yml", file "application-dev.yml" → "dev"
      pattern "environment*.ts",  file "environment.production.ts" → "production"
      pattern ".env*",            file ".env.local" → "local"
    Falls back to 'default' when no extra segment is found.
    """
    import fnmatch
    import re

    for pattern in env_patterns:
        if not fnmatch.fnmatch(basename, pattern):
            continue

        # Convert the glob pattern to a regex that captures the wildcard portion
        # e.g. "application*.yml" → r"^application(.*)\.yml$"
        escaped = re.escape(pattern).replace(r'\*', '(.*)')
        m = re.match(f'^{escaped}$', basename)
        if not m:
            continue

        wildcard_part = m.group(1)  # e.g. "-dev", ".production", ".local", ""
        # Strip leading separator characters (-, ., _) to get the bare name
        name = wildcard_part.lstrip('-._')
        return name if name else 'default'

    return 'default'


def auto_import_configs(repo_path: str, repo_type: str, environment_files: list = None,
                        env_patterns: list = None) -> dict:
    """Scan a repository for existing configuration files and import them.
    Returns a dict of found configs: { 'profile_name': 'content ...' }
    Keys are simple profile names (e.g. 'default', 'local', 'test').
    The caller is responsible for scoping environment_files to a single directory
    to avoid key collisions across multiple source directories.

    env_patterns: glob patterns from the repo-type YAML definition (env_files.patterns).
    Profile names are derived from those patterns (config-driven).
    Files without matching patterns are skipped.
    """
    imported = {}

    if not environment_files or not env_patterns:
        return imported

    for file_path in environment_files:
        if not os.path.isfile(file_path):
            continue

        basename = os.path.basename(file_path)
        name = _profile_name_from_file(basename, env_patterns)

        content = read_config_file_raw(file_path)
        if content:
            imported[name] = content

    return imported


def load_active_config(config_key: str, config_path: str = '') -> str:
    """Load the active config name for a given config_key."""
    if not config_path:
        config_path = get_config_path()
    return _load_config_cached(config_path).get('active_configs', {}).get(config_key, "- Sin Seleccionar -")


def save_active_config(config_key: str, active_name: str, config_path: str = ''):
    """Save the active config name for a given config_key."""
    if not config_path:
        config_path = get_config_path()
    try:
        if os.path.isfile(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}

        if 'active_configs' not in config:
            config['active_configs'] = {}

        config['active_configs'][config_key] = active_name
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        _invalidate_config_cache(config_path)
    except (OSError, json.JSONDecodeError):
        pass
