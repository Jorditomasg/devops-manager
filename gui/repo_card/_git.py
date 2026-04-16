"""_git.py — Git badge and branch management mixin for RepoCard."""
from __future__ import annotations
import threading
import re
from gui.constants import GIT_BADGE_SEMAPHORE_COUNT, BADGE_REFRESH_MS, PORT_PATTERNS_FALLBACK
from gui import theme
from core.i18n import t


class GitMixin:
    """Mixin providing git badge refresh, branch fetching, and log detection."""
    _GIT_BADGE_SEMAPHORE = threading.Semaphore(GIT_BADGE_SEMAPHORE_COUNT)

    def _refresh_badge_loop(self):
        """Periodically refresh the unsigned changes badge."""
        if not self.winfo_exists():
            return
        self._refresh_badge()
        self._badge_timer = self.after(BADGE_REFRESH_MS, self._refresh_badge_loop)

    def _refresh_badge(self, event=None):
        """Single git call to refresh branch, behind count, staged and unstaged badges."""
        def _run():
            if not self._GIT_BADGE_SEMAPHORE.acquire(blocking=False):
                return  # Too many concurrent git calls — skip this cycle
            try:
                from core.git_manager import get_status_summary
                s = get_status_summary(self._repo.path)
                current = s['branch']
                behind = s['behind']
                unstaged = s['unstaged']

                def _update():
                    if not self.winfo_exists():
                        return
                    if hasattr(self, '_changes_count_label') and self._changes_count_label.winfo_exists():
                        self._changes_count_label.configure(text=f"📝 {unstaged}" if unstaged > 0 else "")
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

    def _refresh_branch(self):
        """Refresh current branch display."""
        def _run():
            from core.git_manager import get_current_branch, get_branches
            current = get_current_branch(self._repo.path)
            branches = get_branches(self._repo.path)
            self._branches_cache = branches

            def _update():
                if not self.winfo_exists(): return
                self._current_branch = current
                if branches:
                    if hasattr(self, '_branch_combo'):
                        self._branch_combo.configure(values=sorted(branches))
                if hasattr(self, '_branch_combo'):
                    self._branch_combo.set(current)
                self._update_header_hints()
                self._check_pull_status()
                self._refresh_badge()
                self._trigger_change_callback()
            self.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _reload_repo(self):
        """Reload branch, branch list, and git status from local state (no network)."""
        self._log(t("log.reload_start"))

        def _run():
            from core.git_manager import get_current_branch, get_branches
            current = get_current_branch(self._repo.path)
            branches = get_branches(self._repo.path)
            self._branches_cache = branches

            def _update():
                if not self.winfo_exists():
                    return
                self._current_branch = current
                if branches and hasattr(self, '_branch_combo'):
                    self._branch_combo.configure(values=branches)
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
            from core.git_manager import fetch, get_branches
            fetch(self._repo.path, self._log)
            branches = get_branches(self._repo.path)
            self._branches_cache = branches

            def _update():
                if not self.winfo_exists(): return
                self._branch_combo.configure(values=branches)
            self.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _on_branch_change(self, branch: str):
        """Handle branch change."""
        if branch not in self._branches_cache and branch != "cargando...":
            return

        def _run():
            from core.git_manager import checkout, get_current_branch
            from tkinter import messagebox
            success, msg = checkout(self._repo.path, branch, self._log)
            actual_branch = get_current_branch(self._repo.path)

            if success and actual_branch == branch:
                def _update():
                    if not self.winfo_exists(): return
                    self._current_branch = branch
                    if hasattr(self, '_branch_combo'):
                        self._branch_combo.set(branch)
                    self._update_header_hints()
                    self._check_pull_status()
                    self._refresh_badge()
                    self._trigger_change_callback()
                self.after(0, _update)
            else:
                def _err():
                    if not self.winfo_exists(): return
                    messagebox.showerror(t("dialog.git.checkout_error_title"), t("dialog.git.checkout_error_msg", branch=branch, msg=msg))
                    if hasattr(self, '_branch_combo'):
                        self._branch_combo.set(actual_branch)
                        self._update_header_hints()
                self.after(0, _err)

        threading.Thread(target=_run, daemon=True).start()

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
