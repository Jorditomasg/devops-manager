"""BaseDialog — shared boilerplate for all CTkToplevel dialog windows."""
import os
import tkinter as tk
import customtkinter as ctk

_FALLBACK_ICON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets", "icons", "icon_red.ico",
)

_CASCADE_OFFSET_PX = 20   # px offset per nesting level
_OVERLAY_DARKEN = 0.5     # multiply each pixel by this factor (0.5 = 50% darker)
_OVERLAY_MARKER = '_basedialog_overlay'  # attribute name stored on parent for defensive cleanup


def _deferred_parent_cleanup(parent):
    """Last-resort cleanup scheduled via after() — runs when the event loop is idle."""
    try:
        if not parent.winfo_exists():
            return
        # Scan for any orphaned overlay canvas still on the parent
        for child in list(parent.winfo_children()):
            if getattr(child, _OVERLAY_MARKER, False):
                try:
                    child.place_forget()
                    child.destroy()
                except Exception:
                    pass
        # Force Tk to repaint by generating a synthetic configure event
        parent.event_generate(
            "<Configure>",
            width=parent.winfo_width(),
            height=parent.winfo_height(),
        )
        parent.update_idletasks()
    except Exception:
        pass


class BaseDialog(ctk.CTkToplevel):
    """Mixin/base for all application dialogs.

    Handles: transient parent binding, grab_set, geometry centering, window icon,
    multi-screen positioning, cascade offset for nested dialogs, parent overlay,
    and system feedback on blocked-area clicks.
    """

    def __init__(self, parent, title: str, width: int, height: int):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # Capture snapshot NOW, before the dialog window renders over the parent.
        self._parent_ref = parent
        self._parent_overlay: tk.Canvas | None = None
        self._parent_snapshot = self._capture_parent_snapshot(parent)

        self._set_initial_geometry(parent, width, height)

        root = parent.winfo_toplevel()
        color = getattr(root, '_current_icon_color', 'red')
        icons_dir = getattr(root, '_icons_dir', None)
        if icons_dir:
            icon_path = os.path.join(icons_dir, f"icon_{color}.ico")
        else:
            icon_path = _FALLBACK_ICON_PATH
        if os.path.exists(icon_path):
            self.after(200, lambda p=icon_path: self.iconbitmap(p))

        self.after(10, self._grab_and_focus)

        # Detect clicks outside the modal area (grab re-routes them here)
        self.bind("<Button-1>", self._on_button1, add="+")

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _nesting_level(self) -> int:
        """Count how many BaseDialog ancestors this dialog has."""
        level = 0
        w = self.master
        while isinstance(w, BaseDialog):
            level += 1
            w = getattr(w, 'master', None)
        return level

    def _set_initial_geometry(self, parent, width: int, height: int) -> None:
        """Center on the same screen as parent, with cascade offset per nesting level."""
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except Exception:
            px, py, pw, ph = 0, 0, 800, 600

        x = px + (pw - width) // 2
        y = py + (ph - height) // 2

        level = self._nesting_level()
        x += level * _CASCADE_OFFSET_PX
        y += level * _CASCADE_OFFSET_PX

        self.geometry(f"{width}x{height}+{x}+{y}")

    # ------------------------------------------------------------------
    # Parent overlay — PIL screenshot approach
    # ------------------------------------------------------------------

    def _capture_parent_snapshot(self, parent):
        """Screenshot parent content and return a darkened PIL Image.

        Called in __init__ before the dialog window renders so the dialog itself
        does not appear in the snapshot.  Returns None on any failure.
        """
        try:
            from PIL import ImageGrab
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            if pw <= 1 or ph <= 1:
                return None
            img = ImageGrab.grab(bbox=(px, py, px + pw, py + ph))
            return img.point(lambda p: int(p * _OVERLAY_DARKEN))
        except Exception:
            return None

    def _apply_parent_overlay(self, parent) -> None:
        """Place the darkened snapshot as a Canvas widget on the parent.

        Being a child widget of the parent, the canvas automatically follows
        the parent when it is moved — no separate window, no z-order issues.
        """
        if self._parent_snapshot is None:
            return
        # Remove any stale overlay left on this parent (defensive)
        for child in list(parent.winfo_children()):
            if getattr(child, _OVERLAY_MARKER, False):
                try:
                    child.place_forget()
                    child.destroy()
                except Exception:
                    pass
        try:
            from PIL.ImageTk import PhotoImage
            photo = PhotoImage(self._parent_snapshot)

            pw = self._parent_snapshot.width
            ph = self._parent_snapshot.height
            self._parent_snapshot = None  # free PIL Image — PhotoImage keeps its own copy

            canvas = tk.Canvas(parent, width=pw, height=ph,
                               highlightthickness=0, bd=0)
            canvas.place(x=0, y=0)
            canvas.create_image(0, 0, anchor="nw", image=photo)
            canvas._photo = photo  # prevent garbage collection
            setattr(canvas, _OVERLAY_MARKER, True)  # tag for defensive scan
            canvas.lift()

            self._parent_overlay = canvas
        except Exception:
            self._parent_overlay = None

    def _remove_parent_overlay(self) -> None:
        overlay = self._parent_overlay
        self._parent_overlay = None
        if overlay is not None:
            # Clear visual content first — even if widget removal fails later,
            # the canvas will be blank instead of showing the darkened image.
            try:
                overlay.delete("all")
                overlay._photo = None
            except Exception:
                pass
            try:
                overlay.place_forget()
            except Exception:
                pass
            try:
                overlay.destroy()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Blocked-click feedback
    # ------------------------------------------------------------------

    def _on_button1(self, event: tk.Event) -> None:
        """Called for every Button-1 on this window (including grab-redirected clicks).

        With grab_set() active, pointer events from blocked areas are re-routed here;
        x_root/y_root still hold the actual screen coordinates of the click.
        """
        try:
            dx = self.winfo_rootx()
            dy = self.winfo_rooty()
            dw = self.winfo_width()
            dh = self.winfo_height()
        except Exception:
            return

        if not (dx <= event.x_root <= dx + dw and dy <= event.y_root <= dy + dh):
            self._on_blocked_click()

    def _on_blocked_click(self) -> None:
        """System feedback when user clicks on a blocked (parent) area."""
        try:
            self.bell()
        except Exception:
            pass
        self.lift()
        self.focus_force()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        """Release grab, remove overlay, destroy dialog, schedule parent cleanup."""
        try:
            self.grab_release()
        except Exception:
            pass
        self._remove_parent_overlay()
        parent = self._parent_ref
        super().destroy()
        # Schedule a deferred cleanup+repaint.  Neither synchronous update()
        # nor after(1, ...) reliably repaints the parent on Windows because Tk
        # may still be processing the transient-window teardown.  50 ms gives
        # the WM time to finish, then we scan for orphans and force a
        # <Configure> to guarantee the parent redraws.
        if parent is not None:
            try:
                parent.after(50, lambda p=parent: _deferred_parent_cleanup(p))
            except Exception:
                pass

    def _grab_and_focus(self) -> None:
        """Delayed grab/focus — force deiconify then grab, since CTkToplevel defers its own show."""
        if not self.winfo_exists():
            return
        if not self.winfo_ismapped():
            self.deiconify()
        self._apply_parent_overlay(self._parent_ref)
        self.grab_set()
        self.lift()
        self.focus_force()
