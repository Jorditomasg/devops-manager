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
install.bat    # Windows
./install.sh   # Unix

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
- **`gui/`** — All UI code: `app.py` (main window), `repo_card.py` (per-repo accordion widget), `global_panel.py` (batch controls), `dialogs.py`, `tooltip.py`.
- **`config/repo_types/`** — YAML definitions that drive repository detection and available commands (one file per framework).
- **`ui/presenters/`** — MVP presenters stub (currently minimal).

## Key Design Decisions

**Event Bus** (`domain/ports/event_bus.py`): A thread-safe singleton pub/sub mediator that decouples the GUI from service management. Events include `SERVICE_STATUS_CHANGED`, `REQUEST_START_SERVICE`, `REQUEST_STOP_SERVICE`, `REQUEST_INSTALL_DEPENDENCIES`. All cross-layer communication should go through this bus.

**Config-driven repo detection** (`config/repo_types/*.yml`): Adding support for a new project type means creating a YAML file here — no code changes required. Each definition includes detection rules (file existence heuristics), priority (higher wins when multiple match), commands (install/start/stop), environment file patterns, and Spring Boot readiness patterns.

**Process management** (`infrastructure/process/process_manager.py`): Subprocess execution is async (threads), streams stdout/stderr to the repo card's log panel, and registers an atexit hook for clean shutdown. `service_launcher.py` wraps this with service-lifecycle semantics (ready detection via log regex patterns).

**Configuration persistence** (`devops_manager_config.json`): Stores window geometry, last profile, DB presets, and workspace path. Managed by `core/config_manager.py`. Reads are cached in memory with mtime-based invalidation via `_load_config_cached()`. Any new load function that reads this file must use `_load_config_cached()`; any new save function must call `_invalidate_config_cache(config_path)` after writing.

## GUI Structure

`gui/repo_card.py` (~2000 lines) is the most complex file. Each `RepoCard` is an accordion widget with:
- Collapsed view: checkbox, repo name, branch hint, status indicator, quick action buttons
- Expanded view: branch selector, profile/DB dropdowns, install button, custom command input, log output panel

`gui/app.py` (~850 lines) manages the scrollable list of repo cards, profile selection, DB preset management, and system tray integration (pystray).

## Performance-Critical Patterns (do not break)

**Lazy expand panel** (`gui/repo_card.py`): `_build_expand_panel()` is NOT called in `RepoCard.__init__`. It is called lazily on the first `_toggle_expand()` via the `_expand_panel_built` flag. Widgets like `_branch_combo`, `_config_combo`, `_cmd_entry`, `_db_combo` do not exist until the card is expanded for the first time. Any code that accesses these must guard with `hasattr(self, '_branch_combo')` etc. `set_branch()`, `set_profile()`, and `set_custom_command()` silently no-op on collapsed cards — this is intentional.

**Profile-switch callback suppression** (`gui/app.py`): `_apply_config()` sets `self._applying_profile = True` during the loop and calls `_do_check_profile_changes()` once at the end. `_check_profile_changes()` is a 300 ms debounce wrapper that returns immediately when `_applying_profile` is True. Any new card-level change trigger must respect this pattern — do not call `_do_check_profile_changes()` directly from card code.

**Git badge concurrency cap** (`gui/repo_card.py`): `_GIT_BADGE_SEMAPHORE = threading.Semaphore(3)` limits concurrent `git status` subprocesses. Badge refresh runs every 30 s per card (not 10 s). Docker compose status polls every 15 s (not 4 s). Do not lower these intervals.
