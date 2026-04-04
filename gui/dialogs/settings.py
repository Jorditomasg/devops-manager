"""settings.py — SettingsDialog, JavaVersionsManagerDialog, JavaVersionEditorDialog."""
import os
import sys
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui import theme
from gui.tooltip import ToolTip
from gui.widgets import SearchableCombo
from core.i18n import t, list_available_languages

_LABEL_W = 155  # fixed width for left-column labels in the form


class SettingsDialog(BaseDialog):
    """General settings dialog — single-card form layout."""

    def __init__(self, parent, settings: dict, on_save=None, on_groups_changed=None):
        super().__init__(parent, t("dialog.settings.title"), 580, 100)
        self.resizable(True, False)  # horizontal resize only; height auto-fits

        self._settings = settings
        self._on_save = on_save
        self._on_groups_changed = on_groups_changed
        self._java_versions = dict(settings.get('java_versions', {}))

        self._build_save_bar()
        self._build_form()

        # Auto-fit height to content after widgets are laid out
        self.update_idletasks()
        self.geometry(f"580x{self.winfo_reqheight()}")

    # ── Save bar ──────────────────────────────────────────────────────────────

    def _build_save_bar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=20, pady=12)

        ctk.CTkButton(
            bar, text=t("btn.save_changes"),
            command=self._save, **theme.btn_style("success", width=150, height="lg", font_size="lg")
        ).pack(side="right")

        ctk.CTkButton(
            bar, text=t("btn.cancel"),
            command=self.destroy, **theme.btn_style("neutral", width=100, height="lg", font_size="lg")
        ).pack(side="right", padx=(0, 12))

    # ── Form (single card) ────────────────────────────────────────────────────

    def _build_form(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=10, pady=(8, 0))

        card = ctk.CTkFrame(
            outer, fg_color=theme.C.section,
            corner_radius=theme.G.corner_card,
            border_width=theme.G.border_width,
            border_color=theme.C.settings_border,
        )
        card.pack(fill="x")

        self._build_lang_row(card)
        self._divider(card)
        self._build_workspace_row(card)
        self._divider(card)
        self._build_behavior_row(card)
        self._divider(card)
        self._build_shortcut_row(card)
        self._divider(card)
        self._build_java_row(card)

    def _divider(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color=theme.C.subtle_border).pack(fill="x", padx=12)

    def _row(self, parent):
        """Create a horizontal form row and return it."""
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", padx=0)
        return r

    def _row_label(self, row, key):
        """Add the left-column label to a row."""
        ctk.CTkLabel(
            row, text=t(key), width=_LABEL_W, anchor="w",
            font=theme.font("md", bold=True), text_color=theme.C.text_primary,
        ).pack(side="left", padx=(14, 0), pady=10)

    # ── Row builders ──────────────────────────────────────────────────────────

    def _build_lang_row(self, card):
        row = self._row(card)
        self._row_label(row, "dialog.settings.language_title")

        self._languages = list_available_languages()
        lang_names = [lang["name"] for lang in self._languages]
        current_code = self._settings.get("language", "en_EN")
        current_name = next(
            (l["name"] for l in self._languages if l["code"] == current_code),
            lang_names[0] if lang_names else "English"
        )
        self._lang_combo = SearchableCombo(
            row, values=lang_names, width=190, **theme.combo_style()
        )
        self._lang_combo.set(current_name)
        self._lang_combo.pack(side="left")
        ToolTip(self._lang_combo, t("dialog.settings.language_desc"))

    def _build_workspace_row(self, card):
        row = self._row(card)
        self._row_label(row, "dialog.settings.workspace_title")

        btn = ctk.CTkButton(
            row, text=t("btn.manage_groups"),
            command=self._open_groups_dialog, **theme.btn_style("blue", width=150)
        )
        btn.pack(side="left", padx=(0, 14))
        ToolTip(btn, t("tooltip.manage_groups"))

    def _open_groups_dialog(self):
        from gui.dialogs.workspace_groups import WorkspaceGroupsDialog
        WorkspaceGroupsDialog(self, on_groups_changed=self._on_groups_changed)

    def _build_behavior_row(self, card):
        row = self._row(card)
        self._row_label(row, "dialog.settings.behavior_title")

        self._minimize_to_tray_var = ctk.BooleanVar(value=self._settings.get('minimize_to_tray', True))
        ctk.CTkCheckBox(
            row, text=t("dialog.settings.minimize_to_tray"),
            variable=self._minimize_to_tray_var,
            font=theme.font("md"),
            checkbox_width=theme.G.checkbox_size, checkbox_height=theme.G.checkbox_size,
        ).pack(side="left", padx=(0, 14))

    def _build_shortcut_row(self, card):
        row = self._row(card)
        self._row_label(row, "dialog.settings.shortcut_title")

        if sys.platform == 'win32':
            btn_text = t("btn.create_shortcut_win")
            btn_tip  = t("dialog.settings.shortcut_desc_win")
        else:
            btn_text = t("btn.create_shortcut_linux")
            btn_tip  = t("dialog.settings.shortcut_desc_linux")

        btn = ctk.CTkButton(
            row, text=btn_text,
            command=self._create_shortcut, **theme.btn_style("blue", width=260)
        )
        btn.pack(side="left")
        ToolTip(btn, btn_tip)

    def _build_java_row(self, card):
        row = self._row(card)
        self._row_label(row, "dialog.settings.java_title")

        ctk.CTkButton(
            row, text=t("btn.manage_java"),
            command=self._open_java_manager, **theme.btn_style("purple", width=200)
        ).pack(side="left")

        self._java_count_label = ctk.CTkLabel(
            row, text=self._java_count_text(),
            font=theme.font("sm"), text_color=theme.C.text_muted, anchor="w",
        )
        self._java_count_label.pack(side="left", padx=(10, 14))

    def _java_count_text(self) -> str:
        n = len(self._java_versions)
        if n == 0:
            return t("dialog.settings.java_none_configured")
        return t("dialog.settings.java_n_configured", count=n)

    def _open_java_manager(self):
        def _on_done(versions: dict):
            self._java_versions = versions
            self._java_count_label.configure(text=self._java_count_text())

        JavaVersionsManagerDialog(self, self._java_versions, on_done=_on_done)

    # ── Shortcut creation ─────────────────────────────────────────────────────

    def _create_shortcut(self):
        """Create a Desktop shortcut appropriate for the current OS."""
        app_dir = getattr(self.master, '_app_dir', None)
        if not app_dir:
            messagebox.showerror("Error", t("dialog.settings.shortcut_error"), parent=self)
            return
        try:
            if sys.platform == 'win32':
                self._create_shortcut_windows(app_dir)
            else:
                self._create_shortcut_linux(app_dir)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _create_shortcut_windows(self, app_dir: str):
        run_vbs = os.path.join(app_dir, "scripts", "win", "run.vbs")
        icon_path = os.path.join(app_dir, "assets", "icons", "icon_red.ico")

        windir = os.environ.get('WINDIR', r'C:\Windows')
        wscript = os.path.join(windir, 'System32', 'wscript.exe')
        arguments = f'/nologo "{run_vbs}"'

        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0, None, 0, buf)
        desktop = buf.value or os.path.join(os.path.expanduser("~"), "Desktop")
        lnk_path = os.path.join(desktop, "DevOps Manager.lnk")

        self._create_lnk_ctypes(wscript, lnk_path, icon_path, app_dir, "DevOps Manager", arguments)
        messagebox.showinfo(
            t("dialog.settings.shortcut_success_title"),
            t("dialog.settings.shortcut_success_msg", path=lnk_path),
            parent=self
        )

    def _create_shortcut_linux(self, app_dir: str):
        run_sh = os.path.join(app_dir, "scripts", "linux", "run.sh")
        icon_path = os.path.join(app_dir, "assets", "icons", "icon_red.ico")

        desktop_entry = (
            "[Desktop Entry]\n"
            "Version=1.0\n"
            "Type=Application\n"
            "Name=DevOps Manager\n"
            "Comment=Manage and launch development services\n"
            f"Exec={run_sh}\n"
            f"Icon={icon_path}\n"
            "Terminal=false\n"
            "Categories=Development;Utility;\n"
            "StartupNotify=true\n"
        )

        created = []

        # App launcher
        launcher_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
        if os.path.isdir(launcher_dir):
            path = os.path.join(launcher_dir, "devops-manager.desktop")
            with open(path, "w") as f:
                f.write(desktop_entry)
            created.append(path)

        # Physical desktop
        import subprocess
        try:
            desktop_dir = subprocess.check_output(
                ["xdg-user-dir", "DESKTOP"], text=True
            ).strip()
        except Exception:
            desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")

        if os.path.isdir(desktop_dir):
            path = os.path.join(desktop_dir, "devops-manager.desktop")
            with open(path, "w") as f:
                f.write(desktop_entry)
            os.chmod(path, 0o755)
            created.append(path)

        if created:
            messagebox.showinfo(
                t("dialog.settings.shortcut_success_title"),
                t("dialog.settings.shortcut_success_msg", path="\n".join(created)),
                parent=self
            )
        else:
            messagebox.showwarning(
                t("misc.warning_title"),
                t("dialog.settings.shortcut_unavailable"),
                parent=self
            )

    @staticmethod
    def _guid_from_str(s, GUID, ctypes):
        s = s.strip('{}').replace('-', '')
        g = GUID()
        g.Data1 = int(s[0:8], 16)
        g.Data2 = int(s[8:12], 16)
        g.Data3 = int(s[12:16], 16)
        b = bytes.fromhex(s[16:32])
        for i, v in enumerate(b):
            g.Data4[i] = v
        return g

    @staticmethod
    def _build_shell_link_object(ole32, GUID, guid_from_str, ctypes):
        from ctypes import byref
        CLSID_ShellLink = guid_from_str('{00021401-0000-0000-C000-000000000046}')
        IID_IShellLinkW = guid_from_str('{000214F9-0000-0000-C000-000000000046}')

        ole32.CoInitialize(None)
        ppsl = ctypes.c_void_p(None)
        hr = ole32.CoCreateInstance(
            byref(CLSID_ShellLink), None, 1,
            byref(IID_IShellLinkW), byref(ppsl)
        )
        if hr != 0:
            raise OSError(t("dialog.settings.shortcut_err_link", code=f'{hr & 0xFFFFFFFF:08X}'))

        def get_vtbl(iface):
            vtbl_addr = ctypes.c_void_p.from_address(iface.value).value
            return (ctypes.c_void_p * 64).from_address(vtbl_addr)

        vtbl = get_vtbl(ppsl)

        def str_method(idx):
            return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p)(vtbl[idx])

        return ppsl, vtbl, str_method, get_vtbl, IID_IShellLinkW

    @staticmethod
    def _set_link_properties(ppsl, vtbl, str_method, target_path, working_dir, description, icon_path, ctypes, arguments=''):
        # IShellLinkW vtable: 7=SetDescription, 9=SetWorkingDirectory, 11=SetArguments, 17=SetIconLocation, 20=SetPath
        str_method(20)(ppsl, target_path)
        if arguments:
            str_method(11)(ppsl, arguments)
        str_method(9)(ppsl, working_dir)
        str_method(7)(ppsl, description)
        ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)(vtbl[17])(ppsl, icon_path, 0)

    @staticmethod
    def _create_lnk_ctypes(target_path, lnk_path, icon_path, working_dir, description, arguments=''):
        import ctypes
        from ctypes import byref, POINTER

        ole32 = ctypes.windll.ole32

        class GUID(ctypes.Structure):
            _fields_ = [
                ('Data1', ctypes.c_ulong),
                ('Data2', ctypes.c_ushort),
                ('Data3', ctypes.c_ushort),
                ('Data4', ctypes.c_byte * 8),
            ]

        def guid_from_str(s):
            return SettingsDialog._guid_from_str(s, GUID, ctypes)

        IID_IPersistFile = guid_from_str('{0000010B-0000-0000-C000-000000000046}')

        try:
            ppsl, vtbl, str_method, get_vtbl, IID_IShellLinkW = SettingsDialog._build_shell_link_object(
                ole32, GUID, guid_from_str, ctypes
            )
            SettingsDialog._set_link_properties(
                ppsl, vtbl, str_method, target_path, working_dir, description, icon_path, ctypes, arguments
            )

            pppf = ctypes.c_void_p(None)
            fn_qi = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, POINTER(GUID), POINTER(ctypes.c_void_p))(vtbl[0])
            hr = fn_qi(ppsl, byref(IID_IPersistFile), byref(pppf))
            if hr != 0:
                raise OSError(t("dialog.settings.shortcut_err_qi", code=f'{hr & 0xFFFFFFFF:08X}'))

            vtbl_pf = get_vtbl(pppf)
            fn_save = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)(vtbl_pf[6])
            hr = fn_save(pppf, lnk_path, 1)
            if hr != 0:
                raise OSError(t("dialog.settings.shortcut_err_save", code=f'{hr & 0xFFFFFFFF:08X}'))

            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl_pf[2])(pppf)
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(ppsl)
        finally:
            ole32.CoUninitialize()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        selected_name = self._lang_combo.get()
        if selected_name:
            selected_lang = next((l for l in self._languages if l["name"] == selected_name), None)
            if selected_lang:
                old_code = self._settings.get("language", "en_EN")
                new_code = selected_lang["code"]
                self._settings["language"] = new_code

                if new_code != old_code:
                    from core.i18n import _load_yaml, _TRANSLATIONS_DIR
                    import os as _os
                    new_path = _os.path.join(_TRANSLATIONS_DIR, f"{new_code}.yml")
                    new_strings = _load_yaml(new_path)
                    restart_title = new_strings.get("dialog.settings.language_restart_title", "Restart required")
                    restart_msg = new_strings.get("dialog.settings.language_restart_msg", "Restart the application.")
                    try:
                        restart_msg = restart_msg.format(name=selected_lang["name"])
                    except (KeyError, ValueError):
                        pass
                    messagebox.showinfo(restart_title, restart_msg, parent=self)

        self._settings['java_versions'] = self._java_versions
        self._settings['minimize_to_tray'] = self._minimize_to_tray_var.get()
        if self._on_save:
            self._on_save(self._settings)
        self.destroy()


class JavaVersionsManagerDialog(BaseDialog):
    """Modal for managing the list of registered Java versions."""

    def __init__(self, parent, java_versions: dict, on_done=None):
        super().__init__(parent, t("dialog.settings.java_title"), 560, 380)
        self.resizable(True, True)
        self.minsize(420, 280)

        self._java_versions = dict(java_versions)
        self._on_done = on_done

        self._build_ui()

    def _build_ui(self):
        # Close / apply bar
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=16, pady=12)

        ctk.CTkButton(
            bar, text=t("btn.close"),
            command=self._close, **theme.btn_style("success", width=120)
        ).pack(side="right")

        ctk.CTkButton(
            bar, text=t("btn.autodetect_java"),
            command=self._auto_detect, **theme.btn_style("purple", width=150)
        ).pack(side="left")

        ctk.CTkButton(
            bar, text=t("btn.add_java"),
            command=self._add, **theme.btn_style("neutral", width=130)
        ).pack(side="left", padx=(8, 0))

        # List
        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color=theme.C.section_alt,
            border_width=theme.G.border_width,
            border_color=theme.C.subtle_border,
        )
        self._list_frame.pack(fill="both", expand=True, padx=12, pady=(12, 0))
        self._refresh()

    def _refresh(self):
        for w in self._list_frame.winfo_children():
            w.destroy()

        if not self._java_versions:
            ctk.CTkLabel(
                self._list_frame,
                text=t("dialog.settings.java_no_versions"),
                font=theme.font("sm"), text_color=theme.C.text_placeholder,
            ).pack(pady=10)
            return

        for name, path in self._java_versions.items():
            row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
            row.pack(fill="x", pady=3)

            ctk.CTkLabel(
                row, text=f"☕ {name}",
                font=theme.font("md", bold=True), width=130, anchor="w",
            ).pack(side="left")

            path_display = path if len(path) <= 38 else path[:35] + '...'
            ctk.CTkLabel(
                row, text=path_display,
                font=theme.font("xs", mono=True), text_color=theme.C.text_placeholder, anchor="w",
            ).pack(side="left", padx=(4, 0), fill="x", expand=True)

            ctk.CTkButton(
                row, text="✏", width=28,
                command=lambda n=name: self._edit(n),
                **theme.btn_style("warning", height="sm")
            ).pack(side="right", padx=(2, 0))

            ctk.CTkButton(
                row, text="🗑", width=28,
                command=lambda n=name: self._delete(n),
                **theme.btn_style("danger_deep", height="sm")
            ).pack(side="right")

    def _add(self):
        JavaVersionEditorDialog(self, on_save=self._on_saved)

    def _edit(self, name: str):
        JavaVersionEditorDialog(self, version_name=name,
                                version_path=self._java_versions.get(name, ''),
                                on_save=self._on_saved)

    def _on_saved(self, name: str, path: str):
        self._java_versions[name] = path
        self._refresh()

    def _delete(self, name: str):
        if messagebox.askyesno(t("dialog.settings.java_delete_title"),
                               t("dialog.settings.java_delete_msg", name=name), parent=self):
            del self._java_versions[name]
            self._refresh()

    def _auto_detect(self):
        from core.java_manager import auto_detect_java_paths
        found = auto_detect_java_paths()
        added_count = 0
        for n, p in found.items():
            if n not in self._java_versions and p not in self._java_versions.values():
                self._java_versions[n] = p
                added_count += 1
        self._refresh()

        if added_count > 0:
            messagebox.showinfo(t("dialog.settings.java_detected_title"),
                                t("dialog.settings.java_detected_msg", added_count=added_count), parent=self)
        else:
            if messagebox.askyesno(t("dialog.settings.java_not_found_title"),
                                   t("dialog.settings.java_not_found_msg"), parent=self):
                self._add()

    def _close(self):
        if self._on_done:
            self._on_done(self._java_versions)
        self.destroy()


class JavaVersionEditorDialog(BaseDialog):
    """Dialog for adding/editing a single Java version."""

    def __init__(self, parent, version_name: str = '', version_path: str = '', on_save=None):
        title = t("dialog.settings.java_edit_title") if version_name else t("dialog.settings.java_new_title")
        super().__init__(parent, title, 520, 220)

        self._on_save = on_save

        ctk.CTkLabel(self, text=t("dialog.settings.java_config_header"),
                     font=theme.font("h2", bold=True)).pack(pady=(15, 10))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)
        self._build_fields(form, version_name, version_path)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=15)

        ctk.CTkButton(
            btn_frame, text=t("btn.save"), width=120,
            command=self._save, **theme.btn_style("success")
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text=t("btn.cancel"), width=100,
            command=self.destroy, **theme.btn_style("neutral")
        ).pack(side="right")

    def _build_fields(self, form, version_name: str, version_path: str):
        ctk.CTkLabel(form, text=t("dialog.settings.java_field_name"), font=theme.font("md"),
                     width=80, anchor="w").grid(row=0, column=0, pady=4, sticky="w")
        self._name_entry = ctk.CTkEntry(form, width=380, placeholder_text=t("dialog.settings.java_name_placeholder"))
        self._name_entry.grid(row=0, column=1, pady=4, sticky="w", columnspan=2)
        if version_name:
            self._name_entry.insert(0, version_name)

        ctk.CTkLabel(form, text=t("dialog.settings.java_field_path"), font=theme.font("md"),
                     width=80, anchor="w").grid(row=1, column=0, pady=4, sticky="w")
        self._path_entry = ctk.CTkEntry(form, width=330, placeholder_text=t("dialog.settings.java_path_placeholder"))
        self._path_entry.grid(row=1, column=1, pady=4, sticky="w")
        if version_path:
            self._path_entry.insert(0, version_path)

        def _browse():
            d = filedialog.askdirectory(title=t("dialog.settings.java_dir_title"))
            if d:
                self._path_entry.delete(0, "end")
                self._path_entry.insert(0, d)

        ctk.CTkButton(form, text="📁", width=40, command=_browse,
                      **theme.btn_style("blue")).grid(row=1, column=2, padx=(10, 0))

    def _save(self):
        name = self._name_entry.get().strip()
        path = self._path_entry.get().strip()

        if not name:
            messagebox.showwarning(t("misc.error_title"), t("dialog.settings.java_name_required"), parent=self)
            return
        if not path or not os.path.isdir(path):
            messagebox.showwarning(t("misc.error_title"), t("dialog.settings.java_path_required"), parent=self)
            return

        java_exe = os.path.join(path, "bin", "java.exe" if os.name == 'nt' else "java")
        if not os.path.isfile(java_exe):
            if not messagebox.askyesno(t("dialog.settings.java_exe_warn_title"),
                                       t("dialog.settings.java_exe_warn_msg", java_exe=java_exe), parent=self):
                return

        if self._on_save:
            self._on_save(name, path)
        self.destroy()
