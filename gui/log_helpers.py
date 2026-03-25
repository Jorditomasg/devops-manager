"""Shared log-insertion helpers for all GUI textboxes."""
from __future__ import annotations
import customtkinter as ctk
from gui.constants import LOG_MAX_LINES


def insert_log_line(textbox: ctk.CTkTextbox, text: str, max_lines: int = LOG_MAX_LINES) -> None:
    """Thread-safe log line insertion with automatic line-count trimming.

    Caller is responsible for scheduling on the main thread (after(..) / event_generate).
    """
    textbox.configure(state="normal")
    textbox.insert("end", text + "\n")
    lines = int(textbox.index("end-1c").split(".")[0])
    if lines > max_lines:
        textbox.delete("1.0", f"{lines - max_lines}.0")
    textbox.see("end")
    textbox.configure(state="disabled")
