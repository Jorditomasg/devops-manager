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
        self.grab_set()
        self.lift()
        self.focus_force()
        self.resizable(False, False)
