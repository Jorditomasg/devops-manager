"""ProfileDialog and ImportOptionsDialog — profile management dialogs."""
import os
import json
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui import theme
from gui.constants import PROFILE_DIRTY_SUFFIX
from core.i18n import t


def _unique_profile_name(base: str, existing: list) -> str:
    """Return first non-colliding name: base1, base2, …"""
    n = 1
    while True:
        candidate = f"{base}{n}"
        if candidate not in existing:
            return candidate
        n += 1


def _profiles_equal(a: dict, b: dict) -> bool:
    """Compare two profile dicts ignoring 'name' and 'created' metadata."""
    skip = {'name', 'created'}
    return {k: v for k, v in a.items() if k not in skip} == \
           {k: v for k, v in b.items() if k not in skip}


class ProfileDialog(BaseDialog):
    """Dialog for managing profiles: save, load, import, export."""

    def __init__(self, parent, workspace_dir: str, repos: list,
                 repo_cards: list = None,
                 log_callback=None, on_profile_loaded=None,
                 on_rescan=None, on_profiles_changed=None):
        super().__init__(parent, t("dialog.profile.title"), 580, 520)

        self._workspace_dir = workspace_dir
        self._repos = repos
        self._repo_cards = repo_cards or []
        self._log = log_callback
        self._on_profile_loaded = on_profile_loaded
        self._on_rescan = on_rescan
        self._on_profiles_changed = on_profiles_changed

        self._main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._main_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(self._main_scroll, text=t("dialog.profile.section_title"),
                     font=theme.font("h2", bold=True)).pack(pady=(15, 10))

        self._build_save_section(self._main_scroll)
        self._build_list_section(self._main_scroll)
        self._build_action_buttons(self._main_scroll)

        ctk.CTkLabel(
            self._main_scroll, text=t("dialog.profile.help_text"),
            font=theme.font("sm"), text_color=theme.C.text_placeholder,
            justify="left"
        ).pack(padx=20, pady=(10, 15))

    def _build_save_section(self, scroll):
        """Build the save-name entry, save button and options checkboxes."""
        save_frame = ctk.CTkFrame(scroll, corner_radius=8)
        save_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(save_frame, text=t("dialog.profile.save_current"),
                     font=theme.font("base", bold=True)).pack(anchor="w", padx=10, pady=(10, 5))

        name_row = ctk.CTkFrame(save_frame, fg_color="transparent")
        name_row.pack(fill="x", padx=10, pady=(0, 4))

        self._save_name = ctk.CTkEntry(name_row, width=300,
                                        placeholder_text=t("dialog.profile.name_placeholder"))
        self._save_name.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            name_row, text=t("dialog.profile.btn_save"), width=100,
            command=self._save_profile, **theme.btn_style("success")
        ).pack(side="left")

        opts_row = ctk.CTkFrame(save_frame, fg_color="transparent")
        opts_row.pack(fill="x", padx=10, pady=(0, 10))

        self._include_files_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts_row, text=t("dialog.profile.include_config_files"), variable=self._include_files_var,
            font=theme.font("md"),
            checkbox_width=theme.G.checkbox_size, checkbox_height=theme.G.checkbox_size
        ).pack(side="left")

    def _build_list_section(self, scroll):
        """Build the scrollable list of saved profiles with load/delete/export buttons."""
        load_frame = ctk.CTkFrame(scroll, corner_radius=8)
        load_frame.pack(fill="x", padx=20, pady=5)
        self._list_section_frame = load_frame

        ctk.CTkLabel(load_frame, text=t("dialog.profile.saved_list_title"),
                     font=theme.font("base", bold=True)).pack(anchor="w", padx=10, pady=(10, 5))

        self._profile_list_frame = ctk.CTkScrollableFrame(
            load_frame, height=120, fg_color=theme.C.section_alt,
            border_width=theme.G.border_width, border_color=theme.C.subtle_border
        )
        self._profile_list_frame.pack(fill="x", padx=10, pady=5)

        self._selected_profile = ctk.StringVar(value="")
        self._profile_btns: dict = {}   # profile_name -> CTkButton (avoids full list rebuild on selection)
        self._refresh_list()

        btn_row = ctk.CTkFrame(load_frame, fg_color="transparent")
        btn_row.pack(pady=(0, 10))

        ctk.CTkButton(
            btn_row, text=t("dialog.profile.btn_load"), width=100,
            command=self._load_profile, **theme.btn_style("blue")
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text=t("dialog.profile.btn_delete"), width=100,
            command=self._delete_profile, **theme.btn_style("danger_deep")
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text=t("dialog.profile.btn_export"), width=100,
            command=self._export_profile, **theme.btn_style("warning")
        ).pack(side="left")

    def _build_action_buttons(self, scroll):
        """Build the import-from-file section."""
        import_frame = ctk.CTkFrame(scroll, corner_radius=8)
        import_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(import_frame, text=t("dialog.profile.import_external"),
                     font=theme.font("base", bold=True)).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkButton(
            import_frame, text=t("dialog.profile.btn_import"), width=250,
            command=self._import_profile, **theme.btn_style("purple")
        ).pack(padx=10, pady=(0, 10))

    def _save_profile(self):
        name = self._save_name.get().strip()
        if not name:
            messagebox.showwarning(t("misc.error_title"), t("dialog.profile.error_no_name"))
            return

        from core.profile_manager import build_profile_data, save_profile, list_profiles

        # Check if profile with this name already exists
        existing_profiles = list_profiles()
        if name in existing_profiles:
            if not messagebox.askyesno(t("dialog.profile.overwrite_title"), t("dialog.profile.overwrite_msg", name=name)):
                return

        include_files = self._include_files_var.get()

        profile_data = build_profile_data(
            self._repo_cards,
            include_config_files=include_files
        )

        save_profile(name, profile_data)

        if self._log:
            extra_str = " (con config files)" if include_files else ""
            self._log(f"Configuración guardada: {name}{extra_str}")

        messagebox.showinfo(t("dialog.profile.saved_title"), t("dialog.profile.saved_msg", name=name))
        self._refresh_list()

        if self._on_profiles_changed:
            self._on_profiles_changed(name)

    def _load_profile(self):
        name = self._selected_profile.get()
        if not name or name == "(Sin configs)":
            messagebox.showwarning(t("misc.warning_title"), t("dialog.profile.error_no_selection"))
            return

        from core.profile_manager import load_profile
        data = load_profile(name)
        if not data:
            messagebox.showerror(t("misc.error_title"), t("dialog.profile.error_load_failed", name=name))
            return

        self._apply_profile_data(data)

    def _apply_profile_data(self, data: dict):
        """Apply a profile, showing import options dialog if needed."""
        changes_text = self._build_changes_text(data)

        if changes_text == t("dialog.profile.no_changes"):
            # If nothing really changes (or everything is identical), apply directly.
            self._apply_basic_config(data)
            return
        else:
            from core.profile_manager import get_missing_repos
            missing = get_missing_repos(self._workspace_dir, data)
            has_files = any(
                r.get('config_files') for r in data.get('repos', {}).values()
            )

            ImportOptionsDialog(
                self, data,
                changes_text=changes_text,
                missing_repos=missing,
                has_config_files=has_files,
                workspace_dir=self._workspace_dir,
                log_callback=self._log,
                on_complete=self._on_import_complete
            )

    def _describe_branch_changes(self, changes: list, target_repos: dict,
                                  current_repos: dict, missing_names: set):
        """Populate changes with branch and profile diffs for existing repos."""
        for repo_name, target_cfg in target_repos.items():
            if repo_name in missing_names:
                continue
            if repo_name in current_repos:
                cur_cfg = current_repos[repo_name]
                repo_changes = []

                # Check branch
                if target_cfg.get('branch') and cur_cfg.get('branch') != target_cfg.get('branch'):
                    repo_changes.append(
                        t("dialog.profile.change_branch", from_val=cur_cfg.get('branch') or 'N/A', to_val=target_cfg.get('branch'))
                    )

                # Check profile
                cur_profile = cur_cfg.get('profile') or 'N/A'
                tgt_profile = target_cfg.get('profile') or 'N/A'
                if tgt_profile != 'N/A' and cur_profile != tgt_profile:
                    repo_changes.append(t("dialog.profile.change_profile", from_val=cur_profile, to_val=tgt_profile))

                if repo_changes:
                    changes.append(f"🔄 {repo_name}:\n    " + "\n    ".join(repo_changes))

    def _describe_command_changes(self, changes: list, target_repos: dict):
        """Append config files overwrite line to changes if present."""
        n_files = sum(len(r.get('config_files', {})) for r in target_repos.values())
        if n_files > 0:
            changes.append(t("dialog.profile.changes_overwrite_files", count=n_files))

    def _build_changes_text(self, data: dict) -> str:
        """Comparar el data con el estado actual de los repos."""
        from core.profile_manager import build_profile_data, get_missing_repos
        current_data = build_profile_data(
            self._repo_cards,
            include_config_files=False
        )

        changes = []

        # 1. Repos faltantes (to clone)
        missing = get_missing_repos(self._workspace_dir, data)
        for m in missing:
            changes.append(t("dialog.profile.changes_clone_repo", name=m['name'], branch=m['branch']))

        # 2. Diferencias en repositorios existentes
        target_repos = data.get('repos', {})
        current_repos = current_data.get('repos', {})
        missing_names = {m['name'] for m in missing}

        self._describe_branch_changes(changes, target_repos, current_repos, missing_names)

        # 3. Config files
        self._describe_command_changes(changes, target_repos)

        if not changes:
            return t("dialog.profile.no_changes")

        return "\n\n".join(changes)

    def _apply_basic_config(self, data: dict):
        """Apply basic config (branch, profile, cmd) without interactive dialog."""
        if self._on_profile_loaded:
            self._on_profile_loaded(data)
        if self._log:
            self._log(t("log.profile_applied", name=data.get('name', '??')))
        messagebox.showinfo(t("dialog.profile.loaded_title"), t("dialog.profile.loaded_msg"))
        self.destroy()

    def _on_import_complete(self, data: dict, did_clone: bool):
        """Called when the import options dialog finishes."""
        save_name = getattr(self, '_pending_save_profile_name', None)
        original_name = getattr(self, '_import_original_name', None)
        if save_name:
            from core.profile_manager import save_profile
            save_profile(save_name, data)
            self._pending_save_profile_name = None
            if self._log:
                self._log(t("log.profile_imported_saved", name=save_name))
            if self._on_profiles_changed:
                self._on_profiles_changed(save_name, original_name)
        if self._on_profile_loaded:
            self._on_profile_loaded(data)
        if did_clone and self._on_rescan:
            self._on_rescan()
        self.destroy()

    def _delete_profile(self):
        name = self._selected_profile.get()
        if not name or name == "(Sin configs)":
            messagebox.showwarning(t("misc.warning_title"), t("dialog.profile.error_no_selection"))
            return

        if messagebox.askyesno(t("dialog.profile.confirm_delete_title"), t("dialog.profile.confirm_delete_msg", name=name)):
            from core.profile_manager import delete_profile
            delete_profile(name)
            if self._log:
                self._log(f"Configuración eliminada: {name}")
            self._refresh_list()

            if self._on_profiles_changed:
                self._on_profiles_changed()

    def _export_profile(self):
        name = self._selected_profile.get()
        if not name or name == "(Sin configs)":
            messagebox.showwarning(t("misc.warning_title"), t("dialog.profile.error_no_selection"))
            return

        from core.profile_manager import load_profile, export_profile_to_file
        data = load_profile(name)
        if not data:
            messagebox.showerror(t("misc.error_title"), t("dialog.profile.error_export_failed"))
            return

        dest = filedialog.asksaveasfilename(
            title=t("dialog.profile.export_dialog_title"),
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f'{name}.json'
        )
        if dest:
            if export_profile_to_file(data, dest):
                messagebox.showinfo(t("dialog.profile.exported_title"), t("dialog.profile.exported_msg", path=dest))
            else:
                messagebox.showerror(t("misc.error_title"), t("dialog.profile.error_export_failed"))

    def _import_profile(self):
        filepath = filedialog.askopenfilename(
            title=t("dialog.profile.import_dialog_title"),
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")]
        )
        if not filepath:
            return

        from core.profile_manager import import_profile_from_file, list_profiles, load_profile
        data = import_profile_from_file(filepath)
        if not data:
            messagebox.showerror(t("misc.error_title"), t("dialog.profile.error_invalid_file"))
            return

        original_name = data.get('name', os.path.splitext(os.path.basename(filepath))[0])
        self._import_original_name = original_name  # stored for _on_import_complete

        existing = list_profiles()
        if original_name in existing:
            existing_data = load_profile(original_name)
            if existing_data and _profiles_equal(data, existing_data):
                messagebox.showinfo(
                    t("dialog.profile.no_changes_title"),
                    t("dialog.profile.no_changes_identical", name=original_name)
                )
                return
            profile_name = _unique_profile_name(original_name, existing)
        else:
            profile_name = original_name

        data['name'] = profile_name

        # Track that this import should be saved on completion
        self._pending_save_profile_name = profile_name

        # Show the import options dialog
        self._apply_profile_data(data)

    def _refresh_list(self):
        from core.profile_manager import list_profiles
        profiles = list_profiles()

        for widget in self._profile_list_frame.winfo_children():
            widget.destroy()
        self._profile_btns.clear()

        if not profiles:
            self._list_section_frame.pack_forget()
            self._selected_profile.set("")
            return

        self._list_section_frame.pack(fill="x", padx=20, pady=5)

        _blue = theme.btn_style("blue")
        _neutral = theme.btn_style("neutral")
        current_sel = self._selected_profile.get()
        for profile in profiles:
            is_sel = current_sel == profile
            fg = _blue["fg_color"] if is_sel else _neutral["fg_color"]
            btn = ctk.CTkButton(
                self._profile_list_frame, text=profile,
                anchor="w", fg_color=fg, hover_color=_blue["border_color"],
                font=theme.font("base", bold=True),
                command=lambda p=profile: self._select_profile_item(p)
            )
            btn.pack(fill="x", pady=2)
            self._profile_btns[profile] = btn

        # Ensure selection is valid
        if current_sel not in profiles:
            self._select_profile_item(profiles[0])

    def _select_profile_item(self, profile):
        prev = self._selected_profile.get()
        self._selected_profile.set(profile)
        # Populate save text input so it's easy to overwrite
        self._save_name.delete(0, "end")
        self._save_name.insert(0, profile)
        # Only update the two affected buttons instead of rebuilding the whole list
        _blue = theme.btn_style("blue")
        _neutral = theme.btn_style("neutral")
        if prev and prev in self._profile_btns:
            try:
                self._profile_btns[prev].configure(fg_color=_neutral["fg_color"])
            except Exception:
                pass
        if profile in self._profile_btns:
            try:
                self._profile_btns[profile].configure(fg_color=_blue["fg_color"])
            except Exception:
                pass


class ImportOptionsDialog(BaseDialog):
    """Interactive dialog shown when loading/importing a profile.
    Lets the user choose: clone repos, install deps, overwrite configs.
    """

    def __init__(self, parent, profile_data: dict,
                 changes_text: str = "",
                 missing_repos: list = None,
                 has_config_files: bool = False,
                 workspace_dir: str = '',
                 log_callback=None,
                 on_complete=None):
        super().__init__(parent, t("dialog.import.title"), 580, 650)
        self.minsize(500, 500)
        self.resizable(True, True)

        self._profile_data = profile_data
        self._missing = missing_repos or []
        self._workspace_dir = workspace_dir
        self._log = log_callback
        self._on_complete = on_complete
        self._did_clone = False

        self._init_java_info(parent, profile_data)

        self._main_container = ctk.CTkFrame(self, fg_color="transparent")
        self._main_container.pack(fill="both", expand=True)

        self._build_buttons_frame(self._main_container)

        self._content_area = ctk.CTkFrame(self._main_container, fg_color="transparent")
        self._content_area.pack(side="top", fill="both", expand=True, padx=5, pady=(5, 0))

        # --- STEP 1 ---
        self._step1_scroll = ctk.CTkScrollableFrame(self._content_area, fg_color="transparent")
        self._step1_scroll.pack(fill="both", expand=True)

        self._build_header_frame(self._step1_scroll)

        options_frame = ctk.CTkFrame(self._step1_scroll, corner_radius=8)
        options_frame.pack(fill="x", padx=10, pady=(0, 15))

        self._build_checkboxes_section(options_frame, has_config_files, profile_data)
        self._build_java_mappings_section(options_frame, profile_data)
        self._build_preview_section(self._step1_scroll)

        # --- STEP 2 ---
        self._step2_frame = ctk.CTkFrame(self._content_area, fg_color="transparent")
        self._build_progress_section(self._step2_frame)

        self._base_changes_text = changes_text
        self._update_preview()

    def _init_java_info(self, parent, profile_data: dict):
        """Detect which Java versions from the profile are missing locally."""
        app_instance = parent.master if hasattr(parent, 'master') else None
        self._local_javas = list(getattr(app_instance, '_java_versions', {}).keys()) if app_instance else []

        self._missing_javas = []
        profile_javas = set()
        for r in profile_data.get('repos', {}).values():
            jv = r.get('java_version')
            if jv and jv != "Sistema (Por Defecto)":
                profile_javas.add(jv)

        for p_java in profile_javas:
            if p_java not in self._local_javas:
                self._missing_javas.append(p_java)

    def _build_header_frame(self, parent):
        """Build the title label for the import options dialog."""
        ctk.CTkLabel(parent, text=t("dialog.import.section_title"),
                     font=theme.font("xxl", bold=True)).pack(anchor="w", padx=10, pady=(10, 5))

    def _build_buttons_frame(self, container):
        """Build the bottom Accept/Cancel buttons bar."""
        self._btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        self._btn_frame.pack(side="bottom", fill="x", padx=20, pady=10)

        self._apply_btn = ctk.CTkButton(
            self._btn_frame, text=t("dialog.import.btn_accept"), width=150,
            command=self._apply, **theme.btn_style("success", height="lg")
        )
        self._apply_btn.pack(side="right", padx=(10, 0))

        self._cancel_btn = ctk.CTkButton(
            self._btn_frame, text=t("btn.cancel"), width=100,
            command=self.destroy, **theme.btn_style("neutral", height="lg")
        )
        self._cancel_btn.pack(side="right")

    def _build_checkboxes_section(self, frame, has_config_files: bool, profile_data: dict):
        """Build repo selection checkboxes for clone, install, config files."""
        # ── Missing repos ──
        self._clone_var = ctk.BooleanVar(value=True if self._missing else False)

        if self._missing:
            ctk.CTkLabel(frame, text=t("dialog.import.missing_repos_title"),
                         font=theme.font("base", bold=True),
                         text_color=theme.C.status_starting).pack(anchor="w", padx=10, pady=(10, 0))

            missing_txt = ", ".join([m['name'] for m in self._missing])
            if len(missing_txt) > 80:
                missing_txt = missing_txt[:77] + "..."
            ctk.CTkLabel(frame, text=f"• {missing_txt}",
                         font=theme.font("md"), text_color=theme.C.text_muted).pack(anchor="w", padx=20)

            ctk.CTkCheckBox(frame, text=t("dialog.import.clone_missing"), variable=self._clone_var,
                            command=self._update_preview, checkbox_width=20, checkbox_height=20
                            ).pack(anchor="w", padx=10, pady=(5, 10))

        # ── Config files ──
        self._overwrite_configs_var = ctk.BooleanVar(value=True if has_config_files else False)
        if has_config_files:
            n_files = sum(len(r.get('config_files', {})) for r in profile_data.get('repos', {}).values())
            ctk.CTkCheckBox(frame, text=t("dialog.import.overwrite_files", count=n_files),
                            variable=self._overwrite_configs_var, command=self._update_preview,
                            checkbox_width=20, checkbox_height=20).pack(anchor="w", padx=10, pady=(5, 10))

    def _build_java_mappings_section(self, frame, profile_data: dict):
        """Build Java version mapping table for versions missing locally."""
        self._java_mappings = {}
        if self._missing_javas:
            ctk.CTkLabel(frame, text=t("dialog.import.map_java_title"),
                         font=theme.font("base", bold=True),
                         text_color=theme.C.status_starting).pack(anchor="w", padx=10, pady=(5, 0))

            for missing_jv in self._missing_javas:
                row = ctk.CTkFrame(frame, fg_color="transparent")
                row.pack(fill="x", padx=15, pady=2)
                ctk.CTkLabel(row, text=t("dialog.import.java_needs", version=missing_jv), width=140, anchor="e").pack(side="left", padx=(0, 10))
                options = ["Sistema (Por Defecto)"] + self._local_javas
                var = ctk.StringVar(value="Sistema (Por Defecto)")
                combo = ctk.CTkComboBox(row, values=options, variable=var, width=170)
                combo.pack(side="left")
                self._java_mappings[missing_jv] = var

                # Buscar qué repositorios necesitan esta versión
                repos_needing_java = []
                for repo_name, repo_cfg in profile_data.get('repos', {}).items():
                    if repo_cfg.get('java_version') == missing_jv:
                        repos_needing_java.append(repo_name)

                if repos_needing_java:
                    repos_txt = t("dialog.import.java_used_in") + ", ".join(repos_needing_java)
                    if len(repos_txt) > 50:
                        repos_txt = repos_txt[:47] + "..."
                    ctk.CTkLabel(row, text=repos_txt, font=theme.font("sm", mono=True),
                                 text_color=theme.C.text_placeholder).pack(side="left", padx=(10, 0))
            ctk.CTkLabel(frame, text="").pack(pady=2)

    def _build_preview_section(self, parent):
        """Build changes preview textbox for step 1."""
        ctk.CTkLabel(parent, text=t("dialog.import.changes_summary"),
                     font=theme.font("xl", bold=True)).pack(anchor="w", padx=10, pady=(5, 5))

        self._preview_box = ctk.CTkTextbox(parent, font=theme.font("md", mono=True), wrap="none", height=150)
        self._preview_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _build_progress_section(self, parent):
        """Build progress bar and log textbox for step 2."""
        ctk.CTkLabel(parent, text=t("dialog.import.applying_title"),
                     font=theme.font("xxl", bold=True)).pack(anchor="w", padx=10, pady=(10, 5))

        self._progress_label = ctk.CTkLabel(parent, text=t("dialog.import.preparing"), font=theme.font("base", bold=True),
                                            text_color=theme.C.text_primary)
        self._progress_label.pack(anchor="w", padx=10, pady=(10, 0))
        self._progress = ctk.CTkProgressBar(parent)
        self._progress.pack(fill="x", padx=10, pady=(5, 15))
        self._progress.set(0)

        self._log_detail_label = ctk.CTkLabel(parent, text=t("dialog.import.log_detail"),
                                              font=theme.font("base", bold=True))
        self._log_detail_label.pack(anchor="w", padx=10, pady=(5, 0))
        self._log_box = ctk.CTkTextbox(parent, font=theme.font("sm", mono=True),
                                       wrap="none", state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _update_preview(self):
        """Update the preview textbox dynamically based on selected checkboxes."""
        self._preview_box.configure(state="normal")
        self._preview_box.delete("1.0", "end")

        lines = []

        if self._base_changes_text and t("dialog.profile.no_changes") not in self._base_changes_text:
            lines.append(t("dialog.import.changes_header"))
            for line in self._base_changes_text.splitlines():
                if "Clonar nuevo repo" not in line and "Sobrescribir archivos" not in line and line.strip() != "":
                    lines.append(line)
            lines.append("")

        if self._clone_var.get() and self._missing:
            lines.append(t("dialog.import.clone_header"))
            for m in self._missing:
                repo_cfg = self._profile_data.get('repos', {}).get(m['name'], {})
                java_ver = repo_cfg.get('java_version')
                req_java_text = t("dialog.import.uses_java", version=java_ver) if java_ver and java_ver != "Sistema (Por Defecto)" else ""
                lines.append(t("dialog.import.will_clone", name=m['name'], branch=m.get('branch', 'default'), java=req_java_text))
            lines.append("")

        if self._overwrite_configs_var.get():
            n_files = sum(len(r.get('config_files', {})) for r in self._profile_data.get('repos', {}).values())
            lines.append(t("dialog.import.will_overwrite", count=n_files))

        if not lines:
            lines.append(t("dialog.import.no_changes_selected"))

        self._preview_box.insert("1.0", "\n".join(lines).strip())
        self._preview_box.configure(state="disabled")

    def _log_to_dialog(self, text: str):
        """Append a line to the in-dialog live log box (thread-safe)."""
        def _do():
            try:
                self._log_box.configure(state="normal")
                self._log_box.insert("end", text.rstrip() + "\n")
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
            except tk.TclError:
                pass
        self.after(0, _do)

    def _apply_repos(self, selected_repos: list, _update_progress):
        """Clone missing repos using ThreadPoolExecutor."""
        from core.git_manager import clone, checkout
        from concurrent.futures import ThreadPoolExecutor

        def _combined_log(text: str):
            if self._log:
                self._log(text)
            self._log_to_dialog(text)

        def _clone_repo(m):
            if not m['git_url']:
                _combined_log(f"[import] ⚠ {m['name']}: sin URL de repositorio, clonación omitida")
                _update_progress(f"⚠ {m['name']}: sin URL")
                return
            dest = os.path.join(self._workspace_dir, m['name'])
            try:
                self.after(0, lambda name=m['name']: self._progress_label.configure(
                    text=f"⏳ Clonando: {name}..."
                ))
            except tk.TclError:
                pass
            _combined_log(t("log.import_cloning", name=m['name']))
            success, msg = clone(m['git_url'], dest, _combined_log)
            if success and m.get('branch'):
                checkout(dest, m['branch'], _combined_log)
            if not success:
                _combined_log(t("log.import_clone_error", name=m['name'], msg=msg[:200]))
            _update_progress(f"✅ {m['name']}" if success else f"❌ Error: {m['name']}")
            self._did_clone = True

        with ThreadPoolExecutor(max_workers=5) as executor:
            for m in selected_repos:
                executor.submit(_clone_repo, m)

    def _apply_java_mappings(self):
        """Rewrite java_version in profile_data according to user mappings."""
        if self._missing_javas:
            for repo_name, repo_cfg in self._profile_data.get('repos', {}).items():
                jv = repo_cfg.get('java_version')
                if jv in self._missing_javas:
                    repo_cfg['java_version'] = self._java_mappings[jv].get()

    def _run_with_progress(self, steps: list):
        """Drive a progress bar through a list of callables, updating after each."""
        steps_total = max(len(steps), 1)
        steps_done = 0

        def _update_progress(text: str):
            nonlocal steps_done
            steps_done += 1
            pct = steps_done / steps_total
            try:
                self.after(0, lambda: (
                    self._progress.set(pct),
                    self._progress_label.configure(text=text)
                ))
            except tk.TclError:
                pass

        for step_fn in steps:
            step_fn(_update_progress)

    def _collect_import_settings(self) -> dict:
        """Read all checkbox/combo states and return them as a plain dict."""
        return {
            'clone': self._clone_var.get() and bool(self._missing),
            'overwrite_configs': self._overwrite_configs_var.get(),
        }

    def _schedule_import_done(self):
        """Schedule the final completion UI update on the main thread."""
        def _done():
            self._progress.set(1.0)
            self._progress_label.configure(text=t("dialog.import.completed"))
            
            def _close():
                if self._on_complete:
                    self._on_complete(self._profile_data, self._did_clone)
                self.destroy()

            self._apply_btn.pack_forget()
            self._cancel_btn.configure(state="normal", text=t("dialog.import.btn_close"), command=_close, **theme.btn_style("success", height="lg"))
            
            messagebox.showinfo(t("dialog.import.done_title"), t("log.import_complete"))
        self.after(0, _done)

    def _execute_import_steps(self, settings: dict):
        """Run all selected import steps and schedule the completion callback."""
        steps_total = sum([
            len(self._missing) if settings['clone'] else 0,
            1,  # always: merge saved_environments + config_files → repo_configs
            1 if settings['overwrite_configs'] else 0,
        ])
        steps_total = max(steps_total, 1)
        steps_done = 0

        def _update_progress(text: str):
            nonlocal steps_done
            steps_done += 1
            pct = steps_done / steps_total
            try:
                self.after(0, lambda: (
                    self._progress.set(pct),
                    self._progress_label.configure(text=text)
                ))
            except tk.TclError:
                pass

        if settings['clone']:
            self._did_clone = True
            n = len(self._missing)
            names = ", ".join(m['name'] for m in self._missing)
            try:
                clone_key = "dialog.import.starting_clone_one" if n == 1 else "dialog.import.starting_clone_many"
                self.after(0, lambda k=clone_key: self._progress_label.configure(
                    text=t(k, n=n)
                ))
            except tk.TclError:
                pass
            self._log_to_dialog(t("log.import_starting", names=names))
            self._apply_repos(self._missing, _update_progress)

        self._run_import_repo_configs_step(_update_progress)

        if settings['overwrite_configs']:
            try:
                self.after(0, lambda: self._progress_label.configure(
                    text=t("dialog.import.applying_configs")
                ))
            except tk.TclError:
                pass
            self._log_to_dialog(t("dialog.import.applying_configs"))
            self._run_config_files_step(_update_progress)

        self._schedule_import_done()

    def _run_import_repo_configs_step(self, _update_progress):
        """Always merge saved_environments and config_files from the profile into
        devops_manager_config.json (repo_configs), with smart rename-on-conflict logic.
        Updates active_configs when a rename affects the currently selected environment."""
        from core.profile_manager import (
            apply_saved_environments, apply_config_files_to_repo_configs,
            update_active_configs_for_renames,
        )
        all_renames: dict = {}
        for repo_name, repo_cfg in self._profile_data.get('repos', {}).items():
            saved_envs = repo_cfg.get('saved_environments', {})
            if saved_envs:
                renames = apply_saved_environments(repo_name, saved_envs)
                for k, v in renames.items():
                    all_renames.setdefault(k, {}).update(v)

            cf = repo_cfg.get('config_files', {})
            if cf:
                renames = apply_config_files_to_repo_configs(repo_name, cf)
                for k, v in renames.items():
                    all_renames.setdefault(k, {}).update(v)

        if all_renames:
            update_active_configs_for_renames(all_renames)
            renamed_summary = ", ".join(
                f"{k}: {list(v.keys())}→{list(v.values())}" for k, v in all_renames.items()
            )
            self._log_to_dialog(f"[import] Renombres por conflicto: {renamed_summary}")
            if self._log:
                self._log(f"[import] Configs renombrados por conflicto: {renamed_summary}")

        _update_progress("🗂 Entornos guardados importados")

    def _run_config_files_step(self, _update_progress):
        """Overwrite local config files with those stored in the profile."""
        from core.profile_manager import apply_config_files
        from concurrent.futures import ThreadPoolExecutor

        def _apply_repo_configs(repo_name, repo_cfg):
            cf = repo_cfg.get('config_files', {})
            if not cf:
                return
            repo_path = os.path.join(self._workspace_dir, repo_name)
            if os.path.isdir(repo_path):
                target_env = repo_cfg.get('profile')
                try:
                    apply_config_files(repo_path, repo_cfg.get('type', ''), cf, target_env=target_env)
                except TypeError:
                    apply_config_files(repo_path, repo_cfg.get('type', ''), cf)
                msg = f"[import] Config files aplicados: {repo_name}"
                if self._log:
                    self._log(msg)
                self._log_to_dialog(msg)

        with ThreadPoolExecutor(max_workers=5) as executor:
            for repo_name, repo_cfg in self._profile_data.get('repos', {}).items():
                executor.submit(_apply_repo_configs, repo_name, repo_cfg)

        _update_progress("📝 Config files aplicados")

    def _apply(self):
        """Run all selected import operations."""
        self._apply_btn.configure(state="disabled", text=t("dialog.import.btn_applying"))
        self._cancel_btn.configure(state="disabled")

        # Transition to Step 2
        self._step1_scroll.pack_forget()
        self._step2_frame.pack(fill="both", expand=True)

        settings = self._collect_import_settings()

        def _run():
            self._apply_java_mappings()
            self._execute_import_steps(settings)

        threading.Thread(target=_run, daemon=True).start()
