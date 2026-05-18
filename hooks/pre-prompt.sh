#!/usr/bin/env bash
# Cross-platform hook entry — delegates to Python runner.
# Works on Mac, Linux, Windows (via Git Bash / WSL).
set -e

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Pick venv Python — Unix layout first, then Windows layout (Git Bash)
if [ -x "$PLUGIN_DIR/.venv/bin/python" ]; then
  PY="$PLUGIN_DIR/.venv/bin/python"
elif [ -x "$PLUGIN_DIR/.venv/Scripts/python.exe" ]; then
  PY="$PLUGIN_DIR/.venv/Scripts/python.exe"
else
  PY="${ANONYMIZE_PYTHON:-python3}"
fi

"$PY" "$PLUGIN_DIR/scripts/hook_runner.py"
