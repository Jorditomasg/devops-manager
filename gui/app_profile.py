"""app_profile.py — ProfileManagerMixin extracted from app.py."""
from __future__ import annotations
import os
from gui.constants import PROFILE_DIRTY_SUFFIX
from gui import theme
from core.i18n import t


class ProfileManagerMixin:
    """Mixin providing profile load/save/detect/apply for DevOpsManagerApp."""

    def _profile_dropdown_values(self) -> list:
        """Returns dropdown values: includes t("label.no_profile") only when no profile is active."""
        from core.profile_manager import list_profiles
        names = list_profiles(group_name=self._active_group_name)
        if self._current_profile_name and self._current_profile_name != t("label.no_profile"):
            return names
        return [t("label.no_profile")] + names

    def _refresh_profile_dropdown(self, auto_select_name=None, original_name=None):
        """Reload profile options into topbar dropdown after creation/deletion."""
        profiles = self._profile_dropdown_values()
        if hasattr(self, '_profile_combo'):
            self._profile_combo.configure(values=profiles)

            was_active = (original_name is None or original_name == self._current_profile_name)
            if auto_select_name and auto_select_name in profiles and was_active:
                self._profile_combo.set(auto_select_name)
                self._on_profile_dropdown_change(auto_select_name)
            elif self._current_profile_name in profiles:
                self._profile_combo.set(self._current_profile_name)
            else:
                self._profile_combo.set(t("label.no_profile"))

    def _load_initial_profile_data(self):
        """Loads cached profile data for change tracking on startup."""
        if self._current_profile_name and self._current_profile_name != t("label.no_profile"):
            from core.profile_manager import load_profile
            data = load_profile(self._current_profile_name, group_name=self._active_group_name)
            if data:
                self._current_profile_data = data

    def _on_profile_dropdown_change(self, selected_profile: str):
        if selected_profile == t("label.no_profile"):
            self._current_profile_name = ""
            self._current_profile_data = {}
            lpg = self._settings.get('last_profile_by_group', {})
            lpg[self._active_group_name] = ""
            self._settings['last_profile_by_group'] = lpg
            self._save_settings(self._settings)

            # Limpiar perfiles en cards
            for card in self._repo_cards:
                card.set_profile(t("label.no_selection"))

            # Restore full list (now that no profile is active, show t("label.no_profile") again)
            self._refresh_profile_dropdown()
            return

        from core.profile_manager import load_profile
        data = load_profile(selected_profile, group_name=self._active_group_name)
        if not data:
            self._log(f"Error cargando perfil: {selected_profile}")
            return

        # Assign first, then apply -> to avoid false positive in change check
        self._current_profile_name = selected_profile
        self._current_profile_data = data
        lpg = self._settings.get('last_profile_by_group', {})
        lpg[self._active_group_name] = selected_profile
        self._settings['last_profile_by_group'] = lpg
        self._save_settings(self._settings)

        # Hide t("label.no_profile") from dropdown now that a profile is active
        self._refresh_profile_dropdown()

        self._apply_config(data)

    def _save_current_profile(self):
        """Guards changes to current profile if exists, else opens Config manager."""
        if not self._current_profile_name or self._current_profile_name == t("label.no_profile"):
             # Despliega dialog si no hay uno seleccionado
             self._show_configs()
             return

        from core.profile_manager import build_profile_data, save_profile
        profile_data = build_profile_data(
            self._repo_cards,
            include_config_files=True
        )

        save_profile(self._current_profile_name, profile_data, group_name=self._active_group_name)
        self._current_profile_data = profile_data
        self._do_check_profile_changes()
        self._log(t("log.profile_saved", name=self._current_profile_name))

    def _check_profile_changes(self):
        """Debounced: schedule the actual check 10 ms out, cancelling any pending one.
        Skipped entirely while _apply_config is running (it calls _do_check_profile_changes directly)."""
        if self._applying_profile:
            return
        if self._pending_profile_check:
            try:
                self.after_cancel(self._pending_profile_check)
            except Exception:
                pass
        self._pending_profile_check = self.after(10, self._do_check_profile_changes)

    def _set_profile_combo_dirty(self, dirty: bool):
        """Style the profile combo to indicate unsaved changes (dirty=True) or restore it."""
        if not hasattr(self, '_profile_combo'):
            return
        if dirty:
            self._profile_combo.configure(
                text_color=theme.C.status_logging,
                button_color=theme.C.profile_accent,
                button_hover_color=theme.C.profile_accent,
                font=theme.font("base") + ("italic",),
            )
            self._profile_combo.set(f"{self._current_profile_name}{PROFILE_DIRTY_SUFFIX}")
        else:
            self._profile_combo.configure(
                text_color=theme.C.text_primary,
                button_color=theme.C.profile_accent,
                button_hover_color=theme.C.profile_accent,
                font=theme.font("base"),
            )
            self._profile_combo.set(self._current_profile_name or t("label.no_profile"))

    def _do_check_profile_changes(self):
        """Actual profile-change detection — runs at most once per 300 ms burst."""
        self._pending_profile_check = None
        if not hasattr(self, '_profile_combo'):
            return

        if not self._current_profile_name or self._current_profile_name == t("label.no_profile"):
            self._set_profile_combo_dirty(False)
            return

        has_changed = self._detect_unsaved_profile_changes()
        self._set_profile_combo_dirty(has_changed)

    def _detect_unsaved_profile_changes(self) -> bool:
        """Returns True if current repo cards deviate from _current_profile_data."""
        if not self._current_profile_data:
            return False

        target_repos = self._current_profile_data.get('repos', {})
        card_by_name = {card.get_name(): card for card in self._repo_cards}

        if len(target_repos) != len(card_by_name):
            return True

        return any(
            self._card_differs_from_saved(card_by_name, r_name, t_cfg)
            for r_name, t_cfg in target_repos.items()
        )

    def _card_differs_from_saved(self, card_by_name: dict, r_name: str, t_cfg: dict) -> bool:
        """Returns True if the card for r_name deviates from the saved config t_cfg."""
        if r_name not in card_by_name:
            return True
        card = card_by_name[r_name]

        saved_branch = t_cfg.get('branch')
        if saved_branch is None:
            # Branch excluded from profile when saved — dirty if checkbox is now on
            if card.get_branch_in_profile():
                return True
        else:
            # Branch tracked when saved — dirty if checkbox is now off, or branch changed
            if not card.get_branch_in_profile():
                return True
            if card.get_branch() != saved_branch:
                return True
        cur_prof = card.get_current_profile()
        tgt_prof = t_cfg.get('profile')
        if not cur_prof and not tgt_prof:
            pass # treat None, '', and {} as perfectly equal
        elif cur_prof != tgt_prof:
            return True
        if card.get_custom_command() != t_cfg.get('custom_command', ''):
            return True
        if card.is_selected() != t_cfg.get('selected', True):
            return True
        if self._docker_active_differs(card, t_cfg):
            return True
        if self._docker_services_differ(card, t_cfg):
            return True
        return False

    @staticmethod
    def _docker_active_differs(card, t_cfg: dict) -> bool:
        if not hasattr(card, 'get_docker_compose_active'):
            return False
        current = {os.path.basename(f) for f in card.get_docker_compose_active()}
        saved = {os.path.basename(f) for f in t_cfg.get('docker_compose_active', [])}
        return current != saved

    @staticmethod
    def _docker_services_differ(card, t_cfg: dict) -> bool:
        if not hasattr(card, 'get_docker_profile_services'):
            return False
        current = {os.path.basename(k): sorted(v) for k, v in card.get_docker_profile_services().items()}
        saved = {os.path.basename(k): sorted(v) for k, v in t_cfg.get('docker_profile_services', {}).items()}
        return current != saved

    def _apply_config(self, profile_data: dict, _skip_dirty_check: bool = False):
        """Apply a loaded configuration to all repos.
        Suppresses per-card change callbacks during the loop; runs one check at the end.
        Pass _skip_dirty_check=True on startup to avoid false-positive dirty state
        while async branch loads are still in flight."""
        self._current_profile_data = profile_data
        self._applying_profile = True
        try:
            repos_config = profile_data.get('repos', {})
            for card in self._repo_cards:
                name = card.get_name()
                if name in repos_config:
                    self._apply_config_to_card(card, repos_config[name])
            self._log(t("log.config_applied"))
        finally:
            self._applying_profile = False
            if not _skip_dirty_check:
                self._do_check_profile_changes()

    def _apply_config_to_card(self, card, config: dict):
        """Apply a single repo config to a card."""
        branch = config.get('branch')
        if branch:
            card.set_branch(branch)
            card.set_branch_in_profile(True)
        else:
            card.set_branch_in_profile(False)
        profile = config.get('profile')
        if profile is not None:
            card.set_profile(profile)
        custom_cmd = config.get('custom_command')
        if custom_cmd is not None:
            card.set_custom_command(custom_cmd)
        java_version = config.get('java_version')
        if java_version is not None and hasattr(card, 'selected_java_var'):
            card.selected_java_var.set(java_version)
        selected = config.get('selected')
        if selected is not None:
            card.set_selected(selected)
        if hasattr(card, 'set_docker_compose_active'):
            active = config.get('docker_compose_active', [])
            if active:
                card.set_docker_compose_active(active)
        if hasattr(card, 'set_docker_profile_services'):
            svc_map = config.get('docker_profile_services', {})
            if svc_map:
                card.set_docker_profile_services(svc_map)
