"""InstanceConflictDialog — shown at startup when another instance is already open.

Self-contained CTkToplevel (NOT BaseDialog): it appears BEFORE the main UI is
built, so there is no parent content to screenshot/darken. Centers itself on the
screen and grabs input.

After ``wait_window``, read:
* ``dialog.choice`` — ``'close_others'`` | ``'open_anyway'`` | ``'cancel'``
* ``dialog.remaining`` — instances that did NOT close in time (only for ``close_others``)
"""
import os
import customtkinter as ctk

from gui import theme
from core.i18n import t

_CLOSE_POLL_MS = 300         # how often to re-check that the others are gone
_CLOSE_MAX_POLLS = 40        # ~12 s total before giving up the wait


class InstanceConflictDialog(ctk.CTkToplevel):
    def __init__(self, parent, instance_mgr, others: list[dict]):
        super().__init__(parent)
        self._mgr = instance_mgr
        self._others = others
        self.choice = "cancel"
        self.remaining: list[dict] = []
        self._polls = 0

        self.title(t("dialog.instance_conflict.title"))
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        icons_dir = getattr(parent, "_icons_dir", None)
        if icons_dir:
            icon_path = os.path.join(icons_dir, "icon_red.ico")
            if os.path.exists(icon_path):
                self.after(200, lambda p=icon_path: self.iconbitmap(p))

        n = len(others)
        msg = (t("dialog.instance_conflict.message_one") if n == 1
               else t("dialog.instance_conflict.message_many", count=n))
        ctk.CTkLabel(
            self, text=msg, wraplength=400, justify="left",
            font=theme.font("base", bold=True),
        ).pack(padx=24, pady=(24, 6), anchor="w")

        self._detail = ctk.CTkLabel(
            self, text=t("dialog.instance_conflict.detail"),
            wraplength=400, justify="left", font=theme.font("base"),
        )
        self._detail.pack(padx=24, pady=(0, 16), anchor="w")

        self._btn_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self._btn_frame.pack(fill="x", padx=24, pady=(0, 20))

        self._btn_cancel = ctk.CTkButton(
            self._btn_frame, text=t("dialog.instance_conflict.btn_cancel"), width=100,
            command=self._cancel, **theme.btn_style("neutral"),
        )
        self._btn_cancel.pack(side="right", padx=(8, 0))

        self._btn_open = ctk.CTkButton(
            self._btn_frame, text=t("dialog.instance_conflict.btn_open_anyway"), width=120,
            command=self._open_anyway, **theme.btn_style("warning"),
        )
        self._btn_open.pack(side="right", padx=(8, 0))

        self._btn_close = ctk.CTkButton(
            self._btn_frame, text=t("dialog.instance_conflict.btn_close_others"), width=150,
            command=self._close_others, **theme.btn_style("danger"),
        )
        self._btn_close.pack(side="right")

        self._center_on_screen(460, 200)
        self.after(10, self._grab_and_focus)

    # ── Geometry / focus ───────────────────────────────────────────────────

    def _center_on_screen(self, w: int, h: int) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 3
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _grab_and_focus(self) -> None:
        if not self.winfo_exists():
            return
        if not self.winfo_ismapped():
            self.deiconify()
        self.lift()
        self.grab_set()
        self.focus_force()

    # ── Actions ────────────────────────────────────────────────────────────

    def _open_anyway(self) -> None:
        self.choice = "open_anyway"
        self.destroy()

    def _cancel(self) -> None:
        self.choice = "cancel"
        self.destroy()

    def _close_others(self) -> None:
        # Fire the shutdown, switch to a busy state, then poll (non-blocking, so
        # the dialog stays responsive) until the other ports stop answering.
        self._set_busy()
        self._mgr.send_shutdown(self._others)
        self._poll_closed()

    def _set_busy(self) -> None:
        self._detail.configure(text=t("dialog.instance_conflict.closing"))
        for btn in (self._btn_close, self._btn_open, self._btn_cancel):
            btn.configure(state="disabled")

    def _poll_closed(self) -> None:
        if not self.winfo_exists():
            return
        remaining = self._mgr.still_alive(self._others)
        self._polls += 1
        if not remaining or self._polls >= _CLOSE_MAX_POLLS:
            self.choice = "close_others"
            self.remaining = remaining
            self.destroy()
            return
        self.after(_CLOSE_POLL_MS, self._poll_closed)
