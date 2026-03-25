"""
dialogs.py — Dialog windows for clone, settings, config editor, saved configurations.
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys

from gui import theme


class CloneDialog(ctk.CTkToplevel):
    """Dialog for cloning a new repository."""

    def __init__(self, parent, workspace_dir: str, log_callback=None, on_complete=None):
        super().__init__(parent)
        self.title("Clonar Repositorio")
        self.geometry("500x220")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._workspace_dir = workspace_dir
        self._log = log_callback
        self._on_complete = on_complete

        # URL
        ctk.CTkLabel(self, text="URL del repositorio Git:").pack(
            anchor="w", padx=20, pady=(20, 5))
        self._url_entry = ctk.CTkEntry(self, width=450, placeholder_text="https://...")
        self._url_entry.pack(padx=20)

        # Folder name
        ctk.CTkLabel(self, text="Nombre de la carpeta (opcional):").pack(
            anchor="w", padx=20, pady=(10, 5))
        self._name_entry = ctk.CTkEntry(self, width=450,
                                         placeholder_text="Se autodetecta del URL")
        self._name_entry.pack(padx=20)

        # Progress bar
        self._progress = ctk.CTkProgressBar(self, width=450)
        self._progress.pack(padx=20, pady=(15, 5))
        self._progress.set(0)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)

        self._clone_btn = ctk.CTkButton(
            btn_frame, text="Clonar", width=120,
            command=self._start_clone, **theme.btn_style("blue")
        )
        self._clone_btn.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            command=self.destroy, **theme.btn_style("neutral")
        ).pack(side="right")

    def _start_clone(self):
        url = self._url_entry.get().strip()
        if not url:
            messagebox.showwarning("Error", "Introduce una URL de repositorio")
            return

        name = self._name_entry.get().strip()
        if not name:
            # Auto-detect from URL
            name = url.rstrip('/').split('/')[-1]
            if name.endswith('.git'):
                name = name[:-4]

        dest = os.path.join(self._workspace_dir, name)
        if os.path.isdir(dest):
            messagebox.showwarning("Error", f"La carpeta '{name}' ya existe")
            return

        self._clone_btn.configure(state="disabled", text="Clonando...")

        def _run():
            from core.git_manager import clone

            def update_progress(pct):
                try:
                    self._progress.set(pct / 100)
                except tk.TclError:
                    pass

            success, msg = clone(url, dest, self._log, update_progress)

            def _done():
                if success:
                    self._progress.set(1.0)
                    messagebox.showinfo("Éxito", f"Repositorio clonado: {name}")
                    if self._on_complete:
                        self._on_complete()
                    self.destroy()
                else:
                    messagebox.showerror("Error", f"Error al clonar:\n{msg}")
                    self._clone_btn.configure(state="normal", text="Clonar")
                    self._progress.set(0)

            self.after(0, _done)

        threading.Thread(target=_run, daemon=True).start()


class ConfigEditorDialog(ctk.CTkToplevel):
    """Dialog for editing config files (application.yml / environment.ts)."""

    def __init__(self, parent, filepath: str, log_callback=None):
        super().__init__(parent)
        self.title(f"Editor: {os.path.basename(filepath)}")
        self.geometry("700x550")
        self.transient(parent)
        self.grab_set()

        self._filepath = filepath
        self._log = log_callback

        # Header with file path
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 5))

        ctk.CTkLabel(header, text=filepath, font=theme.font("xs", mono=True),
                     text_color=theme.C.text_placeholder).pack(anchor="w")

        # Text editor
        self._editor = ctk.CTkTextbox(
            self, font=theme.font("base", mono=True), corner_radius=theme.G.corner_panel,
            border_width=theme.G.border_width,
            border_color=(theme.C.file_btn_light, theme.C.card_border)
        )
        self._editor.pack(fill="both", expand=True, padx=15, pady=5)

        # Load content
        from core.config_manager import read_config_file_raw
        content = read_config_file_raw(filepath)
        self._editor.insert("1.0", content)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkButton(
            btn_frame, text="💾 Guardar", width=120,
            command=self._save, **theme.btn_style("success")
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            command=self.destroy, **theme.btn_style("neutral")
        ).pack(side="right")

        ctk.CTkButton(
            btn_frame, text="↩ Recargar", width=100,
            command=self._reload, **theme.btn_style("warning")
        ).pack(side="right", padx=(0, 10))

    def _save(self):
        content = self._editor.get("1.0", "end").rstrip('\n')
        from core.config_manager import write_config_file_raw
        if write_config_file_raw(self._filepath, content):
            if self._log:
                self._log(f"Guardado: {os.path.basename(self._filepath)}")
            messagebox.showinfo("Guardado", "Archivo guardado correctamente (backup creado)")
            self.destroy()
        else:
            messagebox.showerror("Error", "No se pudo guardar el archivo")

    def _reload(self):
        from core.config_manager import read_config_file_raw
        content = read_config_file_raw(self._filepath)
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", content)


class ProfileDialog(ctk.CTkToplevel):
    """Dialog for managing profiles: save, load, import, export."""

    def __init__(self, parent, workspace_dir: str, repos: list,
                 repo_cards: list = None, db_presets: dict = None,
                 log_callback=None, on_profile_loaded=None,
                 on_rescan=None, on_profiles_changed=None):
        super().__init__(parent)
        self.title("Configuraciones Guardadas")
        self.geometry("580x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._workspace_dir = workspace_dir
        self._repos = repos
        self._repo_cards = repo_cards or []
        self._db_presets = db_presets or {}
        self._log = log_callback
        self._on_profile_loaded = on_profile_loaded
        self._on_rescan = on_rescan
        self._on_profiles_changed = on_profiles_changed

        self._main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._main_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(self._main_scroll, text="💾 Configuraciones Guardadas",
                     font=theme.font("h2", bold=True)).pack(pady=(15, 10))

        # ─── Save section ───
        save_frame = ctk.CTkFrame(self._main_scroll, corner_radius=8)
        save_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(save_frame, text="Guardar configuración actual:",
                     font=theme.font("base", bold=True)).pack(anchor="w", padx=10, pady=(10, 5))

        name_row = ctk.CTkFrame(save_frame, fg_color="transparent")
        name_row.pack(fill="x", padx=10, pady=(0, 4))

        self._save_name = ctk.CTkEntry(name_row, width=300,
                                        placeholder_text="Nombre de la configuración...")
        self._save_name.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            name_row, text="💾 Guardar", width=100,
            command=self._save_profile, **theme.btn_style("success")
        ).pack(side="left")

        # Save options
        opts_row = ctk.CTkFrame(save_frame, fg_color="transparent")
        opts_row.pack(fill="x", padx=10, pady=(0, 10))

        self._include_db_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts_row, text="Incluir presets de BD", variable=self._include_db_var,
            font=theme.font("md"),
            checkbox_width=theme.G.checkbox_size, checkbox_height=theme.G.checkbox_size
        ).pack(side="left", padx=(0, 15))

        self._include_files_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts_row, text="Incluir config files (yml/ts)", variable=self._include_files_var,
            font=theme.font("md"),
            checkbox_width=theme.G.checkbox_size, checkbox_height=theme.G.checkbox_size
        ).pack(side="left")

        # ─── Load / Export section ───
        load_frame = ctk.CTkFrame(self._main_scroll, corner_radius=8)
        load_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(load_frame, text="Configuraciones guardadas:",
                     font=theme.font("base", bold=True)).pack(anchor="w", padx=10, pady=(10, 5))

        from core.profile_manager import list_profiles
        profiles = list_profiles()
        
        # Profile List (Scrollable)
        self._profile_list_frame = ctk.CTkScrollableFrame(
            load_frame, height=120, fg_color=theme.C.section_alt,
            border_width=theme.G.border_width, border_color=theme.C.subtle_border
        )
        self._profile_list_frame.pack(fill="x", padx=10, pady=5)
        
        self._selected_profile = ctk.StringVar(value="")
        self._refresh_list()

        btn_row = ctk.CTkFrame(load_frame, fg_color="transparent")
        btn_row.pack(pady=(0, 10))

        ctk.CTkButton(
            btn_row, text="📂 Cargar", width=100,
            command=self._load_profile, **theme.btn_style("blue")
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="🗑 Eliminar", width=100,
            command=self._delete_profile, **theme.btn_style("danger_deep")
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="📤 Exportar", width=100,
            command=self._export_profile, **theme.btn_style("warning")
        ).pack(side="left")

        # ─── Import section ───
        import_frame = ctk.CTkFrame(self._main_scroll, corner_radius=8)
        import_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(import_frame, text="Importar configuración externa:",
                     font=theme.font("base", bold=True)).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkButton(
            import_frame, text="📥 Importar desde archivo...", width=250,
            command=self._import_profile, **theme.btn_style("purple")
        ).pack(padx=10, pady=(0, 10))

        # ─── Info ───
        ctk.CTkLabel(
            self._main_scroll, text="💡 Guardar: guarda repos (URL, rama, env, cmd) + opciones BD/configs.\n"
                       "    Importar: permite clonar repos, instalar deps, aplicar configs.",
            font=theme.font("sm"), text_color=theme.C.text_placeholder,
            justify="left"
        ).pack(padx=20, pady=(10, 15))

    def _save_profile(self):
        name = self._save_name.get().strip()
        if not name:
            messagebox.showwarning("Error", "Introduce un nombre para la configuración")
            return

        from core.profile_manager import build_profile_data, save_profile, list_profiles
        
        # Check if profile with this name already exists
        existing_profiles = list_profiles()
        if name in existing_profiles:
            if not messagebox.askyesno("Sobrescribir", f"El perfil '{name}' ya existe.\n¿Deseas sobrescribirlo con los cambios actuales?"):
                return

        include_db = self._include_db_var.get()
        include_files = self._include_files_var.get()

        profile_data = build_profile_data(
            self._repo_cards,
            db_presets=self._db_presets,
            include_db_presets=include_db,
            include_config_files=include_files
        )

        save_profile(name, profile_data)

        if self._log:
            extras = []
            if include_db:
                extras.append("BD presets")
            if include_files:
                extras.append("config files")
            extra_str = f" (con {', '.join(extras)})" if extras else ""
            self._log(f"Configuración guardada: {name}{extra_str}")

        messagebox.showinfo("Guardado", f"Configuración '{name}' guardada correctamente")
        self._refresh_list()
        
        if self._on_profiles_changed:
            self._on_profiles_changed(name)

    def _load_profile(self):
        name = self._selected_profile.get()
        if not name or name == "(Sin configs)":
            messagebox.showwarning("Aviso", "Selecciona un perfil de la lista primero")
            return

        from core.profile_manager import load_profile
        data = load_profile(name)
        if not data:
            messagebox.showerror("Error", f"No se pudo cargar la configuración '{name}'")
            return

        self._apply_profile_data(data)

    def _apply_profile_data(self, data: dict):
        """Apply a profile, showing import options dialog if needed."""
        changes_text = self._build_changes_text(data)

        if changes_text == "✅ Ningún cambio detectado respecto al estado actual.":
            # If nothing really changes (or everything is identical), we can just proceed
            # but usually the user wants to know it loaded.
            _continue_import()
        else:
            from core.profile_manager import get_missing_repos
            missing = get_missing_repos(self._workspace_dir, data)
            has_db = bool(data.get('db_presets'))
            has_files = any(
                r.get('config_files') for r in data.get('repos', {}).values()
            )

            ImportOptionsDialog(
                self, data,
                changes_text=changes_text,
                missing_repos=missing,
                has_db_presets=has_db,
                has_config_files=has_files,
                workspace_dir=self._workspace_dir,
                log_callback=self._log,
                on_complete=self._on_import_complete
            )

    def _build_changes_text(self, data: dict) -> str:
        """Comparar el data con el estado actual de los repos."""
        from core.profile_manager import build_profile_data, get_missing_repos
        current_data = build_profile_data(
            self._repo_cards,
            db_presets=self._db_presets,
            include_db_presets=False,
            include_config_files=False
        )

        changes = []

        # 1. Repos faltantes (to clone)
        missing = get_missing_repos(self._workspace_dir, data)
        for m in missing:
            changes.append(f"➕ Clonar nuevo repo: {m['name']} (rama: {m['branch']})")

        # 2. Diferencias en repositorios existentes
        target_repos = data.get('repos', {})
        current_repos = current_data.get('repos', {})
        missing_names = {m['name'] for m in missing}

        for repo_name, target_cfg in target_repos.items():
            if repo_name in missing_names:
                continue

            if repo_name in current_repos:
                cur_cfg = current_repos[repo_name]
                repo_changes = []

                # Check branch
                if target_cfg.get('branch') and cur_cfg.get('branch') != target_cfg.get('branch'):
                    repo_changes.append(f"Rama: {cur_cfg.get('branch') or 'N/A'} ➔ {target_cfg.get('branch')}")

                # Check profile
                cur_profile = cur_cfg.get('profile') or 'N/A'
                tgt_profile = target_cfg.get('profile') or 'N/A'
                if tgt_profile != 'N/A' and cur_profile != tgt_profile:
                    repo_changes.append(f"Perfil: {cur_profile} ➔ {tgt_profile}")

                if repo_changes:
                    changes.append(f"🔄 {repo_name}:\n    " + "\n    ".join(repo_changes))

        # 3. Presets BD
        if data.get('db_presets'):
            names = ", ".join(data.get('db_presets').keys())
            changes.append(f"🗄 Importar presets de BD: {names}")

        # 4. Config files
        n_files = sum(len(r.get('config_files', {})) for r in target_repos.values())
        if n_files > 0:
            changes.append(f"📝 Sobrescribir archivos de config ({n_files} archivos)")

        if not changes:
            return "✅ Ningún cambio detectado respecto al estado actual."

        return "\n\n".join(changes)

    def _apply_basic_config(self, data: dict):
        """Apply basic config (branch, profile, cmd) without interactive dialog."""
        if self._on_profile_loaded:
            self._on_profile_loaded(data)
        if self._log:
            self._log(f"Configuración '{data.get('name', '??')}' aplicada")
        messagebox.showinfo("Cargado", "Configuración aplicada correctamente")
        self.destroy()

    def _on_import_complete(self, data: dict, did_clone: bool):
        """Called when the import options dialog finishes."""
        if self._on_profile_loaded:
            self._on_profile_loaded(data)
        if did_clone and self._on_rescan:
            self._on_rescan()
        self.destroy()

    def _delete_profile(self):
        name = self._selected_profile.get()
        if not name or name == "(Sin configs)":
            messagebox.showwarning("Aviso", "Selecciona un perfil de la lista primero")
            return

        if messagebox.askyesno("Confirmar", f"¿Eliminar la configuración '{name}'?"):
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
            messagebox.showwarning("Aviso", "Selecciona un perfil de la lista primero")
            return

        from core.profile_manager import load_profile, export_profile_to_file
        data = load_profile(name)
        if not data:
            messagebox.showerror("Error", "No se pudo leer la configuración")
            return

        dest = filedialog.asksaveasfilename(
            title="Exportar configuración",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f'{name}.json'
        )
        if dest:
            if export_profile_to_file(data, dest):
                messagebox.showinfo("Exportado", f"Configuración exportada a:\n{dest}")
            else:
                messagebox.showerror("Error", "No se pudo exportar la configuración")

    def _import_profile(self):
        filepath = filedialog.askopenfilename(
            title="Importar configuración",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")]
        )
        if not filepath:
            return

        from core.profile_manager import import_profile_from_file
        data = import_profile_from_file(filepath)
        if not data:
            messagebox.showerror("Error", "Archivo de configuración inválido")
            return

        profile_name = data.get('name', os.path.splitext(os.path.basename(filepath))[0])
        # Only parse and optionally import, do not save yet until accepted.
        data['name'] = profile_name

        # Show the import options dialog
        self._apply_profile_data(data)

    def _refresh_list(self):
        from core.profile_manager import list_profiles
        profiles = list_profiles()
        
        for widget in self._profile_list_frame.winfo_children():
            widget.destroy()

        if not profiles:
            ctk.CTkLabel(
                self._profile_list_frame,
                text="(Sin configs guardadas)",
                font=theme.font("md"), text_color=theme.C.text_placeholder
            ).pack(pady=10)
            self._selected_profile.set("")
            return

        _blue = theme.btn_style("blue")
        _neutral = theme.btn_style("neutral")
        for profile in profiles:
            is_sel = self._selected_profile.get() == profile
            fg = _blue["fg_color"] if is_sel else _neutral["fg_color"]
            btn = ctk.CTkButton(
                self._profile_list_frame, text=profile,
                anchor="w", fg_color=fg, hover_color=_blue["border_color"],
                font=theme.font("base", bold=True),
                command=lambda p=profile: self._select_profile_item(p)
            )
            btn.pack(fill="x", pady=2)
            
        # Ensure selection is valid
        if self._selected_profile.get() not in profiles:
            self._select_profile_item(profiles[0])

    def _select_profile_item(self, profile):
        self._selected_profile.set(profile)
        # Populate save text input so it's easy to overwrite
        self._save_name.delete(0, "end")
        self._save_name.insert(0, profile)
        self._refresh_list()  # trigger re-render to update selection color


class ImportOptionsDialog(ctk.CTkToplevel):
    """Interactive dialog shown when loading/importing a profile.
    Lets the user choose: clone repos, install deps, apply BD, overwrite configs.
    """

    def __init__(self, parent, profile_data: dict,
                 changes_text: str = "",
                 missing_repos: list = None,
                 has_db_presets: bool = False,
                 has_config_files: bool = False,
                 workspace_dir: str = '',
                 log_callback=None,
                 on_complete=None):
        super().__init__(parent)
        self.title("Revisar y Aplicar Configuración")
        self.geometry("580x650")
        self.minsize(500, 500)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._profile_data = profile_data
        self._missing = missing_repos or []
        self._workspace_dir = workspace_dir
        self._log = log_callback
        self._on_complete = on_complete
        self._did_clone = False
        
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

        # ── Main Container ──
        self._main_container = ctk.CTkFrame(self, fg_color="transparent")
        self._main_container.pack(fill="both", expand=True)

        # ── Buttons (Bottom) ──
        self._btn_frame = ctk.CTkFrame(self._main_container, fg_color="transparent")
        self._btn_frame.pack(side="bottom", fill="x", padx=20, pady=10)
        
        self._apply_btn = ctk.CTkButton(
            self._btn_frame, text="✅ Aceptar y Aplicar", width=150,
            command=self._apply, **theme.btn_style("success", height="lg")
        )
        self._apply_btn.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            self._btn_frame, text="Cancelar", width=100,
            command=self.destroy, **theme.btn_style("neutral", height="lg")
        ).pack(side="right")

        # ── Main Content Area (Scrollable) ──
        main_scroll = ctk.CTkScrollableFrame(self._main_container, fg_color="transparent")
        main_scroll.pack(side="top", fill="both", expand=True, padx=5, pady=(5, 0))

        ctk.CTkLabel(main_scroll, text="📥 Opciones de Importación",
                     font=theme.font("xxl", bold=True)).pack(anchor="w", padx=10, pady=(10, 5))

        # Checkboxes and Map Frame
        options_frame = ctk.CTkFrame(main_scroll, corner_radius=8)
        options_frame.pack(fill="x", padx=10, pady=(0, 15))

        # ── Missing repos ──
        self._clone_var = ctk.BooleanVar(value=True if self._missing else False)
        self._install_var = ctk.BooleanVar(value=True if self._missing else False)

        if self._missing:
            ctk.CTkLabel(options_frame, text="Repositorios faltantes encontrados:",
                         font=theme.font("base", bold=True), text_color=theme.C.status_starting).pack(anchor="w", padx=10, pady=(10, 0))

            missing_txt = ", ".join([m['name'] for m in self._missing])
            if len(missing_txt) > 80: missing_txt = missing_txt[:77] + "..."
            ctk.CTkLabel(options_frame, text=f"• {missing_txt}",
                         font=theme.font("md"), text_color=theme.C.text_muted).pack(anchor="w", padx=20)

            ctk.CTkCheckBox(options_frame, text="🔗 Clonar repos faltantes", variable=self._clone_var,
                            command=self._update_preview, checkbox_width=20, checkbox_height=20
                            ).pack(anchor="w", padx=10, pady=(5, 2))

            ctk.CTkCheckBox(options_frame, text="📦 Instalar dependencias", variable=self._install_var,
                            command=self._update_preview, checkbox_width=20, checkbox_height=20
                            ).pack(anchor="w", padx=10, pady=(2, 10))

        # ── DB Presets ──
        self._import_db_var = ctk.BooleanVar(value=True if has_db_presets else False)
        if has_db_presets:
            names = ", ".join(profile_data.get('db_presets', {}).keys())
            ctk.CTkCheckBox(options_frame, text=f"🗄 Importar presets de BD ({names})",
                            variable=self._import_db_var, command=self._update_preview,
                            checkbox_width=20, checkbox_height=20).pack(anchor="w", padx=10, pady=5)

        # ── Config files ──
        self._overwrite_configs_var = ctk.BooleanVar(value=True if has_config_files else False)
        if has_config_files:
            n_files = sum(len(r.get('config_files', {})) for r in profile_data.get('repos', {}).values())
            ctk.CTkCheckBox(options_frame, text=f"📝 Sobrescribir {n_files} archivos de config (yml/ts)",
                            variable=self._overwrite_configs_var, command=self._update_preview,
                            checkbox_width=20, checkbox_height=20).pack(anchor="w", padx=10, pady=(5, 10))

        # ── Missing Java Versions ──
        self._java_mappings = {}
        if self._missing_javas:
            ctk.CTkLabel(options_frame, text="Asociar versiones de Java locales:",
                         font=theme.font("base", bold=True), text_color=theme.C.status_starting).pack(anchor="w", padx=10, pady=(5, 0))

            for missing_jv in self._missing_javas:
                row = ctk.CTkFrame(options_frame, fg_color="transparent")
                row.pack(fill="x", padx=15, pady=2)
                ctk.CTkLabel(row, text=f"Perfil pide: {missing_jv} ➔", width=140, anchor="e").pack(side="left", padx=(0, 10))
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
                    repos_txt = " usará en: " + ", ".join(repos_needing_java)
                    if len(repos_txt) > 50:
                        repos_txt = repos_txt[:47] + "..."
                    ctk.CTkLabel(row, text=repos_txt, font=theme.font("sm", mono=True), text_color=theme.C.text_placeholder).pack(side="left", padx=(10, 0))
            ctk.CTkLabel(options_frame, text="").pack(pady=2)

        # ── Changes Preview ──
        ctk.CTkLabel(main_scroll, text="📋 Resumen de Cambios",
                     font=theme.font("xl", bold=True)).pack(anchor="w", padx=10, pady=(5, 5))

        self._preview_box = ctk.CTkTextbox(main_scroll, font=theme.font("md", mono=True), wrap="none", height=150)
        self._preview_box.pack(fill="x", padx=10, pady=(0, 10))

        # ── Progress ──
        self._progress_label = ctk.CTkLabel(main_scroll, text="", font=theme.font("sm"), text_color=theme.C.text_muted)
        self._progress_label.pack(anchor="w", padx=10, pady=(5, 0))
        self._progress = ctk.CTkProgressBar(main_scroll)
        self._progress.pack(fill="x", padx=10, pady=(0, 10))
        self._progress.set(0)

        # Initial preview population
        self._base_changes_text = changes_text
        self._update_preview()

    def _update_preview(self):
        """Update the preview textbox dynamically based on selected checkboxes."""
        self._preview_box.configure(state="normal")
        self._preview_box.delete("1.0", "end")

        lines = []

        if self._base_changes_text and "Ningún cambio detectado" not in self._base_changes_text:
            lines.append("--- CAMBIOS EN REPOSITORIOS (RAMA / PERFIL) ---")
            for line in self._base_changes_text.splitlines():
                if "Clonar nuevo repo" not in line and "Importar presets de BD" not in line and "Sobrescribir archivos" not in line and line.strip() != "":
                    lines.append(line)
            lines.append("")

        if self._clone_var.get() and self._missing:
            lines.append("--- CLONACIÓN ---")
            for m in self._missing:
                repo_cfg = self._profile_data.get('repos', {}).get(m['name'], {})
                java_ver = repo_cfg.get('java_version')
                req_java_text = f" | Usa Java: {java_ver}" if java_ver and java_ver != "Sistema (Por Defecto)" else ""
                lines.append(f"➕ Se clonará: {m['name']} (rama: {m.get('branch', 'default')}){req_java_text}")
            lines.append("")

        if self._install_var.get() and self._missing:
            lines.append("--- INSTALACIÓN ---")
            for m in self._missing:
                lines.append(f"� Se ejecutarán comandos de instalación en: {m['name']}")
            lines.append("")

        if self._import_db_var.get():
            db_presets = self._profile_data.get('db_presets', {})
            names = ", ".join(db_presets.keys())
            lines.append(f"🗄 Se importarán los presets de BD: {names}\n")

        if self._overwrite_configs_var.get():
            n_files = sum(len(r.get('config_files', {})) for r in self._profile_data.get('repos', {}).values())
            lines.append(f"📝 Se sobrescribirán {n_files} archivos de configuración locales.\n")

        if not lines:
            lines.append("✅ Ningún cambio seleccionado.")

        self._preview_box.insert("1.0", "\n".join(lines).strip())
        self._preview_box.configure(state="disabled")

    def _apply(self):
        """Run all selected import operations."""
        self._apply_btn.configure(state="disabled", text="⏳ Aplicando...")

        def _run():
            # Map Java versions before modifying anything
            if self._missing_javas:
                for repo_name, repo_cfg in self._profile_data.get('repos', {}).items():
                    jv = repo_cfg.get('java_version')
                    if jv in self._missing_javas:
                        repo_cfg['java_version'] = self._java_mappings[jv].get()
                        
            steps_total = 0
            if self._clone_var.get() and self._missing:
                steps_total += len(self._missing)
            if self._install_var.get() and self._missing:
                steps_total += len(self._missing)
            if self._import_db_var.get():
                steps_total += 1
            if self._overwrite_configs_var.get():
                steps_total += 1
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

            # 1) Clone missing repos
            if self._clone_var.get() and self._missing:
                from core.git_manager import clone, checkout
                from concurrent.futures import ThreadPoolExecutor
                
                def _clone_repo(m):
                    if not m['git_url']:
                        _update_progress(f"⚠ {m['name']}: sin URL")
                        return
                    dest = os.path.join(self._workspace_dir, m['name'])
                    if self._log:
                        self._log(f"[import] Clonando {m['name']}...")
                    success, msg = clone(m['git_url'], dest, self._log)
                    if success and m.get('branch'):
                        checkout(dest, m['branch'], self._log)
                    _update_progress(f"✅ Clonado: {m['name']}")
                    self._did_clone = True

                with ThreadPoolExecutor(max_workers=5) as executor:
                    for m in self._missing:
                        executor.submit(_clone_repo, m)

            # 2) Install dependencies in background
            if self._install_var.get() and self._missing:
                app_instance = self.master if hasattr(self, 'master') else None
                launcher = getattr(app_instance, '_launcher', None)
                analyzer = getattr(app_instance, '_analyzer', None)
                if launcher and analyzer:
                    for m in self._missing:
                        dest = os.path.join(self._workspace_dir, m['name'])
                        repo_cfg = self._profile_data.get('repos', {}).get(m['name'], {})
                        rtype = repo_cfg.get('type', '')
                        java_ver = repo_cfg.get('java_version', '')

                        r_def = next((t for t in analyzer.repo_types if t.get('type') == rtype), {})
                        cmd_str = r_def.get('commands', {}).get('install_cmd')

                        if cmd_str:
                            _update_progress(f"Iniciando instalación para {m['name']}...")
                            # Start install in background
                            launcher.start_generic_install(m['name'], dest, cmd_str, log=self._log, java_home=java_ver)
                        else:
                            _update_progress(f"⏭ {m['name']}: sin instalación")
                else:
                    if self._log:
                         self._log("[import] Error: service launcher not found, cannot install dependencies in background.")

            # 3) Import DB presets
            if self._import_db_var.get():
                from core.config_manager import get_config_path
                import json
                db_presets = self._profile_data.get('db_presets', {})
                config_path = get_config_path()
                try:
                    if os.path.isfile(config_path):
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                    else:
                        config = {}
                    existing = config.get('db_presets', {})
                    existing.update(db_presets)
                    config['db_presets'] = existing
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=2, ensure_ascii=False)
                    if self._log:
                        self._log(f"[import] BD presets importados: {', '.join(db_presets.keys())}")
                except Exception as e:
                    if self._log:
                        self._log(f"[import] Error importando BD presets: {e}")
                _update_progress("🗄 BD presets importados")

            # 4) Overwrite config files
            if self._overwrite_configs_var.get():
                from core.profile_manager import apply_config_files
                from concurrent.futures import ThreadPoolExecutor
                
                def _apply_repo_configs(repo_name, repo_cfg):
                    cf = repo_cfg.get('config_files', {})
                    if not cf:
                        return
                    repo_path = os.path.join(self._workspace_dir, repo_name)
                    if os.path.isdir(repo_path):
                        # Ensure we handle the target_env correctly by passing it if expected
                        target_env = repo_cfg.get('profile')
                        try:
                            # Apply config, checking if apply_config_files accepts target_env
                            apply_config_files(repo_path, repo_cfg.get('type', ''), cf, target_env=target_env)
                        except TypeError:
                            # Fallback if target_env is not supported
                            apply_config_files(repo_path, repo_cfg.get('type', ''), cf)
                        
                        if self._log:
                            self._log(f"[import] Config files aplicados: {repo_name}")
                
                with ThreadPoolExecutor(max_workers=5) as executor:
                    for repo_name, repo_cfg in self._profile_data.get('repos', {}).items():
                        executor.submit(_apply_repo_configs, repo_name, repo_cfg)
                        
                _update_progress("📝 Config files aplicados")

            # Done
            def _done():
                self._progress.set(1.0)
                self._progress_label.configure(text="✅ Importación completada")
                if self._on_complete:
                    self._on_complete(self._profile_data, self._did_clone)
                messagebox.showinfo("Completado", "Configuración importada y aplicada correctamente")
                self.destroy()

            self.after(0, _done)

        threading.Thread(target=_run, daemon=True).start()


class SettingsDialog(ctk.CTkToplevel):
    """General settings dialog with DB preset management."""

    def __init__(self, parent, settings: dict, on_save=None):
        super().__init__(parent)
        self.title("⚙ Configuración")
        self.geometry("600x550")
        self.minsize(500, 400)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._settings = settings
        self._on_save = on_save
        self._db_presets = dict(settings.get('db_presets', {}))
        self._java_versions = dict(settings.get('java_versions', {}))

        # Save container (Not scrolling, fixed at bottom) - Packed first so it's never pushed off-screen
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

        self._main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._main_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(self._main_scroll, text="Ajustes de DevOps Manager",
                     font=theme.font("h1", bold=True), text_color=theme.C.text_primary).pack(pady=(15, 20))

        # ─── Workspace section ───
        ws_frame = ctk.CTkFrame(self._main_scroll, fg_color=theme.C.section, corner_radius=theme.G.corner_card, border_width=theme.G.border_width, border_color=theme.C.settings_border)
        ws_frame.pack(fill="x", padx=10, pady=(0, 15))

        ws_header = ctk.CTkFrame(ws_frame, fg_color="transparent")
        ws_header.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(ws_header, text="📁 Directorio de Trabajo", font=theme.font("xl", bold=True), text_color=theme.C.text_primary).pack(side="left")
        ctk.CTkLabel(ws_frame, text="Ubicación donde se estructuran los repositorios de tus espacios de trabajo.", font=theme.font("md"), text_color=theme.C.text_muted).pack(anchor="w", padx=15, pady=(2, 12))

        dir_inner = ctk.CTkFrame(ws_frame, fg_color="transparent")
        dir_inner.pack(fill="x", padx=15, pady=(0, 15))
        
        self._workspace_entry = ctk.CTkEntry(dir_inner, height=32, font=theme.font("base", mono=True), fg_color=theme.C.section_alt, border_color=theme.C.subtle_border)
        self._workspace_entry.pack(side="left", fill="x", expand=True)
        self._workspace_entry.insert(0, settings.get('workspace_dir', ''))

        ctk.CTkButton(
            dir_inner, text="Examinar",
            command=self._browse_dir, **theme.btn_style("blue", width=80)
        ).pack(side="left", padx=(10, 0))

        # ─── DB Presets section ───
        db_frame = ctk.CTkFrame(self._main_scroll, fg_color=theme.C.section, corner_radius=theme.G.corner_card, border_width=theme.G.border_width, border_color=theme.C.settings_border)
        db_frame.pack(fill="x", padx=10, pady=(0, 15))

        db_header = ctk.CTkFrame(db_frame, fg_color="transparent")
        db_header.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(db_header, text="🗄️ Presets de BD", font=theme.font("xl", bold=True), text_color=theme.C.text_primary).pack(side="left")
        ctk.CTkLabel(db_frame, text="El template URL admite {db_name} como placeholder autodetectado. Utilízalos en perfiles para reemplazar propiedades en properties.", font=theme.font("md"), text_color=theme.C.text_muted).pack(anchor="w", padx=15, pady=(2, 12))

        self._preset_list_frame = ctk.CTkScrollableFrame(db_frame, height=80, fg_color=theme.C.section_alt, border_width=theme.G.border_width, border_color=theme.C.subtle_border)
        self._preset_list_frame.pack(fill="x", padx=15, pady=(0, 10))
        self._refresh_preset_list()

        add_row = ctk.CTkFrame(db_frame, fg_color="transparent")
        add_row.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            add_row, text="➕ Añadir preset",
            command=self._add_preset, **theme.btn_style("success", width=140)
        ).pack(side="left")

        # ─── Java Versions section ───
        java_frame = ctk.CTkFrame(self._main_scroll, fg_color=theme.C.section, corner_radius=theme.G.corner_card, border_width=theme.G.border_width, border_color=theme.C.settings_border)
        java_frame.pack(fill="x", padx=10, pady=(0, 15))

        java_header = ctk.CTkFrame(java_frame, fg_color="transparent")
        java_header.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(java_header, text="☕ Versiones de Java", font=theme.font("xl", bold=True), text_color=theme.C.text_primary).pack(side="left")
        ctk.CTkLabel(java_frame, text="Registra versiones de JDK locales para usarlas en los servicios Spring Boot y Maven.", font=theme.font("md"), text_color=theme.C.text_muted).pack(anchor="w", padx=15, pady=(2, 12))

        self._java_list_frame = ctk.CTkScrollableFrame(java_frame, height=80, fg_color=theme.C.section_alt, border_width=theme.G.border_width, border_color=theme.C.subtle_border)
        self._java_list_frame.pack(fill="x", padx=15, pady=(0, 10))
        self._refresh_java_list()
        
        java_add_row = ctk.CTkFrame(java_frame, fg_color="transparent")
        java_add_row.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            java_add_row, text="➕ Añadir Java",
            command=self._add_java_version, **theme.btn_style("success", width=130)
        ).pack(side="left")

        ctk.CTkButton(
            java_add_row, text="🔍 Auto-detectar",
            command=self._auto_detect_java, **theme.btn_style("purple", width=140)
        ).pack(side="left", padx=(10, 0))

        # ─── Acceso Rápido section ───
        shortcut_frame = ctk.CTkFrame(self._main_scroll, fg_color=theme.C.section, corner_radius=theme.G.corner_card, border_width=theme.G.border_width, border_color=theme.C.settings_border)
        shortcut_frame.pack(fill="x", padx=10, pady=(0, 15))

        sc_header = ctk.CTkFrame(shortcut_frame, fg_color="transparent")
        sc_header.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(sc_header, text="🖥️ Acceso Rápido", font=theme.font("xl", bold=True), text_color=theme.C.text_primary).pack(side="left")
        ctk.CTkLabel(shortcut_frame, text="Crea un acceso directo en el Escritorio para lanzar la aplicación sin abrir la terminal.", font=theme.font("md"), text_color=theme.C.text_muted).pack(anchor="w", padx=15, pady=(2, 12))

        sc_btn_row = ctk.CTkFrame(shortcut_frame, fg_color="transparent")
        sc_btn_row.pack(fill="x", padx=15, pady=(0, 15))
        ctk.CTkButton(
            sc_btn_row, text="🔗 Crear acceso directo en el Escritorio",
            command=self._create_shortcut, **theme.btn_style("blue", width=280)
        ).pack(side="left")

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
            run_bat = os.path.join(app_dir, "run.bat")
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
            s = s.strip('{}').replace('-', '')
            g = GUID()
            g.Data1 = int(s[0:8], 16)
            g.Data2 = int(s[8:12], 16)
            g.Data3 = int(s[12:16], 16)
            b = bytes.fromhex(s[16:32])
            for i, v in enumerate(b):
                g.Data4[i] = v
            return g

        CLSID_ShellLink = guid_from_str('{00021401-0000-0000-C000-000000000046}')
        IID_IShellLinkW = guid_from_str('{000214F9-0000-0000-C000-000000000046}')
        IID_IPersistFile = guid_from_str('{0000010B-0000-0000-C000-000000000046}')

        ole32.CoInitialize(None)
        try:
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

            # IShellLinkW vtable (IUnknown: 0-2, then):
            # 7=SetDescription, 9=SetWorkingDirectory, 17=SetIconLocation, 20=SetPath
            str_method(20)(ppsl, target_path)
            str_method(9)(ppsl, working_dir)
            str_method(7)(ppsl, description)
            ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)(vtbl[17])(ppsl, icon_path, 0)

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

    def _refresh_preset_list(self):
        """Rebuild the preset list display."""
        for widget in self._preset_list_frame.winfo_children():
            widget.destroy()

        if not self._db_presets:
            ctk.CTkLabel(
                self._preset_list_frame,
                text="(Sin presets configurados)",
                font=theme.font("sm"), text_color=theme.C.text_placeholder
            ).pack(pady=5)
            return

        for name, preset in self._db_presets.items():
            row = ctk.CTkFrame(self._preset_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row, text=f"🗄 {name}",
                font=theme.font("md", bold=True), width=100, anchor="w"
            ).pack(side="left")

            url_display = preset.get('url', '')
            if len(url_display) > 45:
                url_display = url_display[:42] + '...'
            ctk.CTkLabel(
                row, text=url_display,
                font=theme.font("xs", mono=True), text_color=theme.C.text_placeholder, anchor="w"
            ).pack(side="left", padx=(5, 0), fill="x", expand=True)

            ctk.CTkButton(
                row, text="✏", width=28,
                command=lambda n=name: self._edit_preset(n),
                **theme.btn_style("warning", height="sm")
            ).pack(side="right", padx=(2, 0))

            ctk.CTkButton(
                row, text="🗑", width=28,
                command=lambda n=name: self._delete_preset(n),
                **theme.btn_style("danger_deep", height="sm")
            ).pack(side="right")

    def _add_preset(self):
        """Show dialog to add a new DB preset."""
        PresetEditorDialog(self, on_save=self._on_preset_saved)

    def _edit_preset(self, name: str):
        """Show dialog to edit an existing DB preset."""
        preset = self._db_presets.get(name, {})
        PresetEditorDialog(self, preset_name=name, preset_data=preset,
                           on_save=self._on_preset_saved)

    def _on_preset_saved(self, name: str, data: dict):
        """Callback when a preset is saved from the editor dialog."""
        self._db_presets[name] = data
        self._refresh_preset_list()

    def _delete_preset(self, name: str):
        """Delete a DB preset."""
        if messagebox.askyesno("Confirmar", f"¿Eliminar el preset '{name}'?"):
            del self._db_presets[name]
            self._refresh_preset_list()
            
    # --- Java Versions Methods ---
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

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Seleccionar workspace")
        if d:
            self._workspace_entry.delete(0, "end")
            self._workspace_entry.insert(0, d)

    def _save(self):
        self._settings['workspace_dir'] = self._workspace_entry.get().strip()
        self._settings['db_presets'] = self._db_presets
        self._settings['java_versions'] = self._java_versions
        if self._on_save:
            self._on_save(self._settings)
        self.destroy()

    def _open_profile_manager(self):
        if hasattr(self.master, '_show_configs'):
            self.master._show_configs()
            self.destroy()


class PresetEditorDialog(ctk.CTkToplevel):
    """Dialog for adding/editing a single DB preset."""

    def __init__(self, parent, preset_name: str = '', preset_data: dict = None,
                 on_save=None):
        super().__init__(parent)
        self.title("Editar Preset BD" if preset_name else "Nuevo Preset BD")
        self.geometry("520x340")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_save = on_save
        data = preset_data or {}

        ctk.CTkLabel(self, text="🗄 Preset de Base de Datos",
                     font=theme.font("h2", bold=True)).pack(pady=(15, 10))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)

        # Name
        ctk.CTkLabel(form, text="Nombre:", font=theme.font("md"),
                     width=80, anchor="w").grid(row=0, column=0, pady=4, sticky="w")
        self._name_entry = ctk.CTkEntry(form, width=380)
        self._name_entry.grid(row=0, column=1, pady=4)
        if preset_name:
            self._name_entry.insert(0, preset_name)

        # URL
        ctk.CTkLabel(form, text="URL:", font=theme.font("md"),
                     width=80, anchor="w").grid(row=1, column=0, pady=4, sticky="w")
        self._url_entry = ctk.CTkEntry(form, width=380,
                                        placeholder_text="jdbc:mysql://host:3306/{db_name}")
        self._url_entry.grid(row=1, column=1, pady=4)
        if data.get('url'):
            self._url_entry.insert(0, data['url'])

        # Username
        ctk.CTkLabel(form, text="Usuario:", font=theme.font("md"),
                     width=80, anchor="w").grid(row=2, column=0, pady=4, sticky="w")
        self._user_entry = ctk.CTkEntry(form, width=380)
        self._user_entry.grid(row=2, column=1, pady=4)
        if data.get('username'):
            self._user_entry.insert(0, data['username'])

        # Password
        ctk.CTkLabel(form, text="Contraseña:", font=theme.font("md"),
                     width=80, anchor="w").grid(row=3, column=0, pady=4, sticky="w")
        self._pass_entry = ctk.CTkEntry(form, width=380, show="•")
        self._pass_entry.grid(row=3, column=1, pady=4)
        if data.get('password'):
            self._pass_entry.insert(0, data['password'])

        # Driver
        ctk.CTkLabel(form, text="Driver:", font=theme.font("md"),
                     width=80, anchor="w").grid(row=4, column=0, pady=4, sticky="w")
        self._driver_entry = ctk.CTkEntry(form, width=380,
                                           placeholder_text="com.mysql.cj.jdbc.Driver")
        self._driver_entry.grid(row=4, column=1, pady=4)
        if data.get('driver'):
            self._driver_entry.insert(0, data['driver'])

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

    def _save(self):
        name = self._name_entry.get().strip()
        if not name:
            messagebox.showwarning("Error", "El nombre del preset es obligatorio")
            return

        url = self._url_entry.get().strip()
        if not url:
            messagebox.showwarning("Error", "La URL es obligatoria")
            return

        data = {
            'url': url,
            'username': self._user_entry.get().strip(),
            'password': self._pass_entry.get().strip(),
            'driver': self._driver_entry.get().strip() or 'com.mysql.cj.jdbc.Driver',
        }

        if self._on_save:
            self._on_save(name, data)
        self.destroy()

class JavaVersionEditorDialog(ctk.CTkToplevel):
    """Dialog for adding/editing a Java version configuration."""

    def __init__(self, parent, version_name: str = '', version_path: str = '',
                 on_save=None):
        super().__init__(parent)
        self.title("Editar Versión Java" if version_name else "Nueva Versión Java")
        self.geometry("520x220")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_save = on_save

        ctk.CTkLabel(self, text="☕ Configuración de Java",
                     font=theme.font("h2", bold=True)).pack(pady=(15, 10))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)

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
        ).grid(row=1, column=2, padx=(10,0))

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

# ─── Config Manager Dialog ──────────────────────────────────────────────────

class RepoConfigManagerDialog(ctk.CTkToplevel):
    """Dialog to manage Env/App configurations for a repository."""

    def __init__(self, parent, repo, config_key=None, log_callback=None, on_close_callback=None, source_dir=''):
        super().__init__(parent)
        self._repo = repo
        self._config_key = config_key if config_key else repo.name
        self._log = log_callback
        self._on_close = on_close_callback
        self._source_dir = os.path.normpath(source_dir) if source_dir else ''
        
        self.title(f"⚙ Gestor de Entornos/Apps - {self._config_key}")
        self.geometry("850x600")
        self.minsize(700, 450)
        self.transient(parent)
        
        from core.config_manager import load_repo_configs
        self._configs = load_repo_configs(self._config_key)
        
        self._current_selected = None
        
        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.grab_set()
        self.after_idle(lambda: self.after_idle(self._refresh_list))

    def _build_ui(self):
        # Paneles principales
        left_panel = ctk.CTkFrame(self, width=250, corner_radius=0)
        left_panel.pack(side="left", fill="y", padx=0, pady=0)
        left_panel.pack_propagate(False)
        
        right_panel = ctk.CTkFrame(self, fg_color="transparent")
        right_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        # --- Left Panel ---
        ctk.CTkLabel(left_panel, text="Entornos Guardados", font=theme.font("h2", bold=True)).pack(pady=(15, 10))
        
        self._list_frame = ctk.CTkScrollableFrame(left_panel, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        ctk.CTkButton(
            left_panel, text="➕ Nuevo",
            command=self._cmd_new, **theme.btn_style("blue")
        ).pack(fill="x", padx=15, pady=(5, 5))

        ctk.CTkButton(
            left_panel, text="📥 Auto-Importar",
            command=self._cmd_auto_import, **theme.btn_style("purple_alt")
        ).pack(fill="x", padx=15, pady=(0, 15))
        
        # --- Right Panel ---
        self._title_var = ctk.StringVar(value="Selecciona un entorno")
        header = ctk.CTkFrame(right_panel, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(header, textvariable=self._title_var, font=theme.font("h2", bold=True)).pack(side="left")

        self._actions_frame = ctk.CTkFrame(header, fg_color="transparent")
        self._actions_frame.pack(side="right")

        self._btn_rename = ctk.CTkButton(
            self._actions_frame, text="✏️ Renombrar", width=90,
            command=self._cmd_rename, state="disabled",
            **theme.btn_style("neutral")
        )
        self._btn_rename.pack(side="left", padx=3)

        self._btn_duplicate = ctk.CTkButton(
            self._actions_frame, text="📄 Duplicar", width=80,
            command=self._cmd_duplicate, state="disabled",
            **theme.btn_style("neutral")
        )
        self._btn_duplicate.pack(side="left", padx=3)

        self._btn_delete = ctk.CTkButton(
            self._actions_frame, text="🗑 Eliminar", width=80,
            command=self._cmd_delete, state="disabled",
            **theme.btn_style("danger")
        )
        self._btn_delete.pack(side="left", padx=3)

        # Editor
        self._editor = ctk.CTkTextbox(
            right_panel, font=theme.font("base", mono=True),
            wrap="none", corner_radius=theme.G.corner_btn,
            border_width=theme.G.border_width, border_color=theme.C.card_border
        )
        self._editor.pack(fill="both", expand=True, pady=(0, 10))
        self._editor.configure(state="disabled")

        # Save btn
        self._btn_save = ctk.CTkButton(
            right_panel, text="💾 Guardar Cambios en Entorno",
            command=self._cmd_save_text, state="disabled",
            **theme.btn_style("success")
        )
        self._btn_save.pack(side="right")
        
    def _refresh_list(self):
        for widget in self._list_frame.winfo_children():
            widget.destroy()

        _blue = theme.btn_style("blue")
        for name in sorted(self._configs.keys()):
            fg = _blue["fg_color"] if name == self._current_selected else "transparent"
            btn = ctk.CTkButton(
                self._list_frame, text=name, anchor="w",
                fg_color=fg, hover_color=_blue["hover_color"],
                command=lambda n=name: self._select_config(n)
            )
            btn.pack(fill="x", pady=2)
        self.update_idletasks()
            
    def _select_config(self, name: str):
        if self._current_selected and self._current_selected != name:
            self._check_unsaved_changes()
            
        self._current_selected = name
        self._refresh_list()
        
        if name and name in self._configs:
            self._title_var.set(f"Editando: {name}")
            self._editor.configure(state="normal")
            self._editor.delete("1.0", "end")
            self._editor.insert("1.0", self._configs[name])
            
            self._btn_rename.configure(state="normal")
            self._btn_duplicate.configure(state="normal")
            self._btn_delete.configure(state="normal")
            self._btn_save.configure(state="normal")
        else:
            self._title_var.set("Selecciona un entorno")
            self._editor.delete("1.0", "end")
            self._editor.configure(state="disabled")
            
            self._btn_rename.configure(state="disabled")
            self._btn_duplicate.configure(state="disabled")
            self._btn_delete.configure(state="disabled")
            self._btn_save.configure(state="disabled")

    def _check_unsaved_changes(self):
        if not self._current_selected or self._current_selected not in self._configs:
            return
        current_text = self._editor.get("1.0", "end-1c")
        if current_text != self._configs[self._current_selected]:
            if messagebox.askyesno("Cambios sin guardar", f"Hay cambios sin guardar en '{self._current_selected}'. ¿Deseas guardarlos antes de cambiar?"):
                self._cmd_save_text()
                
    def _cmd_save_text(self):
        if not self._current_selected:
            return
        new_text = self._editor.get("1.0", "end-1c")
        self._configs[self._current_selected] = new_text
        self._persist_to_db()
        messagebox.showinfo("Guardado", f"El entorno '{self._current_selected}' se ha actualizado correctamente.")
        
    def _cmd_new(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("Nuevo Entorno", "Nombre del nuevo entorno/app:", parent=self)
        if name:
            name = name.strip()
            if not name:
                return
            if name in self._configs:
                messagebox.showerror("Error", "Ya existe un entorno con ese nombre.")
                return
            self._configs[name] = ""
            self._persist_to_db()
            self._select_config(name)
            
    def _cmd_rename(self):
        if not self._current_selected:
            return
        from tkinter import simpledialog
        new_name = simpledialog.askstring("Renombrar Entorno", "Nuevo nombre:", initialvalue=self._current_selected, parent=self)
        if new_name:
            new_name = new_name.strip()
            if not new_name or new_name == self._current_selected:
                return
            if new_name in self._configs:
                messagebox.showerror("Error", "Ya existe un entorno con ese nombre.")
                return
            
            # Transfer data
            self._configs[new_name] = self._configs.pop(self._current_selected)
            self._persist_to_db()
            self._select_config(new_name)

    def _cmd_duplicate(self):
        if not self._current_selected:
            return
        from tkinter import simpledialog
        new_name = simpledialog.askstring("Duplicar Entorno", "Nombre de la copia:", initialvalue=f"{self._current_selected}_copia", parent=self)
        if new_name:
            new_name = new_name.strip()
            if not new_name:
                return
            if new_name in self._configs:
                messagebox.showerror("Error", "Ya existe un entorno con ese nombre.")
                return
            
            self._configs[new_name] = self._configs[self._current_selected]
            self._persist_to_db()
            self._select_config(new_name)

    def _cmd_delete(self):
        if not self._current_selected:
            return
        if messagebox.askyesno("Eliminar Entorno", f"¿Seguro que deseas eliminar '{self._current_selected}'?"):
            del self._configs[self._current_selected]
            self._persist_to_db()
            self._current_selected = None
            self._select_config(None)

    def _cmd_auto_import(self):
        env_files = getattr(self._repo, 'environment_files', [])
        if not env_files:
            messagebox.showinfo("Auto-Import", "No se encontraron ficheros de configuración en el directorio para importar.")
            return

        # Filter to source_dir when available, otherwise use all env files
        if self._source_dir:
            selected_files = [f for f in env_files if os.path.normpath(os.path.dirname(f)) == self._source_dir]
        else:
            selected_files = env_files

        if not selected_files:
            messagebox.showinfo("Auto-Import", "No se encontraron ficheros de configuración en el directorio para importar.")
            return

        from core.config_manager import auto_import_configs
        imported = auto_import_configs(
            self._repo.path,
            self._repo.repo_type,
            environment_files=selected_files,
            env_patterns=getattr(self._repo, 'env_patterns', None) or None,
        )
        if not imported:
            messagebox.showinfo("Auto-Import", "No se encontraron ficheros de configuración en el directorio para importar.")
            return

        added = 0
        for k, v in imported.items():
            if k not in self._configs:
                self._configs[k] = v
                added += 1

        if added > 0:
            self._persist_to_db()
            self._refresh_list()
            messagebox.showinfo("Auto-Import", f"Se han importado {added} configuraciones correctamente.")
        else:
            messagebox.showinfo("Auto-Import", "No hay configuraciones nuevas que importar (las encontradas ya existen).")
            
    def _persist_to_db(self):
        from core.config_manager import save_repo_configs
        save_repo_configs(self._config_key, self._configs)
        
    def _on_window_close(self):
        self._check_unsaved_changes()
        if self._on_close:
            self._on_close()
        self.destroy()


# --- Docker Compose Services Dialog -------------------------------------------

class DockerComposeDialog(ctk.CTkToplevel):
    """Dialog to manage individual services within a docker-compose file."""

    def __init__(self, parent, compose_file: str, log_callback=None, on_status_change=None,
                 profile_services=None, on_profile_change=None):
        super().__init__(parent)
        self.title(f"Docker Compose - {os.path.basename(compose_file)}")
        self.geometry("900x620")
        self.minsize(660, 420)
        self.transient(parent)
        self.grab_set()

        self._compose_file = compose_file
        self._log = log_callback
        self._on_status_change = on_status_change
        self._on_profile_change = on_profile_change
        self._profile_services = set(profile_services or [])
        self._auto_refresh = True
        self._services = []
        self._service_rows = {}

        from core.db_manager import parse_compose_services
        self._services = parse_compose_services(compose_file)

        self._build_ui()
        self._refresh_status()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_auto_refresh()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 5))

        ctk.CTkLabel(header, text="Servicios Definidos",
                     font=theme.font("h2", bold=True)).pack(side="left")

        # Global Actions
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right")

        self._auto_refresh_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            actions, text="Auto-Refresh", variable=self._auto_refresh_var,
            command=self._toggle_auto_refresh, font=theme.font("md")
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            actions, text="Iniciar Todos", width=110,
            command=self._start_all, **theme.btn_style("success")
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            actions, text="Detener Todos", width=110,
            command=self._stop_all, **theme.btn_style("danger_deep")
        ).pack(side="left")

        # Services List
        self._list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        if not self._services:
            ctk.CTkLabel(self._list_frame,
                         text="No se encontraron servicios en el YAML.",
                         text_color=theme.C.status_error).pack(pady=20)

        for srv in self._services:
            self._build_service_row(srv)

        # Logs Viewer Section
        logs_header = ctk.CTkFrame(self, fg_color="transparent")
        logs_header.pack(fill="x", padx=15, pady=(5, 0))

        self._logs_title = ctk.CTkLabel(
            logs_header, text="Logs: (Seleccione un servicio)",
            font=theme.font("base", bold=True))
        self._logs_title.pack(side="left")

        ctk.CTkButton(
            logs_header, text="Limpiar", width=60,
            command=self._clear_logs, **theme.btn_style("neutral_alt", height="sm")
        ).pack(side="right")

        self._btn_refresh_logs = ctk.CTkButton(
            logs_header, text="Recargar Logs", width=100,
            command=self._refresh_selected_logs, state="disabled",
            **theme.btn_style("neutral", height="sm")
        )
        self._btn_refresh_logs.pack(side="right", padx=5)

        self._logs_box = ctk.CTkTextbox(
            self, font=theme.font("md", mono=True), height=150,
            corner_radius=theme.G.corner_btn, border_width=theme.G.border_width,
            border_color=theme.C.subtle_border
        )
        self._logs_box.pack(fill="x", padx=15, pady=(5, 15))
        self._logs_box.configure(state="disabled")

        self._selected_log_service = None

    def _build_service_row(self, srv: dict):
        name = srv['name']

        row = ctk.CTkFrame(self._list_frame, corner_radius=theme.G.corner_btn,
                           border_width=theme.G.border_width, border_color=theme.C.subtle_border,
                           fg_color=theme.C.section_alt)
        row.pack(fill="x", pady=3, padx=5)

        # Status indicator
        lbl_status = ctk.CTkLabel(row, text="--", text_color=theme.C.text_faint,
                                  width=20, font=theme.font("xl"))
        lbl_status.pack(side="left", padx=10)

        # Info
        info_frame = ctk.CTkFrame(row, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, pady=5)

        ctk.CTkLabel(info_frame, text=name,
                     font=theme.font("lg", bold=True),
                     text_color=theme.C.text_primary).pack(anchor="w")

        details = f"Image: {srv.get('image', 'unknown')}"
        if srv.get('ports'):
            details += f" | Ports: {', '.join(srv.get('ports'))}"

        ctk.CTkLabel(info_frame, text=details,
                     font=theme.font("sm"),
                     text_color=theme.C.text_muted).pack(anchor="w")

        # Profile checkbox
        profile_var = ctk.BooleanVar(value=name in self._profile_services)
        profile_cb = ctk.CTkCheckBox(
            row, text="Perfil", variable=profile_var, width=70,
            font=theme.font("md"), text_color=theme.C.text_muted,
            fg_color=theme.C.docker_border_active, hover_color=theme.C.docker_border_active,
            command=lambda n=name, v=profile_var: self._on_profile_checkbox(n, v)
        )
        profile_cb.pack(side="right", padx=(0, 6))

        # Action Buttons
        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.pack(side="right", padx=10)

        ctk.CTkButton(
            btn_frame, text="Start", width=50,
            command=lambda n=name: self._start_service(n),
            **theme.btn_style("success")
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="Stop", width=50,
            command=lambda n=name: self._stop_service(n),
            **theme.btn_style("danger_deep")
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="Logs", width=50,
            command=lambda n=name: self._view_logs(n),
            **theme.btn_style("neutral_alt")
        ).pack(side="left", padx=(10, 0))

        self._service_rows[name] = {"status_lbl": lbl_status, "profile_var": profile_var}

    def _on_profile_checkbox(self, name: str, var: ctk.BooleanVar):
        if var.get():
            self._profile_services.add(name)
        else:
            self._profile_services.discard(name)
        if self._on_profile_change:
            self._on_profile_change(self._compose_file, list(self._profile_services))

    def _check_docker_daemon(self) -> bool:
        from core.db_manager import is_docker_available
        if not is_docker_available():
            if self._log:
                self._log("[docker] Docker no está disponible. Asegúrate de que Docker Desktop esté en ejecución.")
            return False
        return True

    def _refresh_status(self):
        if not self._services:
            return

        def _bg_check():
            from core.db_manager import get_compose_service_status
            status_map = get_compose_service_status(self._compose_file)

            def _update_ui():
                if not self.winfo_exists():
                    return
                for sname, widgets in self._service_rows.items():
                    state = status_map.get(sname, "stopped")
                    if state == "running":
                        color = theme.C.status_running
                        icon = "ON"
                    else:
                        color = theme.C.status_stopped
                        icon = "OFF"
                    widgets["status_lbl"].configure(text=icon, text_color=color)

                if self._on_status_change:
                    self._on_status_change()

            self.after(0, _update_ui)

        threading.Thread(target=_bg_check, daemon=True).start()

    def _start_auto_refresh(self):
        def _loop():
            if not self.winfo_exists() or not self._auto_refresh:
                return
            if self._auto_refresh_var.get():
                self._refresh_status()
            self.after(5000, _loop)
        self.after(5000, _loop)

    def _toggle_auto_refresh(self):
        self._auto_refresh = self._auto_refresh_var.get()

    def _start_service(self, name: str):
        if not self._check_docker_daemon():
            return
        if self._log:
            self._log(f"Iniciando servicio: {name}")

        def _run():
            from core.db_manager import start_service_compose
            start_service_compose(self._compose_file, name, self._log)
            self._refresh_status()
        threading.Thread(target=_run, daemon=True).start()

    def _stop_service(self, name: str):
        if not self._check_docker_daemon():
            return
        if self._log:
            self._log(f"Deteniendo servicio: {name}")

        def _run():
            from core.db_manager import stop_service_compose
            stop_service_compose(self._compose_file, name, self._log)
            self._refresh_status()
        threading.Thread(target=_run, daemon=True).start()

    def _start_all(self):
        if not self._check_docker_daemon():
            return
        if self._log:
            self._log("Iniciando todos los servicios del compose")

        def _run():
            from core.db_manager import docker_compose_up
            docker_compose_up(self._compose_file, None, self._log)
            self._refresh_status()
        threading.Thread(target=_run, daemon=True).start()

    def _stop_all(self):
        if not self._check_docker_daemon():
            return
        if self._log:
            self._log("Deteniendo todos los servicios del compose")

        def _run():
            from core.db_manager import docker_compose_down
            docker_compose_down(self._compose_file, self._log)
            self._refresh_status()
        threading.Thread(target=_run, daemon=True).start()

    def _view_logs(self, name: str):
        self._selected_log_service = name
        self._logs_title.configure(text=f"Logs: {name}")
        self._btn_refresh_logs.configure(state="normal")
        self._refresh_selected_logs()

    def _refresh_selected_logs(self):
        if not self._selected_log_service:
            return

        self._logs_box.configure(state="normal")
        self._logs_box.delete("1.0", "end")
        self._logs_box.insert("1.0", f"Cargando logs de {self._selected_log_service}...\n")
        self._logs_box.configure(state="disabled")

        def _fetch():
            from core.db_manager import docker_compose_logs
            txt = docker_compose_logs(
                self._compose_file, self._selected_log_service)

            def _update():
                if not self.winfo_exists():
                    return
                self._logs_box.configure(state="normal")
                self._logs_box.delete("1.0", "end")
                self._logs_box.insert("1.0", txt)
                self._logs_box.see("end")
                self._logs_box.configure(state="disabled")
            self.after(0, _update)

        threading.Thread(target=_fetch, daemon=True).start()

    def _clear_logs(self):
        self._logs_box.configure(state="normal")
        self._logs_box.delete("1.0", "end")
        self._logs_box.configure(state="disabled")

    def _on_close(self):
        self._auto_refresh = False
        self.destroy()


