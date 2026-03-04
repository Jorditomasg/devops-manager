"""
log_panel.py — Real-time log output panel with timestamps.
"""
import customtkinter as ctk
from datetime import datetime
import threading

# ── Font constants ──────────────────────────────────────────────
FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"


class LogPanel(ctk.CTkFrame):
    """Scrollable log panel that displays timestamped messages."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(corner_radius=10, fg_color="transparent")

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(header, text="📋 Logs",
                     font=(FONT_FAMILY, 14, "bold")).pack(side="left")

        ctk.CTkButton(
            header, text="Limpiar", width=70, height=28,
            font=(FONT_FAMILY, 10),
            fg_color="#555555", hover_color="#666666",
            command=self.clear
        ).pack(side="right")

        # Log text area — fills the tab
        self._textbox = ctk.CTkTextbox(
            self, font=(FONT_MONO, 11),
            corner_radius=8, border_width=1,
            border_color=("#ccc", "#333"),
            state="disabled"
        )
        self._textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._lock = threading.Lock()
        self._max_lines = 500

    def log(self, message: str):
        """Add a timestamped log message. Thread-safe."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        def _insert():
            self._textbox.configure(state="normal")
            self._textbox.insert("end", line)

            # Trim old lines
            content = self._textbox.get("1.0", "end")
            lines = content.splitlines()
            if len(lines) > self._max_lines:
                excess = len(lines) - self._max_lines
                self._textbox.delete("1.0", f"{excess + 1}.0")

            self._textbox.see("end")
            self._textbox.configure(state="disabled")

        # Schedule on main thread
        try:
            self.after(0, _insert)
        except Exception:
            pass

    def clear(self):
        """Clear all log messages."""
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")
