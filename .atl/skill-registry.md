# Skill Registry — devops-manager

Generated: 2026-04-08
Project: devops-manager

## User Skills

| Name | Trigger | Source |
|------|---------|--------|
| judgment-day | When user says "judgment day", "judgment-day", "review adversarial", "dual review", "doble review", "juzgar", "que lo juzguen" | ~/.claude/skills/judgment-day/SKILL.md |
| go-testing | When writing Go tests, using teatest, or adding test coverage | ~/.claude/skills/go-testing/SKILL.md |
| skill-creator | When user asks to create a new skill, add agent instructions, or document patterns for AI | ~/.claude/skills/skill-creator/SKILL.md |
| sdd-apply | When the orchestrator launches you to implement one or more tasks from a change | ~/.claude/skills/sdd-apply/SKILL.md |
| sdd-archive | When the orchestrator launches you to archive a change after implementation and verification | ~/.claude/skills/sdd-archive/SKILL.md |
| sdd-design | When the orchestrator launches you to write or update the technical design for a change | ~/.claude/skills/sdd-design/SKILL.md |
| sdd-explore | When the orchestrator launches you to think through a feature, investigate the codebase, or clarify requirements | ~/.claude/skills/sdd-explore/SKILL.md |
| sdd-init | When user wants to initialize SDD in a project, or says "sdd init", "iniciar sdd" | ~/.claude/skills/sdd-init/SKILL.md |
| sdd-onboard | When the orchestrator launches you to onboard a user through the full SDD cycle | ~/.claude/skills/sdd-onboard/SKILL.md |
| sdd-propose | When the orchestrator launches you to create or update a proposal for a change | ~/.claude/skills/sdd-propose/SKILL.md |
| sdd-spec | When the orchestrator launches you to write or update specs for a change | ~/.claude/skills/sdd-spec/SKILL.md |
| sdd-tasks | When the orchestrator launches you to create or update the task breakdown for a change | ~/.claude/skills/sdd-tasks/SKILL.md |
| sdd-verify | When the orchestrator launches you to verify a completed (or partially completed) change | ~/.claude/skills/sdd-verify/SKILL.md |

## Project Conventions

| File | Purpose |
|------|---------|
| CLAUDE.md | Project architecture, conventions, performance-critical patterns, GUI structure, key design decisions |

## Compact Rules (for sub-agent injection)

### Python / customtkinter GUI
- Architecture: Layered DDD — domain/, application/, infrastructure/, core/, gui/
- GUI: customtkinter widgets; all colors/fonts via `gui/theme.py` API — NO hardcoded hex/tuples
- Buttons: always use `**theme.btn_style("variant")` — do NOT add explicit `font=` argument (duplicate-keyword error)
- User strings: ALL via `t("key")` from `core/i18n.py` — NEVER hardcode in Python; add keys to both config/translations/*.yml
- Constants: timing, regex, event-binding strings → `gui/constants.py`; NEVER hardcode intervals like `30000`
- Lazy expand panel: `_build_expand_panel()` is NOT called in `__init__`; guard widget access with `hasattr(self, '_widget_name')`
- Config cache: reads via `_load_config_cached()`; saves must call `_invalidate_config_cache(config_path)` after write
- Event bus: cross-layer communication via `domain/ports/event_bus.py` (pub/sub singleton)
- New repo type: add YAML to `config/repo_types/` — no Python changes needed
- Profile apply: set `_applying_profile = True` during loop; never call `_do_check_profile_changes()` from card code directly
- Git badge semaphore: class-level `_GIT_BADGE_SEMAPHORE` (value 3) — do NOT lower badge interval (30s) or Docker poll (15s)
