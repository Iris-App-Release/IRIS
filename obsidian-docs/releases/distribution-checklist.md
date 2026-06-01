---
title: Distribution Checklist
type: release
related: [dmg-build-process, version-history, head-tracking, ui-overlay, asset-pipeline, constraints, productification]
last_updated: 2026-05-31
sources: [Build/build_dmg.sh, Docs/FIRST_LAUNCH_AND_DMG_DESIGN.md, Docs/IRIS_OVERVIEW.txt, Iris.spec]
---

# Distribution Checklist

Steps to cut and ship a new IRIS build. See [[dmg-build-process]] for the
mechanics of the build script itself.

## 1. Prepare

- [ ] Regenerate any procedural assets that changed (`gen_eye_textures.py`,
      `gen_space_background.py`, `make_earth_icon.py` — see [[asset-pipeline]]).
- [ ] Confirm `models/face_landmarker.task` is present (it's the asset most
      likely to be missed; without it, tracking silently degrades to the Haar
      fallback — see [[head-tracking]]).
- [ ] Run the headless sims — `Scripts/validation/sim_*.py` should all exit 0
      ([[headless-simulation]]) — to confirm the frozen physics is intact.
- [ ] Bump `VERSION` in `Build/build_dmg.sh` (this names the DMG and the plist
      version).
- [ ] Install `create-dmg` for the styled installer window
      (`brew install create-dmg`); otherwise the build falls back to a plain
      `hdiutil` list view.

## 2. Build

- [ ] `bash Build/build_dmg.sh` (never a bare `pyinstaller Iris.spec` — the
      case-insensitive `./build` collision; see [[dmg-build-process]]).
- [ ] Build with little else running — it's RAM-heavy on 8 GB and takes ~2–3 min
      ([[constraints]]).

## 3. Verify the bundle (must be done in the GUI session)

The macOS camera (TCC) prompt only appears for a properly bundled `.app`
launched from the GUI — never from a bare `python` in a background shell. So
these checks must run in the user's desktop session:

- [ ] Double-click `dist/Iris.app` → the `demo` window opens with the live Earth
      breathing (scripted idle), glass HUD on top ([[ui-overlay]]).
- [ ] "Enable Camera" → the real macOS camera-permission dialog appears (proves
      `NSCameraUsageDescription` + the stable bundle id are in place).
- [ ] After granting, head motion drives the parallax live.
- [ ] "Enable Desktop Mode" → the window becomes a click-through desktop-level
      wallpaper; the Earth keeps tracking ([[engine-loop-and-daemon]]).
- [ ] Browse Worlds → switching to [[the-watcher]] works live.
- [ ] Reopen the app → it goes straight to the control surface, not a fresh
      onboarding.

## 4. Distribute

From `Docs/IRIS_OVERVIEW.txt`, the intended channels:

- [ ] **Discord / AirDrop** — send `Iris-<version>.dmg`; users open it, drag
      `Iris.app` to Applications, and grant the camera prompt on first run.
- [ ] **GitHub Releases** — host the build(s) for download.

## 5. Known gaps before "real" distribution

- **Code signing & notarization are not configured** (`codesign_identity=None`
  in `Iris.spec`). On another Mac, Gatekeeper will warn/block an unsigned app;
  acceptable for personal/local use, but signing with an Apple Developer ID is
  required for frictionless public distribution.
- The build is **arm64-only** (built on Apple Silicon); an Intel build would need
  a native x86_64 toolchain.
- Requires a webcam and macOS; tuned for ~600 mm viewing distance
  ([[constraints]]).

## Dependencies

Built by [[dmg-build-process]]; results recorded in [[version-history]]. For the signing / notarization milestones and broader commercial path, see [[productification]].
