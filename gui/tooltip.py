"""
tooltip.py — Tooltip widget for customtkinter.
Displays a styled tooltip popup on hover with a configurable delay.
"""
import customtkinter as ctk
import tkinter as tk


class ToolTip:
    """
    Attach a tooltip to any widget.
    Usage:
        ToolTip(my_button, "Descriptive text here")
    """

    DELAY_MS = 500       # Delay before showing
    WRAP_LENGTH = 250    # Max width in pixels before wrapping
    PADDING = (8, 4)     # (x, y) internal padding

    def __init__(self, widget, text: str):
        self._widget = widget
        self._text = text
        self._tip_window = None
        self._after_id = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<ButtonPress>", self._cancel, add="+")

    def _schedule(self, event=None):
        self._cancel()
        self._after_id = self._widget.after(self.DELAY_MS, self._show)

    def _cancel(self, event=None):
        if self._after_id:
            try:
                self._widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        self._hide()

    def _show(self):
        if self._tip_window:
            return

        try:
            # Position: below and slightly right of the widget
            x = self._widget.winfo_rootx() + 12
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        except tk.TclError:
            return

        self._tip_window = tw = ctk.CTkToplevel(self._widget)
        tw.withdraw()
        tw.overrideredirect(True)

        # Remove from taskbar on Windows
        tw.attributes("-topmost", True)

        # Determine colors based on current appearance mode
        mode = ctk.get_appearance_mode()
        if mode == "Dark":
            bg_color = "#2a2a3e"
            text_color = "#e0e0e0"
            border_color = "#444466"
        else:
            bg_color = "#333344"
            text_color = "#f5f5f5"
            border_color = "#555577"

        # Outer frame acts as border
        outer = ctk.CTkFrame(
            tw, corner_radius=6,
            fg_color=border_color,
            bg_color=border_color
        )
        outer.pack(fill="both", expand=True, padx=0, pady=0)

        inner = ctk.CTkFrame(
            outer, corner_radius=5,
            fg_color=bg_color,
            bg_color=bg_color
        )
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        label = ctk.CTkLabel(
            inner, text=self._text,
            font=("Segoe UI", 11),
            text_color=text_color,
            wraplength=self.WRAP_LENGTH,
            justify="left",
            anchor="w"
        )
        label.pack(
            padx=self.PADDING[0], pady=self.PADDING[1]
        )

        tw.geometry(f"+{x}+{y}")
        tw.deiconify()

    def _hide(self):
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None

    def update_text(self, text: str):
        """Update the tooltip text dynamically."""
        self._text = text
