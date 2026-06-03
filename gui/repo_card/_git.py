"""_git.py — Git badge and branch management mixin for RepoCard."""
from __future__ import annotations
import threading
import time
import re
from gui.constants import (
    GIT_BADGE_SEMAPHORE_COUNT, GIT_FETCH_SEMAPHORE_COUNT,
    BADGE_REFRESH_MS, FOCUS_FETCH_THROTTLE_S, PORT_PATTERNS_FALLBACK,
)
from gui import theme
from core.i18n import t


class GitMixin:
    """Mixin providing git badge refresh, branch fetching, and log detection."""
    _GIT_BADGE_SEMAPHORE = threading.Semaphore(GIT_BADGE_SEMAPHORE_COUNT)
    _GIT_BRANCH_SEMAPHORE = threading.Semaphore(GIT_BADGE_SEMAPHORE_COUNT)
    _GIT_FETCH_SEMAPHORE = threading.Semaphore(GIT_FETCH_SEMAPHORE_COUNT)

    def _on_app_focus(self):
        """Called when the app window regains focus (or restores from tray).

        Reflects external branch changes instantly via the cheap local
        `git status` in _refresh_badge (no network), and triggers a background
        `git fetch` at most once per FOCUS_FETCH_THROTTLE_S per card so the
        pull (📥) count stays accurate without a fetch storm on every focus.
        """
        self._refresh_badge()
        now = time.monotonic()
        if now - getattr(self, '_last_focus_fetch', 0.0) >= FOCUS_FETCH_THROTTLE_S:
            self._last_focus_fetch = now
            self._fetch_then_badge()

    def _fetch_then_badge(self):
        """Background fetch (quiet, semaphore-capped) then refresh the badge."""
        def _run():
            if not self._GIT_FETCH_SEMAPHORE.acquire(blocking=False):
                return  # too many concurrent fetches — skip; local badge already refreshed
            try:
                from core.git_manager import fetch_quiet
                fetch_quiet(self._repo.path)
            except Exception:
                pass
            finally:
                self._GIT_FETCH_SEMAPHORE.release()
            if self.winfo_exists():
                self.after(0, self._refresh_badge)
        threading.Thread(target=_run, daemon=True).start()

    def _refresh_badge_loop(self):
        """Periodically refresh the unsigned changes badge."""
        if not self.winfo_exists():
            return
        self._refresh_badge()
        self._badge_timer = self.after(BADGE_REFRESH_MS, self._refresh_badge_loop)

    def _refresh_badge(self, event=None):
        """Single git call to refresh branch, behind count, staged and unstaged badges."""
        # Skip work when the app is minimized to tray. The loop reschedules
        # itself via _refresh_badge_loop, so it resumes on un-minimize.
        # NOTE: do NOT skip on collapsed cards — header badges (_pull_count_label,
        # _changes_count_label) are visible even when the expand panel is hidden.
        try:
            if self.winfo_toplevel().state() == 'iconic':
                return
        except Exception:
            pass

        def _run():
            if not self._GIT_BADGE_SEMAPHORE.acquire(blocking=False):
                return  # Too many concurrent git calls — skip this cycle
            try:
                from core.git_manager import get_status_summary
                s = get_status_summary(self._repo.path)
                current = s['branch']
                behind = s['behind']
                unstaged = s['unstaged']
                conflicts = s.get('conflicts', 0)
                self._cached_behind = behind

                def _update():
                    if not self.winfo_exists():
                        return
                    if hasattr(self, '_changes_count_label') and self._changes_count_label.winfo_exists():
                        self._changes_count_label.configure(text=f"📝 {unstaged}" if unstaged > 0 else "")
                    if hasattr(self, '_conflict_count_label') and self._conflict_count_label.winfo_exists():
                        self._conflict_count_label.configure(text=f"⚠️ {conflicts}" if conflicts > 0 else "")
                    if hasattr(self, '_pull_count_label') and self._pull_count_label.winfo_exists():
                        self._pull_count_label.configure(text=f"📥 {behind}" if behind > 0 else "")
                    if hasattr(self, '_pull_btn'):
                        if behind > 0:
                            self._pull_btn.configure(
                                text=f"⬇ Pull ({behind})",
                                fg_color=theme.btn_style("blue_active")["fg_color"],
                            )
                        else:
                            self._pull_btn.configure(
                                text="⬇ Pull",
                                fg_color=theme.btn_style("blue")["fg_color"],
                            )
                    if current and current not in ('unknown', 'HEAD') and current != self._current_branch:
                        self._current_branch = current
                        if hasattr(self, '_branch_combo'):
                            self._branch_combo.set(current)
                        self._update_header_hints()

                self.after(0, _update)
            except Exception:
                pass
            finally:
                self._GIT_BADGE_SEMAPHORE.release()
        threading.Thread(target=_run, daemon=True).start()

    def _load_ordered_branches(self):
        """Worker-thread helper: read branches, order them by checkout recency, and
        cache both the ordered list and the separator index on the card. Returns
        (ordered_branches, recent_count). This is the single source of truth shared by
        the card's branch combo AND the merge dialog, so recents stay consistent."""
        from core.git_manager import get_branches, order_branches_by_recency
        ordered, rc = order_branches_by_recency(self._repo.path, get_branches(self._repo.path))
        self._branches_cache = ordered
        self._branches_recent_count = rc
        return ordered, rc

    def _refresh_branch(self, _suppress_change_cb: bool = False):
        """Refresh current branch display."""
        def _run():
            self._GIT_BRANCH_SEMAPHORE.acquire()
            try:
                from core.git_manager import get_current_branch
                current = get_current_branch(self._repo.path)
                branches, rc = self._load_ordered_branches()

                if not self._repo.git_remote_url:
                    from core.git_manager import get_remote_url
                    url = get_remote_url(self._repo.path)
                    self._repo.git_remote_url = url

                def _update():
                    if not self.winfo_exists(): return
                    self._current_branch = current
                    if branches and hasattr(self, '_branch_combo'):
                        self._branch_combo.configure(values=branches, separator_after=rc)
                    if hasattr(self, '_branch_combo'):
                        self._branch_combo.set(current)
                    self._update_header_hints()
                    self._check_pull_status()
                    self._refresh_badge()
                    if not _suppress_change_cb:
                        self._trigger_change_callback()
                self.after(0, _update)
            finally:
                self._GIT_BRANCH_SEMAPHORE.release()

        threading.Thread(target=_run, daemon=True).start()

    def _refresh_branch_startup(self):
        """Startup variant: loads branch without triggering profile dirty check."""
        self._refresh_branch(_suppress_change_cb=True)

    def _reload_repo(self):
        """Reload branch, branch list, and git status from local state (no network)."""
        self._log(t("log.reload_start"))

        def _run():
            from core.git_manager import get_current_branch
            current = get_current_branch(self._repo.path)
            branches, rc = self._load_ordered_branches()

            def _update():
                if not self.winfo_exists():
                    return
                self._current_branch = current
                if branches and hasattr(self, '_branch_combo'):
                    self._branch_combo.configure(values=branches, separator_after=rc)
                if hasattr(self, '_branch_combo'):
                    self._branch_combo.set(current)
                self._update_header_hints()
                self._check_pull_status()
                self._refresh_badge()
                self._trigger_change_callback()
                self._log(t("log.reload_done", branch=current))
            self.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _fetch_branches(self):
        """Fetch remote branches."""
        def _run():
            from core.git_manager import fetch
            fetch(self._repo.path, self._log)
            branches, rc = self._load_ordered_branches()

            def _update():
                if not self.winfo_exists(): return
                self._branch_combo.configure(values=branches, separator_after=rc)
            self.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _on_branch_change(self, branch: str):
        """Handle branch change."""
        if branch not in self._branches_cache and branch != "cargando...":
            return

        def _run():
            from core.git_manager import checkout, get_current_branch
            success, msg = checkout(self._repo.path, branch, self._log)
            actual_branch = get_current_branch(self._repo.path)
            if success and actual_branch == branch:
                self.after(0, lambda: self._on_branch_changed_ok(branch))
            else:
                self.after(0, lambda: self._on_branch_change_failed(branch, actual_branch, msg))

        threading.Thread(target=_run, daemon=True).start()

    def _on_branch_changed_ok(self, branch: str):
        """UI update after a successful checkout (UI thread)."""
        if not self.winfo_exists(): return
        self._current_branch = branch
        if hasattr(self, '_branch_combo'):
            self._branch_combo.set(branch)
        self._update_header_hints()
        self._check_pull_status()
        self._refresh_badge()
        self._trigger_change_callback()

    def _on_branch_change_failed(self, branch: str, actual_branch: str, msg: str):
        """Revert combo + show error after a failed checkout (UI thread)."""
        from gui.dialogs.messagebox import show_error
        if not self.winfo_exists(): return
        show_error(self, t("dialog.git.checkout_error_title"), t("dialog.git.checkout_error_msg", branch=branch, msg=msg))
        if hasattr(self, '_branch_combo'):
            self._branch_combo.set(actual_branch)
            self._update_header_hints()

    def _show_modified_files(self, event=None):
        """Show list of modified files in the repo's log panel."""
        def _run():
            from core.git_manager import get_local_changes
            files = get_local_changes(self._repo.path)

            def _log():
                if not self.winfo_exists():
                    return
                if not files:
                    self._log(t("log.no_changes_local"))
                    return
                self._log(t("log.modified_files_header", count=len(files)))
                for f in files:
                    self._log(f"   {f}")
            self.after(0, _log)

        threading.Thread(target=_run, daemon=True).start()

    def _show_conflicts(self, event=None):
        """List merge-conflict files in the repo's log panel."""
        def _run():
            from core.git_manager import get_conflicted_files
            files = get_conflicted_files(self._repo.path)

            def _log():
                if not self.winfo_exists():
                    return
                if not files:
                    self._log(t("log.no_conflicts"))
                    return
                self._log(t("log.conflict_files_header", count=len(files)))
                for f in files:
                    self._log(f"   {f}")
            self.after(0, _log)

        threading.Thread(target=_run, daemon=True).start()

    def _detect_port_from_log(self, line: str):
        """Dynamically detect and update the server port from log output."""
        if self._repo.server_port:
            return  # Port is already statically defined

        patterns = self._repo.port_patterns or PORT_PATTERNS_FALLBACK
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                try:
                    port = int(match.group(1))
                    if self._repo.server_port != port:
                        self._repo.server_port = port
                        self.after(0, lambda: self.winfo_exists() and self._update_status(self._repo.name, self._status))
                except ValueError:
                    pass
                break

    def _detect_status_from_log(self, line: str):
        """Detect service readiness or failure from log output using configurable patterns."""
        if self._status != 'starting':
            return

        ready = self._repo.ready_pattern
        error = self._repo.error_pattern

        if error and re.search(error, line):
            self.after(0, lambda: self.winfo_exists() and self._update_status(self._repo.name, 'error'))
            return

        if ready and re.search(ready, line):
            self.after(0, lambda: self.winfo_exists() and self._update_status(self._repo.name, 'running'))
