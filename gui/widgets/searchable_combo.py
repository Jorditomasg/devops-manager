"""searchable_combo.py — Drop-in replacement for CTkComboBox with searchable dropdown.

The display field is always non-editable. Clicking it opens a popup with:
  - A search/filter entry at the top (auto-focused)
  - A scrollable, filtered list of options

Public API is CTkComboBox-compatible:
    set(value), get() -> str,
    configure(values=..., state=..., text_color=..., font=...,
              button_color=..., button_hover_color=..., command=...)
"""
from __future__ import annotations

import sys
import tkinter as tk
import customtkinter as ctk

from gui import theme
from gui.tooltip import ToolTip
from core.i18n import t


class SearchableCombo(ctk.CTkFrame):
    """Searchable drop-in replacement for CTkComboBox.

    Usage::

        combo = SearchableCombo(parent, values=["a", "b"], command=on_change,
                                **theme.combo_style())
        combo.pack(...)
        combo.set("a")
        value = combo.get()
        combo.configure(values=[...])
    """

    def __init__(
        self,
        parent,
        *,
        values: list[str] | None = None,
        command=None,
        width: int = 200,
        height: int | None = None,
        fg_color=None,
        border_color=None,
        button_color=None,
        button_hover_color=None,
        corner_radius: int | None = None,
        border_width: int = 2,
        font=None,
        state: str = "readonly",
        variable=None,
        **kwargs,
    ):
        self._values: list[str] = list(values or [])
        self._command = command
        self._state = state
        self._variable = variable
        self._combo_font = font
        self._button_color = button_color
        self._button_hover_color = button_hover_color or button_color
        self._popup: ctk.CTkToplevel | None = None
        self._click_bind_id: str | None = None
        self._global_click_root: tk.Misc | None = None
        self._search_var: ctk.StringVar | None = None
        self._search_trace_id: str | None = None
        self._register_after_id: str | None = None
        self._popup_btns: list[ctk.CTkButton] = []

        # Initial selected value
        if variable is not None:
            self._selected = variable.get()
        else:
            self._selected = self._values[0] if self._values else ""

        h = height or theme.G.btn_height_md
        cr = corner_radius if corner_radius is not None else theme.G.corner_combo
        fg = fg_color or theme.C.section
        bc = border_color or theme.C.default_border
        self._inner_color = fg

        super().__init__(
            parent,
            width=width,
            height=h,
            corner_radius=cr,
            fg_color=fg,
            border_color=bc,
            border_width=border_width,
            **kwargs,
        )
        self.pack_propagate(False)
        self.grid_propagate(False)

        self._width = width
        self._height = h
        self._corner_radius = cr

        self._build_display()

    # ── Display ───────────────────────────────────────────────────────────────

    def _build_display(self):
        """Non-editable label showing selected value + dropdown arrow button."""
        self._display_label = ctk.CTkLabel(
            self,
            text=self._selected,
            font=self._combo_font or theme.font("base"),
            text_color=theme.C.text_primary,
            anchor="w",
            cursor="hand2",
        )
        self._display_label.pack(side="left", padx=(6, 0), pady=2, fill="x", expand=True)
        self._display_tooltip = ToolTip(self, self._selected or "")

        sep_color = self._button_color or theme.C.card_border
        self._separator = ctk.CTkFrame(self, width=1, fg_color=sep_color, corner_radius=0)
        self._separator.pack(side="right", fill="y", pady=2)

        self._arrow_btn = ctk.CTkButton(
            self,
            text="▾",
            width=26,
            fg_color=self._inner_color,
            hover_color=self._button_color or theme.C.card_border,
            text_color=theme.C.text_muted,
            font=theme.font("sm"),
            corner_radius=self._corner_radius,
            command=self._toggle_popup,
        )
        self._arrow_btn.pack(side="right", padx=(0, 2), pady=2)

        # "break" stops the event propagating to parent frames (prevents double-toggle)
        self._display_label.bind("<Button-1>", lambda e: (self._toggle_popup(), "break")[1])

        # Propagate hover events so ToolTip works when placed on this widget
        for child in (self._display_label, self._arrow_btn):
            child.bind("<Enter>", lambda e: self.event_generate("<Enter>"), "+")
            child.bind("<Leave>", lambda e: self.event_generate("<Leave>"), "+")

    # ── Popup lifecycle ───────────────────────────────────────────────────────

    def _toggle_popup(self):
        if self._state == "disabled":
            return
        if self._popup and self._popup.winfo_exists():
            self._close_popup()
        else:
            self._open_popup()

    def _open_popup(self):
        """Create and position the searchable dropdown below this widget."""
        # tk.Toplevel avoids CTkToplevel's geometry-scaling issues with overrideredirect.
        # On Windows: overrideredirect(True) removes decorations cleanly.
        # On Linux: overrideredirect breaks focus on Wayland; use popup_menu type hint instead.
        popup = tk.Toplevel(self)
        popup.withdraw()
        if sys.platform == "win32":
            popup.overrideredirect(True)
        else:
            try:
                popup.wm_attributes("-type", "popup_menu")
            except tk.TclError:
                popup.overrideredirect(True)  # X11 fallback
        bg = theme.C.card
        popup.configure(bg=bg if isinstance(bg, str) else bg[0])
        self._popup = popup

        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 2
        w = max(self.winfo_width(), 180)

        # Outer border frame
        outer = ctk.CTkFrame(
            popup,
            fg_color=theme.C.card,
            border_color=theme.C.card_border,
            border_width=1,
            corner_radius=theme.G.corner_card,
        )
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        # Search entry (auto-focused)
        self._search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(
            outer,
            textvariable=self._search_var,
            placeholder_text=t("placeholder.search"),
            font=theme.font("base"),
            height=theme.G.btn_height_md,
            corner_radius=theme.G.corner_btn,
            fg_color=theme.C.section,
            border_color=theme.C.default_border,
        )
        search_entry.pack(fill="x", padx=6, pady=(6, 4))

        # Scrollable list — height capped to 8 visible items
        item_h = 32
        list_h = min(len(self._values), 8) * item_h or item_h
        self._list_frame = ctk.CTkScrollableFrame(
            outer, fg_color="transparent", height=list_h,
        )
        self._list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 6))

        # Scroll forwarder: mousewheel on any child routes to the canvas
        try:
            canvas = self._list_frame._parent_canvas
            canvas.configure(yscrollincrement=20)

            def _forward_scroll(event):
                if event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")
                else:
                    canvas.yview_scroll(int(-event.delta / 120), "units")

            self._popup_scroll_fn = _forward_scroll
            for _sw in (canvas, self._list_frame):
                _sw.bind("<MouseWheel>", _forward_scroll, "+")
                _sw.bind("<Button-4>", _forward_scroll, "+")
                _sw.bind("<Button-5>", _forward_scroll, "+")
        except AttributeError:
            self._popup_scroll_fn = None

        self._popup_btns = []
        self._render_items("")
        self._search_trace_id = self._search_var.trace_add(
            "write", lambda *_: self._render_items(self._search_var.get())
        )

        # Finalize geometry
        popup.update_idletasks()
        popup_h = theme.G.btn_height_md + list_h + 28  # entry + list + padding
        popup.geometry(f"{w}x{popup_h}+{x}+{y}")
        popup.deiconify()
        popup.lift()
        search_entry.focus_set()

        popup.bind("<Escape>", lambda _: self._close_popup())
        # Defer global bind so the opening click doesn't immediately close the popup
        self._register_after_id = self.after(50, self._register_global_click)

    def _render_items(self, filter_text: str):
        """Destroy and recreate list buttons matching the current filter."""
        for btn in self._popup_btns:
            btn.destroy()
        self._popup_btns.clear()

        q = filter_text.strip().lower()
        items = [v for v in self._values if q in v.lower()] if q else self._values

        if not items:
            lbl = ctk.CTkLabel(
                self._list_frame,
                text=t("placeholder.no_results"),
                font=self._combo_font or theme.font("base"),
                text_color=theme.C.text_muted,
                anchor="center",
            )
            lbl.pack(fill="x", pady=8)
            self._popup_btns.append(lbl)  # type: ignore[arg-type]
            return

        for val in items:
            btn = ctk.CTkButton(
                self._list_frame,
                text=val,
                anchor="w",
                height=28,
                fg_color=theme.C.section if val == self._selected else "transparent",
                hover_color=theme.C.section,
                text_color=theme.C.text_primary,
                font=self._combo_font or theme.font("base"),
                corner_radius=theme.G.corner_btn,
                command=lambda v=val: self._select(v),
            )
            btn.pack(fill="x", pady=1)
            if hasattr(self, "_popup_scroll_fn") and self._popup_scroll_fn:
                btn.bind("<MouseWheel>", self._popup_scroll_fn, "+")
                btn.bind("<Button-4>", self._popup_scroll_fn, "+")
                btn.bind("<Button-5>", self._popup_scroll_fn, "+")
            self._popup_btns.append(btn)

    def _register_global_click(self):
        """Register the outside-click handler after a short delay to skip the opening click."""
        self._register_after_id = None
        if self._popup and self._popup.winfo_exists():
            self._global_click_root = self.winfo_toplevel()
            self._click_bind_id = self._global_click_root.bind("<Button-1>", self._on_global_click, "+")

    def _on_global_click(self, event):
        """Close the popup when the user clicks outside it."""
        if not (self._popup and self._popup.winfo_exists()):
            return
        px, py = self._popup.winfo_rootx(), self._popup.winfo_rooty()
        pw, ph = self._popup.winfo_width(), self._popup.winfo_height()
        if not (px <= event.x_root <= px + pw and py <= event.y_root <= py + ph):
            self._close_popup()

    def _close_popup(self):
        # Cancel pending after() that registers the global click handler
        if self._register_after_id:
            try:
                self.after_cancel(self._register_after_id)
            except Exception:
                pass
            self._register_after_id = None
        # Remove the global click binding using the cached root
        if self._click_bind_id and self._global_click_root:
            try:
                self._global_click_root.unbind("<Button-1>", self._click_bind_id)
            except Exception:
                pass
        self._click_bind_id = None
        self._global_click_root = None
        # Remove the search trace to avoid stale callbacks
        if self._search_var and self._search_trace_id:
            try:
                self._search_var.trace_remove("write", self._search_trace_id)
            except Exception:
                pass
        self._search_trace_id = None
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
        self._popup = None
        self._popup_btns = []
        self._popup_scroll_fn = None

    def _select(self, value: str):
        """Select an item: update display, close popup, fire callback."""
        self._close_popup()
        self._selected = value
        if hasattr(self, "_display_label"):
            self._display_label.configure(text=value)
        if hasattr(self, "_display_tooltip"):
            self._display_tooltip.update_text(value)
        if self._variable is not None:
            self._variable.set(value)
        if self._command:
            self._command(value)

    # ── Public API (CTkComboBox-compatible) ───────────────────────────────────

    def set(self, value: str):
        """Set the displayed value without firing the command callback."""
        self._selected = value
        if hasattr(self, "_display_label"):
            self._display_label.configure(text=value)
        if hasattr(self, "_display_tooltip"):
            self._display_tooltip.update_text(value)
        if self._variable is not None:
            self._variable.set(value)

    def get(self) -> str:
        """Return the currently selected value."""
        if self._variable is not None:
            return self._variable.get()
        return self._selected

    def configure(self, **kwargs):
        """Handle combo-specific kwargs before forwarding the rest to CTkFrame."""
        if "values" in kwargs:
            self._values = list(kwargs.pop("values"))
        if "state" in kwargs:
            s = kwargs.pop("state")
            self._state = s
            if hasattr(self, "_display_label"):
                self._display_label.configure(
                    text_color=theme.C.text_muted if s == "disabled" else theme.C.text_primary
                )
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "text_color" in kwargs:
            tc = kwargs.pop("text_color")
            if hasattr(self, "_display_label"):
                self._display_label.configure(text_color=tc)
        if "font" in kwargs:
            f = kwargs.pop("font")
            self._combo_font = f
            if hasattr(self, "_display_label"):
                self._display_label.configure(font=f)
        if "button_color" in kwargs:
            bc = kwargs.pop("button_color")
            self._button_color = bc
            effective = bc or theme.C.card_border
            if hasattr(self, "_arrow_btn"):
                self._arrow_btn.configure(hover_color=effective)
            if hasattr(self, "_separator"):
                self._separator.configure(fg_color=effective)
        if "button_hover_color" in kwargs:
            kwargs.pop("button_hover_color")  # absorbed into button_color logic
        if kwargs:
            super().configure(**kwargs)
