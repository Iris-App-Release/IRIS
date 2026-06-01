#!/bin/bash
# hotswap.sh — Sync changed assets/shaders/worlds into the existing Iris.app
#              and re-sign it.  ~5 seconds vs ~3 minutes for a full rebuild.
#
# Use this when you need to test changes inside the REAL signed app —
# camera head tracking, wallpaper/desktop mode, TCC permission flow, etc.
#
# What CAN be hot-swapped (stored as plain files in the bundle):
#   assets/     textures, images
#   shaders/    GLSL files
#   worlds/     world JSON files
#
# What CANNOT be hot-swapped (compiled into the Iris binary by PyInstaller):
#   Python source files  →  use preview.sh to iterate, full build to ship
#
# Usage:
#   ./hotswap.sh              # sync assets + shaders + worlds, re-sign
#   ./hotswap.sh --launch     # also open the app after swapping
#
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

APP="dist/Iris.app"
RESC="$APP/Contents/Resources"

[ -d "$APP" ] || {
    echo "✗  No dist/Iris.app found. Run Build/build_dmg.sh at least once first."
    exit 1
}

echo "[hotswap] Syncing assets/ …"
rsync -a --delete assets/ "$RESC/assets/"

echo "[hotswap] Syncing shaders/ …"
rsync -a --delete shaders/ "$RESC/shaders/"

echo "[hotswap] Syncing worlds/ …"
rsync -a --delete worlds/ "$RESC/worlds/"

echo "[hotswap] Re-signing (required after any bundle modification)…"
codesign --force --deep --sign - "$APP"

if codesign --verify --deep --strict "$APP" 2>/dev/null; then
    echo "✓  Signature valid."
else
    echo "✗  Code signature failed — camera TCC will auto-deny. Check codesign output."
    exit 1
fi

echo ""
echo "✓  Hot-swap complete. dist/Iris.app is ready."

if [ "${1:-}" = "--launch" ]; then
    echo "[hotswap] Launching dist/Iris.app…"
    open "$APP"
fi
