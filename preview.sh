#!/bin/bash
# preview.sh — Run Iris from source for fast dev iteration.
#
# No rebuild needed. Changes to Python source, shaders, and assets are live
# immediately — just re-run this script. Starts in a windowed demo with
# scripted head motion so all rendering and world logic is exercised.
#
# Usage:
#   ./preview.sh                  # opens whatever world is in preferences
#   ./preview.sh earth            # force-switch to Earth before launch
#   ./preview.sh the_watcher      # force-switch to The Watcher before launch
#
# What works:    full rendering, parallax, zoom, rotation, eye tracking
#                (scripted hx/hy), world switching, texture & shader changes
# What doesn't:  live camera head tracking, wallpaper/desktop mode
#                (both require a signed .app bundle — use dist/Iris.app for those)
#
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON=".venv/bin/python3"
[ -x "$PYTHON" ] || { echo "✗  No venv at .venv — set up the venv first"; exit 1; }

# Optional world pre-select
if [ "${1:-}" != "" ]; then
    WORLD="$1"
    PREF_DIR="$HOME/.iris"
    mkdir -p "$PREF_DIR"
    # Preserve any other keys that might be in preferences.json
    if [ -f "$PREF_DIR/preferences.json" ]; then
        "$PYTHON" -c "
import json, sys
p = json.load(open('$PREF_DIR/preferences.json'))
p['world'] = '$WORLD'
json.dump(p, open('$PREF_DIR/preferences.json', 'w'))
" 2>/dev/null || echo '{"world":"'"$WORLD"'"}' > "$PREF_DIR/preferences.json"
    else
        echo '{"world":"'"$WORLD"'"}' > "$PREF_DIR/preferences.json"
    fi
    echo "[preview] World → $WORLD"
fi

echo "[preview] Launching from source (demo window, scripted head)…"
echo "[preview] Camera/wallpaper not available in source mode — use ./hotswap.sh for that."
echo ""

PARALLAX_MODE=demo "$PYTHON" launcher.py
