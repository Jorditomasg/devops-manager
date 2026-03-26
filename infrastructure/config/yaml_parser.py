import yaml
import os
from typing import Dict, Any, Optional, Tuple

# Module-level cache: filepath -> (mtime, parsed_data)
# Avoids re-parsing unchanged YAML files across repeated calls (e.g. repo scanning)
_YAML_CACHE: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}


class YamlParser:
    """Infrastructure service to parse YAML configuration files robustly."""

    @staticmethod
    def load(filepath: str) -> Optional[Dict[str, Any]]:
        """Load a YAML file into a dictionary, using mtime-based caching."""
        if not os.path.isfile(filepath):
            return None

        try:
            mtime = os.path.getmtime(filepath)
            cached = _YAML_CACHE.get(filepath)
            if cached is not None and cached[0] == mtime:
                return cached[1]

            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            _YAML_CACHE[filepath] = (mtime, data)
            return data
        except (yaml.YAMLError, OSError):
            return None
            
    @staticmethod
    def save(filepath: str, data: Dict[str, Any]) -> bool:
        """Save a dictionary to a YAML file safely."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            return True
        except (yaml.YAMLError, OSError):
            return False
