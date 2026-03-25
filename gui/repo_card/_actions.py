"""_actions.py — Service action methods mixin for RepoCard."""
from __future__ import annotations
import os
import threading
import subprocess
import time
from tkinter import messagebox
from gui.constants import REINSTALL_LBL
from gui.log_helpers import insert_log_line
from gui import theme


def _create_subprocess(cmd_str: str, cwd: str, env: dict = None, shell: bool = True) -> subprocess.Popen:
    """Helper to create a unified subprocess."""
    creationflags = (
        getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    ) if os.name == 'nt' else 0
    return subprocess.Popen(
        cmd_str, cwd=cwd, env=env, shell=shell,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
        creationflags=creationflags,
    )


class ActionsMixin:
    """Mixin providing start/stop/restart/pull/install/clean/seed actions."""

    # ─── Install ──────────────────────────────────────────────────

    def install_dependencies(self, skip_if_installed=False):
        """Method to trigger dependency installation via YAML commands."""
        install_cfg = getattr(self._repo, 'ui_config', {}).get('install', {})
        check_dirs = install_cfg.get('check_dirs', [])

        if not self._repo.run_install_cmd:
            return

        is_installed = False
        if check_dirs:
            is_installed = True
            for cd in check_dirs:
                if not os.path.isdir(os.path.join(self._repo.path, cd)):
                    is_installed = False
                    break
        else:
            is_installed = True

        if skip_if_installed and is_installed:
            return

        self._run_install_cmd(bypass_confirm=True)

    def _build_install_env(self, repo_info) -> dict | None:
        """Build environment dict for the install subprocess (Java override if needed)."""
        if 'java_version' not in repo_info.features:
            return None
        java_choice = getattr(self, 'selected_java_var', None)
        if not java_choice:
            return None
        java_home = self._java_versions.get(java_choice.get(), "")
        if not java_home:
            return None
        from core.java_manager import build_java_env
        env = build_java_env(java_home)
        if self._log:
            self._log(f"Usando JAVA_HOME: {java_home}")
        return env

    def _stream_process_output(self, proc, log_fn):
        """Read stdout line-by-line from *proc* and forward to *log_fn*."""
        for line in iter(proc.stdout.readline, ''):
            if not line:
                break
            if log_fn:
                log_fn(line.strip())

    def _on_install_complete(self, success: bool, check_dirs: list, success_text: str, fail_text: str):
        """Update install button style and status after the install process finishes."""
        self._is_installing = False
        if success:
            _ok_style = theme.btn_style("neutral_alt")
            self._install_btn.configure(
                text=success_text,
                fg_color=_ok_style["fg_color"],
                border_color=_ok_style["border_color"],
                hover_color=_ok_style["hover_color"],
            )
            self._update_header_hints()
            if self._log:
                self._log(f"[{self._repo.name}] Instalación finalizada ✓")
        else:
            _fail_style = theme.btn_style("danger_alt")
            self._install_btn.configure(
                text=fail_text,
                fg_color=_fail_style["fg_color"],
                border_color=_fail_style["border_color"],
                hover_color=_fail_style["hover_color"],
            )
            if self._log:
                self._log(f"[{self._repo.name}] Fallo al instalar. Archivos clave no encontrados.")
        self._update_button_visibility()

    def _run_install_cmd(self, bypass_confirm=False):
        """Run the appropriate install command."""
        repo = self._repo
        path = repo.path

        install_cfg = getattr(repo, 'ui_config', {}).get('install', {})
        check_dirs = install_cfg.get('check_dirs', [])
        already_installed = False

        if check_dirs:
            already_installed = True
            for cd in check_dirs:
                if not os.path.isdir(os.path.join(path, cd)):
                    already_installed = False
                    break

        if hasattr(self, '_install_btn') and already_installed and not bypass_confirm:
            if not messagebox.askyesno("Reinstalar", "¿Estás seguro de que deseas volver a instalar dependencias?"):
                return

        if already_installed and repo.run_reinstall_cmd:
            cmd_str = repo.run_reinstall_cmd
        elif repo.run_install_cmd:
            cmd_str = repo.run_install_cmd
        else:
            return

        success_text = install_cfg.get('label_ok', REINSTALL_LBL)
        fail_text = "Error!"

        if self._log:
            self._log(f"Running {cmd_str}...")

        self._install_btn.configure(text="Installing...", state="disabled")
        self._is_installing = True
        self._update_button_visibility()

        env = self._build_install_env(repo)
        threading.Thread(
            target=self._run_install_thread,
            args=(cmd_str, env, check_dirs, success_text, fail_text),
            daemon=True,
        ).start()

    def _run_install_thread(self, cmd_str, env, check_dirs, success_text, fail_text):
        """Thread body: run the install subprocess, stream output, then report completion."""
        try:
            process = _create_subprocess(cmd_str, cwd=self._repo.path, env=env, shell=True)
            self._stream_process_output(process, self._log)

            try:
                process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                if self._log:
                    self._log(f"[{self._repo.name}] ⚠️ Instalación superó 10 min, proceso terminado")
                try:
                    process.kill()
                    process.wait(timeout=5)
                except OSError:
                    pass

            is_ok = True
            if check_dirs:
                for cd in check_dirs:
                    if not os.path.isdir(os.path.join(self._repo.path, cd)):
                        is_ok = False
                        break

            self.after(0, lambda ok=is_ok: self._on_install_complete(ok, check_dirs, success_text, fail_text))

        except Exception as e:
            if self._log:
                self._log(f"Error en instalación: {e}")

            def _err():
                self._is_installing = False
                self._install_btn.configure(text=fail_text, state="normal")
                self._update_button_visibility()

            self.after(0, _err)

    # ─── Start / Stop / Restart ───────────────────────────────────

    def _get_start_command(self):
        """Get the start command — custom or default."""
        if hasattr(self, '_cmd_entry'):
            custom = self._cmd_entry.get().strip()
            if custom:
                return custom
        return self._repo.run_command or ''

    def _prepare_start_env(self, config_entry=None) -> dict | None:
        """Build env dict for the start subprocess (Java override if needed)."""
        java_home = ''
        if hasattr(self, 'selected_java_var'):
            java_choice = self.selected_java_var.get()
            java_home = self._java_versions.get(java_choice, '')
        if not java_home:
            return None
        try:
            from core.java_manager import build_java_env
            return build_java_env(java_home)
        except (ImportError, OSError):
            return None

    def _on_service_ready(self, port: int):
        """Update status and UI after the ready pattern is detected in service output."""
        self._update_status(self._repo.name, 'running')
        if port and hasattr(self, '_port_label'):
            try:
                self._port_label.configure(text=f":{port}")
            except Exception:
                pass

    def _stream_start_output(self, proc, repo):
        """Read stdout line-by-line, detecting port/status patterns, until EOF."""
        for line in iter(proc.stdout.readline, ''):
            if not line:
                break
            decoded_line = line.strip()
            self._detect_port_from_log(decoded_line)
            self._detect_status_from_log(decoded_line)
            if self._log:
                self._log(decoded_line)

    def _start(self):
        """Start the service using the config-driven run_command from the YAML definition."""
        repo = self._repo

        if 'docker_checkboxes' in repo.features:
            self._start_docker_services()
            return

        # Check for custom command entered by user
        custom_cmd = self._get_start_command()
        if custom_cmd and custom_cmd != repo.run_command:
            self._start_custom(custom_cmd)
            return

        # --- Config-driven generic start ---
        cmd = repo.run_command or ''
        if not cmd:
            if self._log:
                self._log(f"[{repo.name}] ⚠ Sin comando de inicio definido en la configuración YAML.")
            return

        # Append profile flag if selected
        profile = ''
        if hasattr(self, '_profile_combo'):
            profile = self._profile_combo.get()
        elif hasattr(self, '_config_combos') and self._config_combos:
            for _, combo in self._config_combos.items():
                v = combo.get()
                if v and v not in ('- Sin Seleccionar -', ''):
                    profile = v
                    break

        if profile and repo.run_profile_flag:
            cmd = f"{cmd} {repo.run_profile_flag}{profile}"

        env = self._prepare_start_env()

        self._update_status(repo.name, 'starting')
        if self._log:
            self._log(f"[{repo.name}] ▶ {cmd}")

        threading.Thread(
            target=self._run_start_thread,
            args=(cmd, env, profile),
            daemon=True,
            name=f'svc-{repo.name}',
        ).start()

    def _run_start_thread(self, cmd, env, profile):
        """Thread body: launch the service subprocess, stream output, then update status."""
        repo = self._repo
        try:
            process = _create_subprocess(cmd, cwd=repo.path, env=env, shell=True)

            # Track process in legacy launcher so stop/restart work
            from domain.models.running_service import RunningService
            svc = RunningService(name=repo.name, repo_path=repo.path, port=0, profile=profile, status='starting')
            svc.process = process
            self._launcher._services[repo.name] = svc

            # Stay in 'starting' — transition to 'running' is driven by ready_pattern
            if not repo.ready_pattern:
                self.after(0, lambda: self._update_status(repo.name, 'running'))

            self._stream_start_output(process, repo)

            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=5)
                except OSError:
                    pass

            # If still 'starting' when process exits, it failed (unless stopped manually)
            if getattr(self, '_is_stopping_manually', False):
                final_status = 'stopped'
                self._is_stopping_manually = False
            else:
                final_status = 'error' if self._status == 'starting' else 'stopped'

            self.after(0, lambda s=final_status: self._update_status(repo.name, s))
            if self._log:
                self._log(f"[{repo.name}] ⏹ Proceso terminado (código {process.returncode})")

        except Exception as e:
            self.after(0, lambda: self._update_status(repo.name, 'error'))
            if self._log:
                self._log(f"[{repo.name}] ✗ Error: {e}")

    def _start_custom(self, cmd_str: str):
        """Start with a custom command."""
        repo = self._repo
        if self._log:
            self._log(f"Ejecutando: {cmd_str}")

        self._update_status(repo.name, 'starting')

        def _run():
            try:
                process = _create_subprocess(cmd_str, cwd=repo.path, env=None, shell=True)

                # Stay in 'starting' — transition to 'running' is driven by ready_pattern
                if not repo.ready_pattern:
                    self._update_status(repo.name, 'running')

                self._stream_start_output(process, repo)

                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except OSError:
                        pass

                # If still 'starting' when process exits, it failed (unless stopped manually)
                if getattr(self, '_is_stopping_manually', False):
                    final_status = 'stopped'
                    self._is_stopping_manually = False
                else:
                    final_status = 'error' if self._status == 'starting' else 'stopped'

                self._update_status(repo.name, final_status)

            except Exception as e:
                self._update_status(repo.name, 'error')
                if self._log:
                    self._log(f"Error: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _stop(self):
        """Stop the service using the service launcher."""
        repo = self._repo
        if 'docker_checkboxes' in repo.features:
            self._stop_docker_services()
            return

        self._is_stopping_manually = True
        self._launcher.stop_service(repo.name, self._log, self._update_status)

    def _stop_docker_services(self):
        """Stop active docker-compose services."""
        def _run():
            from core.db_manager import docker_compose_down
            for dc_file in self._active_compose_files:
                docker_compose_down(dc_file, log=self._log)
            self._update_compose_counts_now()

        threading.Thread(target=_run, daemon=True).start()

    def _restart(self):
        """Restart the service using the service launcher."""
        repo = self._repo
        if 'docker_checkboxes' in repo.features:
            self._stop_docker_services()
            self.after(2000, self._start_docker_services)
            return

        def _run():
            self._stop()
            time.sleep(0.3)
            self.after(0, self._start)

        threading.Thread(target=_run, daemon=True).start()

    def _pull(self):
        """Pull latest changes."""
        def _run():
            from core.git_manager import get_local_changes, get_commits_behind, get_current_branch, pull

            ignore = getattr(self._repo, 'env_pull_ignore_patterns', [])

            changes = get_local_changes(self._repo.path, ignore_files=ignore)
            if changes:
                def _err():
                    limit = 10
                    display_changes = "\n".join(changes[:limit]) + ("\n..." if len(changes) > limit else "")
                    messagebox.showerror(
                        "Error de Pull",
                        f"No se puede hacer pull en '{self._repo.name}', tienes cambios locales sin guardar "
                        f"que podrían sobreescribirse:\n\n{display_changes}",
                    )
                self.after(0, _err)
                return

            branch = get_current_branch(self._repo.path)
            commits = get_commits_behind(self._repo.path, branch)

            if commits > 0:
                def _ask():
                    if messagebox.askyesno(
                        "Confirmar Pull",
                        f"Hay {commits} nuevo(s) commit(s) en '{branch}'. ¿Quieres descargarlos ahora?",
                    ):
                        threading.Thread(target=_do_pull, daemon=True).start()
                self.after(0, _ask)
            else:
                _do_pull()

        def _do_pull():
            from core.git_manager import pull
            pull(self._repo.path, self._log)
            self._refresh_branch()
            self._check_pull_status()
            self._refresh_badge()

        threading.Thread(target=_run, daemon=True).start()

    def _check_pull_status(self):
        """Update pull button state with commits behind count."""
        def _run():
            from core.git_manager import get_commits_behind, get_current_branch
            branch = get_current_branch(self._repo.path)
            if branch != 'unknown':
                commits = get_commits_behind(self._repo.path, branch)

                def _update():
                    if hasattr(self, '_pull_btn'):
                        if commits > 0:
                            self._pull_btn.configure(
                                text=f"⬇ Pull ({commits})",
                                fg_color=theme.btn_style("blue_active")["fg_color"],
                            )
                        else:
                            self._pull_btn.configure(
                                text="⬇ Pull",
                                fg_color=theme.btn_style("blue")["fg_color"],
                            )

                self.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _clean_repo(self):
        """Clean all local untracked and modified files, removing env overrides."""
        if not messagebox.askyesno(
            "Confirmar Limpieza",
            "¿Seguro que quieres borrar todos los cambios locales no commiteados? "
            "Se deseleccionará la configuración (Env/App) y se restaurarán los ficheros originales.",
        ):
            return

        def _run():
            from core.git_manager import clean_repo
            success, _ = clean_repo(self._repo.path, self._log)
            if success:
                def _restore():
                    if hasattr(self, '_config_combo'):
                        self._config_combo.set("- Sin Seleccionar -")
                        self._on_config_change("- Sin Seleccionar -")
                    if hasattr(self, '_config_combos'):
                        for target_file, combo in self._config_combos.items():
                            combo.set("- Sin Seleccionar -")
                            from core.config_manager import save_active_config
                            save_active_config(self.get_config_key(target_file), "- Sin Seleccionar -")
                            # We don't trigger self._on_config_change for all because clean reverting
                            # the files makes git restore the originals automatically.
                    self._refresh_badge()
                    self._check_pull_status()

                self.after(500, _restore)

        threading.Thread(target=_run, daemon=True).start()

    def _seed(self):
        """Run database seeds."""
        def _run():
            from core.db_manager import run_flyway_seeds
            run_flyway_seeds(self._repo.path, self._log)

        threading.Thread(target=_run, daemon=True).start()
