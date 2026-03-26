"""BaseDialog — shared boilerplate for all CTkToplevel dialog windows."""
import os
import customtkinter as ctk

_FALLBACK_ICON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets", "icons", "icon_red.ico",
)


class BaseDialog(ctk.CTkToplevel):
    """Mixin/base for all application dialogs.

    Handles: transient parent binding, grab_set, geometry centering, window icon.
    Subclasses call super().__init__(parent, title, width, height) then build their UI.
    """

    def __init__(self, parent, title: str, width: int, height: int):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.transient(parent)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
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

    def _grab_and_focus(self):
        """Delayed grab/focus — force deiconify then grab, since CTkToplevel defers its own show."""
        if not self.winfo_exists():
            return
        if not self.winfo_ismapped():
            self.deiconify()
        self.grab_set()
        self.lift()
        self.focus_force()
