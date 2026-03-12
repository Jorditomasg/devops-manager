import yaml
import os
from typing import Dict, Any, Optional

class YamlParser:
    """Infrastructure service to parse YAML configuration files robustly."""
    
    @staticmethod
    def load(filepath: str) -> Optional[Dict[str, Any]]:
        """Load a YAML file into a dictionary."""
        if not os.path.isfile(filepath):
            return None
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            # Here we could log using an injected logger
            return None
            
    @staticmethod
    def save(filepath: str, data: Dict[str, Any]) -> bool:
        """Save a dictionary to a YAML file safely."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            return True
        except Exception:
            return False
