#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  build_dmg.sh — Build Iris.app and Iris.dmg
#
#  Usage:
#    bash Build/build_dmg.sh          # from the project root, or anywhere
#
#  Output:
#    dist/Iris.app   — standalone macOS application (no Python/venv needed)
#    dist/Iris.dmg   — drag-to-install disk image
#
#  Requirements (auto-installed if missing):
#    pyinstaller, Pillow (in requirements.txt); create-dmg (Homebrew, optional —
#    falls back to hdiutil).
#
#  NOTE (case-insensitive macOS): PyInstaller's default work dir is ./build,
#  which COLLIDES with this repo's source `Build/` folder (build === Build).
#  Cleaning ./build would therefore delete Build/ (this script + parallaxctl.py).
#  We deliberately use a non-colliding work dir, $ROOT/.pyi_work, instead — do
#  NOT change BUILD_DIR back to "build". For the same reason, do NOT run a bare
#  `pyinstaller Iris.spec` from the repo root (its default ./build work dir would
#  hit the same collision); always build through this script.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# build_dmg.sh lives in Build/; the project root (venv, launcher.py, assets, …)
# is one level up. Run the whole build from the project root.
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PYTHON="$VENV/bin/python3"

APP_NAME="Iris"
ENTRY="launcher.py"
VERSION="1.1"
BUNDLE_ID="com.iris.parallaxwall"   # stable so macOS TCC remembers the camera grant across rebuilds
DIST_DIR="$ROOT/dist"
BUILD_DIR="$ROOT/.pyi_work"     # NOT "build" — see header note (case-insensitive FS)

# ── Colour output ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
die()  { echo -e "${RED}✗${NC} $*"; exit 1; }

echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   👁  Building Iris v${VERSION}"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Verify venv ────────────────────────────────────────────────────────────
[ -x "$PYTHON" ] || die "No venv python at $PYTHON — set up the venv first."
ok "Python venv found"

# ── 2. Ensure PyInstaller (invoke as a module — the venv's console-script
#       shebangs hardcode the venv's original path, so $VENV/bin/pyinstaller can
#       have a bad interpreter line after the project was renamed). ────────────
if ! "$PYTHON" -c "import PyInstaller" 2>/dev/null; then
    echo "  Installing PyInstaller…"
    "$PYTHON" -m pip install --quiet pyinstaller
fi
ok "PyInstaller ready"

# ── 3. Convert icon (PNG → ICNS) if needed ────────────────────────────────────
ICON_PNG="$ROOT/assets/icon/earth_icon.png"
ICON_ICNS="$ROOT/assets/icon/Iris.icns"

if [ -f "$ICON_PNG" ] && [ ! -f "$ICON_ICNS" ]; then
    echo "  Converting icon PNG → ICNS…"
    ICONSET="$ROOT/assets/icon/Iris.iconset"
    mkdir -p "$ICONSET"
    for SIZE in 16 32 64 128 256 512; do
        sips -z $SIZE $SIZE "$ICON_PNG" \
             --out "$ICONSET/icon_${SIZE}x${SIZE}.png" >/dev/null 2>&1
        sips -z $((SIZE*2)) $((SIZE*2)) "$ICON_PNG" \
             --out "$ICONSET/icon_${SIZE}x${SIZE}@2x.png" >/dev/null 2>&1
    done
    iconutil -c icns "$ICONSET" -o "$ICON_ICNS" 2>/dev/null
    rm -rf "$ICONSET"
    ok "Icon converted"
elif [ -f "$ICON_ICNS" ]; then
    ok "Icon already exists"
else
    warn "No icon PNG found — building without icon"
    ICON_ICNS=""
fi

# ── 4. Clean old build artifacts (safe work dir — never touches Build/) ───────
rm -rf "$DIST_DIR/$APP_NAME.app" "$BUILD_DIR"
ok "Cleaned old build artifacts"

# ── 5. PyInstaller build ──────────────────────────────────────────────────────
#  NOTE (camera permission): the objc/Foundation/AVFoundation hidden-import +
#  collect-all flags below are REQUIRED, not optional. Tracking/face_tracker.py's
#  _request_camera_permission() imports AVFoundation/Foundation lazily inside a
#  try/except, so PyInstaller's static analysis never sees them and its pyobjc
#  hooks never fire — only the compiled .so cores get bundled, WITHOUT each
#  package's pure-Python __init__.py. Then `from AVFoundation import …` raises
#  ImportError in the frozen .app, the helper returns False, the macOS TCC
#  dialog never appears, and head tracking never starts. collect-all bundles the
#  full packages so the import (and the prompt) works. Do NOT remove these.
echo ""
echo "  Building $APP_NAME.app with PyInstaller…"
echo "  (This takes ~2–3 minutes on first run)"
echo ""

# Use an array so paths containing spaces (e.g. "…/IRIS APP/…") survive intact.
ICON_ARGS=()
[ -n "$ICON_ICNS" ] && [ -f "$ICON_ICNS" ] && ICON_ARGS=(--icon "$ICON_ICNS")

"$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --osx-bundle-identifier "$BUNDLE_ID" \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR" \
    --specpath "$BUILD_DIR" \
    "${ICON_ARGS[@]}" \
    \
    --add-data "$ROOT/assets:assets" \
    --add-data "$ROOT/worlds:worlds" \
    --add-data "$ROOT/shaders:shaders" \
    --add-data "$ROOT/models:models" \
    \
    --hidden-import "UI.demo_overlay" \
    --hidden-import "Worlds.world_runtime" \
    --hidden-import "Worlds.world_loader" \
    --hidden-import "mediapipe" \
    --hidden-import "mediapipe.python.solutions" \
    --hidden-import "mediapipe.tasks.python" \
    --hidden-import "mediapipe.tasks.python.vision" \
    --hidden-import "OpenGL" \
    --hidden-import "OpenGL.GL" \
    --hidden-import "OpenGL.GLU" \
    --hidden-import "pygame" \
    --hidden-import "cv2" \
    --hidden-import "objc" \
    --hidden-import "Foundation" \
    --hidden-import "AVFoundation" \
    \
    --collect-all "mediapipe" \
    --collect-all "pygame" \
    --collect-all "objc" \
    --collect-all "Foundation" \
    --collect-all "AVFoundation" \
    \
    "$ENTRY"

ok "PyInstaller build complete"

# ── 6. Verify .app was created ────────────────────────────────────────────────
APP_PATH="$DIST_DIR/$APP_NAME.app"
[ -d "$APP_PATH" ] || die ".app not found after build — check PyInstaller output above"
ok "$APP_NAME.app created at $APP_PATH"

# ── 7. Write Info.plist metadata ──────────────────────────────────────────────
PLIST="$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $APP_NAME"    "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST" 2>/dev/null || true
# CFBundleVersion: Add if absent (PyInstaller omits it), else Set — a bare Set
# silently no-ops when the key doesn't exist (left it blank in v1.1).
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION"        "$PLIST" 2>/dev/null || true
# Required for camera access on macOS
/usr/libexec/PlistBuddy -c \
    "Add :NSCameraUsageDescription string 'Iris uses your camera to track head position for the spatial desktop illusion. No video is stored or transmitted.'" \
    "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c \
    "Set :NSCameraUsageDescription 'Iris uses your camera to track head position for the spatial desktop illusion. No video is stored or transmitted.'" \
    "$PLIST" 2>/dev/null || true
ok "Info.plist patched"

# ── 7b. Re-sign the bundle (CRITICAL — must come AFTER the Info.plist edits) ───
# PyInstaller ad-hoc-signs the bundle during step 5, but step 7 above rewrites
# Info.plist (version + NSCameraUsageDescription) AFTERWARD, which INVALIDATES that
# signature: `codesign --verify` then reports
#   "invalid Info.plist (plist or signature have been modified)".
# macOS TCC SILENTLY DENIES camera (and mic) access to an app whose code signature
# is invalid — no permission dialog ever appears, the request is auto-denied
# (NotDetermined → denied in ~50 ms), and head tracking never starts. That was the
# real cause of "Live status on, but no tracking". Re-sign the whole bundle ad-hoc
# now that every Info.plist edit is done, so the seal is valid and the TCC prompt
# can actually appear. Then VERIFY and fail loudly so this can never silently
# regress again.
echo ""
echo "  Re-signing app bundle (ad-hoc) after Info.plist edits…"
codesign --force --deep --sign - "$APP_PATH" || die "codesign failed — TCC will deny the camera"
if codesign --verify --deep --strict --verbose=2 "$APP_PATH" 2>/dev/null; then
    ok "Code signature valid (TCC camera prompt can appear)"
else
    die "Code signature STILL invalid after re-sign — the camera prompt would be auto-denied"
fi

# ── 8. Build DMG ──────────────────────────────────────────────────────────────
DMG_PATH="$DIST_DIR/$APP_NAME-$VERSION.dmg"
rm -f "$DMG_PATH" "$DIST_DIR/$APP_NAME.dmg"

echo ""
echo "  Building DMG…"

# Stage a clean folder containing ONLY the .app (so the DMG doesn't pick up the
# onedir build, old DMGs, or .DS_Store from dist/).
STAGE="$BUILD_DIR/dmg_stage"
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -R "$APP_PATH" "$STAGE/"

if command -v create-dmg &>/dev/null; then
    create-dmg \
        --volname "$APP_NAME" \
        --window-pos 200 120 \
        --window-size 560 340 \
        --icon-size 100 \
        --icon "$APP_NAME.app" 140 170 \
        --hide-extension "$APP_NAME.app" \
        --app-drop-link 420 170 \
        --no-internet-enable \
        "$DMG_PATH" \
        "$STAGE" \
    || hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG_PATH"
else
    warn "create-dmg not found — using hdiutil (no drag-to-install UI)."
    hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG_PATH"
fi
rm -rf "$STAGE"

ok "DMG created at $DMG_PATH"

# ── 9. Summary ────────────────────────────────────────────────────────────────
DMG_SIZE=$(du -sh "$DMG_PATH" 2>/dev/null | cut -f1)
APP_SIZE=$(du -sh "$APP_PATH" 2>/dev/null | cut -f1)

echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   ✅  Build complete!"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   App:  $APP_PATH  ($APP_SIZE)"
echo "   DMG:  $DMG_PATH  ($DMG_SIZE)"
echo ""
