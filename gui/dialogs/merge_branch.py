"""MergeBranchDialog — merge a branch into the current, another, or a new branch."""
import threading
import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui.dialogs.messagebox import show_warning
from gui.widgets import SearchableCombo
from gui.log_helpers import insert_log_line
from gui import theme
from core.i18n import t


class MergeBranchDialog(BaseDialog):
    """Per-card dialog to merge one branch into a chosen destination.

    Destination can be the current branch, another existing branch, or a new
    branch created from a base. The source can be taken from the remote
    (origin/<x>, fetched first) or the local branch as-is. Optionally pulls the
    destination before merging and pushes after a clean merge.
    """

    def __init__(self, parent, repo_path, repo_name, branches, current_branch,
                 recent_count=0, dirty_ignore=None, log_callback=None, on_complete=None):
        super().__init__(parent, t("dialog.merge.title"), 560, 660)
        self._repo_path = repo_path
        self._repo_name = repo_name
        self._branches = list(branches) if branches else []
        # Separator index shared from the card: number of leading "recent" branches.
        self._recent_count = recent_count
        self._current_branch = current_branch or ''
        self._dirty_ignore = dirty_ignore or []
        self._log = log_callback
        self._on_complete = on_complete

        self._target_mode = ctk.StringVar(value="existing")
        self._source_origin = ctk.StringVar(value="remote")
        self._pull_var = ctk.BooleanVar(value=True)
        self._push_var = ctk.BooleanVar(value=False)

        self._build()
        self._sync_state()
        self._load_branches_async()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build(self):
        pad = 20

        ctk.CTkLabel(
            self, text=t("dialog.merge.repo_label", name=self._repo_name),
            font=theme.font("base", bold=True), text_color=theme.C.text_primary
        ).pack(anchor="w", padx=pad, pady=(16, 8))

        self._build_target_section(pad)
        self._build_source_section(pad)

        ctk.CTkCheckBox(
            self, text=t("dialog.merge.pull_opt"), variable=self._pull_var,
            checkbox_width=theme.G.checkbox_size, checkbox_height=theme.G.checkbox_size,
        ).pack(anchor="w", padx=pad, pady=(2, 4))
        ctk.CTkCheckBox(
            self, text=t("dialog.merge.push_opt"), variable=self._push_var,
            checkbox_width=theme.G.checkbox_size, checkbox_height=theme.G.checkbox_size,
        ).pack(anchor="w", padx=pad, pady=(0, 10))

        # Live log of the merge steps
        ctk.CTkLabel(
            self, text=t("dialog.merge.log_label"),
            font=theme.font("base", bold=True), text_color=theme.C.text_secondary
        ).pack(anchor="w", padx=pad, pady=(2, 2))
        self._log_textbox = ctk.CTkTextbox(
            self, height=140, state="disabled", **theme.log_textbox_style()
        )
        self._log_textbox.pack(fill="both", expand=True, padx=pad, pady=(0, 8))

        btn_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad, pady=(0, 12))

        self._merge_btn = ctk.CTkButton(
            btn_frame, text=t("dialog.merge.btn"), width=140,
            command=self._start_merge, **theme.btn_style("blue")
        )
        self._merge_btn.pack(side="right", padx=(10, 0))
        ctk.CTkButton(
            btn_frame, text=t("btn.cancel"), width=100,
            command=self.destroy, **theme.btn_style("neutral")
        ).pack(side="right")

        # If the card already knows both the branch list AND the current branch,
        # fill the selectors immediately. Otherwise show a loading placeholder and
        # let the background refresh recover them (incl. the current branch).
        if self._branches and self._current_branch:
            self._populate(self._branches, self._recent_count, self._current_branch)
        else:
            self._show_loading()

    def _show_loading(self):
        """Show a loading placeholder in all selectors (display + open dropdown) until
        branches arrive. The reactive `configure` replaces it live once they load."""
        loading = t("label.loading")
        for combo in (self._source_combo, self._existing_combo, self._base_combo):
            combo.configure(values=[loading])
            combo.set(loading)

    def _build_target_section(self, pad):
        frame = ctk.CTkFrame(self, fg_color=theme.C.section, corner_radius=theme.G.corner_panel)
        frame.pack(fill="x", padx=pad, pady=(0, 10))

        ctk.CTkLabel(
            frame, text=t("dialog.merge.target_section"),
            font=theme.font("base", bold=True), text_color=theme.C.text_secondary
        ).pack(anchor="w", padx=12, pady=(8, 4))

        row_ex = ctk.CTkFrame(frame, corner_radius=0, fg_color="transparent")
        row_ex.pack(fill="x", padx=16, pady=2)
        ctk.CTkRadioButton(
            row_ex, text=t("dialog.merge.target_branch"), width=60,
            variable=self._target_mode, value="existing", command=self._sync_state
        ).pack(side="left")
        self._existing_combo = SearchableCombo(
            row_ex, values=[], width=220,
            command=self._on_destination_change, **theme.combo_style()
        )
        self._existing_combo.pack(side="left", padx=(8, 0))

        ctk.CTkRadioButton(
            frame, text=t("dialog.merge.target_new"),
            variable=self._target_mode, value="new", command=self._sync_state
        ).pack(anchor="w", padx=16, pady=(6, 2))

        new_row = ctk.CTkFrame(frame, corner_radius=0, fg_color="transparent")
        new_row.pack(fill="x", padx=36, pady=(0, 10))
        ctk.CTkLabel(
            new_row, text=t("dialog.merge.base_label"), width=60, anchor="w",
            text_color=theme.C.text_secondary, font=theme.font("md")
        ).pack(side="left")
        self._base_combo = SearchableCombo(
            new_row, values=[], width=160, **theme.combo_style()
        )
        self._base_combo.pack(side="left", padx=(4, 10))
        self._new_entry = ctk.CTkEntry(
            new_row, width=170, height=theme.G.btn_height_md,
            corner_radius=theme.G.corner_btn,
            placeholder_text=t("dialog.merge.new_placeholder")
        )
        self._new_entry.pack(side="left")

    def _build_source_section(self, pad):
        frame = ctk.CTkFrame(self, fg_color=theme.C.section, corner_radius=theme.G.corner_panel)
        frame.pack(fill="x", padx=pad, pady=(0, 10))

        ctk.CTkLabel(
            frame, text=t("dialog.merge.source_section"),
            font=theme.font("base", bold=True), text_color=theme.C.text_secondary
        ).pack(anchor="w", padx=12, pady=(8, 4))

        src_row = ctk.CTkFrame(frame, corner_radius=0, fg_color="transparent")
        src_row.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(
            src_row, text=t("dialog.merge.source_label"), anchor="w",
            text_color=theme.C.text_secondary, font=theme.font("md")
        ).pack(side="left")
        self._source_combo = SearchableCombo(
            src_row, values=[], width=230, **theme.combo_style()
        )
        self._source_combo.pack(side="left", padx=(8, 0))

        origin_row = ctk.CTkFrame(frame, corner_radius=0, fg_color="transparent")
        origin_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkRadioButton(
            origin_row, text=t("dialog.merge.origin_remote"),
            variable=self._source_origin, value="remote"
        ).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(
            origin_row, text=t("dialog.merge.origin_local"),
            variable=self._source_origin, value="local"
        ).pack(side="left")

    def _load_branches_async(self):
        """Load the branch list in the background using LOCAL refs only (fast, no
        network) so the selectors fill quickly with recency ordering. An open dropdown
        updates live thanks to SearchableCombo's reactive `configure` — no reopen
        needed. Remote-tracking refs from the last fetch are already included; the
        merge itself fetches when the source is remote."""
        def _run():
            from core.git_manager import (
                get_branches, get_current_branch, order_branches_by_recency,
            )
            cur = get_current_branch(self._repo_path)
            ordered, rc = order_branches_by_recency(self._repo_path, get_branches(self._repo_path))
            self._apply_branches(ordered, rc, current=cur)
        threading.Thread(target=_run, daemon=True).start()

    def _apply_branches(self, branches, recent_count, current=None):
        """Async entry point (called from the background thread): marshal onto the UI
        thread and populate the selectors."""
        if not branches:
            return
        self.after(0, lambda: self._populate(branches, recent_count, current))

    def _populate(self, branches, recent_count, current=None):
        """Push a fresh branch list into the selectors, recovering the current branch
        if the card didn't know it yet, and filling empty/stale selections. Destination
        and base get the full list with a recent/alphabetical divider; the source list
        is derived separately (it excludes the chosen destination)."""
        if not self.winfo_exists() or not branches:
            return
        if current and current not in ('unknown', 'HEAD'):
            self._current_branch = current
        self._branches = branches
        self._recent_count = recent_count
        for combo in (self._existing_combo, self._base_combo):
            combo.configure(values=branches, separator_after=recent_count)
        self._apply_defaults(branches)
        self._refresh_source_values()

    def _apply_defaults(self, branches):
        """Default the destination and base selectors to the current branch when they
        are empty or hold a stale value. The source default is handled separately."""
        if not branches:
            return
        current = self._current_branch if self._current_branch in branches else branches[0]
        self._ensure_selection(self._existing_combo, current, branches)
        self._ensure_selection(self._base_combo, current, branches)

    @staticmethod
    def _ensure_selection(combo, preferred, branches):
        cur = combo.get().strip()
        if cur and cur in branches:
            return  # keep the user's valid choice
        combo.set(preferred)

    def _on_destination_change(self, _value):
        """When the destination branch changes, recompute the source list so it can
        never equal the destination."""
        self._refresh_source_values()

    def _refresh_source_values(self):
        """Rebuild the source selector excluding the current destination branch, so a
        branch can never be merged into itself. In 'new' mode there is no collision
        (the destination is a brand-new branch), so the full list is offered."""
        if not self._branches:
            return
        dest = self._existing_combo.get().strip() if self._target_mode.get() == "existing" else None

        if dest and dest in self._branches:
            src_values = [b for b in self._branches if b != dest]
            recent_slice = self._branches[:self._recent_count]
            src_sep = sum(1 for b in recent_slice if b != dest)
        else:
            src_values = list(self._branches)
            src_sep = self._recent_count

        self._source_combo.configure(values=src_values, separator_after=src_sep)
        # Fix the selection if it is now empty or collides with the destination.
        cur = self._source_combo.get().strip()
        if src_values and (not cur or cur not in src_values):
            self._source_combo.set(src_values[0])

    def _sync_state(self):
        """Enable only the destination inputs relevant to the selected mode, and
        refresh the source list (exclusion only applies in 'existing' mode)."""
        mode = self._target_mode.get()
        self._existing_combo.configure(state="readonly" if mode == "existing" else "disabled")
        self._base_combo.configure(state="readonly" if mode == "new" else "disabled")
        self._new_entry.configure(state="normal" if mode == "new" else "disabled")
        if hasattr(self, "_source_combo"):
            self._refresh_source_values()

    # ── Actions ──────────────────────────────────────────────────────────────

    def _collect_params(self):
        """Validate inputs and return a kwargs dict for merge_branch, or None."""
        source = self._source_combo.get().strip()
        if not source:
            show_warning(self, t("misc.error_title"), t("dialog.merge.error_no_source"))
            return None

        mode = self._target_mode.get()
        params = {
            'source': source,
            'source_remote': self._source_origin.get() == "remote",
            'target_mode': mode,
            'pull_target': self._pull_var.get(),
            'push': self._push_var.get(),
            'dirty_ignore': self._dirty_ignore,
        }

        if mode == "existing":
            target = self._existing_combo.get().strip()
            if not target:
                show_warning(self, t("misc.error_title"), t("dialog.merge.error_no_target"))
                return None
            if target == source:
                show_warning(self, t("misc.error_title"), t("dialog.merge.error_same_branch"))
                return None
            params['target'] = target
        elif mode == "new":
            base = self._base_combo.get().strip()
            new_branch = self._new_entry.get().strip()
            if not base:
                show_warning(self, t("misc.error_title"), t("dialog.merge.error_no_base"))
                return None
            if not new_branch:
                show_warning(self, t("misc.error_title"), t("dialog.merge.error_no_new"))
                return None
            params['base'] = base
            params['new_branch'] = new_branch

        return params

    # ── Logging ──────────────────────────────────────────────────────────────

    def _merge_log(self, line):
        """Logger passed to merge_branch — runs on the worker thread. Mirrors each
        line to the card log AND to this dialog's live log box (on the UI thread)."""
        if self._log:
            self._log(line)
        self.after(0, lambda: self._append_dialog_log(line))

    def _append_dialog_log(self, line):
        if not self.winfo_exists() or not hasattr(self, '_log_textbox'):
            return
        insert_log_line(self._log_textbox, line)

    def _clear_dialog_log(self):
        if not hasattr(self, '_log_textbox'):
            return
        self._log_textbox.configure(state="normal")
        self._log_textbox.delete("1.0", "end")
        self._log_textbox.configure(state="disabled")

    # ── Run / report ─────────────────────────────────────────────────────────

    def _start_merge(self):
        params = self._collect_params()
        if params is None:
            return
        self._clear_dialog_log()
        self._merge_btn.configure(state="disabled", text=t("dialog.merge.btn_running"))
        threading.Thread(target=self._do_merge, args=(params,), daemon=True).start()

    def _do_merge(self, params):
        from core.git_manager import merge_branch
        result = merge_branch(self._repo_path, log=self._merge_log, **params)

        def _done():
            if not self.winfo_exists():
                return
            status = result.get('status')
            if status in ('ok', 'ok_push_failed') and self._on_complete:
                self._on_complete()
            self._report(status, result)

        self.after(0, _done)

    def _to_close_button(self):
        """Turn the primary button into a Close action — used after a terminal outcome
        so the user can read the log before dismissing the dialog."""
        self._merge_btn.configure(state="normal", text=t("btn.close"), command=self.destroy)

    def _reset_merge_button(self):
        """Re-enable the Merge button for a retry (recoverable outcomes)."""
        self._merge_btn.configure(state="normal", text=t("dialog.merge.btn"), command=self._start_merge)

    def _report(self, status, result):
        """Feedback is shown in the live log; the button state signals done vs retry."""
        if status == 'ok':
            self._append_dialog_log(t("dialog.merge.done_ok"))
            self._to_close_button()
        elif status == 'ok_push_failed':
            self._append_dialog_log(t("dialog.merge.done_push_failed", msg=result.get('message', '')))
            self._to_close_button()
        elif status == 'conflict':
            self._append_dialog_log(t("dialog.merge.done_conflict", count=len(result.get('conflicts', []))))
            self._to_close_button()
        elif status == 'blocked_dirty':
            self._append_dialog_log(t("dialog.merge.done_dirty"))
            for f in result.get('dirty', [])[:20]:
                self._append_dialog_log(f"   {f}")
            self._reset_merge_button()
        else:
            self._append_dialog_log(t("dialog.merge.done_error", msg=result.get('message', '')))
            self._reset_merge_button()
