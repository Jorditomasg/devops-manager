"""RepoConfigManagerDialog — manage per-repo config files."""
import os
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui import theme


class RepoConfigManagerDialog(BaseDialog):
    """Dialog to manage Env/App configurations for a repository."""

    def __init__(self, parent, repo, config_key=None, log_callback=None, on_close_callback=None, source_dir=''):
        title = f"⚙ Gestor de Entornos/Apps - {config_key if config_key else repo.name}"
        super().__init__(parent, title, 850, 600)
        # This dialog is resizable (override BaseDialog's fixed size)
        self.resizable(True, True)
        self.minsize(700, 450)

        self._repo = repo
        self._config_key = config_key if config_key else repo.name
        self._log = log_callback
        self._on_close = on_close_callback
        self._source_dir = os.path.normpath(source_dir) if source_dir else ''

        from core.config_manager import load_repo_configs
        self._configs = load_repo_configs(self._config_key)

        self._current_selected = None
        self._config_btns: dict = {}   # config_name -> CTkButton

        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.after_idle(lambda: self.after_idle(self._refresh_list))

    def _build_ui(self):
        # Paneles principales
        left_panel = ctk.CTkFrame(self, width=250, corner_radius=0)
        left_panel.pack(side="left", fill="y", padx=0, pady=0)
        left_panel.pack_propagate(False)

        right_panel = ctk.CTkFrame(self, fg_color="transparent")
        right_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        self._build_list_panel(left_panel)
        self._build_editor_panel(right_panel)
        self._build_action_buttons(right_panel)

    def _build_list_panel(self, frame):
        ctk.CTkLabel(frame, text="Entornos Guardados", font=theme.font("h2", bold=True)).pack(pady=(15, 10))

        self._list_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        ctk.CTkButton(
            frame, text="➕ Nuevo",
            command=self._cmd_new, **theme.btn_style("blue")
        ).pack(fill="x", padx=15, pady=(5, 5))

        ctk.CTkButton(
            frame, text="📥 Auto-Importar",
            command=self._cmd_auto_import, **theme.btn_style("purple_alt")
        ).pack(fill="x", padx=15, pady=(0, 15))

    def _build_editor_panel(self, frame):
        self._title_var = ctk.StringVar(value="Selecciona un entorno")
        header = ctk.CTkFrame(frame, fg_color="transparent")
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
            frame, font=theme.font("base", mono=True),
            wrap="none", corner_radius=theme.G.corner_btn,
            border_width=theme.G.border_width, border_color=theme.C.card_border
        )
        self._editor.pack(fill="both", expand=True, pady=(0, 10))
        self._editor.configure(state="disabled")

    def _build_action_buttons(self, frame):
        self._btn_save = ctk.CTkButton(
            frame, text="💾 Guardar Cambios en Entorno",
            command=self._cmd_save_text, state="disabled",
            **theme.btn_style("success")
        )
        self._btn_save.pack(side="right")

    def _refresh_list(self):
        for widget in self._list_frame.winfo_children():
            widget.destroy()
        self._config_btns.clear()

        _blue = theme.btn_style("blue")
        for name in sorted(self._configs.keys()):
            fg = _blue["fg_color"] if name == self._current_selected else "transparent"
            btn = ctk.CTkButton(
                self._list_frame, text=name, anchor="w",
                fg_color=fg, hover_color=_blue["hover_color"],
                command=lambda n=name: self._select_config(n)
            )
            btn.pack(fill="x", pady=2)
            self._config_btns[name] = btn

    def _select_config(self, name: str):
        if self._current_selected and self._current_selected != name:
            self._check_unsaved_changes()

        prev = self._current_selected
        self._current_selected = name

        # Update only the two affected button colors — no full list rebuild needed
        _blue = theme.btn_style("blue")
        if prev and prev in self._config_btns:
            try:
                self._config_btns[prev].configure(fg_color="transparent")
            except Exception:
                pass
        if name in self._config_btns:
            try:
                self._config_btns[name].configure(fg_color=_blue["fg_color"])
            except Exception:
                pass

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
