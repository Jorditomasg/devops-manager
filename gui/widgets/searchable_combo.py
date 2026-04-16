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
import tkinter.font as tkFont
import customtkinter as ctk

from gui import theme
from gui.tooltip import ToolTip
from gui.constants import POPUP_BORDER_PAD, COMBO_SCROLLBAR_W
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

    _MAX_VISIBLE: int = 9   # maximum rows shown in the list (triggers scroll above this)
    _LIST_ITEM_H: int = 36  # Increased to ensure buttons fit comfortably inside scrollable frame

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
        self._popup_outer: ctk.CTkFrame | None = None
        self._popup_w: int = 0
        self._popup_x: int = 0
        self._popup_y: int = 0
        self._click_bind_id: str | None = None
        self._global_click_root: tk.Misc | None = None
        self._search_var: ctk.StringVar | None = None
        self._search_trace_id: str | None = None
        self._register_after_id: str | None = None
        self._popup_btns: list[ctk.CTkButton] = []
        self._list_canvas: tk.Canvas | None = None
        self._inner_frame: tk.Frame | None = None
        self._list_scrollbar: ctk.CTkScrollbar | None = None
        self._list_canvas_host: tk.Frame | None = None
        self._canvas_window_id: int | None = None
        self._is_popup_scrolling: bool = False

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
        # Right-side elements MUST be packed first so the expanding label
        # only fills the space that remains after the button is placed.
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

        sep_color = self._button_color or theme.C.card_border
        self._separator = ctk.CTkFrame(self, width=1, fg_color=sep_color, corner_radius=0)
        self._separator.pack(side="right", fill="y", pady=2)

        self._display_label = ctk.CTkLabel(
            self,
            text="",
            font=self._combo_font or theme.font("base"),
            text_color=theme.C.text_primary,
            anchor="w",
            cursor="hand2",
        )
        self._display_label.pack(side="left", padx=(6, 0), pady=2, fill="x", expand=True)
        # Attach tooltip directly to the label — avoids unreliable event_generate propagation
        self._display_tooltip = ToolTip(self._display_label, "")

        # "break" stops the event propagating to parent frames (prevents double-toggle)
        self._display_label.bind("<Button-1>", lambda e: (self._toggle_popup(), "break")[1])
        # Re-evaluate truncation whenever the label is resized
        self._display_label.bind("<Configure>", lambda e: self._update_display_text())

        self._update_display_text()

        # Close popup when this widget is destroyed (e.g. app shutdown)
        self.bind("<Destroy>", self._on_self_destroy)

    def _on_self_destroy(self, event):
        if event.widget is self:
            self._close_popup()

    def _make_measure_font(self) -> tkFont.Font:
        """Return a tkFont.Font matching the current combo font, for text measurement."""
        spec = self._combo_font or theme.font("base")
        if isinstance(spec, tuple) and len(spec) >= 2:
            family, size = spec[0], abs(spec[1])
            weight = "bold" if len(spec) > 2 and "bold" in str(spec[2]) else "normal"
            return tkFont.Font(family=family, size=size, weight=weight)
        return tkFont.nametofont("TkDefaultFont")

    def _update_display_text(self):
        """Truncate the displayed text with an ellipsis when it overflows the label width.

        Sets the tooltip to the full text only when truncation occurs; clears it otherwise.
        """
        if not hasattr(self, "_display_label") or not self._display_label.winfo_exists():
            return

        full_text = self._selected
        available_w = self._display_label.winfo_width()

        if available_w <= 1:
            # Widget not yet laid out — set raw text; <Configure> will re-trigger
            self._display_label.configure(text=full_text)
            return

        if not full_text:
            self._display_label.configure(text="")
            self._display_tooltip.update_text("")
            return

        f = self._make_measure_font()
        if f.measure(full_text) <= available_w:
            self._display_label.configure(text=full_text)
            self._display_tooltip.update_text("")
        else:
            ellipsis = "…"
            max_w = available_w - f.measure(ellipsis)
            truncated = full_text
            while truncated and f.measure(truncated) > max_w:
                truncated = truncated[:-1]
            self._display_label.configure(text=truncated + ellipsis)
            self._display_tooltip.update_text(full_text)

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
        search_entry.pack(fill="x", padx=6, pady=(6, 2))

        # Canvas-based scrollable list — replaces CTkScrollableFrame (no private API access)
        card_bg = theme.C.card  # plain str hex, safe for tk widgets
        self._list_canvas_host = tk.Frame(outer, bg=card_bg)
        self._list_canvas_host.pack(fill="x", padx=4, pady=(0, 4))
        # Grid layout: column 0 = canvas (expands), column 1 = scrollbar (fixed width, optional)
        self._list_canvas_host.grid_columnconfigure(0, weight=1)
        self._list_canvas_host.grid_rowconfigure(0, weight=1)

        self._list_canvas = tk.Canvas(
            self._list_canvas_host,
            highlightthickness=0,
            bd=0,
            yscrollincrement=20,
            bg=card_bg,
        )
        self._list_canvas.grid(row=0, column=0, sticky="nsew")

        self._list_scrollbar = ctk.CTkScrollbar(
            self._list_canvas_host,
            orientation="vertical",
            command=self._list_canvas.yview,
            width=COMBO_SCROLLBAR_W,
            fg_color="transparent",
        )
        # Scrollbar is NOT gridded here; _resize_popup() manages grid/grid_remove

        self._inner_frame = tk.Frame(self._list_canvas, bg=card_bg)
        self._canvas_window_id = self._list_canvas.create_window(
            (0, 0), window=self._inner_frame, anchor="nw"
        )

        # Sync scrollregion only when popup is in scrolling mode.
        # When not scrolling, _resize_popup() sets the scrollregion explicitly to match
        # canvas height — this binding must be a no-op to avoid overriding that fix.
        self._inner_frame.bind(
            "<Configure>",
            lambda e: self._list_canvas.configure(
                scrollregion=self._list_canvas.bbox("all")
            ) if self._is_popup_scrolling else None,
        )
        # Keep inner_frame width equal to canvas width
        self._list_canvas.bind(
            "<Configure>",
            lambda e: self._list_canvas.itemconfigure(
                self._canvas_window_id, width=e.width
            ),
        )

        # Scroll forwarder: routes mousewheel to canvas, returns "break" to stop propagation
        # to any widget behind the popup (e.g. the main app scrollable areas).
        def _forward_scroll(event):
            if event.num == 4:
                self._list_canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self._list_canvas.yview_scroll(1, "units")
            else:
                self._list_canvas.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        self._popup_scroll_fn = _forward_scroll
        for _sw in (self._list_canvas, self._inner_frame):
            _sw.bind("<MouseWheel>", _forward_scroll, "+")
            _sw.bind("<Button-4>", _forward_scroll, "+")
            _sw.bind("<Button-5>", _forward_scroll, "+")

        # Store popup state so _resize_popup() can update geometry on each filter change
        self._popup_outer = outer
        self._popup_w = w
        self._popup_x = x
        self._popup_y = y

        self._popup_btns = []
        self._render_items("")  # also calls _resize_popup() → sets initial geometry
        self._search_trace_id = self._search_var.trace_add(
            "write", lambda *_: self._render_items(self._search_var.get())
        )

        popup.deiconify()
        popup.lift()
        search_entry.focus_set()

        popup.bind("<Escape>", lambda _: self._close_popup())
        # Defer global bind so the opening click doesn't immediately close the popup
        self._register_after_id = self.after(50, self._register_global_click)

    def _resize_popup(self):
        """Resize the popup to fit the current number of visible items.

        Uses a deterministic calculation: 44 (search area) + list_h + 4 + POPUP_BORDER_PAD.
        Scrollbar is packed only when count > _MAX_VISIBLE, fully absent otherwise.
        """
        if not (self._popup and self._popup.winfo_exists()):
            return
        if not (self._popup_outer and self._popup_outer.winfo_exists()):
            return

        count = len(self._popup_btns)
        visible_rows = max(1, min(count, self._MAX_VISIBLE))

        # REQ-2: canvas height = min(count, _MAX_VISIBLE) * _LIST_ITEM_H
        list_h = visible_rows * self._LIST_ITEM_H
        self._list_canvas.configure(height=list_h)

        # Scrollbar gridded ONLY when count > _MAX_VISIBLE — fully absent otherwise.
        # Grid layout (not pack) ensures reliable space redistribution when toggling.
        is_scrolling = count > self._MAX_VISIBLE
        self._is_popup_scrolling = is_scrolling
        if is_scrolling:
            self._list_scrollbar.grid(row=0, column=1, sticky="ns")
            self._list_canvas.configure(yscrollcommand=self._list_scrollbar.set)
            # scrollregion is managed by inner_frame <Configure> binding (content > canvas)
        else:
            self._list_scrollbar.grid_remove()
            self._list_canvas.configure(yscrollcommand="")
            # Force scrollregion == canvas height: the <Configure> binding is disabled
            # (is_popup_scrolling=False) so this value won't be overridden by lazy layout.
            self._list_canvas.configure(scrollregion=(0, 0, self._popup_w, list_h))

        self._list_canvas.yview_moveto(0)

        # REQ-5: popup_h = 44 + list_h + 4 + POPUP_BORDER_PAD (deterministic)
        popup_h = 44 + list_h + 4 + POPUP_BORDER_PAD
        self._popup.geometry(
            f"{self._popup_w}x{int(popup_h)}+{self._popup_x}+{self._popup_y}"
        )

    def _render_items(self, filter_text: str):
        """Destroy and recreate list buttons matching the current filter."""
        for btn in self._popup_btns:
            btn.destroy()
        self._popup_btns.clear()

        q = filter_text.strip().lower()
        items = [v for v in self._values if q in v.lower()] if q else self._values

        if not items:
            lbl = ctk.CTkLabel(
                self._inner_frame,
                text=t("placeholder.no_results"),
                font=self._combo_font or theme.font("base"),
                text_color=theme.C.text_muted,
                anchor="center",
            )
            lbl.pack(fill="x", padx=4, pady=6)
            self._popup_btns.append(lbl)  # type: ignore[arg-type]
            self._resize_popup()
            return

        # Prepare for truncation measurement
        f = self._make_measure_font()
        # avail_w: popup_w minus outer margins (22) minus button side padding (4+4=8)
        # minus scrollbar width when active
        is_scrolling = len(items) > self._MAX_VISIBLE
        avail_w = self._popup_w - (30 + COMBO_SCROLLBAR_W if is_scrolling else 30)

        for val in items:
            # Determine display text with ellipsis if too long
            display_text = val
            if f.measure(val) > avail_w:
                ellipsis = "…"
                target_w = avail_w - f.measure(ellipsis)
                # Narrow down until it fits
                while display_text and f.measure(display_text) > target_w:
                    display_text = display_text[:-1]
                display_text += ellipsis

            btn = ctk.CTkButton(
                self._inner_frame,
                text=display_text,
                anchor="w",
                height=28,
                fg_color=theme.C.section if val == self._selected else "transparent",
                hover_color=theme.C.section,
                text_color=theme.C.text_primary,
                font=self._combo_font or theme.font("base"),
                corner_radius=theme.G.corner_btn,
                command=lambda v=val: self._select(v),
            )
            btn.pack(fill="x", padx=4, pady=1)
            
            # Add tooltip with ORIGINAL (full) text
            ToolTip(btn, val)

            if hasattr(self, "_popup_scroll_fn") and self._popup_scroll_fn:
                btn.bind("<MouseWheel>", self._popup_scroll_fn, "+")
                btn.bind("<Button-4>", self._popup_scroll_fn, "+")
                btn.bind("<Button-5>", self._popup_scroll_fn, "+")
            self._popup_btns.append(btn)

        self._resize_popup()

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
        self._popup_outer = None
        self._popup_btns = []
        self._popup_scroll_fn = None
        self._list_canvas = None
        self._inner_frame = None
        self._list_scrollbar = None
        self._list_canvas_host = None
        self._canvas_window_id = None
        self._is_popup_scrolling = False

    def _select(self, value: str):
        """Select an item: update display, close popup, fire callback."""
        self._close_popup()
        self._selected = value
        self._update_display_text()
        if self._variable is not None:
            self._variable.set(value)
        if self._command:
            self._command(value)

    # ── Public API (CTkComboBox-compatible) ───────────────────────────────────

    def set(self, value: str):
        """Set the displayed value without firing the command callback."""
        self._selected = value
        self._update_display_text()
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
                self._update_display_text()
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
