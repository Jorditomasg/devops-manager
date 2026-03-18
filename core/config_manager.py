"""
config_manager.py — Read/write application.yml and environment.ts config files.
DB presets are managed by the user and stored in devops_manager_config.json.
"""
import os
import re
import json
import yaml
import shutil
from datetime import datetime
from typing import Optional


# ─── DB Preset Management ───────────────────────────────────────────────────

def get_config_path() -> str:
    """Get the path to the main config file."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'devops_manager_config.json'
    )


def load_db_presets(config_path: str = '') -> dict:
    """Load DB presets from the config file.
    Returns a dict like:
      { 'preset_name': { 'url': '...', 'username': '...', 'password': '...', 'driver': '...' }, ... }
    """
    if not config_path:
        config_path = get_config_path()
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config.get('db_presets', {})
    except Exception:
        return {}


def save_db_presets(presets: dict, config_path: str = ''):
    """Save DB presets to the config file, preserving other settings."""
    if not config_path:
        config_path = get_config_path()
    try:
        if os.path.isfile(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}
        config['db_presets'] = presets
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def detect_db_name_from_repo(resources_dir: str, profile: str = 'default') -> str:
    """Auto-detect the database name from a repo's Spring config.
    Parses the JDBC URL from application.yml / application-{profile}.yml.
    Returns the detected DB name, or 'db' as fallback.
    """
    config = read_spring_config(resources_dir, profile)
    spring = config.get('spring', {}) or {}
    ds = spring.get('datasource', {}) or {}
    url = ds.get('url', '')
    if url:
        match = re.search(r'/([^/?]+)(\?|$)', url)
        if match:
            return match.group(1)
    return 'db'


# ─── File Backup ─────────────────────────────────────────────────────────────

def backup_file(filepath: str) -> str:
    """Create a timestamped backup of a file before modifying it."""
    return ''


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
    except Exception:
        return {}


def write_spring_config(resources_dir: str, profile: str, config: dict) -> bool:
    """Write a Spring Boot config back to YAML, with backup."""
    if profile == 'default':
        filepath = os.path.join(resources_dir, 'application.yml')
    else:
        filepath = os.path.join(resources_dir, f'application-{profile}.yml')

    try:
        backup_file(filepath)
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True
    except Exception:
        return False


def get_spring_db_info(resources_dir: str, profile: str = 'default') -> dict:
    """Extract database connection info from a Spring profile."""
    config = read_spring_config(resources_dir, profile)
    spring = config.get('spring', {}) or {}
    ds = spring.get('datasource', {}) or {}
    return {
        'url': ds.get('url', ''),
        'username': ds.get('username', ''),
        'password': ds.get('password', ''),
        'driver': ds.get('driverClassName', ''),
    }


def set_spring_db_preset(resources_dir: str, profile: str, preset: dict,
                          db_name: str = '') -> bool:
    """Apply a DB preset (dict) to a Spring config file.
    
    Args:
        resources_dir: Path to src/main/resources
        profile: Spring profile name
        preset: Dict with keys 'url', 'username', 'password', 'driver'
        db_name: Database name to substitute in the URL template. 
                 If empty, auto-detected from the current config.
    """
    if not preset:
        return False

    if not db_name:
        db_name = detect_db_name_from_repo(resources_dir, profile)

    url = preset.get('url', '').format(db_name=db_name)

    config = read_spring_config(resources_dir, profile)
    if 'spring' not in config:
        config['spring'] = {}
    if 'datasource' not in config['spring']:
        config['spring']['datasource'] = {}

    config['spring']['datasource']['url'] = url
    config['spring']['datasource']['username'] = preset.get('username', '')
    config['spring']['datasource']['password'] = preset.get('password', '')
    config['spring']['datasource']['driverClassName'] = preset.get('driver', '')

    return write_spring_config(resources_dir, profile, config)


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
    except Exception:
        return {}


def read_angular_environment_raw(env_file: str) -> str:
    """Read raw content of an Angular environment file."""
    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ''


def write_angular_environment_raw(env_file: str, content: str) -> bool:
    """Write raw content to an Angular environment file with backup."""
    try:
        backup_file(env_file)
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception:
        return False


def read_config_file_raw(filepath: str) -> str:
    """Read any config file as raw text."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ''


def write_config_file_raw(filepath: str, content: str) -> bool:
    """Write any config file with backup."""
    try:
        backup_file(filepath)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception:
        return False

# ─── Repo Configs (Env/App) ─────────────────────────────────────────────────

def load_repo_configs(repo_name: str, config_path: str = '') -> dict:
    """Load the custom environments/profiles for a specific repository.
    Returns a dict like:
      { 'dev': 'content of environment.dev.ts...', 'prod': '...' }
    """
    if not config_path:
        config_path = get_config_path()
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        repo_configs = config.get('repo_configs', {})
        return repo_configs.get(repo_name, {})
    except Exception:
        return {}


def save_repo_configs(repo_name: str, configs_dict: dict, config_path: str = ''):
    """Save the custom environments/profiles for a specific repository."""
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
            
        config['repo_configs'][repo_name] = configs_dict
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def auto_import_configs(repo_path: str, repo_type: str, environment_files: list = None) -> dict:
    """Scan a repository for existing configuration files and import them.
    Returns a dict of found configs: { 'name': 'content ...' }
    """
    imported = {}
    
    if not environment_files:
        return imported

    for file_path in environment_files:
        if not os.path.isfile(file_path):
            continue
            
        name = 'default'
        basename = os.path.basename(file_path)
        
        if 'environment' in basename:
            parts = basename.split('.')
            if len(parts) > 2:
                name = parts[1]
        elif 'application' in basename:
            base = os.path.splitext(basename)[0]
            if '-' in base:
                name = base.split('-', 1)[1]
        elif basename.startswith('.env.'):
            name = basename[5:]
        elif basename == '.env':
            name = 'default'

        content = read_config_file_raw(file_path)
        if content:
            imported[name] = content

    return imported


def load_active_config(config_key: str, config_path: str = '') -> str:
    """Load the active config name for a given config_key."""
    if not config_path:
        config_path = get_config_path()
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        active_configs = config.get('active_configs', {})
        return active_configs.get(config_key, "- Sin Seleccionar -")
    except Exception:
        return "- Sin Seleccionar -"


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
    except Exception:
        pass
