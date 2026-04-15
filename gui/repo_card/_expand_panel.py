"""_expand_panel.py — Expand panel UI mixin for RepoCard."""
from __future__ import annotations
import os
import customtkinter as ctk
import tkinter as tk
from gui import theme
from gui.tooltip import ToolTip
from gui.widgets import SearchableCombo
from gui.constants import BADGE_REFRESH_MS
from gui.log_helpers import insert_log_line
from core.i18n import t

_JAVA_DEFAULT = None  # lazily resolved from i18n on first use


def _java_default_label() -> str:
    global _JAVA_DEFAULT
    if _JAVA_DEFAULT is None:
        _JAVA_DEFAULT = t("label.java_default")
    return _JAVA_DEFAULT


class ExpandPanelMixin:
    """Mixin providing expand panel construction, toggle, status updates."""

    # ─── Build expand panel ───────────────────────────────────────

    def _build_expand_panel(self):
        """Build the expandable details panel."""
        repo = self._repo

        # corner_radius para encajar bien sin tapar las esquinas del padre
        self._expand_panel = ctk.CTkFrame(self, fg_color=theme.C.expand_panel, corner_radius=theme.G.corner_panel)

        ctk.CTkFrame(self._expand_panel, height=1, fg_color=theme.C.divider).pack(fill="x", padx=10)

        content = ctk.CTkFrame(self._expand_panel, fg_color="transparent")
        content.pack(fill="x", padx=12, pady=(4, 4))

        # Row 1: Branch + secondary buttons
        self._build_branch_row(content, repo)
        # Row 2: Conditional selectors
        self._build_selector_row(content, repo)
        # Row 3: Custom start command
        if repo.repo_type != 'docker-infra':
            self._build_command_row(content, repo)
        # Row 3.5: Docker Checkboxes (Below Cmd)
        self._build_docker_row(content, repo)
        # Row 4: Logs
        self._build_log_row(content)

        # Docker status prefetch — runs once on first expand, not at startup
        if getattr(self._repo, 'docker_compose_files', None):
            self.after(600, self._prefetch_docker_status)

    def _build_log_row(self, content):
        """Build the repository log console."""
        self._log_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._log_frame.pack(fill="x", pady=(4, 0))

        header = ctk.CTkFrame(self._log_frame, fg_color="transparent")
        header.pack(fill="x")

        self._log_section_label = ctk.CTkLabel(header, text=t("label.log_section"), font=theme.font("base", bold=True), text_color=theme.C.text_secondary)
        self._log_section_label.pack(side="left")

        clear_btn = ctk.CTkButton(
            header, text=t("btn.clear_log"), width=60,
            command=self._clear_logs, **theme.btn_style("log_action", height="sm")
        )
        clear_btn.pack(side="right")

        detach_btn = ctk.CTkButton(
            header, text=t("btn.detach_log"), width=80,
            command=self._detach_logs, **theme.btn_style("log_action", height="sm")
        )
        detach_btn.pack(side="right", padx=(0, 6))

        self._log_textbox = ctk.CTkTextbox(
            self._log_frame, height=120,
            state="disabled", **theme.log_textbox_style()
        )
        self._log_textbox.pack(fill="x", pady=(4, 0))

        # Flush log lines that arrived before the panel was first opened
        if self._pre_panel_log_buffer:
            for buffered_line in self._pre_panel_log_buffer:
                insert_log_line(self._log_textbox, buffered_line, count_ref=self._log_line_count)
            self._pre_panel_log_buffer.clear()

    def _build_branch_row(self, content, repo):
        """Build branch + secondary buttons row."""
        row1 = ctk.CTkFrame(content, fg_color="transparent")
        row1.pack(fill="x")

        self._build_branch_combo_section(row1)

        # Pull
        self._pull_btn = ctk.CTkButton(
            row1, text="⬇ Pull", width=65,
            command=self._pull, **theme.btn_style("blue")
        )
        self._pull_btn.pack(side="left", padx=(0, 3))
        ToolTip(self._pull_btn, t("tooltip.pull_btn"))

        # Clean
        self._clean_btn = ctk.CTkButton(
            row1, text=t("btn.clean"), width=80,
            command=self._clean_repo, **theme.btn_style("purple")
        )
        self._clean_btn.pack(side="left", padx=(0, 3))
        ToolTip(self._clean_btn, t("tooltip.clean_btn"))

        # Config
        if not repo.environment_files and repo.repo_type != 'docker-infra':
            edit_btn = ctk.CTkButton(
                row1, text=t("btn.config"), width=80,
                command=self._edit_config, **theme.btn_style("neutral")
            )
            edit_btn.pack(side="left")
            ToolTip(edit_btn, t("tooltip.config_btn"))

        # Right-aligned frame for install buttons
        self.right_frame = ctk.CTkFrame(row1, fg_color="transparent", width=0, height=0)
        self.right_frame.pack(side="right", padx=(10, 0))

        # Install Button
        self._build_install_btn(self.right_frame)

    def _build_branch_combo_section(self, row):
        """Build the branch combo box and fetch button within the branch row."""
        ctk.CTkLabel(row, text=t("label.branch"), font=theme.font("lg"),
                     text_color=theme.C.text_secondary, width=50, anchor="e").pack(side="left")

        initial_branches = self._branches_cache if getattr(self, '_branches_cache', None) else [t("label.loading")]
        self._branch_combo = SearchableCombo(
            row, values=initial_branches, width=180,
            command=self._on_branch_change, **theme.combo_style()
        )
        if getattr(self, '_current_branch', None):
            self._branch_combo.set(self._current_branch)
        self._branch_combo.pack(side="left", padx=(6, 4))

        reload_btn = ctk.CTkButton(
            row, text="🔄", width=28,
            command=self._reload_repo, **theme.btn_style("log_action")
        )
        reload_btn.pack(side="left", padx=(0, 6))
        ToolTip(reload_btn, t("tooltip.reload_repo"))

        branch_chk = ctk.CTkCheckBox(
            row, text="", variable=self._branch_in_profile_var,
            width=20,
            checkbox_width=theme.G.checkbox_size, checkbox_height=theme.G.checkbox_size,
            command=self._trigger_change_callback,
        )
        branch_chk.pack(side="left", padx=(0, 10))
        ToolTip(branch_chk, t("tooltip.branch_in_profile"))

    def _build_install_btn(self, parent):
        """Build the general install button (Install or Reinstall) based on UI Config."""
        repo = self._repo
        path = repo.path

        install_cfg = getattr(repo, 'ui_config', {}).get('install', {})
        if not install_cfg and not repo.run_install_cmd:
            return

        check_dirs = install_cfg.get('check_dirs', [])

        # If check_dirs exist, check them. If not, we assume it's not installed yet,
        # or it can never be "installed" in a persistent folder sense.
        is_installed = False
        if check_dirs:
            is_installed = True
            for cd in check_dirs:
                if not os.path.isdir(os.path.join(path, cd)):
                    is_installed = False
                    break

        # Exact command
        if is_installed and repo.run_reinstall_cmd:
            cmd_str = repo.run_reinstall_cmd
        elif repo.run_install_cmd:
            cmd_str = repo.run_install_cmd
        else:
            cmd_str = ""  # Should never happen if 'install' config is present, but just in case

        if not cmd_str:
            return

        tooltip_text = cmd_str

        if is_installed:
            btn_text = t("install.label_ok")
            _variant = "neutral_alt"
        else:
            btn_text = t("install.label_missing")
            _variant = "danger_alt"

        self._install_btn = ctk.CTkButton(
            parent, text=btn_text, width=100,
            command=self._run_install_cmd, **theme.btn_style(_variant)
        )
        self._install_btn.pack(side="left", padx=(0, 6))
        self._install_tooltip = ToolTip(self._install_btn, tooltip_text)

    # ─── Selector row (decomposed) ────────────────────────────────

    def _build_config_combo_section(self, frame, repo):
        """Build config profile selector section."""
        from core.config_manager import load_repo_configs, load_active_config

        env_dirs: dict = {}
        for f in repo.environment_files:
            parent = os.path.dirname(f)
            basename = os.path.basename(f)
            if parent not in env_dirs:
                env_dirs[parent] = f
            else:
                # Priority rules if we already have a file for this directory:
                # 1. Prefer .yml over .properties
                # 2. Prefer environment.ts over specific like environment.prod.ts
                current_file = env_dirs[parent]
                if (current_file.endswith('.properties') and basename.endswith('.yml')) or basename == 'environment.ts':
                    env_dirs[parent] = f

        target_files = sorted(list(env_dirs.values()))
        self._config_combos = {}

        # Extract label prefix from UI config if defined, defaults to 'App'
        lbl_prefix = "App"
        if getattr(repo, 'ui_config', {}) and 'selectors' in repo.ui_config:
            selectors = repo.ui_config['selectors']
            if selectors and isinstance(selectors, list):
                lbl_prefix = selectors[0].get('label', 'App').replace(':', '')

        # Vertical container — use fill=x only, no expand, to keep compact height
        selectors_container = ctk.CTkFrame(frame, fg_color="transparent")
        selectors_container.pack(side="left", padx=0, fill="x", expand=True)

        for target_file in target_files:
            self._build_env_file_selector(selectors_container, target_file, repo, lbl_prefix, target_files)

    def _build_env_file_selector(self, container, target_file, repo, lbl_prefix, all_target_files):
        """Build one selector row (combo + config button + hint label) for a single env file."""
        from core.config_manager import load_repo_configs, load_active_config

        sel_frame = ctk.CTkFrame(container, fg_color="transparent")
        sel_frame.pack(side="top", fill="x", pady=(0, 4))

        # Identify submodule name for tooltip/label
        try:
            rel_path = os.path.relpath(target_file, repo.path)
            mod_name = os.path.dirname(rel_path) or "root"
        except ValueError:
            mod_name = "unknown"

        config_key = self.get_config_key(target_file)
        configs = load_repo_configs(config_key)
        opts = [t("label.no_selection")] + list(configs.keys())

        ctk.CTkLabel(sel_frame, text=f"{lbl_prefix}:", font=theme.font("lg"),
                     text_color=theme.C.text_secondary, width=50, anchor="e").pack(side="left")

        combo = SearchableCombo(
            sel_frame, values=opts, width=180,
            command=lambda val, tf=target_file: self._on_config_change(val, tf),
            **theme.combo_style()
        )
        combo.pack(side="left", padx=(6, 4))

        active_config = load_active_config(config_key)

        # Prefer pending profile value (set by _apply_config before panel was built)
        pending = getattr(self, '_pending_profile', None)
        if pending is not None:
            if isinstance(pending, dict):
                try:
                    rel_tf = os.path.relpath(target_file, repo.path).replace('\\', '/')
                    pending_val = pending.get(rel_tf) or pending.get(target_file)
                except ValueError:
                    pending_val = pending.get(target_file)
            else:
                pending_val = pending
        else:
            pending_val = None

        chosen = pending_val if (pending_val and pending_val in opts) else (active_config if active_config in opts else None)
        if chosen:
            combo.set(chosen)
            self.after(500, self._on_config_change, chosen, target_file, True)
        else:
            combo.set(t("label.no_selection"))

        self._config_combos[target_file] = combo

        cfg_btn = ctk.CTkButton(
            sel_frame, text="⚙", width=28,
            command=lambda tf=target_file: self._open_config_manager(tf),
            **theme.btn_style("neutral", font_size="xl")
        )
        cfg_btn.pack(side="left", padx=(0, 6))
        ToolTip(cfg_btn, t("tooltip.modify_config", name=mod_name))

        # Per-file checkbox: determine initial tracked state
        tracked_keys = getattr(self, '_pending_profile_tracked_keys', None)
        if tracked_keys is None:
            is_tracked = True  # default: all env files tracked
        else:
            try:
                rel_tf = os.path.relpath(target_file, repo.path).replace('\\', '/')
            except ValueError:
                rel_tf = target_file
            is_tracked = rel_tf in tracked_keys

        var = self._profile_in_profile_vars.setdefault(target_file, ctk.BooleanVar(value=is_tracked))
        profile_chk = ctk.CTkCheckBox(
            sel_frame, text="", variable=var,
            width=20,
            checkbox_width=theme.G.checkbox_size, checkbox_height=theme.G.checkbox_size,
            command=self._trigger_change_callback,
        )
        profile_chk.pack(side="left", padx=(0, 10))
        ToolTip(profile_chk, t("tooltip.env_in_profile"))

        # Type label on the right as plain grey hint
        if len(all_target_files) > 1:
            ctk.CTkLabel(sel_frame, text=mod_name, font=theme.font("xs", mono=True),
                         text_color=theme.C.text_faint, anchor="w").pack(side="left", padx=(0, 8))

    def _build_java_combo_section(self, frame, repo):
        """Build Java version selector section (~30 lines)."""
        combo_style = theme.combo_style()
        ctk.CTkLabel(frame, text=t("label.java"), font=theme.font("lg"),
                     text_color=theme.C.text_secondary, width=50, anchor="e").pack(side="left")
        java_options = [_java_default_label()] + list(self._java_versions.keys())
        self._java_combo = SearchableCombo(
            frame, values=java_options, width=150,
            variable=self.selected_java_var, **combo_style
        )
        self._java_combo.pack(side="left", padx=(6, 12))

        if getattr(repo, 'java_version', None):
            self._java_hint_label = ctk.CTkLabel(frame, text=t("label.java_recommended", version=repo.java_version), font=theme.font("md"), text_color=theme.C.text_faint)
            self._java_hint_label.pack(side="left", padx=(0, 10))

            def _on_java_change(*args):
                if not hasattr(self, '_java_hint_label') or not self._java_hint_label.winfo_exists():
                    return
                if self.selected_java_var.get() == _java_default_label():
                    self._java_hint_label.pack(side="left", padx=(0, 10))
                else:
                    self._java_hint_label.pack_forget()

            self.selected_java_var.trace("w", _on_java_change)
            _on_java_change()

    def _build_selector_row(self, content, repo):
        """Build conditional selector row (profile, DB, env, docker)."""
        row2 = ctk.CTkFrame(content, fg_color="transparent")
        has_row2 = False

        if repo.environment_files and repo.repo_type != 'docker-infra':
            has_row2 = True
            self._build_config_combo_section(row2, repo)

        if has_row2:
            row2.pack(fill="x", pady=(4, 0))

        row_java = ctk.CTkFrame(content, fg_color="transparent")
        has_row_java = False

        if 'java_version' in repo.features:
            has_row_java = True
            self._build_java_combo_section(row_java, repo)

        if has_row_java:
            row_java.pack(fill="x", pady=(4, 0))

    def update_java_versions(self, versions: dict):
        """Update available Java versions without restarting."""
        self._java_versions = versions
        if hasattr(self, '_java_combo'):
            java_options = [_java_default_label()] + list(self._java_versions.keys())
            self._java_combo.configure(values=java_options)

            # If current selection is no longer valid, reset to default
            current = self.selected_java_var.get()
            if current not in java_options:
                self.selected_java_var.set(_java_default_label())

    def _build_command_row(self, content, repo):
        """Build custom start command row."""
        row3 = ctk.CTkFrame(content, fg_color="transparent")
        row3.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(row3, text=t("label.cmd"), font=theme.font("lg"),
                     text_color=theme.C.text_secondary, width=50, anchor="e").pack(side="left")

        self._cmd_entry = ctk.CTkEntry(
            row3, height=theme.G.btn_height_md, font=theme.font("md", mono=True),
            corner_radius=theme.G.corner_btn, fg_color=theme.C.section,
            border_color=theme.C.default_border,
            placeholder_text=repo.run_command or t("label.cmd_placeholder")
        )
        self._cmd_entry.pack(side="left", padx=(6, 4), fill="x", expand=True)
        pending_cmd = getattr(self, '_pending_custom_command', '')
        if pending_cmd:
            self._cmd_entry.insert(0, pending_cmd)
        ToolTip(self._cmd_entry, t("tooltip.cmd_entry", cmd=repo.run_command or 'N/A'))

        # Update header hints when command changes
        def _on_cmd_changed(e):
            self._update_header_hints()
            self._trigger_change_callback()

        self._cmd_entry.bind("<FocusOut>", _on_cmd_changed)
        self._cmd_entry.bind("<Return>", _on_cmd_changed)

    def _build_docker_row(self, content, repo):
        """Build docker-compose checkboxes row."""
        if 'docker_checkboxes' not in repo.features or not repo.docker_compose_files:
            return

        row_docker = ctk.CTkFrame(content, fg_color="transparent")
        row_docker.pack(fill="x", pady=(4, 0))

        docker_frame = ctk.CTkFrame(row_docker, fg_color="transparent")
        docker_frame.pack(side="left", padx=(1, 0))

        for dc_file in repo.docker_compose_files:
            dc_name = os.path.basename(dc_file)
            if dc_name == 'docker-compose.yml':
                dc_name = 'docker-compose'
            elif dc_name.startswith('docker-compose.'):
                dc_name = dc_name.replace('docker-compose.', '').replace('.yml', '')

            if dc_name == 'all':
                continue

            cached = self._docker_status_cache.get(dc_file)
            initial_text = f"🐳 {dc_name.title()} [{cached[0]}/{cached[1]}]" if cached else f"🐳 {dc_name.title()} [?/?]"

            # Border reflects running containers if we already have cached data
            if cached and cached[0] > 0:
                btn_color = theme.C.docker_active_fg
                border_color = theme.C.docker_border_running
            elif dc_file in self._active_compose_files:
                btn_color = theme.C.docker_active_fg
                border_color = theme.C.docker_border_active
            else:
                btn_color = theme.C.docker_stopped_fg
                border_color = theme.C.docker_border_stopped
            btn = ctk.CTkButton(
                docker_frame, text=initial_text,
                font=theme.font("md"), height=26,
                fg_color=btn_color, hover_color=theme.C.subtle_border,
                border_width=theme.G.border_width, border_color=border_color,
                corner_radius=theme.G.corner_btn,
                command=lambda f=dc_file: self._open_docker_compose_dialog(f)
            )
            btn.pack(side="left", padx=(0, 6))
            self._docker_compose_buttons[dc_file] = btn

            if dc_file in self._active_compose_files:
                ToolTip(btn, t("tooltip.docker_manage_active"))
            else:
                ToolTip(btn, t("tooltip.docker_manage"))

        # Start thread to update container counts if not running
        if not self._compose_status_thread_running:
            self._compose_status_thread_running = True
            self._start_compose_status_thread()

    # ─── Toggle expand ───────────────────────────────────────────

    def _toggle_expand(self, event=None):
        """Toggle expanded/collapsed state. Builds the panel lazily on first open."""
        self._expanded = not self._expanded
        if self._expanded:
            if not self._expand_panel_built:
                self._build_expand_panel()
                self._expand_panel_built = True
            self._expand_panel.pack(fill="x", padx=3, pady=(0, 2), after=self._header)
            self._toggle_btn.configure(text="▲")
        else:
            self._expand_panel.pack_forget()
            self._toggle_btn.configure(text="▼")

    # ─── Config editing ──────────────────────────────────────────

    def _edit_config(self):
        """Open config editor."""
        repo = self._repo
        config_files = self._get_config_files(repo)
        if not config_files:
            return
        if len(config_files) == 1:
            if self._on_edit_config:
                self._on_edit_config(config_files[0])
        else:
            self._show_file_selector(config_files)

    def _get_config_files(self, repo):
        """Collect config files for the repo type."""
        files = list(repo.environment_files) if repo.environment_files else []
        if getattr(repo, 'docker_compose_files', None):
            files.extend(repo.docker_compose_files)
        return files

    def _show_file_selector(self, files: list):
        """Show a popup to select which config file to edit."""
        popup = ctk.CTkToplevel(self)
        popup.title(t("dialog.select_file_title"))
        popup.geometry("400x300")
        popup.transient(self)
        popup.grab_set()

        ctk.CTkLabel(popup, text=t("label.select_file_to_edit"),
                     font=theme.font("base", bold=True)).pack(pady=(15, 10))

        scroll = ctk.CTkScrollableFrame(popup)
        scroll.pack(fill="both", expand=True, padx=15, pady=5)

        for f in files:
            btn = ctk.CTkButton(
                scroll, text=os.path.basename(f),
                font=theme.font("md"), height=32,
                fg_color="transparent",
                text_color=(theme.C.file_btn_light, theme.C.file_btn_dark),
                hover_color=(theme.C.file_btn_hover_light, theme.C.file_btn_hover_dark),
                anchor="w",
                command=lambda fp=f: (popup.destroy(),
                                      self._on_edit_config(fp) if self._on_edit_config else None)
            )
            btn.pack(fill="x", padx=5, pady=2)

    # ─── Status updates ──────────────────────────────────────────

    def _update_status(self, name: str, status: str):
        """Update the status display."""
        self._status = status

        def _update():
            # Cancel any pending log-flash revert so it doesn't override the new status color
            if hasattr(self, '_log_flash_timer') and self._log_flash_timer:
                self.after_cancel(self._log_flash_timer)
                self._log_flash_timer = None
            color = theme.STATUS_ICONS.get(status, theme.C.status_stopped)
            if status == 'logging':
                color = theme.STATUS_ICONS.get('logging', theme.C.status_logging)
            self._status_label.configure(text="🔴", text_color=color)
            status_texts = {
                'running':    t("label.status.running_port", port=self._repo.server_port or '?'),
                'starting':   t("label.status.starting"),
                'installing': t("label.status.installing"),
                'stopped':    t("label.status.stopped"),
                'error':      t("label.status.error"),
            }
            self._status_text.configure(
                text=status_texts.get(status, status),
                text_color=theme.COLORS.get(status, '#888')
            )
            self._update_button_visibility()

        try:
            self.after(0, _update)
        except tk.TclError:
            pass

    def _on_status_change(self, name: str, status: str):
        """Callback from ServiceLauncher when status changes."""
        if name != self._repo.name:
            return

        self._status = status

        def _update():
            # Basic info updater that was decoupled
            color = theme.STATUS_ICONS.get(status, theme.C.status_stopped)
            if status == 'logging':
                color = theme.STATUS_ICONS.get('logging', theme.C.status_logging)
            self._status_label.configure(text="🔴", text_color=color)
            status_text = {
                'running': t("label.status.running"),
                'starting': t("label.status.starting"),
                'stopped': t("label.status.stopped"),
                'error': t("label.status.error"),
            }.get(status, status)
            self._status_text.configure(
                text=status_text,
                text_color=theme.COLORS.get(status, '#888')
            )
            self._update_button_visibility()

        try:
            self.after(0, _update)
        except tk.TclError:
            pass
