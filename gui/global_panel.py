"""
global_panel.py — Global settings panel to control all repos at once.
Uses card.is_selected() / card.set_selected() for selection from the card checkboxes.
"""
import customtkinter as ctk
from tkinter import messagebox
import threading

from gui.tooltip import ToolTip
from gui import theme
from core.i18n import t

class GlobalPanel(ctk.CTkFrame):
    """Panel with global controls that affect all repo cards."""

    def __init__(self, parent, repo_cards: list = None,
                 log_callback=None, **kwargs):
        super().__init__(parent, corner_radius=theme.G.corner_card, border_width=theme.G.border_width,
                         border_color=theme.C.card_border,
                         fg_color=theme.C.card, **kwargs)

        self._cards = repo_cards or []
        self._log = log_callback

        self._build_ui()

    def set_cards(self, cards: list):
        """Update the list of repo cards."""
        self._cards = cards

    def _build_ui(self):
        """Build the global panel UI."""
        # Title + Select All
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(8, 4))

        ctk.CTkLabel(
            title_frame, text=t("label.global_panel_title"),
            font=theme.font("xxl", bold=True),
            text_color=theme.C.text_primary
        ).pack(side="left")

        # Select All checkbox (toggles all card checkboxes)
        self._select_all_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            title_frame, text=t("label.select_all"), variable=self._select_all_var,
            font=theme.font("md"),
            checkbox_width=theme.G.checkbox_size_sm, checkbox_height=theme.G.checkbox_size_sm,
            text_color=theme.C.text_muted,
            command=self._toggle_select_all
        ).pack(side="right", padx=(10, 0))

        # ─── Row: Branch (left) + Action buttons (right) ───
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(row, text=t("label.global_branch"), font=theme.font("base"),
                     text_color=theme.C.text_secondary, width=45).pack(side="left")

        self._branch_entry = ctk.CTkEntry(
            row, width=180, height=theme.G.btn_height_md, font=theme.font("base"),
            corner_radius=theme.G.corner_btn,
            fg_color=theme.C.section,
            border_color=theme.C.default_border,
            placeholder_text=t("label.branch_placeholder")
        )
        self._branch_entry.pack(side="left", padx=(4, 4))

        self._apply_branch_btn = ctk.CTkButton(
            row, text=t("btn.apply_branch"), width=70,
            command=self._apply_branch_all,
            **theme.btn_style("blue")
        )
        self._apply_branch_btn.pack(side="left", padx=(0, 0))
        ToolTip(self._apply_branch_btn, t("tooltip.apply_branch"))

        self._pull_btn = ctk.CTkButton(
            row, text=t("btn.pull_all"), width=90,
            command=self._pull_all,
            **theme.btn_style("blue", font_size="md")
        )
        self._pull_btn.pack(side="left", padx=(3, 0))
        ToolTip(self._pull_btn, t("tooltip.pull_all"))

        self._install_btn = ctk.CTkButton(
            row, text=t("btn.install_all"), width=95,
            command=self._install_all,
            **theme.btn_style("neutral_alt", font_size="md")
        )
        self._install_btn.pack(side="left", padx=(3, 0))
        ToolTip(self._install_btn, t("tooltip.install_all"))

        # Action buttons — right-aligned
        self._restart_btn = ctk.CTkButton(
            row, text=t("btn.restart"), width=90,
            command=self._restart_selected,
            **theme.btn_style("warning", font_size="md")
        )
        self._restart_btn.pack(side="right", padx=(3, 0))
        ToolTip(self._restart_btn, t("tooltip.restart_selected"))

        self._stop_btn = ctk.CTkButton(
            row, text=t("btn.stop"), width=80,
            command=self._stop_selected,
            **theme.btn_style("danger", font_size="md")
        )
        self._stop_btn.pack(side="right", padx=(3, 0))
        ToolTip(self._stop_btn, t("tooltip.stop_selected"))

        self._start_btn = ctk.CTkButton(
            row, text=t("btn.start"), width=80,
            command=self._start_selected,
            **theme.btn_style("start", font_size="md")
        )
        self._start_btn.pack(side="right", padx=(3, 0))
        ToolTip(self._start_btn, t("tooltip.start_selected"))


    def _set_async_btns_state(self, state: str):
        """Enable or disable the buttons that trigger async background operations."""
        for btn in (self._apply_branch_btn, self._pull_btn, self._install_btn):
            try:
                btn.configure(state=state)
            except Exception:
                pass

    def _toggle_select_all(self):
        """Toggle all repo card checkboxes."""
        val = self._select_all_var.get()
        for card in self._cards:
            card.set_selected(val)

    def _get_selected_cards(self):
        """Get cards that are currently selected (via their checkbox)."""
        return [card for card in self._cards if card.is_selected()]

    def _apply_branch_all(self):
        """Apply a branch to all selected repos. Alert if branch not found in some."""
        branch = self._branch_entry.get().strip()
        if not branch:
            messagebox.showwarning(t("misc.warning_title"), t("misc.enter_branch"))
            return

        selected = self._get_selected_cards()
        if not selected:
            messagebox.showwarning(t("misc.warning_title"), t("misc.no_repos_selected"))
            return

        self._set_async_btns_state("disabled")
        threading.Thread(
            target=self._run_apply_branch,
            args=(branch, selected),
            daemon=True,
        ).start()

    def _run_apply_branch(self, branch: str, selected: list):
        """Background worker for _apply_branch_all."""
        not_found = [card.get_name() for card in selected if not card.set_branch(branch)]
        self.after(0, lambda: self._on_apply_branch_done(branch, selected, not_found))

    def _on_apply_branch_done(self, branch: str, selected: list, not_found: list):
        self._set_async_btns_state("normal")
        if not_found:
            repos_str = "\n".join(f"  • {r}" for r in not_found)
            messagebox.showwarning(
                t("misc.branch_not_found_title"),
                t("misc.branch_not_found_msg", branch=branch, repos=repos_str),
            )
        if self._log:
            changed = len(selected) - len(not_found)
            if not_found:
                self._log(t("log.global_branch_not_found", branch=branch, changed=changed, total=len(selected), missing=len(not_found)))
            else:
                self._log(t("log.global_branch_applied", branch=branch, changed=changed, total=len(selected)))

    def _pull_all(self):
        """Pull all selected repos."""
        selected = self._get_selected_cards()
        if not selected:
            return

        if self._log:
            self._log(t("log.global_pulling", count=len(selected)))

        self._set_async_btns_state("disabled")

        def _run():
            from core.git_manager import pull
            for card in selected:
                repo = card.get_repo_info()
                pull(repo.path, self._log)
            self.after(0, lambda: self._set_async_btns_state("normal"))

        threading.Thread(target=_run, daemon=True).start()

    def _install_all(self):
        """Install dependencies for all selected repos, in parallel, skipping already-installed ones."""
        selected = self._get_selected_cards()
        if not selected:
            return

        # Only install repos that actually need it
        to_install = [
            card for card in selected
            if card.get_repo_info().run_install_cmd
        ]
        if not to_install:
            if self._log:
                self._log(t("log.global_all_installed"))
            return

        if self._log:
            self._log(t("log.global_installing", count=len(to_install)))

        self._set_async_btns_state("disabled")

        remaining = [len(to_install)]  # mutable counter
        lock = threading.Lock()

        def _on_card_done():
            with lock:
                remaining[0] -= 1
                if remaining[0] == 0:
                    self.after(0, lambda: self._set_async_btns_state("normal"))
                    if self._log:
                        self._log(t("log.global_install_done"))

        def _install_card(card):
            card.install_dependencies(skip_if_installed=True)
            _on_card_done()

        for card in to_install:
            threading.Thread(target=_install_card, args=(card,), daemon=True).start()

    def _start_selected(self):
        """Start all selected repos."""
        selected = self._get_selected_cards()
        if self._log:
            self._log(t("log.global_starting", count=len(selected)))
        for card in selected:
            card.do_start()

    def _stop_selected(self):
        """Stop all selected repos."""
        selected = self._get_selected_cards()
        if self._log:
            self._log(t("log.global_stopping", count=len(selected)))
        for card in selected:
            card.do_stop()

    def _restart_selected(self):
        """Restart all selected repos."""
        selected = self._get_selected_cards()
        if self._log:
            self._log(t("log.global_restarting", count=len(selected)))
        for card in selected:
            card.do_stop()

        def _delayed_start():
            for card in selected:
                card.do_start()

        self.after(3000, _delayed_start)

