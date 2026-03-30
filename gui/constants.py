"""Shared constants for the GUI layer."""

# ── Combo / label sentinel values ──────────────────────────────
PROFILE_DIRTY_SUFFIX = " *"

# ── Event bindings ──────────────────────────────────────────────
BTN_CLICK          = "<Button-1>"

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

# ── Port detection fallback (used when repo type defines no port_patterns) ──
PORT_PATTERNS_FALLBACK = [
    r"http://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):(\d+)",
    r"(?:listening on|bound to).*?port\s+(\d+)",
]

