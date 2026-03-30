"""ConfirmCloseDialog — confirmation dialog shown when closing with services running."""
import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui import theme
from core.i18n import t


class ConfirmCloseDialog(BaseDialog):
    """Modal dialog asking the user to confirm closing while services are running.

    After ``wait_window``, check ``dialog.confirmed`` (bool).
    """

    def __init__(self, parent, running_count: int):
        super().__init__(parent, t("dialog.confirm_close.title"), 420, 180)
        self.confirmed = False

        if running_count == 1:
            msg = t("dialog.confirm_close.message_one")
        else:
            msg = t("dialog.confirm_close.message_many", count=running_count)
        ctk.CTkLabel(
            self, text=msg,
            wraplength=380, justify="left",
            font=theme.font("base"),
        ).pack(padx=20, pady=(24, 16), anchor="w")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkButton(
            btn_frame, text=t("dialog.confirm_close.btn_cancel"), width=110,
            command=self._cancel, **theme.btn_style("neutral")
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_frame, text=t("dialog.confirm_close.btn_confirm"), width=130,
            command=self._confirm, **theme.btn_style("danger")
        ).pack(side="right")

    def _confirm(self):
        self.confirmed = True
        self.destroy()

    def _cancel(self):
        self.confirmed = False
        self.destroy()
