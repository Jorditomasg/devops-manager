"""CloneDialog — dialog for cloning a new repository."""
import os
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui import theme


class CloneDialog(BaseDialog):
    """Dialog for cloning a new repository."""

    def __init__(self, parent, workspace_dir: str, log_callback=None, on_complete=None):
        super().__init__(parent, "Clonar Repositorio", 500, 220)
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

    def _build_clone_cmd(self, url: str, name: str) -> tuple:
        """Return (resolved_name, dest_path) from url and optional folder name."""
        if not name:
            name = url.rstrip('/').split('/')[-1]
            if name.endswith('.git'):
                name = name[:-4]
        dest = os.path.join(self._workspace_dir, name)
        return name, dest

    def _start_clone(self):
        url = self._url_entry.get().strip()
        if not url:
            messagebox.showwarning("Error", "Introduce una URL de repositorio")
            return

        name, dest = self._build_clone_cmd(url, self._name_entry.get().strip())
        if os.path.isdir(dest):
            messagebox.showwarning("Error", f"La carpeta '{name}' ya existe")
            return

        self._clone_btn.configure(state="disabled", text="Clonando...")
        threading.Thread(target=self._do_clone, args=(url, dest, name), daemon=True).start()

    def _do_clone(self, url: str, dest: str, name: str) -> None:
        """Run clone in background thread and dispatch result to main thread."""
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
