"""
java_manager.py — Utilities for managing and auto-detecting multiple Java versions.
"""
import os
import subprocess
import re
from typing import Dict, List

def auto_detect_java_paths() -> Dict[str, str]:
    """Auto-detect common Java installations on Windows, Linux, and macOS.
    Returns a dict mapping a descriptive name to the JAVA_HOME path.
    """
    found_javas = {}
    search_paths = []

    if os.name == 'nt':
        search_paths = [
            r"C:\Program Files\Java",
            r"C:\Program Files\Eclipse Adoptium",
            r"C:\Program Files\Amazon Corretto",
            r"C:\Program Files\Microsoft",
            r"C:\Program Files\BellSoft",
            os.path.expanduser(r"~\.jdks")
        ]
    else:
        search_paths = [
            "/usr/lib/jvm",
            "/Library/Java/JavaVirtualMachines",
            os.path.expanduser("~/.jdks"),
            os.path.expanduser("~/.sdkman/candidates/java")
        ]

    for base_dir in search_paths:
        if os.path.isdir(base_dir):
            for entry in os.listdir(base_dir):
                full_path = os.path.join(base_dir, entry)
                if os.path.isdir(full_path):
                    # For macOS, the actual home is usually Contents/Home
                    if os.name == 'posix' and 'JavaVirtualMachines' in base_dir:
                        mac_home = os.path.join(full_path, 'Contents', 'Home')
                        if os.path.isdir(mac_home):
                            full_path = mac_home
                    
                    # Verify it's a valid JDK/JRE by checking for bin/java
                    java_exe = os.path.join(full_path, 'bin', 'java.exe' if os.name == 'nt' else 'java')
                    if os.path.isfile(java_exe):
                        version = _get_java_version(java_exe)
                        if version:
                            name = f"Java {version} ({entry})"
                            found_javas[name] = full_path

    # Also add JAVA_HOME if set and valid
    env_java_home = os.environ.get('JAVA_HOME')
    if env_java_home and os.path.isdir(env_java_home):
        java_exe = os.path.join(env_java_home, 'bin', 'java.exe' if os.name == 'nt' else 'java')
        if os.path.isfile(java_exe):
            version = _get_java_version(java_exe)
            if version:
                found_javas[f"Java {version} (JAVA_HOME)"] = env_java_home

    return found_javas


def _get_java_version(java_exe: str) -> str:
    """Run java -version and extract the version string."""
    try:
        result = subprocess.run(
            [java_exe, "-version"], capture_output=True, text=True, timeout=2,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        # stderr is usually where java -version prints
        output = result.stderr or result.stdout
        
        # Match 'openjdk version "17.0.2"' or 'java version "1.8.0_311"'
        match = re.search(r'(?:java|openjdk) version "([^"]+)"', output)
        if match:
            ver = match.group(1)
            # Simplify '1.8.0_xxx' to '8' and '17.0.x' to '17'
            if ver.startswith('1.'):
                return ver.split('.')[1]
            return ver.split('.')[0]
    except (subprocess.SubprocessError, OSError):
        pass
    return ""

def build_java_env(java_home: str) -> dict:
    """Build a cloned environment dictionary with JAVA_HOME and PATH updated."""
    env = os.environ.copy()
    if java_home and os.path.isdir(java_home):
        env['JAVA_HOME'] = java_home
        # Prepend java_home/bin to PATH
        bin_dir = os.path.join(java_home, 'bin')
        if os.name == 'nt':
            env['PATH'] = f"{bin_dir};{env.get('PATH', '')}"
        else:
            env['PATH'] = f"{bin_dir}:{env.get('PATH', '')}"
    return env
