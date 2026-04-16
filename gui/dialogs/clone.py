"""CloneDialog — dialog for cloning a new repository."""
import os
import threading
import tkinter as tk
from gui.dialogs.messagebox import show_warning, show_info, show_error

import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui import theme
from core.i18n import t


class CloneDialog(BaseDialog):
    """Dialog for cloning a new repository."""

    def __init__(self, parent, workspace_dir: str, log_callback=None, on_complete=None):
        super().__init__(parent, t("dialog.clone.title"), 500, 220)
        self._workspace_dir = workspace_dir
        self._log = log_callback
        self._on_complete = on_complete

        # URL
        ctk.CTkLabel(self, text=t("dialog.clone.url_label")).pack(
            anchor="w", padx=20, pady=(20, 5))
        self._url_entry = ctk.CTkEntry(self, width=450, placeholder_text=t("dialog.clone.url_placeholder"))
        self._url_entry.pack(padx=20)

        # Folder name
        ctk.CTkLabel(self, text=t("dialog.clone.folder_label")).pack(
            anchor="w", padx=20, pady=(10, 5))
        self._name_entry = ctk.CTkEntry(self, width=450,
                                        placeholder_text=t("dialog.clone.folder_placeholder"))
        self._name_entry.pack(padx=20)

        # Progress bar
        self._progress = ctk.CTkProgressBar(self, width=450)
        self._progress.pack(padx=20, pady=(15, 5))
        self._progress.set(0)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)

        self._clone_btn = ctk.CTkButton(
            btn_frame, text=t("dialog.clone.btn"), width=120,
            command=self._start_clone, **theme.btn_style("blue")
        )
        self._clone_btn.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text=t("btn.cancel"), width=100,
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
            show_warning(self, t("misc.error_title"), t("dialog.clone.error_no_url"))
            return

        name, dest = self._build_clone_cmd(url, self._name_entry.get().strip())
        if os.path.isdir(dest):
            show_warning(self, t("misc.error_title"), t("dialog.clone.error_folder_exists", name=name))
            return

        self._clone_btn.configure(state="disabled", text=t("dialog.clone.btn_cloning"))
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
                show_info(self, t("dialog.clone.success_title"), t("dialog.clone.success_msg", name=name))
                if self._on_complete:
                    self._on_complete()
                self.destroy()
            else:
                show_error(self, t("misc.error_title"), t("dialog.clone.error_clone_msg", msg=msg))
                self._clone_btn.configure(state="normal", text=t("dialog.clone.btn"))
                self._progress.set(0)

        self.after(0, _done)
