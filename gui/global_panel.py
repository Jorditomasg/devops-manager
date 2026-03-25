"""
global_panel.py — Global settings panel to control all repos at once.
Uses card.is_selected() / card.set_selected() for selection from the card checkboxes.
"""
import customtkinter as ctk
from tkinter import messagebox
import threading

from gui.tooltip import ToolTip
from gui import theme

class GlobalPanel(ctk.CTkFrame):
    """Panel with global controls that affect all repo cards."""

    def __init__(self, parent, repo_cards: list = None,
                 log_callback=None, **kwargs):
        super().__init__(parent, corner_radius=theme.G.corner_card, border_width=theme.G.border_width,
                         border_color=theme.C.card_border,
                         fg_color=theme.C.card, **kwargs)

        self._cards = repo_cards or []
        self._log = log_callback

        self._build_ui()

    def set_cards(self, cards: list):
        """Update the list of repo cards."""
        self._cards = cards

    def _build_ui(self):
        """Build the global panel UI."""
        # Title + Select All
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(8, 4))

        ctk.CTkLabel(
            title_frame, text="🌐 Panel Global",
            font=theme.font("xxl", bold=True),
            text_color=theme.C.text_primary
        ).pack(side="left")

        # Select All checkbox (toggles all card checkboxes)
        self._select_all_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            title_frame, text="Seleccionar todos", variable=self._select_all_var,
            font=theme.font("md"),
            checkbox_width=theme.G.checkbox_size_sm, checkbox_height=theme.G.checkbox_size_sm,
            text_color=theme.C.text_muted,
            command=self._toggle_select_all
        ).pack(side="right", padx=(10, 0))

        # ─── Row: Branch (left) + Action buttons (right) ───
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(row, text="Rama:", font=theme.font("base"),
                     text_color=theme.C.text_secondary, width=45).pack(side="left")

        self._branch_entry = ctk.CTkEntry(
            row, width=180, height=theme.G.btn_height_md, font=theme.font("base"),
            corner_radius=theme.G.corner_btn,
            fg_color=theme.C.section,
            border_color=theme.C.default_border,
            placeholder_text="develop"
        )
        self._branch_entry.pack(side="left", padx=(4, 4))

        apply_branch_btn = ctk.CTkButton(
            row, text="Aplicar", width=70,
            command=self._apply_branch_all,
            **theme.btn_style("blue")
        )
        apply_branch_btn.pack(side="left", padx=(0, 0))
        ToolTip(apply_branch_btn, "Aplicar esta rama a todos los repos seleccionados")

        pull_btn = ctk.CTkButton(
            row, text="⬇ Pull All", width=90,
            command=self._pull_all,
            **theme.btn_style("blue", font_size="md")
        )
        pull_btn.pack(side="left", padx=(3, 0))
        ToolTip(pull_btn, "Descargar cambios de todos los repos seleccionados")

        install_btn = ctk.CTkButton(
            row, text="📦 Install All", width=95,
            command=self._install_all,
            **theme.btn_style("neutral_alt", font_size="md")
        )
        install_btn.pack(side="left", padx=(3, 0))
        ToolTip(install_btn, "Instalar dependencias de todos los proyectos seleccionados")

        # Action buttons — right-aligned
        restart_btn = ctk.CTkButton(
            row, text="🔄 Restart", width=90,
            command=self._restart_selected,
            **theme.btn_style("warning", font_size="md")
        )
        restart_btn.pack(side="right", padx=(3, 0))
        ToolTip(restart_btn, "Reiniciar todos los servicios seleccionados")

        stop_btn = ctk.CTkButton(
            row, text="⬛ Stop", width=80,
            command=self._stop_selected,
            **theme.btn_style("danger", font_size="md")
        )
        stop_btn.pack(side="right", padx=(3, 0))
        ToolTip(stop_btn, "Detener todos los servicios seleccionados")

        start_btn = ctk.CTkButton(
            row, text="▶ Start", width=80,
            command=self._start_selected,
            **theme.btn_style("start", font_size="md")
        )
        start_btn.pack(side="right", padx=(3, 0))
        ToolTip(start_btn, "Iniciar todos los servicios seleccionados")


    def _toggle_select_all(self):
        """Toggle all repo card checkboxes."""
        val = self._select_all_var.get()
        for card in self._cards:
            card.set_selected(val)

    def _get_selected_cards(self):
        """Get cards that are currently selected (via their checkbox)."""
        return [card for card in self._cards if card.is_selected()]

    def _apply_branch_all(self):
        """Apply a branch to all selected repos. Alert if branch not found in some."""
        branch = self._branch_entry.get().strip()
        if not branch:
            messagebox.showwarning("Aviso", "Introduce un nombre de rama")
            return

        selected = self._get_selected_cards()
        if not selected:
            messagebox.showwarning("Aviso", "No hay repos seleccionados")
            return

        def _run():
            not_found = []
            for card in selected:
                success = card.set_branch(branch)
                if not success:
                    not_found.append(card.get_name())

            if not_found:
                def _alert():
                    repos_str = "\n".join([f"  • {r}" for r in not_found])
                    messagebox.showwarning(
                        "⚠ Rama no encontrada",
                        f"La rama '{branch}' no se encontró en:\n{repos_str}\n\n"
                        "Estos repos mantienen su rama actual."
                    )
                self.after(0, _alert)

            if self._log:
                total = len(selected)
                changed = total - len(not_found)
                self._log(f"[global] Rama '{branch}' aplicada a {changed}/{total} repos"
                          + (f" ({len(not_found)} sin la rama)" if not_found else ""))

        threading.Thread(target=_run, daemon=True).start()

    def _pull_all(self):
        """Pull all selected repos."""
        selected = self._get_selected_cards()
        if not selected:
            return

        if self._log:
            self._log(f"[global] Pulling {len(selected)} repos...")

        def _run():
            from core.git_manager import pull
            for card in selected:
                repo = card.get_repo_info()
                pull(repo.path, self._log)

        threading.Thread(target=_run, daemon=True).start()

    def _install_all(self):
        """Install dependencies for all selected repos."""
        selected = self._get_selected_cards()
        if not selected:
            return

        if self._log:
            self._log(f"[global] Installing dependencies for {len(selected)} repos...")

        for card in selected:
            card.install_dependencies(skip_if_installed=True)

    def _start_selected(self):
        """Start all selected repos."""
        selected = self._get_selected_cards()
        if self._log:
            self._log(f"[global] Starting {len(selected)} services...")
        for card in selected:
            card.do_start()

    def _stop_selected(self):
        """Stop all selected repos."""
        selected = self._get_selected_cards()
        if self._log:
            self._log(f"[global] Stopping {len(selected)} services...")
        for card in selected:
            card.do_stop()

    def _restart_selected(self):
        """Restart all selected repos."""
        selected = self._get_selected_cards()
        if self._log:
            self._log(f"[global] Restarting {len(selected)} services...")
        for card in selected:
            card.do_stop()

        def _delayed_start():
            for card in selected:
                card.do_start()

        self.after(3000, _delayed_start)

