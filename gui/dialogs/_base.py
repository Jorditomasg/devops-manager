"""BaseDialog — shared boilerplate for all CTkToplevel dialog windows."""
import customtkinter as ctk


class BaseDialog(ctk.CTkToplevel):
    """Mixin/base for all application dialogs.

    Handles: transient parent binding, grab_set, geometry centering.
    Subclasses call super().__init__(parent, title, width, height) then build their UI.
    """

    def __init__(self, parent, title: str, width: int, height: int):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.transient(parent)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(10, self._grab_and_focus)

    def _grab_and_focus(self):
        """Delayed grab/focus — force deiconify then grab, since CTkToplevel defers its own show."""
        if not self.winfo_exists():
            return
        if not self.winfo_ismapped():
            self.deiconify()
        self.attributes('-topmost', True)
        self.grab_set()
        self.lift()
        self.focus_force()
