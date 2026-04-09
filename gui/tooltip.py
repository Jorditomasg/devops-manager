"""
tooltip.py — Tooltip widget for customtkinter.
Displays a styled tooltip popup on hover with a configurable delay.
"""
import customtkinter as ctk
import tkinter as tk

from gui import theme

# Cache delay once at import time — avoids a dict lookup on every mouse-enter event
_TOOLTIP_DELAY_MS: int = theme.tooltip_delay()


class ToolTip:
    """
    Attach a tooltip to any widget.
    Usage:
        ToolTip(my_button, "Descriptive text here")
    """

    def __init__(self, widget, text: str):
        self._widget = widget
        self._text = text
        self._tip_window = None
        self._after_id = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<ButtonPress>", self._cancel, add="+")

    def _schedule(self, event=None):
        if not self._text:
            return
        self._cancel()
        self._after_id = self._widget.after(_TOOLTIP_DELAY_MS, self._show)

    def _cancel(self, event=None):
        if self._after_id:
            try:
                self._widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        self._hide()

    def _show(self):
        if self._tip_window or not self._text:
            return

        try:
            # Prevent showing tooltip if mouse has left the widget bounds
            x_mouse = self._widget.winfo_pointerx()
            y_mouse = self._widget.winfo_pointery()
            x_widget = self._widget.winfo_rootx()
            y_widget = self._widget.winfo_rooty()
            w_widget = self._widget.winfo_width()
            h_widget = self._widget.winfo_height()
            
            if not (x_widget <= x_mouse <= x_widget + w_widget and 
                    y_widget <= y_mouse <= y_widget + h_widget):
                return

            # Position: below and slightly right of the widget
            x = x_widget + 12
            y = y_widget + h_widget + 4
        except tk.TclError:
            return

        self._tip_window = tw = ctk.CTkToplevel(self._widget)
        tw.withdraw()
        tw.overrideredirect(True)

        # Remove from taskbar on Windows
        tw.attributes("-topmost", True)

        mode = ctk.get_appearance_mode()
        bg_color, text_color, border_color = theme.tooltip_colors(mode)

        # Outer frame acts as border
        outer = ctk.CTkFrame(
            tw, corner_radius=theme.G.corner_tooltip,
            fg_color=border_color,
            bg_color=border_color
        )
        outer.pack(fill="both", expand=True, padx=0, pady=0)

        inner = ctk.CTkFrame(
            outer, corner_radius=theme.G.corner_tooltip - 1,
            fg_color=bg_color,
            bg_color=bg_color
        )
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        label = ctk.CTkLabel(
            inner, text=self._text,
            font=theme.font("md"),
            text_color=text_color,
            wraplength=theme.tooltip_wrap(),
            justify="left",
            anchor="w"
        )
        label.pack(padx=8, pady=4)

        tw.geometry(f"+{x}+{y}")
        tw.deiconify()

    def _hide(self):
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None

    def update_text(self, text: str):
        """Update the tooltip text dynamically. Cancels any pending/visible tooltip if cleared."""
        self._text = text
        if not text:
            self._cancel()
