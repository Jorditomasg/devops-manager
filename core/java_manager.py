"""
java_manager.py — Utilities for managing and auto-detecting multiple Java versions.
"""
import os
import subprocess
import re
from typing import Dict, List

def _java_search_paths() -> List[str]:
    """Platform-specific base directories where JDKs are commonly installed."""
    if os.name == 'nt':
        return [
            r"C:\Program Files\Java",
            r"C:\Program Files\Eclipse Adoptium",
            r"C:\Program Files\Amazon Corretto",
            r"C:\Program Files\Microsoft",
            r"C:\Program Files\BellSoft",
            os.path.expanduser(r"~\.jdks"),
        ]
    return [
        "/usr/lib/jvm",
        "/Library/Java/JavaVirtualMachines",
        os.path.expanduser("~/.jdks"),
        os.path.expanduser("~/.sdkman/candidates/java"),
    ]


def _jdk_home(base_dir: str, entry: str) -> str:
    """Resolve the JAVA_HOME for a JDK directory entry (handles macOS Contents/Home)."""
    full_path = os.path.join(base_dir, entry)
    if os.name == 'posix' and 'JavaVirtualMachines' in base_dir:
        mac_home = os.path.join(full_path, 'Contents', 'Home')
        if os.path.isdir(mac_home):
            return mac_home
    return full_path


def _java_label(java_home: str, suffix: str):
    """(name, java_home) when java_home holds a valid java with a detectable version, else (None, None)."""
    java_exe = os.path.join(java_home, 'bin', 'java.exe' if os.name == 'nt' else 'java')
    if not os.path.isfile(java_exe):
        return None, None
    version = _get_java_version(java_exe)
    if not version:
        return None, None
    return f"Java {version} ({suffix})", java_home


def auto_detect_java_paths() -> Dict[str, str]:
    """Auto-detect common Java installations on Windows, Linux, and macOS.
    Returns a dict mapping a descriptive name to the JAVA_HOME path.
    """
    found_javas = {}
    for base_dir in _java_search_paths():
        if not os.path.isdir(base_dir):
            continue
        for entry in os.listdir(base_dir):
            if not os.path.isdir(os.path.join(base_dir, entry)):
                continue
            name, home = _java_label(_jdk_home(base_dir, entry), entry)
            if name:
                found_javas[name] = home

    # Also add JAVA_HOME if set and valid
    env_java_home = os.environ.get('JAVA_HOME')
    if env_java_home and os.path.isdir(env_java_home):
        name, home = _java_label(env_java_home, 'JAVA_HOME')
        if name:
            found_javas[name] = home

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
