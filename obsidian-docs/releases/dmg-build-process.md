---
title: DMG Build Process
type: release
related: [engine-loop-and-daemon, asset-pipeline, head-tracking, distribution-checklist, version-history, constraints]
last_updated: 2026-05-31
sources: [Build/build_dmg.sh, Iris.spec, requirements.txt]
---

# DMG Build Process

## Purpose

This is how IRIS becomes a thing you can double-click: a single script,
`Build/build_dmg.sh`, freezes the Python project into a self-contained
`Iris.app` (no Python, venv, or Terminal needed) and wraps it in a
drag-to-install `Iris-<version>.dmg`. PyInstaller does the bundling; the script
adds the macOS-specific finishing (icon, Info.plist, camera permission, styled
DMG).

## One command

```bash
bash Build/build_dmg.sh        # run from anywhere; it cd's to the project root
```

Outputs:
- `dist/Iris.app` — the standalone application.
- `dist/Iris-<version>.dmg` — the disk image (version from `VERSION` in the
  script, currently **1.5**).

## What the script does, step by step

1. **Verify the venv** at `.venv/` and use its `python3`.
2. **Ensure PyInstaller** is installed (invoked as `python -m PyInstaller`, not
   the console script — the venv's script shebangs hardcode the original venv
   path and break after the project folder was renamed).
3. **Convert the icon** `assets/icon/earth_icon.png` → `Iris.icns` via `sips` +
   `iconutil` (only if the `.icns` is missing).
4. **Clean** old artifacts from a *safe* work dir (see the gotcha below).
5. **PyInstaller build** — `--windowed`, entry `launcher.py`, bundling
   `assets/`, `worlds/`, `shaders/`, `models/` via `--add-data`; hidden imports
   for the lazily/strings-imported modules (`UI.demo_overlay`, the `Worlds.*`
   modules) and the heavy deps (`mediapipe`, `OpenGL`, `pygame`, `cv2`); plus
   `--collect-all` for `mediapipe`, `pygame`, and the **pyobjc** packages
   (`objc`, `Foundation`, `AVFoundation`) — the last three are required because
   the camera-permission path imports AVFoundation *lazily inside a try/except*,
   so PyInstaller's static analysis never sees them and would otherwise bundle
   only their `.so` cores without the pure-Python modules.
6. **Patch `Info.plist`** with `PlistBuddy`: display name, `CFBundleShortVersionString`
   / `CFBundleVersion`, and — crucially — `NSCameraUsageDescription`.
7. **Re-sign the bundle (ad-hoc) — CRITICAL, and it MUST come after step 6.**
   `codesign --force --deep --sign - "$APP_PATH"`, then `codesign --verify --deep
   --strict` (the build *fails loudly* if verification fails). PyInstaller already
   ad-hoc-signs the bundle, but step 6's `Info.plist` edits **invalidate** that
   signature (`"invalid Info.plist (plist or signature have been modified)"`), and
   **macOS TCC silently denies camera access to an invalidly-signed app** — no
   prompt, instant auto-deny, so head tracking never starts. Re-signing after all
   plist edits restores a valid seal so the camera prompt can appear. This was the
   ultimate root cause of the 2026-05-31 "Live, but no tracking" bug — see
   [[known_issues]]. *(Do not reorder: any step that mutates the bundle must
   precede this re-sign.)*
8. **Build the DMG**: stage *only* the `.app` into a clean folder, then use
   `create-dmg` for the styled drag-to-Applications window, falling back to
   `hdiutil` (plain list view) if `create-dmg` isn't installed.

## The PyInstaller spec (`Iris.spec`)

`Iris.spec` encodes the same configuration declaratively: `Analysis(['launcher.py'])`,
the four data dirs, the hidden imports, `collect_all('mediapipe')` +
`collect_all('pygame')`, a UPX-compressed `EXE`, and a `BUNDLE` that produces
`Iris.app` with the icon, the stable bundle id, and the camera-usage string.
The script normally generates its spec into the work dir; this root copy is the
canonical reference. **Do not run a bare `pyinstaller Iris.spec` from the repo
root** — see the gotcha.

## Two macOS gotchas the script encodes

- **Case-insensitive filesystem collision.** PyInstaller's default work dir is
  `./build`, which on a case-insensitive Mac is the *same path* as the source
  `Build/` folder. Cleaning it would delete `Build/` (this script) and
  `parallaxctl.py`. The script therefore uses `$ROOT/.pyi_work` as the work dir
  and warns never to change it back — and never to run a bare
  `pyinstaller Iris.spec` (whose default `./build` would hit the same collision).
  This is the same incident that caused [[daemon-control]] to be reconstructed.
- **Stable bundle id for camera permission.** `BUNDLE_ID =
  com.iris.parallaxwall` is fixed across rebuilds so macOS TCC remembers the
  camera grant. A missing/changing id makes the OS forget the grant, leaving
  Desktop Mode rendering but unresponsive (no head tracking — see
  [[head-tracking]]). The `NSCameraUsageDescription` string is also **required**
  for the permission prompt to appear at all.

## Dependencies (`requirements.txt`)

Runtime deps: `pygame`, `PyOpenGL`, `numpy`, `opencv-python-headless`,
`mediapipe`, `Pillow`, plus the macOS-only PyObjC frameworks
(`pyobjc-framework-Cocoa`, `-Quartz`, `-AVFoundation`) gated on
`sys_platform == 'darwin'` — safe to skip elsewhere, with graceful fallbacks.

## Constraints

- The build is RAM-hungry (PyInstaller + mediapipe + opencv) and takes ~2–3 min;
  it targets an 8 GB M2, so build with little else running. See [[constraints]].
- **Ad-hoc signing only; no Developer ID / notarization.** PyInstaller signs
  ad-hoc and the script re-signs ad-hoc after the `Info.plist` edits (step 7) so
  the signature is *valid* — which is what lets the camera (TCC) prompt appear on
  *this* machine. But ad-hoc cdhashes change every rebuild, so macOS may re-prompt
  for the camera (or need `tccutil reset Camera com.iris.parallaxwall`) after a
  fresh build, and Gatekeeper still warns on *other* Macs. A real Developer ID
  signature + notarization would make grants stable and remove the warning. See
  [[distribution-checklist]].
- Built arm64-only on an Apple-Silicon Mac.

## Dependencies (wiki)

Packages [[engine-loop-and-daemon]] and bundles the [[asset-pipeline]] outputs +
the [[head-tracking]] model. Feeds [[version-history]] and
[[distribution-checklist]].
