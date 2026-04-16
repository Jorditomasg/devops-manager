"""gui/dialogs/messagebox — themed replacements for tkinter.messagebox.

Public API (drop-in replacements):
    show_info(parent, title, message)
    show_warning(parent, title, message)
    show_error(parent, title, message)
    ask_yes_no(parent, title, message) -> bool
"""

from __future__ import annotations

import customtkinter as ctk
from gui import theme
from gui.dialogs._base import BaseDialog

_ICONS: dict[str, tuple[str, str]] = {
    "info":     ("ℹ", "#6366f1"),
    "warning":  ("⚠", "#f59e0b"),
    "error":    ("✕", "#ef4444"),
    "question": ("?", "#7c3aed"),
}


class _AppMessageDialog(BaseDialog):
    """Internal: themed modal dialog — icon + message + buttons."""

    def __init__(
        self,
        parent,
        title: str,
        message: str,
        buttons: list[tuple[str, object, str]],
        icon_key: str,
    ):
        char_per_line = 52
        line_count = max(1, -(-len(message) // char_per_line) + message.count("\n"))
        # 20px padding (top+bottom) + 20px/line + 10px gap + 28px button + 30px title bar
        height = max(108, 88 + line_count * 20)
        super().__init__(parent, title, 460, height)
        self.result: object = None
        self._build(message, buttons, icon_key)

    def _build(self, message: str, buttons: list, icon_key: str) -> None:
        icon_char, accent = _ICONS.get(icon_key, ("ℹ", "#6366f1"))

        root = ctk.CTkFrame(self, fg_color=theme.C.card, corner_radius=0)
        root.pack(fill="both", expand=True)

        # Colored left accent bar
        bar = ctk.CTkFrame(root, fg_color=accent, width=5, corner_radius=0)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)

        # Main content
        content = ctk.CTkFrame(root, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=18, pady=10)

        # Button row anchored to bottom — must be packed BEFORE msg_row
        btn_row = ctk.CTkFrame(content, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x")

        # Icon + message row above buttons
        msg_row = ctk.CTkFrame(content, fg_color="transparent")
        msg_row.pack(side="top", fill="x", pady=(0, 10))

        ctk.CTkLabel(
            msg_row,
            text=icon_char,
            font=theme.font("xl", bold=True),
            text_color=accent,
            width=28,
        ).pack(side="left", anchor="n", padx=(0, 10))

        ctk.CTkLabel(
            msg_row,
            text=message,
            font=theme.font("base"),
            text_color=theme.C.text_primary,
            wraplength=370,
            justify="left",
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        for label, result, variant in reversed(buttons):
            ctk.CTkButton(
                btn_row,
                text=label,
                command=lambda r=result: self._close(r),
                **theme.btn_style(variant, height="md", width=90),
            ).pack(side="right", padx=(6, 0))

    def _close(self, result: object) -> None:
        self.result = result
        self.destroy()


# ── Public API ────────────────────────────────────────────────────────────────

def show_info(parent, title: str, message: str) -> None:
    dlg = _AppMessageDialog(parent, title, message, [("OK", True, "blue")], "info")
    dlg.wait_window()


def show_warning(parent, title: str, message: str) -> None:
    dlg = _AppMessageDialog(parent, title, message, [("OK", True, "warning")], "warning")
    dlg.wait_window()


def show_error(parent, title: str, message: str) -> None:
    dlg = _AppMessageDialog(parent, title, message, [("OK", True, "danger")], "error")
    dlg.wait_window()


def ask_yes_no(parent, title: str, message: str) -> bool:
    dlg = _AppMessageDialog(
        parent, title, message,
        [("No", False, "neutral"), ("Yes", True, "blue")],
        "question",
    )
    dlg.wait_window()
    return bool(dlg.result)
