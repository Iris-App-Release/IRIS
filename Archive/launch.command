#!/bin/bash
# Parallax Wall — double-clickable launcher.
# Creates / updates the project venv as needed, then runs main.py.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
MAIN="$SCRIPT_DIR/main.py"
REQS="$SCRIPT_DIR/requirements.txt"

cd "$SCRIPT_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Parallax Wall"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Pick the best available Python (3.11 strongly preferred for mediapipe wheels)
PYTHON=""
for c in \
    /opt/homebrew/opt/python@3.11/bin/python3.11 \
    /opt/homebrew/bin/python3.11 \
    /usr/local/bin/python3.11 \
    python3.11 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    python3 ; do
    if command -v "$c" &>/dev/null; then
        PYTHON="$c"
        break
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "ERROR: Python 3.9+ not found. Install via: brew install python@3.11"
    read -r -p "Press ENTER to close…"
    exit 1
fi
echo "  Python: $($PYTHON --version) at $PYTHON"

# Create the venv on first run
if [[ ! -x "$VENV/bin/python" ]]; then
    echo "  Creating virtual environment…"
    "$PYTHON" -m venv "$VENV"
fi

VPY="$VENV/bin/python"
VPIP="$VENV/bin/pip"
STAMP="$VENV/.parallax_setup_done"

# First-time setup — skip on subsequent launches for instant startup.
# We don't fail-fast on the optional macOS framework installs; missing
# pyobjc bits just disable the desktop-wallpaper level (main + tracker
# fall back gracefully).
if [[ ! -f "$STAMP" ]] || [[ "$REQS" -nt "$STAMP" ]]; then
    echo "  First-time setup — installing dependencies…"
    "$VPY" -m pip install --upgrade pip --quiet || true
    if "$VPIP" install -r "$REQS" --quiet ; then
        touch "$STAMP"
        echo "  Dependencies installed."
    else
        echo
        echo "  ! pip install hit a problem. Retrying without --quiet:"
        "$VPIP" install -r "$REQS" || true
        # Verify the core deps actually imported — pyobjc frameworks are optional
        if "$VPY" -c "import pygame, OpenGL.GL, numpy, cv2, mediapipe" 2>/dev/null; then
            touch "$STAMP"
            echo "  Core dependencies present — continuing despite warnings."
        else
            echo
            echo "  Could not install core dependencies. Please check the errors above."
            read -r -p "Press ENTER to close…"
            exit 1
        fi
    fi
fi

echo "  Launching…"
echo
exec "$VPY" "$MAIN"
