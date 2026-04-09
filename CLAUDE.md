# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python desktop application (customtkinter GUI) for managing and launching multiple development services (Spring Boot, Angular, React, Nx, Maven, Docker Compose) from a single interface. It scans a workspace directory, detects repository types via config-driven rules, and provides start/stop/configure controls for each.

## Running the Application

```bash
# Windows — silent launcher (no terminal window)
scripts\win\run.vbs

# Windows — from console
scripts\win\run.bat

# Linux/Unix — from terminal or file manager
./scripts/linux/run.sh

# Or activate venv first (after install)
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Unix
python main.py

# Run with explicit workspace
.venv/bin/python main.py /path/to/workspace
```

There is no build step. No test suite or linter configuration exists in the project.

## Installation

Requires [uv](https://docs.astral.sh/uv/) — installs Python automatically if needed (Python >=3.9).

```bash
# Automated (installs uv if not present)
scripts\win\install.bat    # Windows
./scripts/linux/install.sh # Unix

# Manual (with uv already installed)
uv sync
```

## Architecture

The codebase follows a layered DDD-influenced architecture:

- **`domain/`** — Pure models (`RepoInfo`, `RunningService`), the `EventBus` port, and domain exceptions. No framework dependencies.
- **`application/`** — `ProjectAnalyzerService` (repo detection) and `ManageServicesUseCase` (service orchestration).
- **`infrastructure/`** — `ProcessManager` (subprocess lifecycle) and YAML/properties file parsers.
- **`core/`** — Managers for config, DB presets, git operations, Java version detection, logging, and service launching.
- **`gui/`** — All UI code: `app.py` (main window) + `app_profile.py` (profile mixin), `repo_card/` package (per-repo accordion widget split into focused mixins), `dialogs/` package (8 dialog classes with shared `BaseDialog`), `widgets/` package (reusable custom widgets: `SearchableCombo`), `global_panel.py` (batch controls), `constants.py` (shared magic strings/numbers), `log_helpers.py` (shared log insertion), `tooltip.py`, `theme.py` (UI theme loader).
- **`config/repo_types/`** — YAML definitions that drive repository detection and available commands (one file per framework).
- **`config/ui_theme.yml`** — Editable UI theme: colors, fonts, sizes, button variants. Overrides the defaults embedded in `gui/theme.py`.
- **`scripts/`** — OS-separated subdirectories: `scripts/win/` (Windows: `run.vbs` silent launcher, `run.bat` console, `install.bat`, `compile.bat`, `run-compiled.bat`) and `scripts/linux/` (Linux/Unix: `run.sh`, `install.sh`, `compile.sh`, `run-compiled.sh`). `build-installer.bat` stays at `scripts/` root (CI/CD only).
- **`.github/workflows/`** — GitHub Actions CI/CD pipeline triggered on `v*` tags or manual dispatch: builds a standalone Windows executable with Nuitka, signs it via SignPath, and publishes it as a GitHub Release.

## Scripts Structure

Scripts are split by OS under `scripts/win/` and `scripts/linux/`. There is no flat-root equivalent — always use the subfolder path:

| Action | Windows | Linux |
|--------|---------|-------|
| Install | `scripts\win\install.bat` | `./scripts/linux/install.sh` |
| Run (silent) | `scripts\win\run.vbs` | — |
| Run | `scripts\win\run.bat` | `./scripts/linux/run.sh` |
| Compile | `scripts\win\compile.bat` | `./scripts/linux/compile.sh` |
| Run compiled | `scripts\win\run-compiled.bat` | `./scripts/linux/run-compiled.sh` |

`build-installer.bat` stays at `scripts/` root — CI/CD only.

**Windows launcher** (`run.vbs`): uses `WScript.Shell.Run` with `windowStyle=0` so no CMD window appears. Path to project root is computed with three nested `GetParentFolderName` calls on `WScript.ScriptFullName` (file → `win/` → `scripts/` → root).

**Linux launcher** (`run.sh`): calls `.venv/bin/python` directly (no `uv run` overhead). Detects terminal via `-t 1`: stays attached if running from shell, detaches with `nohup` if launched from file manager or desktop shortcut.

**Desktop shortcut creation**: `install.bat` / `install.sh` create a shortcut automatically after install. Can also be recreated any time from **Settings → Quick Access** — the button adapts to the current OS (`.lnk` on Windows via `IShellLink` ctypes, `.desktop` on Linux via `xdg-user-dir DESKTOP`).

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
- `clone.py` — git clone dialog
- `config_editor.py` — YAML/properties config file editor
- `profile.py` — profile save/load/manage dialog
- `settings.py` — application settings (language, workspace, Java, shortcuts)
- `repo_config_manager.py` — per-repo command and environment overrides
- `docker_compose.py` — docker-compose profile selector and controls
- `workspace_groups.py` — workspace group management (create, edit, assign repos to groups)
- `confirm_close.py` — confirmation dialog shown when closing with running services

`gui/widgets/` is a package of reusable custom widgets:
- `searchable_combo.py` — `SearchableCombo`: a CTkComboBox replacement with a live-filter search entry and a scrollable popup (canvas + CTkScrollbar). Used wherever repo/branch/profile lists exceed a few items.

`gui/app.py` manages the scrollable list of repo cards and system tray integration (pystray). Profile load/save/detect/apply logic lives in `gui/app_profile.py` (`ProfileManagerMixin`).

`gui/constants.py` centralises all magic strings, timing values, regex patterns, and concurrency limits used across GUI files.

`gui/log_helpers.py` provides `insert_log_line(textbox, text)` — the shared log insertion helper used by all log panels.

## Performance-Critical Patterns (do not break)

**Lazy expand panel** (`gui/repo_card/_expand_panel.py`): `_build_expand_panel()` is NOT called in `RepoCard.__init__`. It is called lazily on the first `_toggle_expand()` via the `_expand_panel_built` flag. Widgets like `_branch_combo`, `_config_combo`, `_cmd_entry`, `_db_combo` do not exist until the card is expanded for the first time. Any code that accesses these must guard with `hasattr(self, '_branch_combo')` etc. `set_branch()`, `set_profile()`, and `set_custom_command()` silently no-op on collapsed cards — this is intentional.

**Profile-switch callback suppression** (`gui/app_profile.py`): `_apply_config()` sets `self._applying_profile = True` during the loop and calls `_do_check_profile_changes()` once at the end. `_check_profile_changes()` is a 300 ms debounce wrapper that returns immediately when `_applying_profile` is True. Any new card-level change trigger must respect this pattern — do not call `_do_check_profile_changes()` directly from card code.

**Parallel repo detection** (`application/services/project_analyzer.py`): `detect_repos` classifies all candidate directories concurrently via `ThreadPoolExecutor(max_workers=min(8, n))`. Each `_classify_repo` call runs `os.walk` + a git subprocess — parallelising gives a meaningful speedup with 5+ repos. `executor.map` is used (not `as_completed`) because it preserves the input alphabetical order.

**Git badge concurrency cap** (`gui/repo_card/_git.py`): `_GIT_BADGE_SEMAPHORE = threading.Semaphore(GIT_BADGE_SEMAPHORE_COUNT)` (value: 3) is a class variable on `GitMixin` limiting concurrent `git status` subprocesses. Badge refresh runs every 30 s per card (`BADGE_REFRESH_MS = 30_000` in `gui/constants.py`). Docker compose status polls every 15 s (`DOCKER_POLL_MS = 15_000`). Do not lower these intervals.

**Constants** (`gui/constants.py`): Timing values, regex patterns, event-binding strings, and limits live here. Never add hardcoded intervals like `30000` to GUI files — import from `gui.constants` instead. User-visible strings must NOT go in `constants.py`; they belong in the translation YAML files.

**System tray window state** (`gui/app.py`): `_on_window_configure` tracks every non-iconic/non-withdrawn `<Configure>` event into `self._last_visible_state` (keys: `geometry`, `state`, `fullscreen`). `_restore_window` reads this snapshot to reapply the exact state before hide — fullscreen, zoomed/maximized, or normal with geometry. Do NOT snapshot state inside `_on_window_unmap`; by the time `<Unmap>` fires Tk has already transitioned to iconic, making both `self.state()` and `self.attributes('-fullscreen')` stale.

**Internationalisation** (`core/i18n.py` + `config/translations/`): All user-visible strings are translated via `t("key")`. Call `init_i18n(language_code)` once at startup in `main.py` before any widget is created. Translation files live in `config/translations/<code>.yml` (e.g. `en_EN.yml`, `es_ES.yml`). Keys follow a dot-namespaced convention: `btn.*`, `label.*`, `tooltip.*`, `dialog.<name>.*`, `log.*`, `misc.*`, `install.*`. Adding a new user-visible string requires: (1) add the key to both YAML files, (2) use `t("key")` in the GUI code. Never hardcode user-visible strings in Python. The language setting is stored in `devops_manager_config.json` under `"language"` and takes effect on next restart.
