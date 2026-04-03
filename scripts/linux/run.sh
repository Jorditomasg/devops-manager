#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
PYTHON="$ROOT_DIR/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "Virtual environment not found. Please run './install.sh' first."
    exit 1
fi

# If stdout is a terminal the user launched from a shell — stay attached.
# Otherwise (file manager, desktop shortcut) detach silently.
if [ -t 1 ]; then
    exec "$PYTHON" "$ROOT_DIR/main.py" "$@"
else
    nohup "$PYTHON" "$ROOT_DIR/main.py" "$@" > /dev/null 2>&1 &
fi
