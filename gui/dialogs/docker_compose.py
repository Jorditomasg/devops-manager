"""DockerComposeDialog — manage and monitor docker-compose services."""
import os
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from gui.dialogs._base import BaseDialog
from gui.log_helpers import insert_log_line
from gui.constants import LOG_MAX_LINES
from gui import theme


class DockerComposeDialog(BaseDialog):
    """Dialog to manage individual services within a docker-compose file."""

    def __init__(self, parent, compose_file: str, log_callback=None, on_status_change=None,
                 profile_services=None, on_profile_change=None):
        title = f"Docker Compose - {os.path.basename(compose_file)}"
        super().__init__(parent, title, 900, 620)
        # This dialog is resizable (override BaseDialog's fixed size)
        self.resizable(True, True)
        self.minsize(660, 420)

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

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 5))

        ctk.CTkLabel(header, text="Servicios Definidos",
                     font=theme.font("h2", bold=True)).pack(side="left")

        self._build_control_buttons(header)

        # Services List
        self._list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        if not self._services:
            ctk.CTkLabel(self._list_frame,
                         text="No se encontraron servicios en el YAML.",
                         text_color=theme.C.status_error).pack(pady=20)

        self._build_services_list(self._list_frame)

        self._build_log_panel(self)

    def _build_services_list(self, frame):
        for srv in self._services:
            self._build_service_row(srv)

    def _build_log_panel(self, frame):
        # Logs Viewer Section
        logs_header = ctk.CTkFrame(frame, fg_color="transparent")
        logs_header.pack(fill="x", padx=15, pady=(5, 0))

        self._logs_title = ctk.CTkLabel(
            logs_header, text="Logs: (Seleccione un servicio)",
            font=theme.font("base", bold=True))
        self._logs_title.pack(side="left")

        ctk.CTkButton(
            logs_header, text="Limpiar", width=60,
            command=self._clear_logs, **theme.btn_style("neutral_alt", height="sm")
        ).pack(side="right")

        self._btn_refresh_logs = ctk.CTkButton(
            logs_header, text="Recargar Logs", width=100,
            command=self._refresh_selected_logs, state="disabled",
            **theme.btn_style("neutral", height="sm")
        )
        self._btn_refresh_logs.pack(side="right", padx=5)

        self._logs_box = ctk.CTkTextbox(
            frame, font=theme.font("md", mono=True), height=150,
            corner_radius=theme.G.corner_btn, border_width=theme.G.border_width,
            border_color=theme.C.subtle_border
        )
        self._logs_box.pack(fill="x", padx=15, pady=(5, 15))
        self._logs_box.configure(state="disabled")

        self._selected_log_service = None

    def _build_control_buttons(self, frame):
        # Global Actions
        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(side="right")

        self._auto_refresh_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            actions, text="Auto-Refresh", variable=self._auto_refresh_var,
            command=self._toggle_auto_refresh, font=theme.font("md")
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            actions, text="Iniciar Todos", width=110,
            command=self._start_all, **theme.btn_style("success")
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            actions, text="Detener Todos", width=110,
            command=self._stop_all, **theme.btn_style("danger_deep")
        ).pack(side="left")

    def _build_service_row(self, srv: dict):
        name = srv['name']

        row = ctk.CTkFrame(self._list_frame, corner_radius=theme.G.corner_btn,
                           border_width=theme.G.border_width, border_color=theme.C.subtle_border,
                           fg_color=theme.C.section_alt)
        row.pack(fill="x", pady=3, padx=5)

        # Status indicator
        lbl_status = ctk.CTkLabel(row, text="--", text_color=theme.C.text_faint,
                                  width=20, font=theme.font("xl"))
        lbl_status.pack(side="left", padx=10)

        # Info
        info_frame = ctk.CTkFrame(row, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, pady=5)

        ctk.CTkLabel(info_frame, text=name,
                     font=theme.font("lg", bold=True),
                     text_color=theme.C.text_primary).pack(anchor="w")

        details = f"Image: {srv.get('image', 'unknown')}"
        if srv.get('ports'):
            details += f" | Ports: {', '.join(srv.get('ports'))}"

        ctk.CTkLabel(info_frame, text=details,
                     font=theme.font("sm"),
                     text_color=theme.C.text_muted).pack(anchor="w")

        self._build_service_checkboxes(row, srv)
        self._build_service_buttons(row, name)

        self._service_rows[name] = {
            "status_lbl": lbl_status,
            "profile_var": self._service_rows.get(name, {}).get("profile_var"),
        }

    def _build_service_checkboxes(self, row_frame, service: dict):
        name = service['name']
        profile_var = ctk.BooleanVar(value=name in self._profile_services)
        profile_cb = ctk.CTkCheckBox(
            row_frame, text="Perfil", variable=profile_var, width=70,
            font=theme.font("md"), text_color=theme.C.text_muted,
            fg_color=theme.C.docker_border_active, hover_color=theme.C.docker_border_active,
            command=lambda n=name, v=profile_var: self._on_profile_checkbox(n, v)
        )
        profile_cb.pack(side="right", padx=(0, 6))
        # Store profile_var so _build_service_row can reference it
        if name not in self._service_rows:
            self._service_rows[name] = {}
        self._service_rows[name]["profile_var"] = profile_var

    def _build_service_buttons(self, row_frame, name: str):
        btn_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        btn_frame.pack(side="right", padx=10)

        ctk.CTkButton(
            btn_frame, text="Start", width=50,
            command=lambda n=name: self._start_service(n),
            **theme.btn_style("success")
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="Stop", width=50,
            command=lambda n=name: self._stop_service(n),
            **theme.btn_style("danger_deep")
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="Logs", width=50,
            command=lambda n=name: self._view_logs(n),
            **theme.btn_style("neutral_alt")
        ).pack(side="left", padx=(10, 0))

    def _on_profile_checkbox(self, name: str, var: ctk.BooleanVar):
        if var.get():
            self._profile_services.add(name)
        else:
            self._profile_services.discard(name)
        if self._on_profile_change:
            self._on_profile_change(self._compose_file, list(self._profile_services))

    def _check_docker_daemon(self) -> bool:
        from core.db_manager import is_docker_available
        if not is_docker_available():
            if self._log:
                self._log("[docker] Docker no está disponible. Asegúrate de que Docker Desktop esté en ejecución.")
            return False
        return True

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
                        icon = "ON"
                    else:
                        color = theme.C.status_stopped
                        icon = "OFF"
                    widgets["status_lbl"].configure(text=icon, text_color=color)

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
            txt = docker_compose_logs(
                self._compose_file, self._selected_log_service)

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
