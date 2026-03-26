# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python desktop application (customtkinter GUI) for managing and launching multiple development services (Spring Boot, Angular, React, Nx, Maven, Docker Compose) from a single interface. It scans a workspace directory, detects repository types via config-driven rules, and provides start/stop/configure controls for each.

## Running the Application

```bash
# Activate venv first
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Unix

# Run (uses parent directory as workspace)
python main.py

# Run with explicit workspace
python main.py /path/to/workspace
```

There is no build step. No test suite or linter configuration exists in the project.

## Installation

```bash
# Automated
scripts\install.bat    # Windows
./scripts/install.sh   # Unix

# Manual
python -m venv .venv
pip install -r requirements.txt
```

## Architecture

The codebase follows a layered DDD-influenced architecture:

- **`domain/`** — Pure models (`RepoInfo`, `RunningService`), the `EventBus` port, and domain exceptions. No framework dependencies.
- **`application/`** — `ProjectAnalyzerService` (repo detection) and `ManageServicesUseCase` (service orchestration).
- **`infrastructure/`** — `ProcessManager` (subprocess lifecycle) and YAML/properties file parsers.
- **`core/`** — Managers for config, DB presets, git operations, Java version detection, logging, and service launching.
- **`gui/`** — All UI code: `app.py` (main window) + `app_profile.py` (profile mixin), `repo_card/` package (per-repo accordion widget split into focused mixins), `dialogs/` package (9 dialog classes with shared `BaseDialog`), `global_panel.py` (batch controls), `constants.py` (shared magic strings/numbers), `log_helpers.py` (shared log insertion), `tooltip.py`, `theme.py` (UI theme loader).
- **`config/repo_types/`** — YAML definitions that drive repository detection and available commands (one file per framework).
- **`config/ui_theme.yml`** — Editable UI theme: colors, fonts, sizes, button variants. Overrides the defaults embedded in `gui/theme.py`.
- **`scripts/`** — Shell scripts for install (`install.bat/sh`), run (`run.bat/sh`), Nuitka compilation (`compile.bat/sh`), and running the compiled binary (`run_compiled.bat/sh`).
- **`.github/workflows/`** — GitHub Actions CI/CD pipeline triggered on `v*` tags or manual dispatch: builds a standalone Windows executable with Nuitka, signs it via SignPath, and publishes it as a GitHub Release.

## Key Design Decisions

**Event Bus** (`domain/ports/event_bus.py`): A thread-safe singleton pub/sub mediator that decouples the GUI from service management. Events include `SERVICE_STATUS_CHANGED`, `REQUEST_START_SERVICE`, `REQUEST_STOP_SERVICE`, `REQUEST_INSTALL_DEPENDENCIES`. All cross-layer communication should go through this bus.

**Config-driven repo detection** (`config/repo_types/*.yml`): Adding support for a new project type means creating a YAML file here — no code changes required. Each definition includes detection rules (file existence heuristics), priority (higher wins when multiple match), commands (install/start/stop), environment file patterns, and Spring Boot readiness patterns.

**Process management** (`infrastructure/process/process_manager.py`): Subprocess execution is async (threads), streams stdout/stderr to the repo card's log panel, and registers an atexit hook for clean shutdown. `service_launcher.py` wraps this with service-lifecycle semantics (ready detection via log regex patterns).

**Configuration persistence** (`devops_manager_config.json`): Stores window geometry, last profile, DB presets, and workspace path. Managed by `core/config_manager.py`. Reads are cached in memory with mtime-based invalidation via `_load_config_cached()`. Any new load function that reads this file must use `_load_config_cached()`; any new save function must call `_invalidate_config_cache(config_path)` after writing.

**Centralized UI theme** (`gui/theme.py` + `config/ui_theme.yml`): All colors, fonts, sizes, and button variants are defined in one place. `gui/theme.py` loads `config/ui_theme.yml` once at import time and merges it over embedded `_DEFAULTS` — so the app always starts even if the YAML is missing. All GUI files import via `from gui import theme` and must use the theme API instead of hardcoded hex values or font tuples.

Key API:
- `theme.font(size_key, bold=False, mono=False)` → font tuple, e.g. `theme.font("base")`, `theme.font("h1", bold=True)`
- `theme.btn_style(variant, height="md", width=None, font_size="base")` → kwargs dict for `ctk.CTkButton` — use as `**theme.btn_style("start")`; do NOT also pass an explicit `font=` argument or it will raise a duplicate-keyword error
- `theme.combo_style(height="md")` → kwargs dict for `ctk.CTkComboBox`
- `theme.log_textbox_style(detached=False)` → kwargs dict for log `ctk.CTkTextbox`
- `theme.C.*` — color namespace: `theme.C.card`, `theme.C.text_primary`, `theme.C.status_running`, etc.
- `theme.G.*` — geometry namespace: `theme.G.corner_btn`, `theme.G.btn_height_md`, etc.
- `theme.STATUS_ICONS` — dict mapping status strings to their display colors

Button variants available: `success`, `start`, `danger`, `danger_alt`, `danger_deep`, `warning`, `blue`, `blue_active`, `neutral`, `neutral_alt`, `purple`, `purple_alt`, `purple_global`, `log_action`, `toggle_expand`, `profile_accent`.

## GUI Structure

`gui/repo_card/` is a package splitting the accordion widget by concern:
- `_base.py` — `RepoCard` composite class: `__init__`, `destroy`, public getters/setters. Inherits all mixins.
- `_header.py` — `HeaderMixin`: `_build_ui`, `_build_header`, `_build_action_buttons`, `_update_button_visibility`, `_update_header_hints`
- `_expand_panel.py` — `ExpandPanelMixin`: `_build_expand_panel`, `_build_*_row`, `_toggle_expand`, `_update_status`, `_on_status_change`
- `_log.py` — `LogMixin`: `_repo_log`, `_clear_logs`, `_detach_logs`, `_flash_log_icon`
- `_git.py` — `GitMixin`: badge refresh loop, branch fetching, port/status detection from log
- `_config.py` — `ConfigMixin`: Spring config file writing, environment config management
- `_docker.py` — `DockerMixin`: docker-compose profile changes, status polling, button updates
- `_actions.py` — `ActionsMixin`: start/stop/restart/pull/install/clean/seed

`gui/dialogs/` is a package with one file per dialog group:
- `_base.py` — `BaseDialog(ctk.CTkToplevel)`: shared title/geometry/transient/grab_set boilerplate
- `clone.py`, `config_editor.py`, `profile.py`, `settings.py`, `repo_config_manager.py`, `docker_compose.py`

`gui/app.py` manages the scrollable list of repo cards and system tray integration (pystray). Profile load/save/detect/apply logic lives in `gui/app_profile.py` (`ProfileManagerMixin`).

`gui/constants.py` centralises all magic strings, timing values, regex patterns, and concurrency limits used across GUI files.

`gui/log_helpers.py` provides `insert_log_line(textbox, text)` — the shared log insertion helper used by all log panels.

## Performance-Critical Patterns (do not break)

**Lazy expand panel** (`gui/repo_card/_expand_panel.py`): `_build_expand_panel()` is NOT called in `RepoCard.__init__`. It is called lazily on the first `_toggle_expand()` via the `_expand_panel_built` flag. Widgets like `_branch_combo`, `_config_combo`, `_cmd_entry`, `_db_combo` do not exist until the card is expanded for the first time. Any code that accesses these must guard with `hasattr(self, '_branch_combo')` etc. `set_branch()`, `set_profile()`, and `set_custom_command()` silently no-op on collapsed cards — this is intentional.

**Profile-switch callback suppression** (`gui/app_profile.py`): `_apply_config()` sets `self._applying_profile = True` during the loop and calls `_do_check_profile_changes()` once at the end. `_check_profile_changes()` is a 300 ms debounce wrapper that returns immediately when `_applying_profile` is True. Any new card-level change trigger must respect this pattern — do not call `_do_check_profile_changes()` directly from card code.

**Git badge concurrency cap** (`gui/repo_card/_git.py`): `_GIT_BADGE_SEMAPHORE = threading.Semaphore(GIT_BADGE_SEMAPHORE_COUNT)` (value: 3) is a class variable on `GitMixin` limiting concurrent `git status` subprocesses. Badge refresh runs every 30 s per card (`BADGE_REFRESH_MS = 30_000` in `gui/constants.py`). Docker compose status polls every 15 s (`DOCKER_POLL_MS = 15_000`). Do not lower these intervals.

**Constants** (`gui/constants.py`): All magic strings, timing values, regex patterns, and limits live here. Never add inline string literals like `"- Ninguna (Local) -"` or hardcoded intervals like `30000` to GUI files — import from `gui.constants` instead.
