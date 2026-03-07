"""
global_panel.py — Global settings panel to control all repos at once.
Uses card.is_selected() / card.set_selected() for selection from the card checkboxes.
"""
import customtkinter as ctk
from tkinter import messagebox
import threading

from gui.tooltip import ToolTip

# ── Font constants ──────────────────────────────────────────────
FONT_FAMILY = "Segoe UI"
NO_DB_PRESET = "(Sin presets BD)"


class GlobalPanel(ctk.CTkFrame):
    """Panel with global controls that affect all repo cards."""

    def __init__(self, parent, db_presets=None, repo_cards: list = None,
                 log_callback=None, **kwargs):
        super().__init__(parent, corner_radius=10, border_width=1,
                         border_color="#3b3768",
                         fg_color="#16132e", **kwargs)

        self._cards = repo_cards or []
        self._db_presets = db_presets or {}
        self._log = log_callback

        self._build_ui()

    def set_cards(self, cards: list):
        """Update the list of repo cards."""
        self._cards = cards

    def update_db_presets(self, presets: dict):
        """Update available DB presets (called when settings change)."""
        self._db_presets = presets
        db_options = list(presets.keys()) if presets else [NO_DB_PRESET]
        self._db_combo.configure(values=db_options)
        if presets:
            self._db_combo.set(db_options[0])
        else:
            self._db_combo.set(NO_DB_PRESET)

    def _build_ui(self):
        """Build the global panel UI."""
        # Title + Select All
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(8, 4))

        ctk.CTkLabel(
            title_frame, text="🌐 Panel Global",
            font=(FONT_FAMILY, 15, "bold"),
            text_color="#e0e7ff"
        ).pack(side="left")

        # Select All checkbox (toggles all card checkboxes)
        self._select_all_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            title_frame, text="Seleccionar todos", variable=self._select_all_var,
            font=(FONT_FAMILY, 11), checkbox_width=16, checkbox_height=16,
            text_color="#94a3b8",
            command=self._toggle_select_all
        ).pack(side="right", padx=(10, 0))

        # ─── Row 1: Branch + DB ───
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=15, pady=(0, 4))

        # Branch
        ctk.CTkLabel(row1, text="Rama:", font=(FONT_FAMILY, 12),
                     text_color="#c7d2fe", width=45).pack(side="left")

        self._branch_entry = ctk.CTkEntry(
            row1, width=180, height=28, font=(FONT_FAMILY, 12),
            corner_radius=6, fg_color="#1e1b4b",
            border_color="#4338ca",
            placeholder_text="develop"
        )
        self._branch_entry.pack(side="left", padx=(4, 4))

        apply_branch_btn = ctk.CTkButton(
            row1, text="Aplicar", width=70, height=28,
            font=(FONT_FAMILY, 11),
            fg_color="#172554", hover_color="#2563eb",
            border_width=1, border_color="#3b82f6",
            corner_radius=6,
            command=self._apply_branch_all
        )
        apply_branch_btn.pack(side="left", padx=(0, 10))
        ToolTip(apply_branch_btn, "Aplicar esta rama a todos los repos seleccionados")

        # DB
        ctk.CTkLabel(row1, text="BD:", font=(FONT_FAMILY, 12),
                     text_color="#c7d2fe", width=25).pack(side="left")

        db_options = list(self._db_presets.keys()) if self._db_presets else [NO_DB_PRESET]
        self._db_combo = ctk.CTkComboBox(
            row1, values=db_options,
            width=130, height=28, font=(FONT_FAMILY, 12),
            corner_radius=6, fg_color="#1e1b4b",
            border_color="#4338ca", button_color="#4338ca",
        )
        self._db_combo.pack(side="left", padx=(4, 4))
        if self._db_presets:
            self._db_combo.set(db_options[0])
        else:
            self._db_combo.set(NO_DB_PRESET)

        apply_db_btn = ctk.CTkButton(
            row1, text="Aplicar", width=70, height=28,
            font=(FONT_FAMILY, 11),
            fg_color="#2e1065", hover_color="#9333ea",
            border_width=1, border_color="#a855f7",
            corner_radius=6,
            command=self._apply_db_all
        )
        apply_db_btn.pack(side="left")
        ToolTip(apply_db_btn, "Aplicar preset de BD a todos los repos seleccionados")

        # ─── Row 2: Action buttons ───
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=15, pady=(0, 8))

        btn_style = {"height": 28, "font": (FONT_FAMILY, 11), "corner_radius": 6,
                     "border_width": 1}

        pull_btn = ctk.CTkButton(
            row2, text="⬇ Pull All", width=90,
            fg_color="#172554", hover_color="#2563eb",
            border_color="#3b82f6",
            command=self._pull_all, **btn_style
        )
        pull_btn.pack(side="left", padx=(0, 3))
        ToolTip(pull_btn, "Descargar cambios de todos los repos seleccionados")

        install_btn = ctk.CTkButton(
            row2, text="📦 Install All", width=95,
            fg_color="#1e293b", hover_color="#334155",
            border_color="#64748b",
            command=self._install_all, **btn_style
        )
        install_btn.pack(side="left", padx=(0, 3))
        ToolTip(install_btn, "Instalar dependencias de todos los proyectos seleccionados")

        start_btn = ctk.CTkButton(
            row2, text="▶ Start", width=80,
            fg_color="#144d28", hover_color="#16a34a",
            border_color="#22c55e",
            command=self._start_selected, **btn_style
        )
        start_btn.pack(side="left", padx=(0, 3))
        ToolTip(start_btn, "Iniciar todos los servicios seleccionados")

        stop_btn = ctk.CTkButton(
            row2, text="⬛ Stop", width=80,
            fg_color="#4c1616", hover_color="#dc2626",
            border_color="#ef4444",
            command=self._stop_selected, **btn_style
        )
        stop_btn.pack(side="left", padx=(0, 3))
        ToolTip(stop_btn, "Detener todos los servicios seleccionados")

        restart_btn = ctk.CTkButton(
            row2, text="🔄 Restart", width=90,
            fg_color="#4a3310", hover_color="#d97706",
            border_color="#f59e0b",
            command=self._restart_selected, **btn_style
        )
        restart_btn.pack(side="left", padx=(0, 3))
        ToolTip(restart_btn, "Reiniciar todos los servicios seleccionados")

        seed_btn = ctk.CTkButton(
            row2, text="🌱 Seed All", width=90,
            fg_color="#2e1065", hover_color="#9333ea",
            border_color="#a855f7",
            command=self._seed_all, **btn_style
        )
        seed_btn.pack(side="left")
        ToolTip(seed_btn, "Ejecutar seeds de BD para todos los repos")

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

    def _apply_db_all(self):
        """Apply DB preset to all selected repos."""
        preset_name = self._db_combo.get()
        if preset_name == NO_DB_PRESET:
            messagebox.showwarning("Aviso", "No hay presets de BD configurados.\n"
                                   "Ve a ⚙ Configuración para añadir presets.")
            return

        selected = self._get_selected_cards()

        if not selected:
            messagebox.showwarning("Aviso", "No hay repos seleccionados")
            return

        count = 0
        for card in selected:
            card.set_db_preset(preset_name)
            count += 1

        if self._log:
            self._log(f"[global] BD '{preset_name}' aplicada a {count} repos")

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

    def _seed_all(self):
        """Run seeds for all repos that support it."""
        if self._log:
            self._log("[global] Running seeds...")

        def _run():
            for card in self._cards:
                repo = card.get_repo_info()
                if repo.has_seeds or (repo.repo_type == 'docker-infra' and repo.has_database):
                    from core.db_manager import run_flyway_seeds
                    run_flyway_seeds(repo.path, self._log)

        threading.Thread(target=_run, daemon=True).start()
