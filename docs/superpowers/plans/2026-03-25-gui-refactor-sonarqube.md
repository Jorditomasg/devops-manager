# GUI Refactor & SonarQube Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split three large GUI files (~4900 lines total) into focused modules of ≤300 lines each, while fixing all SonarQube issues (methods >50L, magic strings, duplicated code, missing base class, silent errors).

**Architecture:** `gui/repo_card/` package splits `RepoCard` by concern (UI building, actions, docker, config, log); `gui/dialogs/` package splits the 9 dialog classes into individual files with a shared `BaseDialog`; `gui/constants.py` and `gui/log_helpers.py` centralise cross-cutting code.

**Tech Stack:** Python 3.x, customtkinter, tkinter, threading — no new dependencies.

---

## File Map

### New files to create
| File | Responsibility | Target lines |
|------|---------------|-------------|
| `gui/constants.py` | All magic strings, numbers, regex patterns | ~60 |
| `gui/log_helpers.py` | Shared `insert_log_line()`, `LogMixin` | ~50 |
| `gui/repo_card/__init__.py` | Re-exports `RepoCard`, public API unchanged | ~10 |
| `gui/repo_card/_base.py` | `RepoCard` class skeleton: `__init__`, `destroy`, public getters/setters | ~180 |
| `gui/repo_card/_header.py` | `_build_header`, `_build_ui`, `_update_button_visibility`, `_update_header_hints` | ~180 |
| `gui/repo_card/_expand_panel.py` | `_build_expand_panel`, `_build_log_row`, `_build_branch_row`, `_build_install_btn`, `_build_selector_row`, `_build_command_row`, `_build_docker_row` | ~280 |
| `gui/repo_card/_actions.py` | `_start`, `_stop`, `_restart`, `_pull`, `_clean_repo`, `_seed`, `_run_install_cmd`, `_start_custom`, `_check_pull_status` | ~280 |
| `gui/repo_card/_docker.py` | `_start_docker_services`, `_on_docker_profile_change`, `_start_compose_status_thread`, `_update_compose_counts_now` | ~100 |
| `gui/repo_card/_config.py` | `_resolve_target_file`, `_handle_unselect_config`, `_write_spring_config`, `_apply_config_data`, `_on_config_change`, `_open_config_manager`, `_on_db_change`, `_get_config_key` | ~180 |
| `gui/repo_card/_log.py` | `_repo_log`, `_clear_logs`, `_detach_logs`, `_flash_log_icon` | ~120 |
| `gui/repo_card/_git.py` | `_refresh_badge`, `_refresh_badge_loop`, `_refresh_branch`, `_fetch_branches`, `_on_branch_change`, `_detect_port_from_log`, `_detect_status_from_log` | ~120 |
| `gui/dialogs/__init__.py` | Re-exports all dialog classes | ~20 |
| `gui/dialogs/_base.py` | `BaseDialog(ctk.CTkToplevel)` with shared boilerplate | ~40 |
| `gui/dialogs/clone.py` | `CloneDialog` | ~100 |
| `gui/dialogs/config_editor.py` | `ConfigEditorDialog` | ~70 |
| `gui/dialogs/profile.py` | `ProfileDialog`, `ImportOptionsDialog` | ~380 |
| `gui/dialogs/settings.py` | `SettingsDialog`, `PresetEditorDialog`, `JavaVersionEditorDialog` | ~280 |
| `gui/dialogs/repo_config_manager.py` | `RepoConfigManagerDialog` | ~270 |
| `gui/dialogs/docker_compose.py` | `DockerComposeDialog` | ~310 |
| `gui/app_profile.py` | `ProfileManagerMixin` extracted from `app.py` (profile load/save/detect/apply) | ~160 |

### Files to modify
| File | Change |
|------|--------|
| `gui/repo_card.py` | **Delete** — replaced by package |
| `gui/dialogs.py` | **Delete** — replaced by package |
| `gui/app.py` | Import from new locations; mix in `ProfileManagerMixin`; remove extracted code |

---

## Task 1 — Create `gui/constants.py`

**Files:**
- Create: `gui/constants.py`

> No tests needed — pure constants, verified by import.

- [ ] **Step 1: Collect all magic strings/numbers from the three files**

Grep for hardcoded strings/numbers in the three files. The full list:

```python
# gui/constants.py
"""Shared constants for the GUI layer."""

# ── Combo / label sentinel values ──────────────────────────────
NO_DB_PRESET       = "- Ninguna (Local) -"
NO_PROFILE_TEXT    = "— Sin perfil —"
PROFILE_DIRTY_SUFFIX = " *"

# ── Button labels ───────────────────────────────────────────────
BTN_CLICK          = "<Button-1>"
BTN_CONFIG_TEXT    = "⚙ Config"
BTN_CONFIG_TOOLTIP = "Editar configuración"
REINSTALL_LBL      = "Reinstall ✓"

# ── Timing (milliseconds / seconds) ────────────────────────────
BADGE_REFRESH_MS   = 30_000   # git badge poll interval per card
DOCKER_POLL_MS     = 15_000   # docker-compose status poll
PROFILE_DEBOUNCE_MS = 300     # profile-change debounce

# ── Concurrency limits ──────────────────────────────────────────
GIT_BADGE_SEMAPHORE_COUNT = 3

# ── Log limits ──────────────────────────────────────────────────
LOG_MAX_LINES      = 500

# ── Config file ─────────────────────────────────────────────────
CONFIG_FILE        = "devops_manager_config.json"

# ── Port detection regexes ──────────────────────────────────────
import re
PORT_REGEXES = [
    re.compile(r"Tomcat (?:started on|initialized with) port.*?(\d+)", re.IGNORECASE),
    re.compile(r"http://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])[:\s]+(\d+)", re.IGNORECASE),
    re.compile(r"(?:listening on|bound to).*?port\s+(\d+)", re.IGNORECASE),
    re.compile(r"Local:\s*http://localhost:(\d+)", re.IGNORECASE),
]
```

- [ ] **Step 2: Write the file**

Write exactly the content above to `gui/constants.py`.

- [ ] **Step 3: Verify import works**

```bash
cd c:/Users/JordiTomásOrizon.AzureAD/PROYECTOS/BOA2/devops-manager
.venv/Scripts/python -c "from gui.constants import NO_DB_PRESET, PORT_REGEXES; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
rtk git add gui/constants.py && rtk git commit -m "feat(gui): add constants module to eliminate magic strings"
```

---

## Task 2 — Create `gui/log_helpers.py`

**Files:**
- Create: `gui/log_helpers.py`

- [ ] **Step 1: Extract the shared log-insertion pattern**

All three files repeat this logic:
```python
textbox.configure(state="normal")
textbox.insert("end", text + "\n")
lines = int(textbox.index("end-1c").split(".")[0])
if lines > MAX_LINES:
    textbox.delete("1.0", f"{lines - MAX_LINES}.0")
textbox.see("end")
textbox.configure(state="disabled")
```

Create `gui/log_helpers.py`:

```python
"""Shared log-insertion helpers for all GUI textboxes."""
from __future__ import annotations
import customtkinter as ctk
from gui.constants import LOG_MAX_LINES


def insert_log_line(textbox: ctk.CTkTextbox, text: str, max_lines: int = LOG_MAX_LINES) -> None:
    """Thread-safe log line insertion with automatic line-count trimming.

    Caller is responsible for scheduling on the main thread (after(..) / event_generate).
    """
    textbox.configure(state="normal")
    textbox.insert("end", text + "\n")
    lines = int(textbox.index("end-1c").split(".")[0])
    if lines > max_lines:
        textbox.delete("1.0", f"{lines - max_lines}.0")
    textbox.see("end")
    textbox.configure(state="disabled")
```

- [ ] **Step 2: Write the file**

- [ ] **Step 3: Verify import**

```bash
.venv/Scripts/python -c "from gui.log_helpers import insert_log_line; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
rtk git add gui/log_helpers.py && rtk git commit -m "feat(gui): add shared log_helpers module"
```

---

## Task 3 — Create `gui/dialogs/_base.py`

**Files:**
- Create: `gui/dialogs/` package
- Create: `gui/dialogs/__init__.py`
- Create: `gui/dialogs/_base.py`

- [ ] **Step 1: Create package skeleton**

```bash
mkdir gui/dialogs
```

Create `gui/dialogs/__init__.py` (placeholder — will be filled in Task 10):
```python
# Populated in later tasks — kept as package marker for now
```

- [ ] **Step 2: Write `_base.py`**

```python
"""BaseDialog — shared boilerplate for all CTkToplevel dialog windows."""
import customtkinter as ctk


class BaseDialog(ctk.CTkToplevel):
    """Mixin/base for all application dialogs.

    Handles: transient parent binding, grab_set, geometry centering.
    Subclasses call super().__init__(parent, title, width, height) then build their UI.
    """

    def __init__(self, parent, title: str, width: int, height: int):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.transient(parent)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.resizable(False, False)
```

- [ ] **Step 3: Verify import**

```bash
.venv/Scripts/python -c "from gui.dialogs._base import BaseDialog; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
rtk git add gui/dialogs/__init__.py gui/dialogs/_base.py && rtk git commit -m "feat(gui/dialogs): add BaseDialog and package skeleton"
```

---

## Task 4 — Migrate `CloneDialog` and `ConfigEditorDialog`

**Files:**
- Create: `gui/dialogs/clone.py`
- Create: `gui/dialogs/config_editor.py`
- Modify: `gui/dialogs/__init__.py`

- [ ] **Step 1: Read source sections in `dialogs.py`**

Read lines 14-177 from `gui/dialogs.py`.

- [ ] **Step 2: Create `gui/dialogs/clone.py`**

Copy `CloneDialog` class (lines 14-107) into the new file. Apply fixes:
- Inherit from `BaseDialog` instead of `ctk.CTkToplevel`
- Remove the 5 boilerplate lines (`transient`, `grab_set`, `geometry`, `lift`, `focus_force`) — handled by `BaseDialog.__init__`
- Replace `500x220` magic string: call `super().__init__(parent, "Clonar Repositorio", 500, 220)`
- Imports: `from gui.dialogs._base import BaseDialog`; `from gui import theme`

Fix SonarQube: `_start_clone` (46 lines) — extract `_build_clone_cmd(url, target_dir)` helper that returns the git command string (pure function, testable).

- [ ] **Step 3: Create `gui/dialogs/config_editor.py`**

Copy `ConfigEditorDialog` (lines 110-177). Apply:
- Inherit from `BaseDialog`
- Replace geometry magic `700x550` with `super().__init__(parent, "Editor de Configuración", 700, 550)`

- [ ] **Step 4: Update `gui/dialogs/__init__.py`**

```python
"""gui.dialogs — public re-exports for all dialog classes."""
from gui.dialogs.clone import CloneDialog
from gui.dialogs.config_editor import ConfigEditorDialog

__all__ = ["CloneDialog", "ConfigEditorDialog"]
```

- [ ] **Step 5: Verify existing imports still work**

```bash
.venv/Scripts/python -c "from gui.dialogs import CloneDialog, ConfigEditorDialog; print('OK')"
```

- [ ] **Step 6: Commit**

```bash
rtk git add gui/dialogs/clone.py gui/dialogs/config_editor.py gui/dialogs/__init__.py
rtk git commit -m "refactor(gui/dialogs): migrate CloneDialog and ConfigEditorDialog to package"
```

---

## Task 5 — Migrate `ProfileDialog` and `ImportOptionsDialog`

**Files:**
- Create: `gui/dialogs/profile.py`
- Modify: `gui/dialogs/__init__.py`

- [ ] **Step 1: Read source section**

Read lines 180-877 from `gui/dialogs.py`.

- [ ] **Step 2: Create `gui/dialogs/profile.py`**

Move both classes. Apply fixes:

**ProfileDialog:**
- Inherit from `BaseDialog`; remove boilerplate lines; replace geometry `800x560`
- `_build_changes_text` (57 lines) — extract `_describe_branch_changes`, `_describe_profile_changes`, `_describe_command_changes` as private helpers (each ~15 lines)

**ImportOptionsDialog:**
- Inherit from `BaseDialog`; replace geometry `820x700`
- Break `__init__` (155 lines) into:
  - `_build_checkboxes_section(frame)` — repo selection checkboxes
  - `_build_java_mappings_section(frame)` — Java version table
  - `_build_preview_section(frame)` — preview textbox
- Break `_apply` (115 lines) into:
  - `_apply_repos(selected_repos)` — applies branch/profile/command per repo
  - `_apply_java_mappings()` — writes Java version mappings
  - `_run_with_progress(steps)` — drives progress bar through a list of callables

- [ ] **Step 3: Update `__init__.py`**

Add:
```python
from gui.dialogs.profile import ProfileDialog, ImportOptionsDialog
```

- [ ] **Step 4: Verify**

```bash
.venv/Scripts/python -c "from gui.dialogs import ProfileDialog, ImportOptionsDialog; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
rtk git add gui/dialogs/profile.py gui/dialogs/__init__.py
rtk git commit -m "refactor(gui/dialogs): migrate ProfileDialog and ImportOptionsDialog"
```

---

## Task 6 — Migrate `SettingsDialog`, `PresetEditorDialog`, `JavaVersionEditorDialog`

**Files:**
- Create: `gui/dialogs/settings.py`
- Modify: `gui/dialogs/__init__.py`

- [ ] **Step 1: Read source section**

Read lines 914-1405 from `gui/dialogs.py`.

- [ ] **Step 2: Create `gui/dialogs/settings.py`**

Move the three classes. Apply fixes:

**SettingsDialog (118-line __init__):**
- Inherit from `BaseDialog`; remove boilerplate; replace geometry `820x680`
- Break `__init__` into:
  - `_build_workspace_section(frame)` — workspace folder row
  - `_build_presets_section(frame)` — DB presets list + buttons
  - `_build_java_section(frame)` — Java version list + buttons
  - `_build_shortcut_section(frame)` — shortcut creation buttons
- `_create_lnk_ctypes` (77 lines) — extract `_build_shell_link_object()` and `_set_link_properties(shell_link, ...)` (each ~30 lines)

**PresetEditorDialog (74-line __init__):**
- Inherit from `BaseDialog`; replace geometry `420x300`
- Extract `_build_fields(frame)` helper

**JavaVersionEditorDialog (58-line __init__):**
- Inherit from `BaseDialog`; replace geometry `420x260`
- Extract `_build_fields(frame)` helper

- [ ] **Step 3: Update `__init__.py`**

```python
from gui.dialogs.settings import SettingsDialog, PresetEditorDialog, JavaVersionEditorDialog
```

- [ ] **Step 4: Verify**

```bash
.venv/Scripts/python -c "from gui.dialogs import SettingsDialog; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
rtk git add gui/dialogs/settings.py gui/dialogs/__init__.py
rtk git commit -m "refactor(gui/dialogs): migrate SettingsDialog, PresetEditorDialog, JavaVersionEditorDialog"
```

---

## Task 7 — Migrate `RepoConfigManagerDialog` and `DockerComposeDialog`

**Files:**
- Create: `gui/dialogs/repo_config_manager.py`
- Create: `gui/dialogs/docker_compose.py`
- Modify: `gui/dialogs/__init__.py`

- [ ] **Step 1: Read source sections**

Read lines 1492-2070 from `gui/dialogs.py`.

- [ ] **Step 2: Create `gui/dialogs/repo_config_manager.py`**

Move `RepoConfigManagerDialog`. Apply:
- Inherit from `BaseDialog`; replace geometry `900x600`
- `_build_ui` (73 lines) → split into `_build_list_panel(frame)`, `_build_editor_panel(frame)`, `_build_action_buttons(frame)`

- [ ] **Step 3: Create `gui/dialogs/docker_compose.py`**

Move `DockerComposeDialog`. Apply:
- Inherit from `BaseDialog`; replace geometry `820x640`
- `_build_ui` (71 lines) → split into `_build_services_list(frame)`, `_build_log_panel(frame)`, `_build_control_buttons(frame)`
- `_build_service_row` (63 lines) → extract `_build_service_checkboxes(row_frame, service)` and `_build_service_buttons(row_frame, service)` helpers

- [ ] **Step 4: Update `__init__.py`** — add both imports and finalize `__all__`

```python
"""gui.dialogs — public dialog classes."""
from gui.dialogs.clone import CloneDialog
from gui.dialogs.config_editor import ConfigEditorDialog
from gui.dialogs.profile import ProfileDialog, ImportOptionsDialog
from gui.dialogs.settings import SettingsDialog, PresetEditorDialog, JavaVersionEditorDialog
from gui.dialogs.repo_config_manager import RepoConfigManagerDialog
from gui.dialogs.docker_compose import DockerComposeDialog

__all__ = [
    "CloneDialog", "ConfigEditorDialog",
    "ProfileDialog", "ImportOptionsDialog",
    "SettingsDialog", "PresetEditorDialog", "JavaVersionEditorDialog",
    "RepoConfigManagerDialog", "DockerComposeDialog",
]
```

- [ ] **Step 5: Verify all dialogs importable**

```bash
.venv/Scripts/python -c "from gui.dialogs import CloneDialog, ProfileDialog, SettingsDialog, RepoConfigManagerDialog, DockerComposeDialog; print('OK')"
```

- [ ] **Step 6: Update all callers of `gui.dialogs`**

Search and replace in `gui/app.py` and `gui/repo_card.py`:
```
from gui.dialogs import ...   # already works via __init__
```
No import changes needed if the old `from gui import dialogs` or `from gui.dialogs import X` patterns are kept consistent.

- [ ] **Step 7: Commit**

```bash
rtk git add gui/dialogs/repo_config_manager.py gui/dialogs/docker_compose.py gui/dialogs/__init__.py
rtk git commit -m "refactor(gui/dialogs): migrate RepoConfigManagerDialog and DockerComposeDialog; finalize package"
```

---

## Task 8 — Delete `gui/dialogs.py` and verify

**Files:**
- Delete: `gui/dialogs.py`
- Modify: any remaining `from gui.dialogs import` or `import gui.dialogs` references

- [ ] **Step 1: Find all imports of old dialogs.py**

```bash
grep -rn "from gui.dialogs" gui/ --include="*.py"
grep -rn "import dialogs" gui/ --include="*.py"
```

- [ ] **Step 2: Confirm all references are satisfied by the new package**

The new `gui/dialogs/__init__.py` re-exports all classes under the same names, so existing `from gui.dialogs import X` statements work unchanged.

- [ ] **Step 3: Delete old file**

```bash
git rm gui/dialogs.py
```

- [ ] **Step 4: Smoke-test application start**

```bash
.venv/Scripts/python -c "import gui.app; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
rtk git commit -m "refactor(gui/dialogs): remove monolithic dialogs.py — fully replaced by package"
```

---

## Task 9 — Create `gui/repo_card/` package skeleton + `_log.py`

**Files:**
- Create: `gui/repo_card/` package
- Create: `gui/repo_card/__init__.py` (stub)
- Create: `gui/repo_card/_log.py`

- [ ] **Step 1: Create package directory**

```bash
mkdir gui/repo_card
```

- [ ] **Step 2: Create `__init__.py` stub**

```python
# Populated in Task 14 after all sub-modules exist
from gui.repo_card._base import RepoCard  # noqa: F401
```

(Leave `_base.py` creation for Task 11 — keep stub comment for now.)

Actually, create it as:
```python
# gui/repo_card/__init__.py — filled after _base.py created in Task 11
```

- [ ] **Step 3: Create `gui/repo_card/_log.py`**

Read lines 491-602 of `gui/repo_card.py` (old file). Extract `_clear_logs`, `_detach_logs`, `_repo_log`, `_flash_log_icon` into a mixin class `LogMixin`.

Apply fixes:
- Replace duplicated textbox insertion code with `insert_log_line()` from `gui.log_helpers`
- Replace magic number `500` with `LOG_MAX_LINES` from `gui.constants`

```python
"""_log.py — Log management mixin for RepoCard."""
from __future__ import annotations
import customtkinter as ctk
import tkinter as tk
import threading
from gui.log_helpers import insert_log_line
from gui.constants import LOG_MAX_LINES
from gui import theme


class LogMixin:
    """Mixin providing _repo_log, _clear_logs, _detach_logs, _flash_log_icon.
    Requires self._log_box, self._log_detached_win, self._detached_log_box,
    self.repo_info to be set by the main RepoCard.__init__.
    """

    def _repo_log(self, text: str, level: str = "INFO") -> None:
        ...  # moved from repo_card.py:542-581

    def _clear_logs(self) -> None:
        ...  # moved from repo_card.py:491-503

    def _detach_logs(self) -> None:
        ...  # moved from repo_card.py:505-540

    def _flash_log_icon(self, icon: str = "📋") -> None:
        ...  # moved from repo_card.py:583-602
```

(Fill with actual code moved from source file.)

- [ ] **Step 4: Verify import**

```bash
.venv/Scripts/python -c "from gui.repo_card._log import LogMixin; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
rtk git add gui/repo_card/__init__.py gui/repo_card/_log.py
rtk git commit -m "feat(gui/repo_card): add package skeleton and LogMixin"
```

---

## Task 10 — Create `gui/repo_card/_git.py`

**Files:**
- Create: `gui/repo_card/_git.py`

- [ ] **Step 1: Read source lines**

Read lines 147-173 and 972-1040 from `gui/repo_card.py` (old monolith).

- [ ] **Step 2: Create `_git.py` mixin**

Extract `_refresh_badge`, `_refresh_badge_loop`, `_refresh_branch`, `_fetch_branches`, `_on_branch_change`, `_detect_port_from_log`, `_detect_status_from_log` into `GitMixin`.

Apply fixes:
- Replace `_GIT_BADGE_SEMAPHORE = threading.Semaphore(3)` module-global with import from `gui.constants` (`GIT_BADGE_SEMAPHORE_COUNT`) and instantiate inside the class: `_GIT_BADGE_SEMAPHORE = threading.Semaphore(GIT_BADGE_SEMAPHORE_COUNT)` as a class variable
- Replace `PORT_REGEXES` usage with import from `gui.constants`
- Replace magic `30000` with `BADGE_REFRESH_MS`

- [ ] **Step 3: Verify import**

```bash
.venv/Scripts/python -c "from gui.repo_card._git import GitMixin; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
rtk git add gui/repo_card/_git.py
rtk git commit -m "feat(gui/repo_card): add GitMixin (_git.py)"
```

---

## Task 11 — Create `gui/repo_card/_config.py`

**Files:**
- Create: `gui/repo_card/_config.py`

- [ ] **Step 1: Read source lines**

Read lines 1041-1216 from `gui/repo_card.py`.

- [ ] **Step 2: Create `_config.py` mixin**

Extract `_resolve_target_file`, `_handle_unselect_config`, `_write_spring_config`, `_apply_config_data`, `_on_config_change`, `_open_config_manager`, `_on_db_change`, `get_config_key` into `ConfigMixin`.

Apply fixes:
- Add `if not preset:` guard in `_on_db_change` before accessing preset dict keys (SonarQube: missing null check)
- Replace `NO_DB_PRESET` inline string with import from `gui.constants`

- [ ] **Step 3: Verify import**

```bash
.venv/Scripts/python -c "from gui.repo_card._config import ConfigMixin; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
rtk git add gui/repo_card/_config.py
rtk git commit -m "feat(gui/repo_card): add ConfigMixin (_config.py)"
```

---

## Task 12 — Create `gui/repo_card/_docker.py`

**Files:**
- Create: `gui/repo_card/_docker.py`

- [ ] **Step 1: Read source lines**

Read lines 1527-1636 from `gui/repo_card.py`.

- [ ] **Step 2: Create `_docker.py` mixin**

Extract `_on_docker_profile_change`, `_update_compose_counts_now`, `_start_compose_status_thread`, `_start_docker_services` into `DockerMixin`.

Apply fixes:
- Replace magic `15` (seconds) with `DOCKER_POLL_MS // 1000` from constants
- `_start_compose_status_thread` (61 lines): extract inner closure body into `_poll_compose_status(event, timeout)` method (reduces nesting depth)

- [ ] **Step 3: Verify import**

```bash
.venv/Scripts/python -c "from gui.repo_card._docker import DockerMixin; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
rtk git add gui/repo_card/_docker.py
rtk git commit -m "feat(gui/repo_card): add DockerMixin (_docker.py)"
```

---

## Task 13 — Create `gui/repo_card/_actions.py`

**Files:**
- Create: `gui/repo_card/_actions.py`

- [ ] **Step 1: Read source lines**

Read lines 1198-1761 from `gui/repo_card.py`.

- [ ] **Step 2: Create `_actions.py` mixin**

Extract `_run_install_cmd`, `_get_start_command`, `_start`, `_start_custom`, `_stop`, `_restart`, `_pull`, `_check_pull_status`, `_clean_repo`, `_seed` into `ActionsMixin`.

Apply SonarQube fixes (most critical):

**`_run_install_cmd` (114 lines):**
- Extract `_build_install_env(repo_info)` → returns env dict (20 lines)
- Extract `_stream_process_output(proc, log_fn)` → reads stdout line-by-line (15 lines)
- Extract `_on_install_complete(success)` → updates button + status (15 lines)
- Remaining `_run_install_cmd` becomes ~40 lines (orchestrator only)

**`_start` (103 lines):**
- Extract `_prepare_start_env(config_entry)` → returns env dict (20 lines)
- Extract `_on_service_ready(port)` → status + UI update on ready detection (15 lines)
- Extract `_stream_start_output(proc, ready_event, config_entry)` → reads stdout, detects ready/port (30 lines)
- Remaining `_start` becomes ~35 lines

- [ ] **Step 3: Verify import**

```bash
.venv/Scripts/python -c "from gui.repo_card._actions import ActionsMixin; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
rtk git add gui/repo_card/_actions.py
rtk git commit -m "feat(gui/repo_card): add ActionsMixin (_actions.py) with extracted sub-methods"
```

---

## Task 14 — Create `gui/repo_card/_header.py` and `_expand_panel.py`

**Files:**
- Create: `gui/repo_card/_header.py`
- Create: `gui/repo_card/_expand_panel.py`

- [ ] **Step 1: Read source UI building sections**

Read lines 190-953 from `gui/repo_card.py`.

- [ ] **Step 2: Create `_header.py`**

Extract `_build_ui`, `_build_header`, `_update_button_visibility`, `_update_header_hints` into `HeaderMixin`.

Apply fix: `_build_header` (115 lines) → extract `_build_header_left(frame)` (checkbox + name label) and `_build_header_right(frame)` (status + buttons) — each ~40 lines.

- [ ] **Step 3: Create `_expand_panel.py`**

Extract `_build_expand_panel`, `_build_log_row`, `_build_branch_row`, `_build_install_btn`, `_build_selector_row`, `_build_command_row`, `_build_docker_row`, `_toggle_expand`, `_update_status`, `_on_status_change`, `_show_file_selector`, `_edit_config`, `_get_config_files` into `ExpandPanelMixin`.

Apply fix: `_build_selector_row` (144 lines) → extract:
- `_build_config_combo_section(frame)` — config profile selector (~40 lines)
- `_build_db_combo_section(frame)` — DB preset selector (~35 lines)
- `_build_java_combo_section(frame)` — Java version selector (~30 lines)
- Remaining `_build_selector_row` calls these 3 helpers (~15 lines)

- [ ] **Step 4: Verify imports**

```bash
.venv/Scripts/python -c "from gui.repo_card._header import HeaderMixin; from gui.repo_card._expand_panel import ExpandPanelMixin; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
rtk git add gui/repo_card/_header.py gui/repo_card/_expand_panel.py
rtk git commit -m "feat(gui/repo_card): add HeaderMixin and ExpandPanelMixin"
```

---

## Task 15 — Create `gui/repo_card/_base.py` (main `RepoCard` class)

**Files:**
- Create: `gui/repo_card/_base.py`
- Modify: `gui/repo_card/__init__.py`

- [ ] **Step 1: Create `_base.py`**

`RepoCard` now simply inherits all mixins and keeps only `__init__`, `destroy`, and the public API getters/setters (lines 1837-2012 of old file):

```python
"""_base.py — RepoCard composed from focused mixins."""
import customtkinter as ctk
import threading

from gui.repo_card._log import LogMixin
from gui.repo_card._git import GitMixin
from gui.repo_card._config import ConfigMixin
from gui.repo_card._docker import DockerMixin
from gui.repo_card._actions import ActionsMixin
from gui.repo_card._header import HeaderMixin
from gui.repo_card._expand_panel import ExpandPanelMixin
from gui.constants import (
    NO_DB_PRESET, BADGE_REFRESH_MS, GIT_BADGE_SEMAPHORE_COUNT
)


class RepoCard(
    HeaderMixin,
    ExpandPanelMixin,
    LogMixin,
    GitMixin,
    ConfigMixin,
    DockerMixin,
    ActionsMixin,
    ctk.CTkFrame,
):
    """Accordion repo card — collapsed bar + expandable details.

    All logic is in focused mixins; this class owns __init__, destroy,
    and the public getter/setter API.
    """

    _GIT_BADGE_SEMAPHORE = threading.Semaphore(GIT_BADGE_SEMAPHORE_COUNT)

    def __init__(self, parent, repo_info, service_launcher, ...):
        # Initialize CTkFrame first, then mixins if needed
        ctk.CTkFrame.__init__(self, parent, ...)
        # Set all instance variables (moved from old __init__)
        ...
        self._build_ui()
        self._start_badge_refresh()

    def destroy(self):
        ...  # cleanup (moved from old lines 98-117)

    # ── Public getters ────────────────────────────────────────────
    def is_selected(self): ...
    def get_custom_command(self): ...
    def get_current_profile(self): ...
    def get_branch(self): ...
    def get_name(self): ...
    def get_repo_info(self): ...
    def get_docker_compose_active(self): ...
    def get_docker_profile_services(self): ...
    def get_status(self): ...

    # ── Public setters ────────────────────────────────────────────
    def set_selected(self, value): ...
    def set_branch(self, branch): ...
    def set_db_preset(self, preset): ...
    def set_profile(self, profile_name): ...
    def set_custom_command(self, cmd): ...
    def set_docker_profile_services(self, services): ...
    def set_docker_compose_active(self, active): ...
    def update_java_versions(self, versions): ...

    # ── Public actions ────────────────────────────────────────────
    def do_pull(self): ...
    def do_start(self): ...
    def do_stop(self): ...
```

- [ ] **Step 2: Update `gui/repo_card/__init__.py`**

```python
"""gui.repo_card — public API for the RepoCard widget."""
from gui.repo_card._base import RepoCard  # noqa: F401

__all__ = ["RepoCard"]
```

- [ ] **Step 3: Verify**

```bash
.venv/Scripts/python -c "from gui.repo_card import RepoCard; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
rtk git add gui/repo_card/_base.py gui/repo_card/__init__.py
rtk git commit -m "refactor(gui/repo_card): compose RepoCard from mixins in _base.py"
```

---

## Task 16 — Delete old `gui/repo_card.py` and wire up `app.py`

**Files:**
- Delete: `gui/repo_card.py`
- Modify: `gui/app.py` (update imports)

- [ ] **Step 1: Find all imports of old repo_card.py**

```bash
grep -rn "from gui.repo_card import\|from gui import repo_card\|import repo_card" --include="*.py" .
```

- [ ] **Step 2: Update `gui/app.py` imports**

`from gui.repo_card import RepoCard` — unchanged (package now provides this).

- [ ] **Step 3: Delete old file**

```bash
git rm gui/repo_card.py
```

- [ ] **Step 4: Full smoke test**

```bash
.venv/Scripts/python -c "
from gui.app import DevOpsManagerApp
print('All imports OK')
"
```

- [ ] **Step 5: Commit**

```bash
rtk git commit -m "refactor(gui): remove monolithic repo_card.py — fully replaced by package"
```

---

## Task 17 — Extract `ProfileManagerMixin` from `app.py`

**Files:**
- Create: `gui/app_profile.py`
- Modify: `gui/app.py`

- [ ] **Step 1: Read profile section**

Read lines 476-662 from `gui/app.py`.

- [ ] **Step 2: Create `gui/app_profile.py`**

Extract `_refresh_profile_dropdown`, `_load_initial_profile_data`, `_on_profile_dropdown_change`, `_save_current_profile`, `_check_profile_changes`, `_set_profile_combo_dirty`, `_do_check_profile_changes`, `_detect_unsaved_profile_changes`, `_apply_config`, `_apply_config_to_card` into `ProfileManagerMixin`.

Apply fixes:
- Replace hardcoded color hex in `_set_profile_combo_dirty` with `theme.C.*` constant
- Replace `NO_PROFILE_TEXT` string with import from `gui.constants`
- Replace `PROFILE_DIRTY_SUFFIX` ` *` string with constant from `gui.constants`

- [ ] **Step 3: Modify `app.py`**

```python
from gui.app_profile import ProfileManagerMixin

class DevOpsManagerApp(ProfileManagerMixin, ctk.CTk):
    ...
```
Remove the extracted methods from `app.py`.

- [ ] **Step 4: Verify**

```bash
.venv/Scripts/python -c "from gui.app import DevOpsManagerApp; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
rtk git add gui/app_profile.py gui/app.py
rtk git commit -m "refactor(gui/app): extract ProfileManagerMixin to app_profile.py"
```

---

## Task 18 — Final Verification

- [ ] **Step 1: Verify all new files are under 300 lines**

```bash
wc -l gui/constants.py gui/log_helpers.py gui/app_profile.py \
  gui/repo_card/*.py gui/dialogs/*.py
```

Any file > 300 lines needs further splitting — re-apply the relevant task.

- [ ] **Step 2: Verify no SonarQube-flagged patterns remain**

Check for methods > 50 lines:
```bash
grep -n "def " gui/repo_card/_actions.py gui/repo_card/_expand_panel.py | head -40
```
Manually verify the extracted methods are each ≤ 50 lines.

- [ ] **Step 3: Verify no magic strings remain in GUI files**

```bash
grep -rn '"- Ninguna\|NO_DB_PRESET\|30000\|15000\|LOG_MAX_LINES" ' gui/ --include="*.py"
```
Expected: only appear in `gui/constants.py`.

- [ ] **Step 4: Run application**

```bash
.venv/Scripts/python main.py
```
Expected: application window opens, no import errors.

- [ ] **Step 5: Final commit**

```bash
rtk git add -A
rtk git commit -m "refactor(gui): complete GUI refactor — split into focused modules, fix SonarQube issues"
```

---

## Summary of SonarQube Issues Resolved

| Issue | Where | Fix |
|-------|-------|-----|
| Method > 50 lines | `_run_install_cmd` (114L), `_start` (103L), `_build_selector_row` (144L), `ImportOptionsDialog.__init__` (155L), `_apply` (115L), `SettingsDialog.__init__` (118L), `_build_changes_text` (57L) | Extracted sub-methods in Tasks 13–14, 5–6 |
| Duplicated log insertion | 3 locations | Unified via `insert_log_line()` in Task 2 |
| Magic strings | 50+ occurrences | Centralised in `gui/constants.py` in Task 1 |
| No base dialog class | 9 dialogs with 5 repeated lines each | `BaseDialog` in Task 3 |
| Missing null check | `_on_db_change` | Added in Task 11 |
| Module-level mutable global semaphore | `_GIT_BADGE_SEMAPHORE` | Moved to class variable in Task 15 |
| Long parameter lists | `ProfileDialog.__init__` (8 params) | Unchanged (acceptable for dialogs — flagged for awareness) |
| Silent error on profile import | `_import_profile` | Add `try/except json.JSONDecodeError` with user-visible error in Task 5 |
