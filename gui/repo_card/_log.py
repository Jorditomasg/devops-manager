"""_log.py — Log management mixin for RepoCard."""
from __future__ import annotations
import os
import re
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from gui.log_helpers import insert_log_line
from gui.constants import LOG_MAX_LINES
from gui import theme


class LogMixin:
    """Mixin providing _repo_log, _clear_logs, _detach_logs, _flash_log_icon.
    Requires self._log_box, self._log_detached_win, self._detached_log_box,
    self.repo_info to be set by the main RepoCard.__init__.
    """

    def _clear_logs(self):
        """Clear the embedded and detached logs, and hide the console."""
        if hasattr(self, '_log_textbox'):
            self._log_textbox.configure(state="normal")
            self._log_textbox.delete("1.0", "end")
            self._log_textbox.configure(state="disabled")
            self._log_line_count[0] = 0

        if getattr(self, '_detached_log_textbox', None) and self._detached_log_textbox.winfo_exists():
            self._detached_log_textbox.configure(state="normal")
            self._detached_log_textbox.delete("1.0", "end")
            self._detached_log_textbox.configure(state="disabled")
            self._detached_log_line_count[0] = 0

        self._has_logs = False

    def _detach_logs(self):
        """Open the logs in a separate detached window."""
        # Prevent multiple detached windows
        if getattr(self, '_detached_log_window', None) and self._detached_log_window.winfo_exists():
            self._detached_log_window.focus()
            return

        self._detached_log_window = ctk.CTkToplevel(self)
        self._detached_log_window.title(f"Logs - {self._repo.name}")
        self._detached_log_window.geometry("800x600")

        # Set window icon (always red for consistency)
        try:
            app_dir = getattr(self.winfo_toplevel(), '_app_dir', None)
            if app_dir:
                _icon_path = os.path.join(app_dir, "assets", "icons", "icon_red.ico")
                if os.path.exists(_icon_path):
                    self._detached_log_window.after(200, lambda p=_icon_path: self._detached_log_window.iconbitmap(p))
        except Exception:
            pass

        # Bring window to front
        self.after(100, lambda: self._detached_log_window.lift())
        self.after(110, lambda: self._detached_log_window.focus_force())

        header = ctk.CTkFrame(self._detached_log_window, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkButton(
            header, text="🗑 Limpiar", width=60,
            command=self._clear_logs,
            **theme.btn_style("log_action", height="sm", font_size="sm")
        ).pack(side="left")

        self._detached_log_textbox = ctk.CTkTextbox(
            self._detached_log_window,
            **theme.log_textbox_style(detached=True)
        )
        self._detached_log_textbox.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        # Copy current content (deferred so the window can render first)
        def _copy_content():
            if not hasattr(self, '_log_textbox'):
                return
            current_logs = self._log_textbox.get("1.0", "end")
            self._detached_log_textbox.configure(state="normal")
            self._detached_log_textbox.insert("end", current_logs)
            self._detached_log_textbox.configure(state="disabled")
            self._detached_log_textbox.see("end")
            # Sync line counter with the copied content
            self._detached_log_line_count[0] = self._log_line_count[0]

        self._detached_log_window.after(0, _copy_content)

    def _repo_log(self, message: str):
        """Add a timestamped log message to this repo's console. Thread-safe."""
        if message:
            # Eliminar secuencias de escape ANSI (ej. colores)
            message = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', message)

        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"

        def _insert():
            self._has_logs = True

            if hasattr(self, '_log_textbox'):
                insert_log_line(self._log_textbox, line, count_ref=self._log_line_count)
            else:
                self._pre_panel_log_buffer.append(line)

            if getattr(self, '_detached_log_textbox', None) and self._detached_log_textbox.winfo_exists():
                insert_log_line(self._detached_log_textbox, line, count_ref=self._detached_log_line_count)

            self._flash_log_icon()

        try:
            self.after(0, _insert)
        except tk.TclError:
            pass

    def _flash_log_icon(self):
        """Temporarily change the status icon color to orange when a log is received."""
        if not hasattr(self, '_status_label'):
            return

        # Only flash orange if status is already running or starting
        if getattr(self, '_status', 'stopped') not in ('running', 'starting'):
            return

        if hasattr(self, '_log_flash_timer') and self._log_flash_timer:
            self.after_cancel(self._log_flash_timer)

        self._status_label.configure(text="🔴", text_color=theme.STATUS_ICONS.get('logging', theme.C.status_logging))

        def _revert():
            if hasattr(self, '_status_label') and hasattr(self, '_status'):
                self._status_label.configure(text="🔴", text_color=theme.STATUS_ICONS.get(self._status, theme.C.status_stopped))
            self._log_flash_timer = None

        self._log_flash_timer = self.after(3000, _revert)
