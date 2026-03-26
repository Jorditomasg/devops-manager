"""DockerComposeDialog — manage and monitor docker-compose services."""
import os
import threading
from tkinter import messagebox
import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui import theme
from gui.tooltip import ToolTip


class DockerComposeDialog(BaseDialog):
    """Dialog to manage individual services within a docker-compose file."""

    def __init__(self, parent, compose_file: str, log_callback=None, on_status_change=None,
                 profile_services=None, on_profile_change=None):
        title = f"Docker Compose - {os.path.basename(compose_file)}"
        super().__init__(parent, title, 900, 640)
        self.resizable(True, True)
        self.minsize(680, 440)

        self._compose_file = compose_file
        self._log = log_callback
        self._on_status_change = on_status_change
        self._on_profile_change = on_profile_change
        self._profile_services = set(profile_services or [])
        self._auto_refresh = True
        self._services = []
        self._service_rows = {}

        from core.db_manager import parse_compose_services
        self._services = parse_compose_services(compose_file)

        self._build_ui()
        self._refresh_status()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_auto_refresh()

    # ─── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 5))

        ctk.CTkLabel(header, text="Servicios Definidos",
                     font=theme.font("h2", bold=True)).pack(side="left")

        self._profile_count_lbl = ctk.CTkLabel(
            header, text=self._profile_count_text(),
            font=theme.font("md"), text_color=theme.C.docker_border_active
        )
        self._profile_count_lbl.pack(side="left", padx=(12, 0))

        self._build_control_buttons(header)

        self._list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        if not self._services:
            ctk.CTkLabel(self._list_frame,
                         text="No se encontraron servicios en el YAML.",
                         text_color=theme.C.status_error).pack(pady=20)

        for srv in self._services:
            self._build_service_row(srv)

        self._build_log_panel(self)

    def _build_control_buttons(self, frame):
        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(side="right")

        self._auto_refresh_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            actions, text="Auto-Refresh", variable=self._auto_refresh_var,
            command=self._toggle_auto_refresh, font=theme.font("md")
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            actions, text="Iniciar todos", width=110,
            command=self._start_all, **theme.btn_style("success")
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            actions, text="Detener todos", width=110,
            command=self._stop_all, **theme.btn_style("danger_deep")
        ).pack(side="left")

    def _build_service_row(self, srv: dict):
        name = srv['name']

        row = ctk.CTkFrame(self._list_frame, corner_radius=theme.G.corner_btn,
                           border_width=theme.G.border_width, border_color=theme.C.subtle_border,
                           fg_color=theme.C.section_alt, height=44)
        row.pack(fill="x", pady=2, padx=5)
        row.pack_propagate(False)

        # Right side first (so info_frame expand fills the remaining space correctly)
        right_frame = ctk.CTkFrame(row, fg_color="transparent")
        right_frame.pack(side="right", padx=(0, 10))
        self._build_service_buttons(right_frame, name)

        # Checkbox left of status dot — no label, tooltip explains it
        self._build_service_profile_checkbox(row, name)

        # Status dot — vertically centered
        lbl_dot = ctk.CTkLabel(row, text="●", width=16,
                               font=theme.font("lg"), text_color=theme.C.text_faint)
        lbl_dot.pack(side="left", padx=(4, 2))

        # Service info: name + details on one compact line
        details = srv.get('image', 'N/A')
        if srv.get('ports'):
            details += f"  ·  {', '.join(srv['ports'])}"

        info_frame = ctk.CTkFrame(row, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(info_frame, text=name,
                     font=theme.font("base", bold=True),
                     text_color=theme.C.text_primary, anchor="w").pack(side="left")

        ctk.CTkLabel(info_frame, text=f"  {details}",
                     font=theme.font("sm"), text_color=theme.C.text_muted, anchor="w").pack(side="left")

        # Status text label (updated by _refresh_status)
        lbl_status_text = ctk.CTkLabel(row, text="...", width=85,
                                       font=theme.font("sm"), text_color=theme.C.text_faint, anchor="e")
        lbl_status_text.pack(side="right", padx=(0, 6))

        self._service_rows[name] = {
            "status_lbl": lbl_dot,
            "status_text_lbl": lbl_status_text,
            "profile_var": self._service_rows.get(name, {}).get("profile_var"),
        }

    def _build_service_profile_checkbox(self, row_frame, name: str):
        profile_var = ctk.BooleanVar(value=name in self._profile_services)
        cb = ctk.CTkCheckBox(
            row_frame, text="", variable=profile_var, width=24, checkbox_width=18, checkbox_height=18,
            fg_color=theme.C.docker_border_active,
            hover_color=theme.C.docker_border_active,
            command=lambda n=name, v=profile_var: self._on_profile_checkbox(n, v)
        )
        cb.pack(side="left", padx=(8, 0))
        ToolTip(cb, "Marcar para que este servicio se inicie automáticamente\ncuando pulses Start en la tarjeta del repositorio.\nSe guarda en el perfil activo.")
        if name not in self._service_rows:
            self._service_rows[name] = {}
        self._service_rows[name]["profile_var"] = profile_var

    def _build_service_buttons(self, row_frame, name: str):
        btn_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        btn_frame.pack(side="right", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="Start", width=54,
            command=lambda n=name: self._start_service(n),
            **theme.btn_style("success")
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="Stop", width=54,
            command=lambda n=name: self._stop_service(n),
            **theme.btn_style("danger_deep")
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="Logs", width=54,
            command=lambda n=name: self._view_logs(n),
            **theme.btn_style("neutral_alt")
        ).pack(side="left", padx=(8, 0))

    def _build_log_panel(self, frame):
        logs_header = ctk.CTkFrame(frame, fg_color="transparent")
        logs_header.pack(fill="x", padx=15, pady=(5, 0))

        self._logs_title = ctk.CTkLabel(
            logs_header, text="Logs: (seleccione un servicio)",
            font=theme.font("base", bold=True))
        self._logs_title.pack(side="left")

        ctk.CTkButton(
            logs_header, text="Limpiar", width=60,
            command=self._clear_logs, **theme.btn_style("neutral_alt", height="sm")
        ).pack(side="right")

        self._btn_refresh_logs = ctk.CTkButton(
            logs_header, text="Recargar", width=80,
            command=self._refresh_selected_logs, state="disabled",
            **theme.btn_style("neutral", height="sm")
        )
        self._btn_refresh_logs.pack(side="right", padx=(0, 5))

        self._logs_box = ctk.CTkTextbox(
            frame, font=theme.font("md", mono=True), height=150,
            corner_radius=theme.G.corner_btn, border_width=theme.G.border_width,
            border_color=theme.C.subtle_border
        )
        self._logs_box.pack(fill="x", padx=15, pady=(5, 15))
        self._logs_box.configure(state="disabled")
        self._selected_log_service = None

    # ─── Profile helpers ──────────────────────────────────────────────────────

    def _profile_count_text(self) -> str:
        n = len(self._profile_services)
        return f"({n} en perfil)" if n else ""

    def _refresh_profile_count(self):
        if hasattr(self, '_profile_count_lbl') and self._profile_count_lbl.winfo_exists():
            self._profile_count_lbl.configure(text=self._profile_count_text())

    def _on_profile_checkbox(self, name: str, var: ctk.BooleanVar):
        if var.get():
            self._profile_services.add(name)
        else:
            self._profile_services.discard(name)
        self._refresh_profile_count()
        if self._on_profile_change:
            self._on_profile_change(self._compose_file, list(self._profile_services))

    # ─── Docker actions ───────────────────────────────────────────────────────

    def _check_docker_daemon(self) -> bool:
        from core.db_manager import is_docker_available
        if not is_docker_available():
            if self._log:
                self._log("[docker] Docker no está disponible. Asegúrate de que Docker Desktop esté en ejecución.")
            return False
        return True

    def _start_service(self, name: str):
        if not self._check_docker_daemon():
            return
        if self._log:
            self._log(f"Iniciando servicio: {name}")

        def _run():
            from core.db_manager import start_service_compose
            start_service_compose(self._compose_file, name, self._log)
            self._refresh_status()
        threading.Thread(target=_run, daemon=True).start()

    def _stop_service(self, name: str):
        if not self._check_docker_daemon():
            return
        if self._log:
            self._log(f"Deteniendo servicio: {name}")

        def _run():
            from core.db_manager import stop_service_compose
            stop_service_compose(self._compose_file, name, self._log)
            self._refresh_status()
        threading.Thread(target=_run, daemon=True).start()

    def _start_all(self):
        if not self._check_docker_daemon():
            return
        if self._log:
            self._log("Iniciando todos los servicios del compose")

        def _run():
            from core.db_manager import docker_compose_up
            docker_compose_up(self._compose_file, None, self._log)
            self._refresh_status()
        threading.Thread(target=_run, daemon=True).start()

    def _stop_all(self):
        if not self._check_docker_daemon():
            return
        if self._log:
            self._log("Deteniendo todos los servicios del compose")

        def _run():
            from core.db_manager import docker_compose_down
            docker_compose_down(self._compose_file, self._log)
            self._refresh_status()
        threading.Thread(target=_run, daemon=True).start()

    # ─── Status refresh ───────────────────────────────────────────────────────

    def _refresh_status(self):
        if not self._services:
            return

        def _bg_check():
            from core.db_manager import get_compose_service_status
            status_map = get_compose_service_status(self._compose_file)

            def _update_ui():
                if not self.winfo_exists():
                    return
                for sname, widgets in self._service_rows.items():
                    state = status_map.get(sname, "stopped")
                    if state == "running":
                        color = theme.C.status_running
                        status_text = "En ejecución"
                    else:
                        color = theme.C.status_stopped
                        status_text = "Detenido"
                    widgets["status_lbl"].configure(text="●", text_color=color)
                    if "status_text_lbl" in widgets:
                        widgets["status_text_lbl"].configure(text=status_text, text_color=color)
                if self._on_status_change:
                    self._on_status_change()

            self.after(0, _update_ui)

        threading.Thread(target=_bg_check, daemon=True).start()

    def _start_auto_refresh(self):
        def _loop():
            if not self.winfo_exists() or not self._auto_refresh:
                return
            if self._auto_refresh_var.get():
                self._refresh_status()
            self.after(5000, _loop)
        self.after(5000, _loop)

    def _toggle_auto_refresh(self):
        self._auto_refresh = self._auto_refresh_var.get()

    # ─── Logs ─────────────────────────────────────────────────────────────────

    def _view_logs(self, name: str):
        self._selected_log_service = name
        self._logs_title.configure(text=f"Logs: {name}")
        self._btn_refresh_logs.configure(state="normal")
        self._refresh_selected_logs()

    def _refresh_selected_logs(self):
        if not self._selected_log_service:
            return
        self._logs_box.configure(state="normal")
        self._logs_box.delete("1.0", "end")
        self._logs_box.insert("1.0", f"Cargando logs de {self._selected_log_service}...\n")
        self._logs_box.configure(state="disabled")

        def _fetch():
            from core.db_manager import docker_compose_logs
            txt = docker_compose_logs(self._compose_file, self._selected_log_service)

            def _update():
                if not self.winfo_exists():
                    return
                self._logs_box.configure(state="normal")
                self._logs_box.delete("1.0", "end")
                self._logs_box.insert("1.0", txt)
                self._logs_box.see("end")
                self._logs_box.configure(state="disabled")
            self.after(0, _update)
        threading.Thread(target=_fetch, daemon=True).start()

    def _clear_logs(self):
        self._logs_box.configure(state="normal")
        self._logs_box.delete("1.0", "end")
        self._logs_box.configure(state="disabled")

    def _on_close(self):
        self._auto_refresh = False
        self.destroy()
