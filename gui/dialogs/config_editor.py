"""ConfigEditorDialog — dialog for editing config files."""
import os
from tkinter import messagebox

import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui import theme
from core.i18n import t


class ConfigEditorDialog(BaseDialog):
    """Dialog for editing config files (application.yml / environment.ts)."""

    def __init__(self, parent, filepath: str, log_callback=None):
        super().__init__(parent, f"Editor: {os.path.basename(filepath)}", 700, 550)
        self._filepath = filepath
        self._log = log_callback
        self._dirty = False
        self._base_title = f"Editor: {os.path.basename(filepath)}"

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

        # Track changes via the underlying tk.Text <<Modified>> virtual event
        self._editor._textbox.bind("<<Modified>>", self._on_editor_modified)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkButton(
            btn_frame, text=t("btn.save"), width=120,
            command=self._save, **theme.btn_style("success")
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text=t("btn.cancel"), width=100,
            command=self._on_close, **theme.btn_style("neutral")
        ).pack(side="right")

        ctk.CTkButton(
            btn_frame, text=t("btn.reload"), width=100,
            command=self._reload, **theme.btn_style("warning")
        ).pack(side="right", padx=(0, 10))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_editor_modified(self, event=None):
        """Called by tk.Text <<Modified>> when the content changes."""
        if not self._dirty:
            self._dirty = True
            self.title(self._base_title + " *")
        # Reset the modified flag so subsequent edits keep triggering the event
        self._editor._textbox.edit_modified(False)

    def _on_close(self):
        """Prompt for confirmation when closing with unsaved changes."""
        if self._dirty and not messagebox.askyesno(
            t("dialog.config_editor.unsaved_title"),
            t("dialog.config_editor.unsaved_msg"),
            parent=self,
        ):
            return
        self.destroy()

    def _save(self):
        content = self._editor.get("1.0", "end").rstrip('\n')
        from core.config_manager import write_config_file_raw
        if write_config_file_raw(self._filepath, content):
            if self._log:
                self._log(f"Guardado: {os.path.basename(self._filepath)}")
            messagebox.showinfo(t("dialog.config_editor.saved_title"), t("dialog.config_editor.saved_msg"))
            self._dirty = False
            self.destroy()
        else:
            messagebox.showerror(t("misc.error_title"), t("dialog.config_editor.error_save"))

    def _reload(self):
        from core.config_manager import read_config_file_raw
        content = read_config_file_raw(self._filepath)
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", content)
        self._dirty = False
        self.title(self._base_title)
