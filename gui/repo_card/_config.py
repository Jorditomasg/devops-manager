"""_config.py — Configuration management mixin for RepoCard."""
from __future__ import annotations
import os
import threading
from tkinter import messagebox
import customtkinter as ctk
from gui.constants import NO_DB_PRESET
from gui import theme


class ConfigMixin:
    """Mixin providing config file management and DB preset handling."""

    def get_config_key(self, target_file: str) -> str:
        """Get the unique config key for a specific module's target file.
        Format: 'repo-name::relative/dir/path'
        e.g. 'boa2-backend-configuracion::src/main/resources'
        """
        repo_path = self._repo.path
        if not target_file:
            return self._repo.name

        rel_path = os.path.relpath(target_file, repo_path).replace('\\', '/')
        dir_path = '/'.join(rel_path.split('/')[:-1])  # strip filename
        if not dir_path or dir_path == '.':
            dir_path = 'root'

        return f"{self._repo.name}::{dir_path}"

    def _resolve_target_file(self, repo, target_file: str) -> str:
        """Resolve the target config file path."""
        if target_file:
            return target_file

        main_filename = getattr(repo, 'env_main_config_filename', '')
        if not main_filename:
            return target_file

        for ef in repo.environment_files:
            if os.path.basename(ef) == main_filename:
                return ef

        if hasattr(repo, 'env_default_dir'):
            return os.path.join(repo.path, repo.env_default_dir, main_filename)

        return target_file

    def _handle_unselect_config(self, target_file: str, skip_log: bool, is_real_change: bool):
        """Restore original config when unselected."""
        should_log = not skip_log or is_real_change
        if self._log and should_log:
            self._log(f"[{self._repo.name}] Configuración deseleccionada. Restaurando configuración original.")

        if target_file and os.path.isfile(target_file):
            import subprocess
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            subprocess.run(['git', 'checkout', '--', target_file], cwd=self._repo.path, capture_output=True, creationflags=flags)

        self.after(0, self._update_header_hints)
        self._trigger_change_callback()

    def _write_spring_config(self, repo, target_file: str, config_data) -> tuple[bool, str]:
        """Write Spring Boot specific configuration."""
        from core.config_manager import write_config_file_raw
        config_str = str(config_data)

        is_props = "=" in config_str.split("\n", 3)[0] or "=" in config_str
        if is_props and not config_str.startswith("spring:") and not config_str.startswith("server:"):
            target_file = target_file.replace('.yml', '.properties')
        else:
            target_file = target_file.replace('.properties', '.yml')

        opposite_file = target_file.replace('.properties', '.yml') if target_file.endswith('.properties') else target_file.replace('.yml', '.properties')

        if os.path.exists(opposite_file):
            try:
                os.remove(opposite_file)
            except OSError:
                pass

        target_classes_file = os.path.join(repo.path, 'target', 'classes', os.path.basename(opposite_file))
        if os.path.exists(target_classes_file):
            try:
                os.remove(target_classes_file)
            except OSError:
                pass

        return write_config_file_raw(target_file, config_data), target_file

    def _apply_config_data(self, target_file: str, config_name: str, config_data, skip_log: bool, is_real_change: bool):
        """Write config data to the target file."""
        from core.config_manager import write_angular_environment_raw, write_config_file_raw
        import json

        should_log = not skip_log or is_real_change

        if not config_data:
            if self._log and should_log:
                self._log(f"[{self._repo.name}] La configuración '{config_name}' no se encontró.")
            return

        writer_type = getattr(self._repo, 'env_config_writer_type', 'raw')

        if writer_type == 'angular':
            content = "\n".join([f"export const environment = {json.dumps(config_data, indent=2)};", ""]) if isinstance(config_data, dict) else str(config_data)
            res = write_angular_environment_raw(target_file, content)
        elif writer_type == 'spring':
            res, target_file = self._write_spring_config(self._repo, target_file, config_data)
        else:
            res = write_config_file_raw(target_file, config_data)

        if res:
            if self._log and should_log:
                self._log(f"[{self._repo.name}] Configuración '{config_name}' aplicada.")
        elif should_log:
            self.after(0, lambda tf=target_file: messagebox.showerror("Error", f"No se pudo escribir en '{tf}'"))

        self.after(0, self._update_header_hints)
        self._trigger_change_callback()

    def _on_config_change(self, config_name: str, target_file: str = None, skip_log: bool = False):
        """Handle env/app change and overwrite target config file."""
        from core.config_manager import load_repo_configs, save_active_config, load_active_config

        repo = self._repo
        target_file = self._resolve_target_file(repo, target_file)
        config_key = self.get_config_key(target_file)

        active_before = load_active_config(config_key)
        is_real_change = (active_before != config_name)
        save_active_config(config_key, config_name)

        def _run_change():
            if config_name == "- Sin Seleccionar -":
                self._handle_unselect_config(target_file, skip_log, is_real_change)
                return

            configs = load_repo_configs(config_key)
            self._apply_config_data(target_file, config_name, configs.get(config_name), skip_log, is_real_change)

        threading.Thread(target=_run_change, daemon=True).start()

    def _open_config_manager(self, target_file: str = None):
        """Open the RepoConfigManagerDialog for this repository."""
        from gui.dialogs import RepoConfigManagerDialog

        config_key = self.get_config_key(target_file) if target_file else self._repo.name

        if target_file:
            source_dir = os.path.dirname(target_file)
        else:
            default_dir = getattr(self._repo, 'env_default_dir', '')
            source_dir = os.path.join(self._repo.path, default_dir) if default_dir else ''

        def _on_configs_updated():
            def _do_update():
                from core.config_manager import load_repo_configs
                configs = load_repo_configs(config_key)
                opts = ["- Sin Seleccionar -"] + list(configs.keys())
                if hasattr(self, '_config_combos'):
                    combo = self._config_combos.get(target_file)
                    if combo and combo.winfo_exists():
                        combo.configure(values=opts)
                        curr = combo.get()
                        if curr not in opts:
                            combo.set("- Sin Seleccionar -")
                    self._update_header_hints()
                elif hasattr(self, '_config_combo') and self._config_combo.winfo_exists():
                    self._config_combo.configure(values=opts)
                    curr = self._config_combo.get()
                    if curr not in opts:
                        self._config_combo.set("- Sin Seleccionar -")
                        self._update_header_hints()
            self.after(0, _do_update)

        RepoConfigManagerDialog(
            self.winfo_toplevel(),
            repo=self._repo,
            config_key=config_key,
            log_callback=self._log,
            on_close_callback=_on_configs_updated,
            source_dir=source_dir,
        )

    def _on_db_change(self, preset_name: str):
        """Handle DB preset change."""
        if preset_name == NO_DB_PRESET:
            return
        preset = self._db_presets.get(preset_name)
        if not preset:
            return

        def _run():
            from core.config_manager import set_spring_db_preset
            profile = getattr(self, '_profile_combo', None)
            active_profile = profile.get() if profile else 'default'
            resources_dir = os.path.join(self._repo.path, getattr(self._repo, 'env_default_dir', 'src/main/resources'))
            success = set_spring_db_preset(resources_dir, active_profile, preset)
            if self._log:
                msg = f"BD cambiada a: {preset_name}" if success else "Error al cambiar BD"
                self._log(f"[{self._repo.name}] {msg}")

        threading.Thread(target=_run, daemon=True).start()
