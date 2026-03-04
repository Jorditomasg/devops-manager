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
            fg_color="#2196F3", hover_color="#1976D2",
            command=self._start_clone
        )
        self._clone_btn.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            fg_color="#555", hover_color="#666",
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
            fg_color="#4CAF50", hover_color="#388E3C",
            command=self._save
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            fg_color="#555", hover_color="#666",
            command=self.destroy
        ).pack(side="right")

        ctk.CTkButton(
            btn_frame, text="↩ Recargar", width=100,
            fg_color="#FF9800", hover_color="#F57C00",
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
                 on_rescan=None):
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

        ctk.CTkLabel(self, text="💾 Configuraciones Guardadas",
                     font=(FONT_FAMILY, 16, "bold")).pack(pady=(15, 10))

        # ─── Save section ───
        save_frame = ctk.CTkFrame(self, corner_radius=8)
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
            fg_color="#4CAF50", hover_color="#388E3C",
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
        load_frame = ctk.CTkFrame(self, corner_radius=8)
        load_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(load_frame, text="Configuraciones guardadas:",
                     font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        from core.profile_manager import list_profiles
        profiles = list_profiles(workspace_dir)

        self._profile_list = ctk.CTkComboBox(
            load_frame, values=profiles if profiles else ["(Sin configs)"],
            width=300
        )
        self._profile_list.pack(padx=10, pady=5)

        btn_row = ctk.CTkFrame(load_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            btn_row, text="📂 Cargar", width=100,
            fg_color="#2196F3", hover_color="#1976D2",
            command=self._load_profile
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="🗑 Eliminar", width=100,
            fg_color="#f44336", hover_color="#d32f2f",
            command=self._delete_profile
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="📤 Exportar", width=100,
            fg_color="#FF9800", hover_color="#F57C00",
            command=self._export_profile
        ).pack(side="left")

        # ─── Import section ───
        import_frame = ctk.CTkFrame(self, corner_radius=8)
        import_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(import_frame, text="Importar configuración externa:",
                     font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkButton(
            import_frame, text="📥 Importar desde archivo...", width=250,
            fg_color="#9C27B0", hover_color="#7B1FA2",
            command=self._import_profile
        ).pack(padx=10, pady=(0, 10))

        # ─── Info ───
        ctk.CTkLabel(
            self, text="💡 Guardar: guarda repos (URL, rama, env, cmd) + opciones BD/configs.\n"
                       "    Importar: permite clonar repos, instalar deps, aplicar configs.",
            font=(FONT_FAMILY, 10), text_color="#888",
            justify="left"
        ).pack(padx=20, pady=(10, 15))

    def _save_profile(self):
        name = self._save_name.get().strip()
        if not name:
            messagebox.showwarning("Error", "Introduce un nombre para la configuración")
            return

        from core.profile_manager import build_profile_data, save_profile

        include_db = self._include_db_var.get()
        include_files = self._include_files_var.get()

        profile_data = build_profile_data(
            self._repo_cards,
            db_presets=self._db_presets,
            include_db_presets=include_db,
            include_config_files=include_files
        )

        save_profile(self._workspace_dir, name, profile_data)

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

    def _load_profile(self):
        name = self._profile_list.get()
        if not name or name == "(Sin configs)":
            return

        from core.profile_manager import load_profile
        data = load_profile(self._workspace_dir, name)
        if not data:
            messagebox.showerror("Error", f"No se pudo cargar la configuración '{name}'")
            return

        self._apply_profile_data(data)

    def _apply_profile_data(self, data: dict):
        """Apply a profile, showing import options dialog if needed."""
        from core.profile_manager import get_missing_repos
        missing = get_missing_repos(self._workspace_dir, data)
        has_db = bool(data.get('db_presets'))
        has_files = any(
            r.get('config_files') for r in data.get('repos', {}).values()
        )

        # If there are options to present, show the import options dialog
        if missing or has_db or has_files:
            ImportOptionsDialog(
                self, data,
                missing_repos=missing,
                has_db_presets=has_db,
                has_config_files=has_files,
                workspace_dir=self._workspace_dir,
                log_callback=self._log,
                on_complete=self._on_import_complete
            )
        else:
            # Simple case: just apply branch/profile/cmd
            self._apply_basic_config(data)

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
        name = self._profile_list.get()
        if not name or name == "(Sin configs)":
            return

        if messagebox.askyesno("Confirmar", f"¿Eliminar la configuración '{name}'?"):
            from core.profile_manager import delete_profile
            delete_profile(self._workspace_dir, name)
            if self._log:
                self._log(f"Configuración eliminada: {name}")
            self._refresh_list()

    def _export_profile(self):
        name = self._profile_list.get()
        if not name or name == "(Sin configs)":
            return

        from core.profile_manager import load_profile, export_profile_to_file
        data = load_profile(self._workspace_dir, name)
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

        # Save it locally first
        from core.profile_manager import save_profile
        profile_name = data.get('name', os.path.splitext(os.path.basename(filepath))[0])
        save_profile(self._workspace_dir, profile_name, data)

        if self._log:
            self._log(f"Configuración importada: {profile_name}")
        self._refresh_list()

        # Show the import options dialog
        self._apply_profile_data(data)

    def _refresh_list(self):
        from core.profile_manager import list_profiles
        profiles = list_profiles(self._workspace_dir)
        self._profile_list.configure(values=profiles if profiles else ["(Sin configs)"])
        if profiles:
            self._profile_list.set(profiles[0])
        else:
            self._profile_list.set("(Sin configs)")


class ImportOptionsDialog(ctk.CTkToplevel):
    """Interactive dialog shown when loading/importing a profile.
    Lets the user choose: clone repos, install deps, apply BD, overwrite configs.
    """

    def __init__(self, parent, profile_data: dict,
                 missing_repos: list = None,
                 has_db_presets: bool = False,
                 has_config_files: bool = False,
                 workspace_dir: str = '',
                 log_callback=None,
                 on_complete=None):
        super().__init__(parent)
        self.title("Opciones de Importación")
        self.geometry("520x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._profile_data = profile_data
        self._missing = missing_repos or []
        self._workspace_dir = workspace_dir
        self._log = log_callback
        self._on_complete = on_complete
        self._did_clone = False

        ctk.CTkLabel(self, text="📥 Opciones de Importación",
                     font=(FONT_FAMILY, 15, "bold")).pack(pady=(15, 10))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20)

        # ── Missing repos ──
        if self._missing:
            ctk.CTkLabel(content, text="Repos que no existen en el workspace:",
                         font=(FONT_FAMILY, 12, "bold"),
                         text_color="#f59e0b").pack(anchor="w", pady=(5, 3))

            missing_frame = ctk.CTkScrollableFrame(content, height=80,
                                                    corner_radius=6)
            missing_frame.pack(fill="x", pady=(0, 5))

            for m in self._missing:
                url_hint = m['git_url'][:60] + '...' if len(m['git_url']) > 60 else m['git_url']
                ctk.CTkLabel(
                    missing_frame,
                    text=f"  • {m['name']}  ({url_hint})",
                    font=(FONT_FAMILY, 10), text_color="#94a3b8",
                    anchor="w"
                ).pack(anchor="w")

            self._clone_var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                content, text="🔗 Clonar repos faltantes",
                variable=self._clone_var,
                font=(FONT_FAMILY, 12), checkbox_width=20, checkbox_height=20
            ).pack(anchor="w", pady=(2, 0))

            self._install_var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                content, text="📦 Instalar dependencias (npm ci / mvn install)",
                variable=self._install_var,
                font=(FONT_FAMILY, 12), checkbox_width=20, checkbox_height=20
            ).pack(anchor="w", pady=(2, 0))
        else:
            self._clone_var = ctk.BooleanVar(value=False)
            self._install_var = ctk.BooleanVar(value=False)

        # ── DB Presets ──
        if has_db_presets:
            db_presets = profile_data.get('db_presets', {})
            names = ", ".join(db_presets.keys())
            self._import_db_var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                content,
                text=f"🗄 Importar presets de BD ({names})",
                variable=self._import_db_var,
                font=(FONT_FAMILY, 12), checkbox_width=20, checkbox_height=20
            ).pack(anchor="w", pady=(10, 0))
        else:
            self._import_db_var = ctk.BooleanVar(value=False)

        # ── Config files ──
        if has_config_files:
            n_files = sum(
                len(r.get('config_files', {}))
                for r in profile_data.get('repos', {}).values()
            )
            self._overwrite_configs_var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                content,
                text=f"📝 Sobrescribir archivos de config ({n_files} archivos)",
                variable=self._overwrite_configs_var,
                font=(FONT_FAMILY, 12), checkbox_width=20, checkbox_height=20
            ).pack(anchor="w", pady=(10, 0))
        else:
            self._overwrite_configs_var = ctk.BooleanVar(value=False)

        # ── Progress ──
        self._progress_label = ctk.CTkLabel(
            content, text="", font=(FONT_FAMILY, 10), text_color="#94a3b8"
        )
        self._progress_label.pack(anchor="w", pady=(15, 2))

        self._progress = ctk.CTkProgressBar(content, width=460)
        self._progress.pack(fill="x", pady=(0, 5))
        self._progress.set(0)

        # ── Buttons ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))

        self._apply_btn = ctk.CTkButton(
            btn_frame, text="✅ Aplicar", width=120,
            fg_color="#4CAF50", hover_color="#388E3C",
            command=self._apply
        )
        self._apply_btn.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            fg_color="#555", hover_color="#666",
            command=self.destroy
        ).pack(side="right")

    def _apply(self):
        """Run all selected import operations."""
        self._apply_btn.configure(state="disabled", text="⏳ Aplicando...")

        def _run():
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

            # 2) Install dependencies
            if self._install_var.get() and self._missing:
                import subprocess
                for m in self._missing:
                    dest = os.path.join(self._workspace_dir, m['name'])
                    repo_cfg = self._profile_data.get('repos', {}).get(m['name'], {})
                    rtype = repo_cfg.get('type', '')

                    if rtype == 'angular':
                        if self._log:
                            self._log(f"[import] npm ci en {m['name']}...")
                        try:
                            subprocess.run(
                                ['npm', 'ci'], cwd=dest, shell=True,
                                capture_output=True, timeout=300
                            )
                        except Exception:
                            pass
                        _update_progress(f"📦 npm ci: {m['name']}")

                    elif rtype in ('spring-boot', 'maven-lib'):
                        if self._log:
                            self._log(f"[import] mvn install en {m['name']}...")
                        mvnw = os.path.join(dest, 'mvnw.cmd' if os.name == 'nt' else 'mvnw')
                        cmd = [mvnw, 'install', '-DskipTests'] if os.path.isfile(mvnw) else ['mvn', 'install', '-DskipTests']
                        try:
                            subprocess.run(
                                cmd, cwd=dest,
                                capture_output=True, timeout=600
                            )
                        except Exception:
                            pass
                        _update_progress(f"🔧 mvn install: {m['name']}")
                    else:
                        _update_progress(f"⏭ {m['name']}: sin instalación")

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
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._settings = settings
        self._on_save = on_save
        self._db_presets = dict(settings.get('db_presets', {}))

        ctk.CTkLabel(self, text="⚙ Configuración General",
                     font=("Segoe UI", 16, "bold")).pack(pady=(20, 15))

        # Workspace dir
        ctk.CTkLabel(self, text="Directorio del workspace:").pack(
            anchor="w", padx=20, pady=(0, 3))

        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.pack(fill="x", padx=20)

        self._workspace_entry = ctk.CTkEntry(dir_frame, width=470)
        self._workspace_entry.pack(side="left")
        self._workspace_entry.insert(0, settings.get('workspace_dir', ''))

        ctk.CTkButton(
            dir_frame, text="📁", width=40,
            command=self._browse_dir
        ).pack(side="left", padx=(5, 0))

        # ─── DB Presets section ───
        ctk.CTkLabel(self, text="Presets de Base de Datos:",
                     font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=20, pady=(20, 5))

        ctk.CTkLabel(self, text="URL template usa {db_name} como placeholder del nombre de BD.",
                     font=("Segoe UI", 9), text_color="#888").pack(
            anchor="w", padx=20, pady=(0, 5))

        preset_frame = ctk.CTkFrame(self, corner_radius=8)
        preset_frame.pack(fill="x", padx=20, pady=(0, 5))

        # Preset list
        self._preset_list_frame = ctk.CTkScrollableFrame(preset_frame, height=100)
        self._preset_list_frame.pack(fill="x", padx=10, pady=(10, 5))
        self._refresh_preset_list()

        # Add preset button row
        add_row = ctk.CTkFrame(preset_frame, fg_color="transparent")
        add_row.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            add_row, text="➕ Añadir preset", width=130,
            fg_color="#4CAF50", hover_color="#388E3C",
            font=("Segoe UI", 11),
            command=self._add_preset
        ).pack(side="left")

        # Save
        ctk.CTkButton(
            self, text="💾 Guardar", width=120,
            fg_color="#4CAF50", hover_color="#388E3C",
            command=self._save
        ).pack(pady=15)

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
                fg_color="#FF9800", hover_color="#F57C00",
                font=("Segoe UI", 11),
                command=lambda n=name: self._edit_preset(n)
            ).pack(side="right", padx=(2, 0))

            ctk.CTkButton(
                row, text="🗑", width=28, height=24,
                fg_color="#f44336", hover_color="#d32f2f",
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

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Seleccionar workspace")
        if d:
            self._workspace_entry.delete(0, "end")
            self._workspace_entry.insert(0, d)

    def _save(self):
        self._settings['workspace_dir'] = self._workspace_entry.get().strip()
        self._settings['db_presets'] = self._db_presets
        if self._on_save:
            self._on_save(self._settings)
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
            fg_color="#4CAF50", hover_color="#388E3C",
            command=self._save
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=100,
            fg_color="#555", hover_color="#666",
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
