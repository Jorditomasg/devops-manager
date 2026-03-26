"""settings.py — SettingsDialog, JavaVersionEditorDialog."""
import os
import sys
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui import theme


class SettingsDialog(BaseDialog):
    """General settings dialog."""

    def __init__(self, parent, settings: dict, on_save=None):
        super().__init__(parent, "⚙ Configuración", 600, 550)
        # This dialog is resizable (override BaseDialog's fixed size)
        self.resizable(True, True)
        self.minsize(500, 400)

        self._settings = settings
        self._on_save = on_save
        self._java_versions = dict(settings.get('java_versions', {}))

        self._build_save_bar()
        self._build_main_container()

    def _build_save_bar(self):
        """Build the fixed bottom save/cancel bar."""
        self._save_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._save_frame.pack(side="bottom", fill="x", padx=20, pady=15)

        ctk.CTkButton(
            self._save_frame, text="💾 Guardar Cambios",
            command=self._save, **theme.btn_style("success", width=150, height="lg", font_size="lg")
        ).pack(side="right")

        ctk.CTkButton(
            self._save_frame, text="Cancelar",
            command=self.destroy, **theme.btn_style("neutral", width=100, height="lg", font_size="lg")
        ).pack(side="right", padx=(0, 15))

    def _build_main_container(self):
        """Build scrollable container with title and all section frames."""
        self._main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._main_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(self._main_scroll, text="Ajustes de DevOps Manager",
                     font=theme.font("h1", bold=True), text_color=theme.C.text_primary).pack(pady=(15, 20))

        self._build_section(self._build_workspace_section)
        self._build_section(self._build_java_section)
        self._build_section(self._build_shortcut_section)

    def _build_section(self, builder_fn):
        """Create a themed section frame and pass it to the given builder function."""
        frame = ctk.CTkFrame(
            self._main_scroll, fg_color=theme.C.section,
            corner_radius=theme.G.corner_card,
            border_width=theme.G.border_width,
            border_color=theme.C.settings_border
        )
        frame.pack(fill="x", padx=10, pady=(0, 15))
        builder_fn(frame)

    # ── Section builders ──────────────────────────────────────────────────────

    def _build_workspace_section(self, frame):
        """Build the workspace folder row."""
        ws_header = ctk.CTkFrame(frame, fg_color="transparent")
        ws_header.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(
            ws_header, text="📁 Directorio de Trabajo",
            font=theme.font("xl", bold=True), text_color=theme.C.text_primary
        ).pack(side="left")
        ctk.CTkLabel(
            frame,
            text="Ubicación donde se estructuran los repositorios de tus espacios de trabajo.",
            font=theme.font("md"), text_color=theme.C.text_muted
        ).pack(anchor="w", padx=15, pady=(2, 12))

        dir_inner = ctk.CTkFrame(frame, fg_color="transparent")
        dir_inner.pack(fill="x", padx=15, pady=(0, 15))

        self._workspace_entry = ctk.CTkEntry(
            dir_inner, height=32,
            font=theme.font("base", mono=True),
            fg_color=theme.C.section_alt,
            border_color=theme.C.subtle_border
        )
        self._workspace_entry.pack(side="left", fill="x", expand=True)
        self._workspace_entry.insert(0, self._settings.get('workspace_dir', ''))

        ctk.CTkButton(
            dir_inner, text="Examinar",
            command=self._browse_dir, **theme.btn_style("blue", width=80)
        ).pack(side="left", padx=(10, 0))

    def _build_java_section(self, frame):
        """Build the Java version list + buttons."""
        java_header = ctk.CTkFrame(frame, fg_color="transparent")
        java_header.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(
            java_header, text="☕ Versiones de Java",
            font=theme.font("xl", bold=True), text_color=theme.C.text_primary
        ).pack(side="left")
        ctk.CTkLabel(
            frame,
            text="Registra versiones de JDK locales para usarlas en los servicios Spring Boot y Maven.",
            font=theme.font("md"), text_color=theme.C.text_muted
        ).pack(anchor="w", padx=15, pady=(2, 12))

        self._java_list_frame = ctk.CTkScrollableFrame(
            frame, height=80,
            fg_color=theme.C.section_alt,
            border_width=theme.G.border_width,
            border_color=theme.C.subtle_border
        )
        self._java_list_frame.pack(fill="x", padx=15, pady=(0, 10))
        self._refresh_java_list()

        java_add_row = ctk.CTkFrame(frame, fg_color="transparent")
        java_add_row.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            java_add_row, text="➕ Añadir Java",
            command=self._add_java_version, **theme.btn_style("success", width=130)
        ).pack(side="left")

        ctk.CTkButton(
            java_add_row, text="🔍 Auto-detectar",
            command=self._auto_detect_java, **theme.btn_style("purple", width=140)
        ).pack(side="left", padx=(10, 0))

    def _build_shortcut_section(self, frame):
        """Build the shortcut creation buttons."""
        sc_header = ctk.CTkFrame(frame, fg_color="transparent")
        sc_header.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(
            sc_header, text="🖥️ Acceso Rápido",
            font=theme.font("xl", bold=True), text_color=theme.C.text_primary
        ).pack(side="left")
        ctk.CTkLabel(
            frame,
            text="Crea un acceso directo en el Escritorio para lanzar la aplicación sin abrir la terminal.",
            font=theme.font("md"), text_color=theme.C.text_muted
        ).pack(anchor="w", padx=15, pady=(2, 12))

        sc_btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        sc_btn_row.pack(fill="x", padx=15, pady=(0, 15))
        ctk.CTkButton(
            sc_btn_row, text="🔗 Crear acceso directo en el Escritorio",
            command=self._create_shortcut, **theme.btn_style("blue", width=280)
        ).pack(side="left")

    # ── Shortcut creation ─────────────────────────────────────────────────────

    def _create_shortcut(self):
        """Create a Desktop shortcut pointing to run.bat with the app icon (ctypes, no PowerShell)."""
        if sys.platform != 'win32':
            messagebox.showinfo("No disponible", "La creación de accesos directos solo está disponible en Windows.", parent=self)
            return
        try:
            app_dir = getattr(self.master, '_app_dir', None)
            if not app_dir:
                messagebox.showerror("Error", "No se pudo determinar el directorio de la aplicación.", parent=self)
                return
            run_bat = os.path.join(app_dir, "scripts", "run.bat")
            icon_path = os.path.join(app_dir, "assets", "icons", "icon_red.ico")

            # Resolve real Desktop path (handles OneDrive-redirected desktops)
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0, None, 0, buf)  # CSIDL_DESKTOP = 0
            desktop = buf.value or os.path.join(os.path.expanduser("~"), "Desktop")
            lnk_path = os.path.join(desktop, "DevOps Manager.lnk")

            self._create_lnk_ctypes(run_bat, lnk_path, icon_path, app_dir, "DevOps Manager")
            messagebox.showinfo("Acceso directo creado", f"Se ha creado 'DevOps Manager' en:\n{lnk_path}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    @staticmethod
    def _guid_from_str(s, GUID, ctypes):
        """Parse a GUID string like '{XXXXXXXX-...}' into a GUID struct."""
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
        """Create the IShellLinkW COM object and return (ppsl, vtbl, str_method, get_vtbl, IID_IShellLinkW)."""
        from ctypes import byref
        CLSID_ShellLink = guid_from_str('{00021401-0000-0000-C000-000000000046}')
        IID_IShellLinkW = guid_from_str('{000214F9-0000-0000-C000-000000000046}')

        ole32.CoInitialize(None)
        ppsl = ctypes.c_void_p(None)
        hr = ole32.CoCreateInstance(
            byref(CLSID_ShellLink), None, 1,  # CLSCTX_INPROC_SERVER
            byref(IID_IShellLinkW), byref(ppsl)
        )
        if hr != 0:
            raise OSError(f'CoCreateInstance IShellLink falló: 0x{hr & 0xFFFFFFFF:08X}')

        def get_vtbl(iface):
            vtbl_addr = ctypes.c_void_p.from_address(iface.value).value
            return (ctypes.c_void_p * 64).from_address(vtbl_addr)

        vtbl = get_vtbl(ppsl)

        def str_method(idx):
            return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p)(vtbl[idx])

        return ppsl, vtbl, str_method, get_vtbl, IID_IShellLinkW

    @staticmethod
    def _set_link_properties(ppsl, vtbl, str_method, target_path, working_dir, description, icon_path, ctypes):
        """Set IShellLinkW properties: path, working dir, description, icon."""
        # IShellLinkW vtable (IUnknown: 0-2, then):
        # 7=SetDescription, 9=SetWorkingDirectory, 17=SetIconLocation, 20=SetPath
        str_method(20)(ppsl, target_path)
        str_method(9)(ppsl, working_dir)
        str_method(7)(ppsl, description)
        ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)(vtbl[17])(ppsl, icon_path, 0)

    @staticmethod
    def _create_lnk_ctypes(target_path, lnk_path, icon_path, working_dir, description):
        """Create a Windows .lnk shortcut via IShellLink COM using ctypes only (no subprocess)."""
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
                ppsl, vtbl, str_method, target_path, working_dir, description, icon_path, ctypes
            )

            # QueryInterface → IPersistFile
            pppf = ctypes.c_void_p(None)
            fn_qi = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, POINTER(GUID), POINTER(ctypes.c_void_p))(vtbl[0])
            hr = fn_qi(ppsl, byref(IID_IPersistFile), byref(pppf))
            if hr != 0:
                raise OSError(f'QI IPersistFile falló: 0x{hr & 0xFFFFFFFF:08X}')

            vtbl_pf = get_vtbl(pppf)

            # IPersistFile vtable (IUnknown:0-2, IPersist:3, then): 4=IsDirty, 5=Load, 6=Save
            fn_save = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)(vtbl_pf[6])
            hr = fn_save(pppf, lnk_path, 1)
            if hr != 0:
                raise OSError(f'IPersistFile::Save falló: 0x{hr & 0xFFFFFFFF:08X}')

            # Release
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl_pf[2])(pppf)
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(ppsl)
        finally:
            ole32.CoUninitialize()

    # ── Java version management ───────────────────────────────────────────────

    def _refresh_java_list(self):
        """Rebuild the java versions list display."""
        for widget in self._java_list_frame.winfo_children():
            widget.destroy()

        if not self._java_versions:
            ctk.CTkLabel(
                self._java_list_frame,
                text="(Sin versiones configuradas. Usa '➕ Añadir Java' o '🔍 Auto-detectar')",
                font=theme.font("sm"), text_color=theme.C.text_placeholder
            ).pack(pady=5)
            return

        for name, path in self._java_versions.items():
            row = ctk.CTkFrame(self._java_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row, text=f"☕ {name}",
                font=theme.font("md", bold=True), width=120, anchor="w"
            ).pack(side="left")

            path_display = path
            if len(path_display) > 35:
                path_display = path_display[:32] + '...'
            ctk.CTkLabel(
                row, text=path_display,
                font=theme.font("xs", mono=True), text_color=theme.C.text_placeholder, anchor="w"
            ).pack(side="left", padx=(5, 0), fill="x", expand=True)

            ctk.CTkButton(
                row, text="✏", width=28,
                command=lambda n=name: self._edit_java(n),
                **theme.btn_style("warning", height="sm")
            ).pack(side="right", padx=(2, 0))

            ctk.CTkButton(
                row, text="🗑", width=28,
                command=lambda n=name: self._delete_java(n),
                **theme.btn_style("danger_deep", height="sm")
            ).pack(side="right")

    def _auto_detect_java(self):
        """Auto-detect Java installations and add them to the list."""
        from core.java_manager import auto_detect_java_paths
        found = auto_detect_java_paths()
        added_count = 0
        for name, path in found.items():
            # Avoid overwriting existing custom paths with identical names if they exist
            if name not in self._java_versions and path not in self._java_versions.values():
                self._java_versions[name] = path
                added_count += 1

        self._refresh_java_list()

        if added_count > 0:
            messagebox.showinfo("Java Detectado", f"Se han encontrado y añadido {added_count} instalaciones de Java automáticamente.")
        else:
            res = messagebox.askyesno(
                "Java No Encontrado",
                "No se encontraron nuevas instalaciones de Java automáticamente.\n\n¿Deseas añadir la ruta a tu Java manualmente?"
            )
            if res:
                self._add_java_version()

    def _add_java_version(self):
        """Open the Java Version Editor dialog to add a new version."""
        JavaVersionEditorDialog(self, on_save=self._on_java_saved)

    def _edit_java(self, name: str):
        """Open the Java Version Editor dialog to edit an existing version."""
        path = self._java_versions.get(name, "")
        JavaVersionEditorDialog(self, version_name=name, version_path=path,
                                on_save=self._on_java_saved)

    def _on_java_saved(self, name: str, path: str):
        """Callback when a Java version is saved."""
        self._java_versions[name] = path
        self._refresh_java_list()

    def _delete_java(self, name: str):
        """Delete a Java version."""
        if messagebox.askyesno("Confirmar", f"¿Eliminar la configuración de Java '{name}'?"):
            del self._java_versions[name]
            self._refresh_java_list()

    # ── Workspace / save ──────────────────────────────────────────────────────

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Seleccionar workspace")
        if d:
            self._workspace_entry.delete(0, "end")
            self._workspace_entry.insert(0, d)

    def _save(self):
        self._settings['workspace_dir'] = self._workspace_entry.get().strip()
        self._settings['java_versions'] = self._java_versions
        if self._on_save:
            self._on_save(self._settings)
        self.destroy()

    def _open_profile_manager(self):
        if hasattr(self.master, '_show_configs'):
            self.master._show_configs()
            self.destroy()


class JavaVersionEditorDialog(BaseDialog):
    """Dialog for adding/editing a Java version configuration."""

    def __init__(self, parent, version_name: str = '', version_path: str = '',
                 on_save=None):
        title = "Editar Versión Java" if version_name else "Nueva Versión Java"
        super().__init__(parent, title, 520, 220)

        self._on_save = on_save

        ctk.CTkLabel(self, text="☕ Configuración de Java",
                     font=theme.font("h2", bold=True)).pack(pady=(15, 10))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)
        self._build_fields(form, version_name, version_path)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=15)

        ctk.CTkButton(
            btn_frame, text="💾 Guardar", width=120,
            command=self._save, **theme.btn_style("success")
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            command=self.destroy, **theme.btn_style("neutral")
        ).pack(side="right")

    def _build_fields(self, form, version_name: str, version_path: str):
        """Build the form fields for Java version name and JAVA_HOME path."""
        # Name
        ctk.CTkLabel(form, text="Nombre:", font=theme.font("md"),
                     width=80, anchor="w").grid(row=0, column=0, pady=4, sticky="w")
        self._name_entry = ctk.CTkEntry(form, width=380, placeholder_text="Ej: Java 17 o Java 8 (Corretto)")
        self._name_entry.grid(row=0, column=1, pady=4, sticky="w", columnspan=2)
        if version_name:
            self._name_entry.insert(0, version_name)

        # Path (JAVA_HOME)
        ctk.CTkLabel(form, text="Directorio:", font=theme.font("md"),
                     width=80, anchor="w").grid(row=1, column=0, pady=4, sticky="w")
        self._path_entry = ctk.CTkEntry(form, width=330, placeholder_text="JAVA_HOME path (carpeta principal con /bin)")
        self._path_entry.grid(row=1, column=1, pady=4, sticky="w")
        if version_path:
            self._path_entry.insert(0, version_path)

        def _browse_path():
            d = filedialog.askdirectory(title="Seleccionar directorio JAVA_HOME")
            if d:
                self._path_entry.delete(0, "end")
                self._path_entry.insert(0, d)

        ctk.CTkButton(
            form, text="📁", width=40,
            command=_browse_path, **theme.btn_style("blue")
        ).grid(row=1, column=2, padx=(10, 0))

    def _save(self):
        name = self._name_entry.get().strip()
        path = self._path_entry.get().strip()

        if not name:
            messagebox.showwarning("Error", "El nombre identificativo de la versión Java es obligatorio.")
            return

        if not path or not os.path.isdir(path):
            messagebox.showwarning("Error", "Debes especificar una ruta válida de un directorio para el JAVA_HOME.")
            return

        # Simple heuristic to make sure it looks like a valid JAVA_HOME
        java_exe = os.path.join(path, "bin", "java.exe" if os.name == 'nt' else "java")
        if not os.path.isfile(java_exe):
            if not messagebox.askyesno("Advertencia", f"No se ha encontrado el ejecutable java en {java_exe}. ¿Estás seguro de que esta es una ruta JAVA_HOME válida?"):
                return

        if self._on_save:
            self._on_save(name, path)
        self.destroy()
