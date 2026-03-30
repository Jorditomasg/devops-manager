"""ConfirmCloseDialog — confirmation dialog shown when closing with services running."""
import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui import theme


class ConfirmCloseDialog(BaseDialog):
    """Modal dialog asking the user to confirm closing while services are running.

    After ``wait_window``, check ``dialog.confirmed`` (bool).
    """

    def __init__(self, parent, running_count: int):
        super().__init__(parent, "Servicios en ejecución", 420, 180)
        self.confirmed = False

        noun = "servicio" if running_count == 1 else "servicios"
        msg = (
            f"Hay {running_count} {noun} corriendo.\n"
            "¿Querés cerrar la aplicación igualmente?"
        )
        ctk.CTkLabel(
            self, text=msg,
            wraplength=380, justify="left",
            font=theme.font("base"),
        ).pack(padx=20, pady=(24, 16), anchor="w")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkButton(
            btn_frame, text="Cancelar", width=110,
            command=self._cancel, **theme.btn_style("neutral")
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_frame, text="Cerrar igual", width=130,
            command=self._confirm, **theme.btn_style("danger")
        ).pack(side="right")

    def _confirm(self):
        self.confirmed = True
        self.destroy()

    def _cancel(self):
        self.confirmed = False
        self.destroy()
