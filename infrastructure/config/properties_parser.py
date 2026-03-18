import os
from typing import Dict, Any, Optional
import json

class PropertiesParser:
    """Infrastructure service to parse Java .properties files."""

    @staticmethod
    def load(filepath: str) -> Optional[Dict[str, str]]:
        """Load a simple properties file into a dictionary."""
        if not os.path.isfile(filepath):
            return None
            
        props = {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, val = line.split('=', 1)
                    props[key.strip()] = val.strip()
            return props
        except OSError:
            return None

class JsonStore:
    """Infrastructure service to read/write dicts to JSON."""
    
    @staticmethod
    def load(filepath: str) -> Dict[str, Any]:
        if not os.path.isfile(filepath):
            return {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
            
    @staticmethod
    def save(filepath: str, data: Dict[str, Any]) -> bool:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            return True
        except OSError:
            return False
