"""
git_manager.py — Git operations: clone, pull, fetch, branch listing, checkout.
"""
from __future__ import annotations
import subprocess
import os
import fnmatch
from typing import Optional, Callable


LogCallback = Optional[Callable[[str], None]]

# Porcelain XY codes that mark an unmerged (merge-conflict) path.
_UNMERGED_CODES = {'DD', 'AU', 'UD', 'UA', 'DU', 'AA', 'UU'}


def _run_git_command(args: list[str], repo_path: str, timeout: int = 10) -> subprocess.CompletedProcess:
    """Helper to execute git commands safely and unify configurations."""
    return subprocess.run(
        args,
        capture_output=True, encoding='utf-8', errors='replace', cwd=repo_path, timeout=timeout,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    )



def _parse_local_branches(stdout: str) -> list[str]:
    """Branch names from `git branch --no-color` output."""
    out = []
    for line in stdout.splitlines():
        b = line.strip().lstrip('* ').strip()
        if b and not b.startswith('('):
            out.append(b)
    return out


def _parse_remote_branches(stdout: str) -> list[str]:
    """Branch names (origin/ stripped) from `git branch -r --no-color` output."""
    out = []
    for line in stdout.splitlines():
        b = line.strip()
        if b and '->' not in b:
            out.append(b.replace('origin/', '', 1))
    return out


def get_branches(repo_path: str, include_remote: bool = True) -> list[str]:
    """List all branches (local + remote) for a repo."""
    branches = []
    try:
        result = _run_git_command(['git', 'branch', '--no-color'], repo_path)
        if result.returncode == 0:
            branches.extend(_parse_local_branches(result.stdout))

        if include_remote:
            result = _run_git_command(['git', 'branch', '-r', '--no-color'], repo_path)
            if result.returncode == 0:
                branches.extend(_parse_remote_branches(result.stdout))
    except (subprocess.SubprocessError, OSError):
        pass
    return sorted(set(branches))


def get_recent_checked_out_branches(repo_path: str) -> list[str]:
    """Branches recently checked out, most-recent first, de-duplicated.

    Parses the HEAD reflog ('checkout: moving from X to Y'). Because every
    checkout writes a HEAD reflog entry regardless of the tool used (VS Code,
    CLI, etc.), this reflects the branches the user actually switches to. Commit
    hashes from detached checkouts are filtered out by the caller (not in the
    branch list).
    """
    import re as _re
    out: list[str] = []
    seen: set[str] = set()
    try:
        res = _run_git_command(['git', 'reflog', '--format=%gs', '-n', '300'], repo_path, timeout=10)
        if res.returncode == 0:
            pat = _re.compile(r'checkout: moving from \S+ to (\S+)')
            for line in res.stdout.splitlines():
                m = pat.match(line.strip())
                if m:
                    b = m.group(1)
                    if b not in seen:
                        seen.add(b)
                        out.append(b)
    except (subprocess.SubprocessError, OSError):
        pass
    except Exception:
        pass
    return out


def order_branches_by_recency(repo_path: str, branches: list[str], limit: int = 7) -> tuple[list[str], int]:
    """Order *branches* with the `limit` most recently checked-out first, rest alphabetical.

    Returns (ordered_branches, recent_count) where recent_count is the number of
    leading "recent" entries — i.e. where the alphabetical section begins.
    """
    recent = get_recent_checked_out_branches(repo_path)
    branch_set = set(branches)
    top: list[str] = []
    for b in recent:
        if b in branch_set and b not in top:
            top.append(b)
        if len(top) >= limit:
            break
    rest = sorted(b for b in branch_set if b not in top)
    return top + rest, len(top)


def get_current_branch(repo_path: str) -> str:
    """Get current branch name."""
    try:
        result = _run_git_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], repo_path, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return 'unknown'


def get_commit_sha(repo_path: str, ref: str = 'HEAD') -> Optional[str]:
    """Resolve *ref* to a full commit SHA, or None if it can't be resolved."""
    try:
        result = _run_git_command(['git', 'rev-parse', '--verify', '--quiet', ref], repo_path, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _merge_in_progress(repo_path: str) -> bool:
    """True when a merge is half-done (MERGE_HEAD present), e.g. left by a conflict."""
    try:
        result = _run_git_command(['git', 'rev-parse', '--verify', '--quiet', 'MERGE_HEAD'], repo_path, timeout=5)
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


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


def fetch_quiet(repo_path: str) -> bool:
    """Lightweight background fetch to refresh remote-tracking refs.

    No logging, no --all/--prune: just updates the current remote so the
    `behind` count from get_status_summary reflects new upstream commits.
    Used by the on-focus throttled refresh — keep it lean.
    """
    try:
        result = _run_git_command(['git', 'fetch', '--quiet'], repo_path, timeout=30)
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False
    except Exception:
        return False


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



def _emit_clone_progress(line: str, progress_callback) -> None:
    """Parse a percentage from a `git clone --progress` line and report it."""
    if not (progress_callback and '%' in line):
        return
    try:
        progress_callback(int(line.split('%')[0].split()[-1]))
    except (ValueError, IndexError):
        pass


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
            _emit_clone_progress(line, progress_callback)

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


def _parse_status_branch_header(header_line: str, out: dict) -> None:
    """Parse the `## branch...upstream [ahead N, behind M]` porcelain header into out."""
    import re as _re
    if not header_line.startswith('## '):
        return
    header = header_line[3:]
    branch_part = header.split('...')[0].split(' ')[0]
    out['branch'] = branch_part if branch_part else 'unknown'
    m = _re.search(r'behind (\d+)', header)
    if m:
        out['behind'] = int(m.group(1))


def _count_status_line(line: str, out: dict) -> None:
    """Tally one porcelain status line into staged/unstaged/conflicts counts."""
    if len(line) < 2:
        return
    x, y = line[0], line[1]
    if x == '?' and y == '?':
        out['unstaged'] += 1       # untracked
    elif (x + y) in _UNMERGED_CODES:
        out['conflicts'] += 1      # merge conflict (unmerged path)
    else:
        if x != ' ':
            out['staged'] += 1     # index change
        if y != ' ':
            out['unstaged'] += 1   # worktree change


def get_status_summary(repo_path: str) -> dict:
    """Single git call returning branch, behind count, staged and unstaged file counts.

    Replaces separate calls to get_current_branch + get_commits_behind + count_modified_files.
    Parses `git status --porcelain -b` output:
      - First line: ## <branch>...<upstream> [ahead N, behind M]
      - Subsequent lines: XY <path>  where X=index (staged), Y=worktree (unstaged)
    Returns: {'branch': str, 'behind': int, 'staged': int, 'unstaged': int, 'conflicts': int}
    """
    out = {'branch': 'unknown', 'behind': 0, 'staged': 0, 'unstaged': 0, 'conflicts': 0}
    try:
        result = _run_git_command(
            ['git', '--no-optional-locks', 'status', '--porcelain', '-b', '--untracked-files=normal'],
            repo_path, timeout=10
        )
    except (subprocess.SubprocessError, OSError):
        return out
    if result.returncode != 0:
        return out

    lines = result.stdout.splitlines()
    if lines:
        _parse_status_branch_header(lines[0], out)
    for line in lines[1:]:
        _count_status_line(line, out)
    return out


def get_conflicted_files(repo_path: str) -> list[str]:
    """Return paths currently in merge-conflict (unmerged) state."""
    try:
        result = _run_git_command(
            ['git', 'diff', '--name-only', '--diff-filter=U'], repo_path, timeout=10
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.SubprocessError, OSError):
        pass
    except Exception:
        pass
    return []


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


def _pull_ff_only(repo_path: str, log: LogCallback, name: str) -> None:
    """Best-effort fast-forward pull of the current branch (non-fatal on failure).

    Used as a pre-merge step. A failure (no upstream, diverged, etc.) is logged
    but does not abort the merge — the merge itself surfaces real problems.
    """
    res = _run_git_command(['git', 'pull', '--ff-only'], repo_path, timeout=120)
    msg = (res.stdout + '\n' + res.stderr).strip()
    if log:
        if res.returncode == 0:
            log(f"[merge] {name}: pull OK")
        else:
            log(f"[merge] {name}: aviso al hacer pull — {msg}")


def _create_merge_new_branch(repo_path, name, base, new_branch, pull_target, log) -> tuple[bool, str]:
    """Checkout base, optionally pull, then create new_branch from it. Returns (ok, error_message)."""
    def _log(msg):
        if log:
            log(msg)
    if not new_branch:
        return False, 'missing new branch name'
    if base:
        ok, msg = checkout(repo_path, base, log)
        if not ok:
            return False, msg
    if pull_target:
        _pull_ff_only(repo_path, log, name)
    cr = _run_git_command(['git', 'checkout', '-b', new_branch], repo_path, timeout=30)
    if cr.returncode != 0:
        emsg = (cr.stderr or cr.stdout).strip()
        _log(f"[merge] {name}: no se pudo crear '{new_branch}' — {emsg}")
        return False, emsg
    _log(f"[merge] {name}: rama '{new_branch}' creada desde '{base}'.")
    return True, ''


def _position_merge_destination(repo_path, name, target_mode, target, base, new_branch, pull_target, log) -> tuple[bool, str]:
    """Checkout/create the destination branch per target_mode. Returns (ok, error_message)."""
    if target_mode == 'new':
        return _create_merge_new_branch(repo_path, name, base, new_branch, pull_target, log)
    if target_mode == 'existing':
        if not target:
            return False, 'missing target branch'
        ok, msg = checkout(repo_path, target, log)
        if not ok:
            return False, msg
    if pull_target:
        _pull_ff_only(repo_path, log, name)
    return True, ''


def _push_after_merge(repo_path, name, log) -> tuple[bool, str]:
    """Push the destination (auto --set-upstream on first push). Returns (ok, error_message)."""
    def _log(msg):
        if log:
            log(msg)
    _log(f"[merge] {name}: push...")
    pr = _run_git_command(['git', 'push'], repo_path, timeout=120)
    if pr.returncode != 0:
        # Likely no upstream yet (new branch) — retry with --set-upstream.
        cur = get_current_branch(repo_path)
        pr2 = _run_git_command(['git', 'push', '--set-upstream', 'origin', cur], repo_path, timeout=120)
        if pr2.returncode != 0:
            emsg = (pr2.stderr or pr2.stdout).strip()
            _log(f"[merge] {name}: merge OK pero push FALLÓ — {emsg}")
            return False, emsg
    _log(f"[merge] {name}: push OK")
    return True, ''


def _prepare_merge(repo_path, name, source_remote, dirty_ignore, log) -> Optional[dict]:
    """Pre-merge guards: block on a dirty tree, fetch remote refs. Returns a failure
    result-fragment to short-circuit, or None to proceed."""
    def _log(msg):
        if log:
            log(msg)
    changes = get_local_changes(repo_path, ignore_files=dirty_ignore or [])
    if changes:
        _log(f"[merge] {name}: cancelado — hay cambios locales sin commitear.")
        return {'status': 'blocked_dirty', 'dirty': changes, 'message': 'dirty working tree'}
    if source_remote:
        _log(f"[merge] {name}: fetch...")
        fr = _run_git_command(['git', 'fetch', '--all', '--prune'], repo_path, timeout=120)
        if fr.returncode != 0:
            emsg = (fr.stderr or fr.stdout).strip()
            _log(f"[merge] {name}: fetch FALLÓ — {emsg}")
            return {'status': 'error', 'message': emsg}
    return None


def _execute_merge(repo_path, name, merge_ref, log) -> dict:
    """Run `git merge merge_ref`. Returns {status: ok|conflict|error, message, conflicts}."""
    def _log(msg):
        if log:
            log(msg)
    _log(f"[merge] {name}: git merge {merge_ref}...")
    mr = _run_git_command(['git', 'merge', merge_ref], repo_path, timeout=120)
    merge_out = (mr.stdout + '\n' + mr.stderr).strip()
    if merge_out:
        _log(f"[merge] {merge_out}")
    if mr.returncode != 0:
        conflicts = get_conflicted_files(repo_path)
        if conflicts:
            _log(f"[merge] {name}: ⚠️ CONFLICTO en {len(conflicts)} fichero(s). "
                 f"Resolvé manualmente y commiteá.")
            return {'status': 'conflict', 'message': merge_out, 'conflicts': conflicts}
        return {'status': 'error', 'message': merge_out, 'conflicts': []}
    return {'status': 'ok', 'message': merge_out, 'conflicts': []}


def merge_branch(repo_path: str, *, source: str, source_remote: bool = True,
                 target_mode: str = 'current', target: Optional[str] = None,
                 base: Optional[str] = None, new_branch: Optional[str] = None,
                 pull_target: bool = True, push: bool = False,
                 dirty_ignore: Optional[list[str]] = None,
                 log: LogCallback = None) -> dict:
    """Merge *source* into a destination branch.

    target_mode:
      - 'current'  → merge into the branch currently checked out.
      - 'existing' → checkout *target* first, then merge.
      - 'new'      → checkout *base*, create *new_branch* from it, then merge.

    source_remote: if True, fetch and merge ``origin/<source>``; else merge the
    local ``<source>`` branch as-is.

    pull_target: fast-forward pull of the destination (or base, for 'new') before merging.
    push: push the destination after a clean merge (auto --set-upstream if needed).

    On conflict, the working tree is LEFT in the conflicted state for manual
    resolution — it is never aborted.

    Returns a dict:
      {'status': 'ok' | 'conflict' | 'blocked_dirty' | 'error' | 'ok_push_failed',
       'message': str, 'conflicts': list[str], 'dirty': list[str]}
    """
    name = os.path.basename(repo_path)
    result = {'status': 'error', 'message': '', 'conflicts': [], 'dirty': []}

    def _log(msg: str) -> None:
        if log:
            log(msg)

    try:
        # 1+2. Refuse a dirty tree; refresh remote refs when merging from a remote branch.
        prep = _prepare_merge(repo_path, name, source_remote, dirty_ignore, log)
        if prep is not None:
            result.update(prep)
            return result

        # 3. Position the destination branch.
        ok, emsg = _position_merge_destination(
            repo_path, name, target_mode, target, base, new_branch, pull_target, log
        )
        if not ok:
            result['message'] = emsg
            return result

        # 4. Merge.
        merge_ref = f'origin/{source}' if source_remote else source
        mres = _execute_merge(repo_path, name, merge_ref, log)
        result['status'] = mres['status']
        result['message'] = mres['message']
        result['conflicts'] = mres['conflicts']
        if mres['status'] != 'ok':
            return result

        # 5. Optional push.
        if push:
            pushed, push_emsg = _push_after_merge(repo_path, name, log)
            if not pushed:
                result['status'] = 'ok_push_failed'
                result['message'] = push_emsg
                return result

        _log(f"[merge] {name}: ✓ merge completado.")
        return result

    except (subprocess.SubprocessError, OSError) as e:
        result['status'] = 'error'
        result['message'] = str(e)
        _log(f"[merge] {name}: error — {e}")
        return result
    except Exception as e:
        result['status'] = 'error'
        result['message'] = str(e)
        _log(f"[merge] {name}: error inesperado — {e}")
        return result


def revert_merge(repo_path: str, revert_point: dict, log: LogCallback = None) -> dict:
    """Undo a merge done by :func:`merge_branch`, returning the working tree to the
    branch the user was on before it started.

    *revert_point* is a snapshot captured BEFORE the merge mutated anything::

        {'mode': 'existing' | 'new',
         'original_branch': str,
         # existing mode:
         'dest': str, 'dest_head_before': <SHA>,
         # new mode:
         'new_branch': str}

    Steps: abort an in-progress (conflicted) merge, hard-reset a completed merge on
    the destination back to its pre-merge commit, return to the original branch, and
    delete a branch created only for this merge ('new' mode). A push that already
    reached the remote is NOT undone here — the caller decides whether to call this.

    Returns ``{'status': 'ok'}`` or ``{'status': 'error', 'message': str}``.
    """
    name = os.path.basename(repo_path)

    def _log(msg: str) -> None:
        if log:
            log(msg)

    try:
        mode = revert_point.get('mode')
        original = revert_point.get('original_branch')

        # 1. Abort a half-finished merge (conflict state) before touching refs.
        if _merge_in_progress(repo_path):
            _run_git_command(['git', 'merge', '--abort'], repo_path, timeout=30)
            _log(f"[merge] {name}: merge en progreso abortado.")

        # 2. Undo a completed merge: reset the destination back to its pre-merge commit
        #    (this also drops the optional fast-forward pull done before the merge).
        if mode == 'existing':
            dest = revert_point.get('dest')
            head_before = revert_point.get('dest_head_before')
            if dest and head_before:
                co = _run_git_command(['git', 'checkout', dest], repo_path, timeout=30)
                if co.returncode == 0:
                    _run_git_command(['git', 'reset', '--hard', head_before], repo_path, timeout=30)
                    _log(f"[merge] {name}: '{dest}' restaurada a {head_before[:8]}.")

        # 3. Back to the branch the user started on.
        if original and original not in ('unknown', 'HEAD'):
            _run_git_command(['git', 'checkout', original], repo_path, timeout=30)
            _log(f"[merge] {name}: de vuelta en '{original}'.")

        # 4. Drop a branch created only for this merge ('new' mode).
        if mode == 'new':
            new_branch = revert_point.get('new_branch')
            if new_branch:
                _run_git_command(['git', 'branch', '-D', new_branch], repo_path, timeout=30)
                _log(f"[merge] {name}: rama '{new_branch}' eliminada.")

        _log(f"[merge] {name}: ✓ cambios revertidos.")
        return {'status': 'ok'}
    except (subprocess.SubprocessError, OSError) as e:
        _log(f"[merge] {name}: error al revertir — {e}")
        return {'status': 'error', 'message': str(e)}
    except Exception as e:
        _log(f"[merge] {name}: error inesperado al revertir — {e}")
        return {'status': 'error', 'message': str(e)}
