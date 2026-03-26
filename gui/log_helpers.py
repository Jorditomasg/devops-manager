"""Shared log-insertion helpers for all GUI textboxes."""
from __future__ import annotations
from typing import Optional, List
import customtkinter as ctk
from gui.constants import LOG_MAX_LINES


def insert_log_line(
    textbox: ctk.CTkTextbox,
    text: str,
    max_lines: int = LOG_MAX_LINES,
    count_ref: Optional[List[int]] = None,
) -> None:
    """Thread-safe log line insertion with automatic line-count trimming.

    Caller is responsible for scheduling on the main thread (after(..) / event_generate).

    Args:
        textbox: The CTkTextbox to insert into.
        text: The log line to append (a newline is added automatically).
        max_lines: Maximum number of lines to keep in the textbox.
        count_ref: Optional single-element list [current_count] for O(1) trimming.
                   When provided the expensive textbox.index() query is skipped.
                   The element is incremented on insert and decremented on trim.
    """
    textbox.configure(state="normal")
    textbox.insert("end", text + "\n")

    if count_ref is not None:
        count_ref[0] += 1
        if count_ref[0] > max_lines:
            textbox.delete("1.0", "2.0")
            count_ref[0] -= 1
    else:
        lines = int(textbox.index("end-1c").split(".")[0])
        if lines > max_lines:
            textbox.delete("1.0", f"{lines - max_lines}.0")

    textbox.see("end")
    textbox.configure(state="disabled")
