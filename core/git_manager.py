"""
git_manager.py — Git operations: clone, pull, fetch, branch listing, checkout.
"""
from __future__ import annotations
import subprocess
import os
import fnmatch
from typing import Optional, Callable


LogCallback = Optional[Callable[[str], None]]


def _run_git_command(args: list[str], repo_path: str, timeout: int = 10) -> subprocess.CompletedProcess:
    """Helper to execute git commands safely and unify configurations."""
    return subprocess.run(
        args,
        capture_output=True, encoding='utf-8', errors='replace', cwd=repo_path, timeout=timeout,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    )



def get_branches(repo_path: str, include_remote: bool = True) -> list[str]:
    """List all branches (local + remote) for a repo."""
    branches = []
    try:
        # Local branches
        result = _run_git_command(['git', 'branch', '--no-color'], repo_path)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                b = line.strip().lstrip('* ').strip()
                if b and not b.startswith('('):
                    branches.append(b)

        if include_remote:
            # Remote branches
            result = _run_git_command(['git', 'branch', '-r', '--no-color'], repo_path)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    b = line.strip()
                    if b and '->' not in b:
                        # Remove origin/ prefix for display
                        short = b.replace('origin/', '', 1)
                        if short not in branches:
                            branches.append(short)
    except (subprocess.SubprocessError, OSError):
        pass
    return sorted(set(branches))


def get_current_branch(repo_path: str) -> str:
    """Get current branch name."""
    try:
        result = _run_git_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], repo_path, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return 'unknown'


def fetch(repo_path: str, log: LogCallback = None) -> tuple[bool, str]:
    """Fetch all remotes."""
    try:
        if log:
            log(f"[git] Fetching {os.path.basename(repo_path)}...")
        result = _run_git_command(['git', 'fetch', '--all', '--prune'], repo_path, timeout=60)
        msg = result.stdout.strip() + '\n' + result.stderr.strip()
        if log:
            log(f"[git] Fetch {os.path.basename(repo_path)}: {'OK' if result.returncode == 0 else 'FAILED'}")
        return result.returncode == 0, msg.strip()
    except (subprocess.SubprocessError, OSError) as e:
        if log:
            log(f"[git] Fetch error: {e}")
        return False, str(e)
    except Exception as e:
        if log:
            log(f"[git] Fetch unexpected error: {e}")
        return False, str(e)


def pull(repo_path: str, log: LogCallback = None) -> tuple[bool, str]:
    """Pull current branch from origin."""
    try:
        name = os.path.basename(repo_path)
        if log:
            log(f"[git] Pulling {name}...")
        result = _run_git_command(['git', 'pull', '--ff-only'], repo_path, timeout=120)
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
    except (subprocess.SubprocessError, OSError) as e:
        if log:
            log(f"[git] Pull error: {e}")
        return False, str(e)
    except Exception as e:
        if log:
            log(f"[git] Pull unexpected error: {e}")
        return False, str(e)


def checkout(repo_path: str, branch: str, log: LogCallback = None) -> tuple[bool, str]:
    """Checkout a branch. If it's a remote branch, create a tracking local branch."""
    name = os.path.basename(repo_path)
    try:
        # Check current branch first to avoid unnecessary git commands and logging
        current = get_current_branch(repo_path)
        if current == branch:
            return True, f"Already on '{branch}'"

        if log:
            log(f"[git] Checking out '{branch}' in {name}...")

        # First try local checkout
        result = _run_git_command(['git', 'checkout', branch], repo_path, timeout=30)
        if result.returncode == 0:
            if log:
                log(f"[git] {name}: Switched to '{branch}'")
            return True, result.stdout.strip()

        # If failed, try creating from remote
        result = _run_git_command(['git', 'checkout', '-b', branch, f'origin/{branch}'], repo_path, timeout=30)
        msg = result.stdout.strip() + '\n' + result.stderr.strip()
        success = result.returncode == 0
        if log:
            if success:
                log(f"[git] {name}: Created and switched to '{branch}' from remote")
            else:
                log(f"[git] {name}: Checkout FAILED - {msg}")
        return success, msg.strip()
    except (subprocess.SubprocessError, OSError) as e:
        if log:
            log(f"[git] Checkout error: {e}")
        return False, str(e)
    except Exception as e:
        if log:
            log(f"[git] Checkout unexpected error: {e}")
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
    except (subprocess.SubprocessError, OSError) as e:
        if log:
            log(f"[git] Clone error: {e}")
        return False, str(e)
    except Exception as e:
        if log:
            log(f"[git] Clone unexpected error: {e}")
        return False, str(e)


def has_branch(repo_path: str, branch: str) -> bool:
    """Check if a branch exists in the repo (local or remote)."""
    branches = get_branches(repo_path, include_remote=True)
    return branch in branches


def get_remote_url(repo_path: str) -> Optional[str]:
    """Get origin remote URL."""
    try:
        result = _run_git_command(['git', 'remote', 'get-url', 'origin'], repo_path, timeout=5)
        if result.returncode == 0:
            url = result.stdout.strip()
            # Convert SSH URLs to HTTPS for browser opening
            if url.startswith('git@'):
                url = url.replace(':', '/').replace('git@', 'https://')
                if url.endswith('.git'):
                    url = url[:-4]
            return url
    except (subprocess.SubprocessError, OSError):
        pass
    except Exception:
        pass
    return None


def get_commits_behind(repo_path: str) -> int:
    """Get number of commits the current branch is behind its upstream tracking branch (@{u})."""
    try:
        result = _run_git_command(
            ['git', 'rev-list', '--count', 'HEAD..@{u}'],
            repo_path, timeout=5
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (subprocess.SubprocessError, OSError):
        pass
    except Exception:
        pass
    return 0


def get_status_summary(repo_path: str) -> dict:
    """Single git call returning branch, behind count, staged and unstaged file counts.

    Replaces separate calls to get_current_branch + get_commits_behind + count_modified_files.
    Parses `git status --porcelain -b` output:
      - First line: ## <branch>...<upstream> [ahead N, behind M]
      - Subsequent lines: XY <path>  where X=index (staged), Y=worktree (unstaged)
    Returns: {'branch': str, 'behind': int, 'staged': int, 'unstaged': int}
    """
    import re as _re
    out = {'branch': 'unknown', 'behind': 0, 'staged': 0, 'unstaged': 0}
    try:
        result = _run_git_command(
            ['git', '--no-optional-locks', 'status', '--porcelain', '-b', '--untracked-files=normal'],
            repo_path, timeout=10
        )
    except (subprocess.SubprocessError, OSError):
        return out
    if result.returncode != 0:
        return out

    for i, line in enumerate(result.stdout.splitlines()):
        if i == 0:
            # ## main...origin/main [ahead 1, behind 2]
            if line.startswith('## '):
                header = line[3:]
                branch_part = header.split('...')[0].split(' ')[0]
                out['branch'] = branch_part if branch_part else 'unknown'
                m = _re.search(r'behind (\d+)', header)
                if m:
                    out['behind'] = int(m.group(1))
            continue

        if len(line) < 2:
            continue
        x, y = line[0], line[1]
        if x == '?' and y == '?':
            out['unstaged'] += 1       # untracked
        else:
            if x != ' ':
                out['staged'] += 1     # index change
            if y != ' ':
                out['unstaged'] += 1   # worktree change

    return out


def count_modified_files(repo_path: str) -> int:
    """Count number of modified/untracked files."""
    try:
        result = _run_git_command(['git', '--no-optional-locks', 'status', '--porcelain', '--untracked-files=all'], repo_path, timeout=5)
        if result.returncode == 0:
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            return len(lines)
    except (subprocess.SubprocessError, OSError):
        pass
    except Exception:
        pass
    return 0


def get_local_changes(repo_path: str, ignore_files: list[str] = None) -> list[str]:
    """Get a list of modified files, ignoring specific filenames."""
    if ignore_files is None:
        ignore_files = []
    changes = []
    try:
        result = _run_git_command(['git', '--no-optional-locks', 'status', '--porcelain', '--untracked-files=all'], repo_path, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if not line.strip():
                    continue
                # Status is 2 chars, then space, then filename
                file_path = line[3:].strip()
                filename = os.path.basename(file_path)

                if not any(fnmatch.fnmatch(filename, pattern) for pattern in ignore_files):
                    changes.append(file_path)
    except (subprocess.SubprocessError, OSError):
        pass
    except Exception:
        pass
    return changes


def clean_repo(repo_path: str, log: LogCallback = None) -> tuple[bool, str]:
    """Discard all local changes (reset hard and clean)."""
    name = os.path.basename(repo_path)
    try:
        if log:
            log(f"[git] Limpiando {name} (reset --hard & clean)...")
            
        # Add all to track them (so new files are discarded by reset/clean properly)
        _run_git_command(['git', 'add', '-A'], repo_path, timeout=30)
        
        # Reset hard
        res1 = _run_git_command(['git', 'reset', '--hard', 'HEAD'], repo_path, timeout=30)
        
        # Clean untracked
        res2 = _run_git_command(['git', 'clean', '-fd'], repo_path, timeout=30)
        
        success = res1.returncode == 0 and res2.returncode == 0
        msg = res1.stdout.strip() + '\n' + res2.stdout.strip()
        
        if log:
            if success:
                log(f"[git] {name} limpio correctamente.")
            else:
                log(f"[git] Error limpiando {name}: {res1.stderr.strip()} {res2.stderr.strip()}")
                
        return success, msg
    except (subprocess.SubprocessError, OSError) as e:
        if log:
            log(f"[git] Clean error: {e}")
        return False, str(e)
    except Exception as e:
        if log:
            log(f"[git] Clean unexpected error: {e}")
        return False, str(e)
