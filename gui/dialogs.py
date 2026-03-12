"""
dialogs.py — Dialog windows for clone, settings, config editor, saved configurations.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os

# ── Font constants ──────────────────────────────────────────────
FONT_FAMILY = "Segoe UI"


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
            fg_color="#172554", hover_color="#2563eb",
            border_width=1, border_color="#3b82f6",
            command=self._start_clone
        )
        self._clone_btn.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            fg_color="#1e293b", hover_color="#475569",
            border_width=1, border_color="#64748b",
            command=self.destroy
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
                except Exception:
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

        ctk.CTkLabel(header, text=filepath, font=("Consolas", 10),
                     text_color="#888").pack(anchor="w")

        # Text editor
        self._editor = ctk.CTkTextbox(
            self, font=("Consolas", 12), corner_radius=8,
            border_width=1, border_color=("#ccc", "#444")
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
            fg_color="#064e3b", hover_color="#047857",
            border_width=1, border_color="#10b981",
            command=self._save
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            fg_color="#1e293b", hover_color="#475569",
            border_width=1, border_color="#64748b",
            command=self.destroy
        ).pack(side="right")

        ctk.CTkButton(
            btn_frame, text="↩ Recargar", width=100,
            fg_color="#4a3310", hover_color="#d97706",
            border_width=1, border_color="#f59e0b",
            command=self._reload
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
                     font=(FONT_FAMILY, 16, "bold")).pack(pady=(15, 10))

        # ─── Save section ───
        save_frame = ctk.CTkFrame(self._main_scroll, corner_radius=8)
        save_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(save_frame, text="Guardar configuración actual:",
                     font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        name_row = ctk.CTkFrame(save_frame, fg_color="transparent")
        name_row.pack(fill="x", padx=10, pady=(0, 4))

        self._save_name = ctk.CTkEntry(name_row, width=300,
                                        placeholder_text="Nombre de la configuración...")
        self._save_name.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            name_row, text="💾 Guardar", width=100,
            fg_color="#064e3b", hover_color="#047857",
            border_width=1, border_color="#10b981",
            command=self._save_profile
        ).pack(side="left")

        # Save options
        opts_row = ctk.CTkFrame(save_frame, fg_color="transparent")
        opts_row.pack(fill="x", padx=10, pady=(0, 10))

        self._include_db_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts_row, text="Incluir presets de BD", variable=self._include_db_var,
            font=(FONT_FAMILY, 11), checkbox_width=18, checkbox_height=18
        ).pack(side="left", padx=(0, 15))

        self._include_files_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts_row, text="Incluir config files (yml/ts)", variable=self._include_files_var,
            font=(FONT_FAMILY, 11), checkbox_width=18, checkbox_height=18
        ).pack(side="left")

        # ─── Load / Export section ───
        load_frame = ctk.CTkFrame(self._main_scroll, corner_radius=8)
        load_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(load_frame, text="Configuraciones guardadas:",
                     font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        from core.profile_manager import list_profiles
        profiles = list_profiles()
        
        # Profile List (Scrollable)
        self._profile_list_frame = ctk.CTkScrollableFrame(
            load_frame, height=120, fg_color="#0f172a", 
            border_width=1, border_color="#1e293b"
        )
        self._profile_list_frame.pack(fill="x", padx=10, pady=5)
        
        self._selected_profile = ctk.StringVar(value="")
        self._refresh_list()

        btn_row = ctk.CTkFrame(load_frame, fg_color="transparent")
        btn_row.pack(pady=(0, 10))

        ctk.CTkButton(
            btn_row, text="📂 Cargar", width=100,
            fg_color="#172554", hover_color="#2563eb",
            border_width=1, border_color="#3b82f6",
            command=self._load_profile
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="🗑 Eliminar", width=100,
            fg_color="#450a0a", hover_color="#dc2626",
            border_width=1, border_color="#ef4444",
            command=self._delete_profile
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="📤 Exportar", width=100,
            fg_color="#4a3310", hover_color="#d97706",
            border_width=1, border_color="#f59e0b",
            command=self._export_profile
        ).pack(side="left")

        # ─── Import section ───
        import_frame = ctk.CTkFrame(self._main_scroll, corner_radius=8)
        import_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(import_frame, text="Importar configuración externa:",
                     font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkButton(
            import_frame, text="📥 Importar desde archivo...", width=250,
            fg_color="#2e1065", hover_color="#6d28d9",
            border_width=1, border_color="#7c3aed",
            command=self._import_profile
        ).pack(padx=10, pady=(0, 10))

        # ─── Info ───
        ctk.CTkLabel(
            self._main_scroll, text="💡 Guardar: guarda repos (URL, rama, env, cmd) + opciones BD/configs.\n"
                       "    Importar: permite clonar repos, instalar deps, aplicar configs.",
            font=(FONT_FAMILY, 10), text_color="#888",
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
                font=(FONT_FAMILY, 11), text_color="#888"
            ).pack(pady=10)
            self._selected_profile.set("")
            return

        for profile in profiles:
            color = "#1e293b"
            if self._selected_profile.get() == profile:
                color = "#2563eb"  # Selected color

            btn = ctk.CTkButton(
                self._profile_list_frame, text=profile,
                anchor="w", fg_color=color, hover_color="#3b82f6",
                font=(FONT_FAMILY, 12, "bold"),
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
            self._btn_frame, text="✅ Aceptar y Aplicar", width=150, height=36,
            fg_color="#064e3b", hover_color="#047857",
            border_width=1, border_color="#10b981",
            font=("Segoe UI", 12, "bold"),
            command=self._apply
        )
        self._apply_btn.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            self._btn_frame, text="Cancelar", width=100, height=36,
            fg_color="#1e293b", hover_color="#475569",
            border_width=1, border_color="#64748b",
            command=self.destroy
        ).pack(side="right")

        # ── Main Content Area (Scrollable) ──
        main_scroll = ctk.CTkScrollableFrame(self._main_container, fg_color="transparent")
        main_scroll.pack(side="top", fill="both", expand=True, padx=5, pady=(5, 0))

        ctk.CTkLabel(main_scroll, text="📥 Opciones de Importación",
                     font=(FONT_FAMILY, 15, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        # Checkboxes and Map Frame
        options_frame = ctk.CTkFrame(main_scroll, corner_radius=8)
        options_frame.pack(fill="x", padx=10, pady=(0, 15))

        # ── Missing repos ──
        self._clone_var = ctk.BooleanVar(value=True if self._missing else False)
        self._install_var = ctk.BooleanVar(value=True if self._missing else False)

        if self._missing:
            ctk.CTkLabel(options_frame, text="Repositorios faltantes encontrados:",
                         font=(FONT_FAMILY, 12, "bold"), text_color="#f59e0b").pack(anchor="w", padx=10, pady=(10, 0))

            missing_txt = ", ".join([m['name'] for m in self._missing])
            if len(missing_txt) > 80: missing_txt = missing_txt[:77] + "..."
            ctk.CTkLabel(options_frame, text=f"• {missing_txt}",
                         font=(FONT_FAMILY, 11), text_color="#94a3b8").pack(anchor="w", padx=20)

            ctk.CTkCheckBox(options_frame, text="🔗 Clonar repos faltantes", variable=self._clone_var,
                            command=self._update_preview, checkbox_width=20, checkbox_height=20
                            ).pack(anchor="w", padx=10, pady=(5, 2))

            ctk.CTkCheckBox(options_frame, text="📦 Instalar dependencias (npm/mvn)", variable=self._install_var,
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
                         font=(FONT_FAMILY, 12, "bold"), text_color="#f59e0b").pack(anchor="w", padx=10, pady=(5, 0))

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
                    ctk.CTkLabel(row, text=repos_txt, font=("Consolas", 10), text_color="#888").pack(side="left", padx=(10, 0))
            ctk.CTkLabel(options_frame, text="").pack(pady=2)

        # ── Changes Preview ──
        ctk.CTkLabel(main_scroll, text="📋 Resumen de Cambios",
                     font=(FONT_FAMILY, 14, "bold")).pack(anchor="w", padx=10, pady=(5, 5))

        self._preview_box = ctk.CTkTextbox(main_scroll, font=("Consolas", 11), wrap="none", height=150)
        self._preview_box.pack(fill="x", padx=10, pady=(0, 10))

        # ── Progress ──
        self._progress_label = ctk.CTkLabel(main_scroll, text="", font=(FONT_FAMILY, 10), text_color="#94a3b8")
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
                except Exception:
                    pass

            # 1) Clone missing repos
            if self._clone_var.get() and self._missing:
                from core.git_manager import clone, checkout
                for m in self._missing:
                    if not m['git_url']:
                        _update_progress(f"⚠ {m['name']}: sin URL")
                        continue
                    dest = os.path.join(self._workspace_dir, m['name'])
                    if self._log:
                        self._log(f"[import] Clonando {m['name']}...")
                    success, msg = clone(m['git_url'], dest, self._log)
                    if success and m.get('branch'):
                        checkout(dest, m['branch'], self._log)
                    _update_progress(f"✅ Clonado: {m['name']}")
                    self._did_clone = True

            # 2) Install dependencies in background
            if self._install_var.get() and self._missing:
                app_instance = self.master if hasattr(self, 'master') else None
                launcher = getattr(app_instance, '_launcher', None)
                if launcher:
                    for m in self._missing:
                        dest = os.path.join(self._workspace_dir, m['name'])
                        repo_cfg = self._profile_data.get('repos', {}).get(m['name'], {})
                        rtype = repo_cfg.get('type', '')
                        java_ver = repo_cfg.get('java_version', '')
                        
                        # Iniciar la instalación usando el service launcher para que se vea en el log de cada card y no bloquee
                        if rtype == 'angular':
                            _update_progress(f"Iniciando instalación npm para {m['name']}...")
                            launcher.start_angular_install(m['name'], dest, log=self._log)
                        elif rtype in ('spring-boot', 'maven-lib'):
                            _update_progress(f"Iniciando instalación mvn para {m['name']}...")
                            launcher.start_maven_install(m['name'], dest, log=self._log, java_home="")
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
                for repo_name, repo_cfg in self._profile_data.get('repos', {}).items():
                    cf = repo_cfg.get('config_files', {})
                    if not cf:
                        continue
                    repo_path = os.path.join(self._workspace_dir, repo_name)
                    if os.path.isdir(repo_path):
                        apply_config_files(repo_path, repo_cfg.get('type', ''), cf)
                        if self._log:
                            self._log(f"[import] Config files aplicados: {repo_name}")
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

        self._main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._main_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(self._main_scroll, text="Ajustes de DevOps Manager",
                     font=("Segoe UI", 18, "bold"), text_color="#f8fafc").pack(pady=(15, 20))

        # ─── Workspace section ───
        ws_frame = ctk.CTkFrame(self._main_scroll, fg_color="#1e1b4b", corner_radius=10, border_width=1, border_color="#312e81")
        ws_frame.pack(fill="x", padx=10, pady=(0, 15))

        ws_header = ctk.CTkFrame(ws_frame, fg_color="transparent")
        ws_header.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(ws_header, text="📁 Directorio de Trabajo", font=("Segoe UI", 14, "bold"), text_color="#e2e8f0").pack(side="left")
        ctk.CTkLabel(ws_frame, text="Ubicación donde se estructuran los repositorios de tus espacios de trabajo.", font=("Segoe UI", 11), text_color="#94a3b8").pack(anchor="w", padx=15, pady=(2, 12))

        dir_inner = ctk.CTkFrame(ws_frame, fg_color="transparent")
        dir_inner.pack(fill="x", padx=15, pady=(0, 15))
        
        self._workspace_entry = ctk.CTkEntry(dir_inner, height=32, font=("Consolas", 12), fg_color="#0f172a", border_color="#334155")
        self._workspace_entry.pack(side="left", fill="x", expand=True)
        self._workspace_entry.insert(0, settings.get('workspace_dir', ''))

        ctk.CTkButton(
            dir_inner, text="Examinar", width=80, height=32,
            fg_color="#172554", hover_color="#2563eb",
            border_width=1, border_color="#3b82f6",
            font=("Segoe UI", 12, "bold"),
            command=self._browse_dir
        ).pack(side="left", padx=(10, 0))

        # ─── DB Presets section ───
        db_frame = ctk.CTkFrame(self._main_scroll, fg_color="#1e1b4b", corner_radius=10, border_width=1, border_color="#312e81")
        db_frame.pack(fill="x", padx=10, pady=(0, 15))

        db_header = ctk.CTkFrame(db_frame, fg_color="transparent")
        db_header.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(db_header, text="🗄️ Presets de BD", font=("Segoe UI", 14, "bold"), text_color="#e2e8f0").pack(side="left")
        ctk.CTkLabel(db_frame, text="El template URL admite {db_name} como placeholder autodetectado. Utilízalos en perfiles para reemplazar propiedades en properties.", font=("Segoe UI", 11), text_color="#94a3b8").pack(anchor="w", padx=15, pady=(2, 12))

        self._preset_list_frame = ctk.CTkScrollableFrame(db_frame, height=80, fg_color="#0f172a", border_width=1, border_color="#1e293b") 
        self._preset_list_frame.pack(fill="x", padx=15, pady=(0, 10))
        self._refresh_preset_list()

        add_row = ctk.CTkFrame(db_frame, fg_color="transparent")
        add_row.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            add_row, text="➕ Añadir preset", width=140, height=32,
            fg_color="#064e3b", hover_color="#047857",
            border_width=1, border_color="#10b981",
            font=("Segoe UI", 12, "bold"),
            command=self._add_preset
        ).pack(side="left")

        # ─── Java Versions section ───
        java_frame = ctk.CTkFrame(self._main_scroll, fg_color="#1e1b4b", corner_radius=10, border_width=1, border_color="#312e81")
        java_frame.pack(fill="x", padx=10, pady=(0, 15))

        java_header = ctk.CTkFrame(java_frame, fg_color="transparent")
        java_header.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(java_header, text="☕ Versiones de Java", font=("Segoe UI", 14, "bold"), text_color="#e2e8f0").pack(side="left")
        ctk.CTkLabel(java_frame, text="Registra versiones de JDK locales para usarlas en los servicios Spring Boot y Maven.", font=("Segoe UI", 11), text_color="#94a3b8").pack(anchor="w", padx=15, pady=(2, 12))
        
        self._java_list_frame = ctk.CTkScrollableFrame(java_frame, height=80, fg_color="#0f172a", border_width=1, border_color="#1e293b")
        self._java_list_frame.pack(fill="x", padx=15, pady=(0, 10))
        self._refresh_java_list()
        
        java_add_row = ctk.CTkFrame(java_frame, fg_color="transparent")
        java_add_row.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            java_add_row, text="➕ Añadir Java", width=130, height=32,
            fg_color="#064e3b", hover_color="#047857",
            border_width=1, border_color="#10b981",
            font=("Segoe UI", 12, "bold"),
            command=self._add_java_version
        ).pack(side="left")
        
        ctk.CTkButton(
            java_add_row, text="🔍 Auto-detectar", width=140, height=32,
            fg_color="#2e1065", hover_color="#6d28d9",
            border_width=1, border_color="#7c3aed",
            font=("Segoe UI", 12, "bold"),
            command=self._auto_detect_java
        ).pack(side="left", padx=(10, 0))

        # Save container (Not scrolling, fixed at bottom)
        save_frame = ctk.CTkFrame(self, fg_color="transparent")
        save_frame.pack(fill="x", padx=20, pady=15)

        ctk.CTkButton(
            save_frame, text="💾 Guardar Cambios", width=150, height=36,
            fg_color="#064e3b", hover_color="#047857",
            border_width=1, border_color="#10b981",
            font=("Segoe UI", 13, "bold"),
            command=self._save
        ).pack(side="right")
        
        ctk.CTkButton(
            save_frame, text="Cancelar", width=100, height=36,
            fg_color="#1e293b", hover_color="#475569",
            border_width=1, border_color="#64748b",
            font=("Segoe UI", 13),
            command=self.destroy
        ).pack(side="right", padx=(0, 15))

    def _refresh_preset_list(self):
        """Rebuild the preset list display."""
        for widget in self._preset_list_frame.winfo_children():
            widget.destroy()

        if not self._db_presets:
            ctk.CTkLabel(
                self._preset_list_frame,
                text="(Sin presets configurados)",
                font=("Segoe UI", 10), text_color="#888"
            ).pack(pady=5)
            return

        for name, preset in self._db_presets.items():
            row = ctk.CTkFrame(self._preset_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row, text=f"🗄 {name}",
                font=("Segoe UI", 11, "bold"), width=100, anchor="w"
            ).pack(side="left")

            url_display = preset.get('url', '')
            if len(url_display) > 45:
                url_display = url_display[:42] + '...'
            ctk.CTkLabel(
                row, text=url_display,
                font=("Consolas", 9), text_color="#888", anchor="w"
            ).pack(side="left", padx=(5, 0), fill="x", expand=True)

            ctk.CTkButton(
                row, text="✏", width=28, height=24,
                fg_color="#4a3310", hover_color="#d97706",
                border_width=1, border_color="#f59e0b",
                font=("Segoe UI", 11),
                command=lambda n=name: self._edit_preset(n)
            ).pack(side="right", padx=(2, 0))

            ctk.CTkButton(
                row, text="🗑", width=28, height=24,
                fg_color="#450a0a", hover_color="#dc2626",
                border_width=1, border_color="#ef4444",
                font=("Segoe UI", 11),
                command=lambda n=name: self._delete_preset(n)
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
                font=("Segoe UI", 10), text_color="#888"
            ).pack(pady=5)
            return

        for name, path in self._java_versions.items():
            row = ctk.CTkFrame(self._java_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row, text=f"☕ {name}",
                font=("Segoe UI", 11, "bold"), width=120, anchor="w"
            ).pack(side="left")

            path_display = path
            if len(path_display) > 35:
                path_display = path_display[:32] + '...'
            ctk.CTkLabel(
                row, text=path_display,
                font=("Consolas", 9), text_color="#888", anchor="w"
            ).pack(side="left", padx=(5, 0), fill="x", expand=True)

            ctk.CTkButton(
                row, text="✏", width=28, height=24,
                fg_color="#4a3310", hover_color="#d97706",
                border_width=1, border_color="#f59e0b",
                font=("Segoe UI", 11),
                command=lambda n=name: self._edit_java(n)
            ).pack(side="right", padx=(2, 0))

            ctk.CTkButton(
                row, text="🗑", width=28, height=24,
                fg_color="#450a0a", hover_color="#dc2626",
                border_width=1, border_color="#ef4444",
                font=("Segoe UI", 11),
                command=lambda n=name: self._delete_java(n)
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
                     font=("Segoe UI", 14, "bold")).pack(pady=(15, 10))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)

        # Name
        ctk.CTkLabel(form, text="Nombre:", font=("Segoe UI", 11),
                     width=80, anchor="w").grid(row=0, column=0, pady=4, sticky="w")
        self._name_entry = ctk.CTkEntry(form, width=380)
        self._name_entry.grid(row=0, column=1, pady=4)
        if preset_name:
            self._name_entry.insert(0, preset_name)

        # URL
        ctk.CTkLabel(form, text="URL:", font=("Segoe UI", 11),
                     width=80, anchor="w").grid(row=1, column=0, pady=4, sticky="w")
        self._url_entry = ctk.CTkEntry(form, width=380,
                                        placeholder_text="jdbc:mysql://host:3306/{db_name}")
        self._url_entry.grid(row=1, column=1, pady=4)
        if data.get('url'):
            self._url_entry.insert(0, data['url'])

        # Username
        ctk.CTkLabel(form, text="Usuario:", font=("Segoe UI", 11),
                     width=80, anchor="w").grid(row=2, column=0, pady=4, sticky="w")
        self._user_entry = ctk.CTkEntry(form, width=380)
        self._user_entry.grid(row=2, column=1, pady=4)
        if data.get('username'):
            self._user_entry.insert(0, data['username'])

        # Password
        ctk.CTkLabel(form, text="Contraseña:", font=("Segoe UI", 11),
                     width=80, anchor="w").grid(row=3, column=0, pady=4, sticky="w")
        self._pass_entry = ctk.CTkEntry(form, width=380, show="•")
        self._pass_entry.grid(row=3, column=1, pady=4)
        if data.get('password'):
            self._pass_entry.insert(0, data['password'])

        # Driver
        ctk.CTkLabel(form, text="Driver:", font=("Segoe UI", 11),
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
            fg_color="#064e3b", hover_color="#047857",
            border_width=1, border_color="#10b981",
            command=self._save
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            fg_color="#1e293b", hover_color="#475569",
            border_width=1, border_color="#64748b",
            command=self.destroy
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


    def _accept(self):
        self.destroy()
        if self._on_accept:
            self._on_accept()

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
                     font=("Segoe UI", 14, "bold")).pack(pady=(15, 10))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)

        # Name
        ctk.CTkLabel(form, text="Nombre:", font=("Segoe UI", 11),
                     width=80, anchor="w").grid(row=0, column=0, pady=4, sticky="w")
        self._name_entry = ctk.CTkEntry(form, width=380, placeholder_text="Ej: Java 17 o Java 8 (Corretto)")
        self._name_entry.grid(row=0, column=1, pady=4, sticky="w", columnspan=2)
        if version_name:
            self._name_entry.insert(0, version_name)

        # Path (JAVA_HOME)
        ctk.CTkLabel(form, text="Directorio:", font=("Segoe UI", 11),
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
            fg_color="#172554", hover_color="#2563eb",
            border_width=1, border_color="#3b82f6",
            command=_browse_path
        ).grid(row=1, column=2, padx=(10,0))

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=15)

        ctk.CTkButton(
            btn_frame, text="💾 Guardar", width=120,
            fg_color="#064e3b", hover_color="#047857",
            border_width=1, border_color="#10b981",
            command=self._save
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            fg_color="#1e293b", hover_color="#475569",
            border_width=1, border_color="#64748b",
            command=self.destroy
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

    def __init__(self, parent, repo, config_key=None, log_callback=None, on_close_callback=None):
        super().__init__(parent)
        self._repo = repo
        self._config_key = config_key if config_key else repo.name
        self._log = log_callback
        self._on_close = on_close_callback
        
        self.title(f"⚙ Gestor de Entornos/Apps - {self._config_key}")
        self.geometry("850x600")
        self.minsize(700, 450)
        self.transient(parent)
        
        from core.config_manager import load_repo_configs
        self._configs = load_repo_configs(self._config_key)
        if not self._configs:
            legacy_configs = load_repo_configs(self._repo.name)
            if legacy_configs:
                self._configs = legacy_configs.copy()
        
        self._current_selected = None
        
        self._build_ui()
        self._refresh_list()
        
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.grab_set()

    def _build_ui(self):
        # Paneles principales
        left_panel = ctk.CTkFrame(self, width=250, corner_radius=0)
        left_panel.pack(side="left", fill="y", padx=0, pady=0)
        left_panel.pack_propagate(False)
        
        right_panel = ctk.CTkFrame(self, fg_color="transparent")
        right_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        # --- Left Panel ---
        ctk.CTkLabel(left_panel, text="Entornos Guardados", font=("Segoe UI", 14, "bold")).pack(pady=(15, 10))
        
        self._list_frame = ctk.CTkScrollableFrame(left_panel, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        btn_style = {"height": 28, "font": ("Segoe UI", 12), "corner_radius": 6, "border_width": 1}
        
        ctk.CTkButton(
            left_panel, text="➕ Nuevo",
            fg_color="#172554", hover_color="#2563eb", border_color="#3b82f6",
            command=self._cmd_new, **btn_style
        ).pack(fill="x", padx=15, pady=(5, 5))
        
        ctk.CTkButton(
            left_panel, text="📥 Auto-Importar",
            fg_color="#4c1d95", hover_color="#6d28d9", border_color="#7c3aed",
            command=self._cmd_auto_import, **btn_style
        ).pack(fill="x", padx=15, pady=(0, 15))
        
        # --- Right Panel ---
        self._title_var = ctk.StringVar(value="Selecciona un entorno")
        header = ctk.CTkFrame(right_panel, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(header, textvariable=self._title_var, font=("Segoe UI", 16, "bold")).pack(side="left")
        
        self._actions_frame = ctk.CTkFrame(header, fg_color="transparent")
        self._actions_frame.pack(side="right")
        
        self._btn_rename = ctk.CTkButton(
            self._actions_frame, text="✏️ Renombrar", width=90,
            fg_color="#1e293b", hover_color="#475569", border_color="#64748b",
            command=self._cmd_rename, state="disabled", **btn_style
        )
        self._btn_rename.pack(side="left", padx=3)
        
        self._btn_duplicate = ctk.CTkButton(
            self._actions_frame, text="📄 Duplicar", width=80,
            fg_color="#1e293b", hover_color="#475569", border_color="#64748b",
            command=self._cmd_duplicate, state="disabled", **btn_style
        )
        self._btn_duplicate.pack(side="left", padx=3)
        
        self._btn_delete = ctk.CTkButton(
            self._actions_frame, text="🗑 Eliminar", width=80,
            fg_color="#4c1616", hover_color="#dc2626", border_color="#ef4444",
            command=self._cmd_delete, state="disabled", **btn_style
        )
        self._btn_delete.pack(side="left", padx=3)
        
        # Editor
        self._editor = ctk.CTkTextbox(
            right_panel, font=("Consolas", 12),
            wrap="none", corner_radius=6, border_width=1, border_color="#3b3768"
        )
        self._editor.pack(fill="both", expand=True, pady=(0, 10))
        self._editor.configure(state="disabled")
        
        # Save btn
        self._btn_save = ctk.CTkButton(
            right_panel, text="💾 Guardar Cambios en Entorno", height=32,
            font=("Segoe UI", 14, "bold"), corner_radius=6,
            fg_color="#064e3b", hover_color="#047857", border_width=1, border_color="#10b981",
            command=self._cmd_save_text, state="disabled"
        )
        self._btn_save.pack(side="right")
        
    def _refresh_list(self):
        for widget in self._list_frame.winfo_children():
            widget.destroy()
            
        for name in sorted(self._configs.keys()):
            color = "#3b82f6" if name == self._current_selected else "transparent"
            btn = ctk.CTkButton(
                self._list_frame, text=name, anchor="w",
                fg_color=color, hover_color="#2563eb",
                command=lambda n=name: self._select_config(n)
            )
            btn.pack(fill="x", pady=2)
            
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
        from core.config_manager import auto_import_configs
        imported = auto_import_configs(
            self._repo.path, 
            self._repo.repo_type, 
            environment_files=getattr(self._repo, 'environment_files', [])
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
            messagebox.showinfo("Auto-Import", f"Se han importado {added} configuraciones correctamente.")
            self._refresh_list()
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
