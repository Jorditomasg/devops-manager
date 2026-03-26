"""BaseDialog — shared boilerplate for all CTkToplevel dialog windows."""
import os
import customtkinter as ctk

_ICON_PATH = os.path.join(
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
        if os.path.exists(_ICON_PATH):
            self.after(200, lambda: self.iconbitmap(_ICON_PATH))
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
