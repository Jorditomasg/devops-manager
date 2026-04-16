"""_header.py — Header UI building mixin for RepoCard."""
from __future__ import annotations
import os
import subprocess
import sys
import webbrowser
import customtkinter as ctk
import tkinter as tk
from gui import theme
from gui.tooltip import ToolTip
from core.i18n import t

BTN_CLICK = "<Button-1>"


class HeaderMixin:
    """Mixin providing header UI construction and update methods."""

    def _on_hover_enter(self, event=None):
        self._header.configure(fg_color=theme.C.card_hover)

    def _on_hover_leave(self, event=None):
        self._header.configure(fg_color="transparent")

    def _on_map(self, event=None):
        # Cuando se muestra visualmente, vinculamos FocusIn del TopLevel de forma aditiva
        if not hasattr(self, '_focus_bound'):
            try:
                self.winfo_toplevel().bind("<FocusIn>", self._refresh_badge, add="+")
                self._focus_bound = True
            except tk.TclError:
                pass

    def _build_ui(self):
        """Build all UI elements for the card."""
        self._build_header()
        # Expand panel is built lazily on first _toggle_expand call

    # ─── HEADER (always visible, compact) ────────────────────────

    def _build_header(self):
        """Build the collapsed header bar."""
        self._header = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2")
        self._header.pack(fill="x", padx=6, pady=4)
        self._header.bind(BTN_CLICK, self._toggle_expand)

        # Right section must be packed first so it reserves space before the
        # left section's expanding branch-hint label fills the remainder.
        self._build_header_right(self._header)
        self._build_header_left(self._header)

    def _build_header_left(self, frame):
        """Build the checkbox + name label section of the header."""
        repo = self._repo
        type_color = repo.ui_config.get('color', '#888')

        # Checkbox
        ctk.CTkCheckBox(
            frame, text="", variable=self.selected_var,
            checkbox_width=18, checkbox_height=18, width=20, corner_radius=4,
            command=self._trigger_change_callback
        ).pack(side="left", padx=(4, 4))

        # Status dot
        self._status_label = ctk.CTkLabel(
            frame, text="🔴",
            font=theme.font("xl"), width=30,
            text_color=theme.STATUS_ICONS.get('stopped', theme.C.status_stopped)
        )
        self._status_label.pack(side="left", padx=(0, 6))
        self._status_label.bind(BTN_CLICK, self._toggle_expand)

        # Type badge
        ctk.CTkLabel(
            frame,
            text=f" {repo.repo_type.replace('-', ' ').title()} ",
            font=theme.font("xs", bold=True),
            text_color=theme.C.text_white, fg_color=type_color,
            corner_radius=theme.G.corner_badge, height=18
        ).pack(side="left", padx=(0, 8))

        # Name
        name_label = ctk.CTkLabel(
            frame, text=f"{repo.ui_config.get('icon', '📁')} {repo.name}",
            font=theme.font("h2", bold=True), anchor="w",
            text_color=theme.C.text_primary
        )
        name_label.pack(side="left")
        name_label.bind(BTN_CLICK, self._toggle_expand)
        if repo.git_remote_url:
            ToolTip(name_label, t("tooltip.open_repo"))
            name_label.bind("<Button-3>", lambda e: webbrowser.open(repo.git_remote_url))

        self._build_header_name_hints(frame)

    def _build_header_name_hints(self, frame):
        """Build pull, staged, unstaged badges and branch hint labels."""
        # Pending pulls badge
        self._pull_count_label = ctk.CTkLabel(
            frame, text="",
            font=theme.font("md", bold=True), text_color=theme.C.text_accent
        )
        self._pull_count_label.pack(side="left", padx=(4, 0))
        self._pull_count_label.bind("<Button-1>", lambda e: self._pull())
        ToolTip(self._pull_count_label, t("tooltip.pending_pulls"))

        # Unstaged / untracked changes badge
        self._changes_count_label = ctk.CTkLabel(
            frame, text="",
            font=theme.font("md", bold=True), text_color=theme.C.text_warning_badge
        )
        self._changes_count_label.pack(side="left", padx=(4, 4))
        self._changes_count_label.bind("<Button-1>", self._show_modified_files)
        ToolTip(self._changes_count_label, t("tooltip.modified_files"))

        # Danger env badge (yellow, shown when a dangerous env is active)
        self._danger_env_badge = ctk.CTkLabel(
            frame, text="",
            font=theme.font("xs", bold=True), text_color=theme.C.text_warning_badge, anchor="w"
        )
        self._danger_env_badge.pack(side="left", padx=(4, 0))
        ToolTip(self._danger_env_badge, t("tooltip.danger_env_badge"))
        self._danger_env_badge.bind(BTN_CLICK, self._toggle_expand)

        # Warning badge (yellow, shown only when deps missing)
        self._branch_hint_warn = ctk.CTkLabel(
            frame, text="",
            font=theme.font("xs", mono=True), text_color=theme.C.text_warning_badge, anchor="w"
        )
        self._branch_hint_warn.pack(side="left", padx=(6, 0))
        self._branch_hint_warn.bind(BTN_CLICK, self._toggle_expand)

        # Branch + profile hints (grey, right of name)
        self._branch_hint = ctk.CTkLabel(
            frame, text="",
            font=theme.font("xs", mono=True), text_color=theme.C.text_faint, anchor="w"
        )
        self._branch_hint.pack(side="left", padx=(0, 0), fill="x", expand=True)
        self._branch_hint.bind(BTN_CLICK, self._toggle_expand)

    def _build_header_right(self, frame):
        """Build the status + action buttons section of the header.

        All widgets use side="right" and are packed in reverse visual order
        (rightmost first) so they reserve their space before the left section's
        expanding branch-hint fills the remainder.  Visual result (left→right):
        [status_text] [port] [action_btns] [📁] [▼]
        """
        repo = self._repo

        # Expand toggle (rightmost) — packed first
        self._toggle_btn = ctk.CTkButton(
            frame, text="▼", width=28,
            text_color=theme.C.text_accent_bright,
            command=self._toggle_expand, **theme.btn_style("toggle_expand", font_size="md")
        )
        self._toggle_btn.pack(side="right", padx=(4, 2))
        ToolTip(self._toggle_btn, t("tooltip.expand"))

        # Open in Explorer
        self._explorer_btn = ctk.CTkButton(
            frame, text="📁", width=28,
            command=self._open_in_explorer, **theme.btn_style("neutral", font_size="md")
        )
        self._explorer_btn.pack(side="right", padx=(4, 2))
        ToolTip(self._explorer_btn, t("tooltip.open_explorer"))

        # Action buttons frame
        self._build_action_buttons(frame)

        # Port label
        if repo.server_port:
            ctk.CTkLabel(
                frame, text=f":{repo.server_port}",
                font=theme.font("md", bold=True, mono=True), text_color=theme.C.text_accent
            ).pack(side="right", padx=(0, 8))

        # Status text (leftmost of the right group)
        self._status_text = ctk.CTkLabel(
            frame, text=t("label.status.stopped"),
            font=theme.font("base"), text_color=theme.C.text_muted
        )
        self._status_text.pack(side="right", padx=(0, 4))

    def _build_action_buttons(self, frame):
        """Build the start/stop/restart action buttons."""
        self._action_btns_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self._action_btns_frame.pack(side="right", padx=(0, 4))

        self._start_btn = ctk.CTkButton(
            self._action_btns_frame, text="▶", width=32,
            command=self._start, **theme.btn_style("start", font_size="lg")
        )
        ToolTip(self._start_btn, t("tooltip.start_btn"))

        self._stop_btn = ctk.CTkButton(
            self._action_btns_frame, text="⬛", width=32,
            command=self._stop, **theme.btn_style("danger", font_size="lg")
        )
        ToolTip(self._stop_btn, t("tooltip.stop_btn"))

        self._restart_btn = ctk.CTkButton(
            self._action_btns_frame, text="🔄", width=32,
            command=self._restart, **theme.btn_style("warning", font_size="lg")
        )
        ToolTip(self._restart_btn, t("tooltip.restart_btn"))
        self._update_button_visibility()

    def _open_in_explorer(self):
        path = self._repo.path
        try:
            if os.name == 'nt':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            if hasattr(self, '_global_log') and self._global_log:
                self._global_log(f"Error opening explorer: {e}", level="error")

    def _update_button_visibility(self):
        """Show only relevant action buttons based on status."""
        if not hasattr(self, '_start_btn'):
            return

        is_installing = getattr(self, '_is_installing', False)
        is_running = self._status in ('running', 'starting')

        # Skip costly relayout if nothing changed since the last call
        new_state = (is_installing, is_running)
        if getattr(self, '_last_btn_vis_state', None) == new_state:
            return
        self._last_btn_vis_state = new_state

        self._start_btn.pack_forget()
        self._stop_btn.pack_forget()
        self._restart_btn.pack_forget()

        if is_installing:
            if is_running:
                self._stop_btn.pack(side="left", padx=(0, 2))
                self._stop_btn.configure(state="disabled")
                self._restart_btn.pack(side="left", padx=(0, 2))
                self._restart_btn.configure(state="disabled")
            else:
                self._start_btn.pack(side="left", padx=(0, 2))
                self._start_btn.configure(state="disabled")
        else:
            if is_running:
                self._stop_btn.pack(side="left", padx=(0, 2))
                self._stop_btn.configure(state="normal")
                self._restart_btn.pack(side="left", padx=(0, 2))
                self._restart_btn.configure(state="normal")
            else:
                self._start_btn.pack(side="left", padx=(0, 2))
                self._start_btn.configure(state="normal")

        if hasattr(self, '_install_btn'):
            if is_running:
                self._install_btn.configure(state="disabled")
            elif not is_installing:
                self._install_btn.configure(state="normal")

    def _update_header_hints(self):
        """Update the branch + profile hint text in the header."""
        if not self.winfo_exists():
            return
        parts = []
        # Branch
        if hasattr(self, '_branch_combo'):
            branch = self._branch_combo.get()
            if branch and branch != "cargando...":
                parts.append(f"⎇ {branch}")
        elif self._current_branch:
            parts.append(f"⎇ {self._current_branch}")
        # Profile / Env
        if hasattr(self, '_config_combos') and self._config_combos:
            for _, combo in self._config_combos.items():
                v = combo.get()
                if v and v not in (t("label.no_selection"), ''):
                    parts.append(f"⚙ {v}")
                    break
        else:
            pending = getattr(self, '_pending_profile', None)
            if isinstance(pending, dict):
                for v in pending.values():
                    if v and v not in (t("label.no_selection"), ''):
                        parts.append(f"⚙ {v}")
                        break
            elif isinstance(pending, str) and pending:
                parts.append(f"⚙ {pending}")
        # Custom command
        if hasattr(self, '_cmd_entry'):
            cmd = self._cmd_entry.get().strip()
            if cmd:
                parts.append(f"$ {cmd}")
            elif self._repo.run_command:
                parts.append(f"$ {self._repo.run_command}")
        elif self._repo.run_command:
            parts.append(f"$ {self._repo.run_command}")

        is_installed = True
        install_cfg = getattr(self._repo, 'ui_config', {}).get('install', {})
        check_dirs = install_cfg.get('check_dirs', []) if install_cfg else []

        if check_dirs:
            for cd in check_dirs:
                if not os.path.isdir(os.path.join(self._repo.path, cd)):
                    is_installed = False
                    break

        if not is_installed and self._repo.run_install_cmd:
            warn_text = t("install.status_deps_missing")
            hint_text = ("   " + "   ".join(parts)) if parts else ""
        else:
            warn_text = ""
            hint_text = "   ".join(parts)

        # Only push to widgets when content actually changed (avoids redundant redraws)
        new_hints = (warn_text, hint_text)
        if getattr(self, '_last_header_hints_state', None) == new_hints:
            return
        self._last_header_hints_state = new_hints
        self._branch_hint_warn.configure(text=warn_text)
        self._branch_hint.configure(text=hint_text)
