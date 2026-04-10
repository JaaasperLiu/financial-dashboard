#!/usr/bin/env bash
# Launcher for the Financial Dashboard.
#
# On first run this script creates a virtual environment in .venv/ and
# installs dependencies from requirements.txt. On subsequent runs it
# reuses the venv and only reinstalls if requirements.txt has changed
# since the last install. Then it launches the app.
#
# Usage:
#   ./run.sh

set -euo pipefail

# Resolve the repo root from this script's location so it works no matter
# where the user invokes it from (cwd, Finder, Spotlight, etc.).
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VENV_DIR=".venv"
STAMP="$VENV_DIR/.requirements.sha256"

# Pick a python3 interpreter. Prefer python3, fall back to python.
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "error: no python3 interpreter found on PATH" >&2
    echo "install Python 3.10+ from https://www.python.org/downloads/" >&2
    exit 1
fi

# Create the venv on first run.
if [ ! -d "$VENV_DIR" ]; then
    echo "[run.sh] creating virtual environment in $VENV_DIR ..."
    "$PY" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"

# (Re)install dependencies if requirements.txt has changed since the last
# successful install. We fingerprint requirements.txt and compare.
CURRENT_HASH="$(shasum -a 256 requirements.txt | awk '{print $1}')"
STORED_HASH=""
if [ -f "$STAMP" ]; then
    STORED_HASH="$(cat "$STAMP")"
fi

if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
    echo "[run.sh] installing dependencies (requirements.txt changed) ..."
    "$VENV_PY" -m pip install --upgrade pip >/dev/null
    "$VENV_PY" -m pip install -r requirements.txt
    echo "$CURRENT_HASH" > "$STAMP"
fi

# Hand off to the app. `exec` replaces this shell so Ctrl-C goes straight
# to Python and the process tree stays tidy.
exec "$VENV_PY" main.py "$@"
