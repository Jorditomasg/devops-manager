"""
git_manager.py — Git operations: clone, pull, fetch, branch listing, checkout.
"""
from __future__ import annotations
import subprocess
import os
from typing import Optional, Callable


LogCallback = Optional[Callable[[str], None]]


def get_branches(repo_path: str, include_remote: bool = True) -> list[str]:
    """List all branches (local + remote) for a repo."""
    branches = []
    try:
        # Local branches
        result = subprocess.run(
            ['git', 'branch', '--no-color'],
            capture_output=True, text=True, cwd=repo_path, timeout=10,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                b = line.strip().lstrip('* ').strip()
                if b and not b.startswith('('):
                    branches.append(b)

        if include_remote:
            # Remote branches
            result = subprocess.run(
                ['git', 'branch', '-r', '--no-color'],
                capture_output=True, text=True, cwd=repo_path, timeout=10,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    b = line.strip()
                    if b and '->' not in b:
                        # Remove origin/ prefix for display
                        short = b.replace('origin/', '', 1)
                        if short not in branches:
                            branches.append(short)
    except Exception:
        pass
    return sorted(set(branches))


def get_current_branch(repo_path: str) -> str:
    """Get current branch name."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, cwd=repo_path, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return 'unknown'


def fetch(repo_path: str, log: LogCallback = None) -> tuple[bool, str]:
    """Fetch all remotes."""
    try:
        if log:
            log(f"[git] Fetching {os.path.basename(repo_path)}...")
        result = subprocess.run(
            ['git', 'fetch', '--all', '--prune'],
            capture_output=True, text=True, cwd=repo_path, timeout=60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        msg = result.stdout.strip() + '\n' + result.stderr.strip()
        if log:
            log(f"[git] Fetch {os.path.basename(repo_path)}: {'OK' if result.returncode == 0 else 'FAILED'}")
        return result.returncode == 0, msg.strip()
    except Exception as e:
        if log:
            log(f"[git] Fetch error: {e}")
        return False, str(e)


def pull(repo_path: str, log: LogCallback = None) -> tuple[bool, str]:
    """Pull current branch from origin."""
    try:
        name = os.path.basename(repo_path)
        if log:
            log(f"[git] Pulling {name}...")
        result = subprocess.run(
            ['git', 'pull', '--ff-only'],
            capture_output=True, text=True, cwd=repo_path, timeout=120,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        msg = result.stdout.strip() + '\n' + result.stderr.strip()
        success = result.returncode == 0
        if log:
            if 'Already up to date' in msg:
                log(f"[git] {name}: Already up to date")
            elif success:
                log(f"[git] {name}: Pull OK")
            else:
                log(f"[git] {name}: Pull FAILED - {msg}")
        return success, msg.strip()
    except Exception as e:
        if log:
            log(f"[git] Pull error: {e}")
        return False, str(e)


def checkout(repo_path: str, branch: str, log: LogCallback = None) -> tuple[bool, str]:
    """Checkout a branch. If it's a remote branch, create a tracking local branch."""
    name = os.path.basename(repo_path)
    try:
        if log:
            log(f"[git] Checking out '{branch}' in {name}...")

        # First try local checkout
        result = subprocess.run(
            ['git', 'checkout', branch],
            capture_output=True, text=True, cwd=repo_path, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode == 0:
            if log:
                log(f"[git] {name}: Switched to '{branch}'")
            return True, result.stdout.strip()

        # If failed, try creating from remote
        result = subprocess.run(
            ['git', 'checkout', '-b', branch, f'origin/{branch}'],
            capture_output=True, text=True, cwd=repo_path, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        msg = result.stdout.strip() + '\n' + result.stderr.strip()
        success = result.returncode == 0
        if log:
            if success:
                log(f"[git] {name}: Created and switched to '{branch}' from remote")
            else:
                log(f"[git] {name}: Checkout FAILED - {msg}")
        return success, msg.strip()
    except Exception as e:
        if log:
            log(f"[git] Checkout error: {e}")
        return False, str(e)


def clone(url: str, dest: str, log: LogCallback = None,
          progress_callback: Optional[Callable[[int], None]] = None) -> tuple[bool, str]:
    """Clone a repository to dest directory."""
    try:
        name = os.path.basename(dest)
        if log:
            log(f"[git] Cloning {url} into {name}...")

        process = subprocess.Popen(
            ['git', 'clone', '--progress', url, dest],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )

        stderr_output = []
        for line in iter(process.stderr.readline, ''):
            if not line:
                break
            stderr_output.append(line.strip())
            if log:
                log(f"[git] {line.strip()}")
            # Parse progress percentage
            if progress_callback and '%' in line:
                try:
                    pct = int(line.split('%')[0].split()[-1])
                    progress_callback(pct)
                except (ValueError, IndexError):
                    pass

        process.wait()
        msg = '\n'.join(stderr_output)
        success = process.returncode == 0
        if log:
            log(f"[git] Clone {'OK' if success else 'FAILED'}: {name}")
        return success, msg
    except Exception as e:
        if log:
            log(f"[git] Clone error: {e}")
        return False, str(e)


def has_branch(repo_path: str, branch: str) -> bool:
    """Check if a branch exists in the repo (local or remote)."""
    branches = get_branches(repo_path, include_remote=True)
    return branch in branches


def get_remote_url(repo_path: str) -> Optional[str]:
    """Get origin remote URL."""
    try:
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, cwd=repo_path, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Convert SSH URLs to HTTPS for browser opening
            if url.startswith('git@'):
                url = url.replace(':', '/').replace('git@', 'https://')
                if url.endswith('.git'):
                    url = url[:-4]
            return url
    except Exception:
        pass
    return None
