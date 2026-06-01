# IRIS — Claude Code Project Context

## Read these first (in order)

1. `obsidian-docs/Handover.md` — full system state, architecture, rules, next steps
2. `obsidian-docs/architecture/constraints.md` — hard limits and calibrated values
3. `obsidian-docs/development/current-focus.md` — what's actively in progress

The Obsidian wiki (`obsidian-docs/`) is the authoritative design reference for this project.

---

## Project in one sentence

IRIS is a macOS wallpaper app that uses webcam head-tracking and an off-axis OpenGL
frustum to make the monitor appear to be a window into a live 3D world.

---

## Hard rules — never break without explicit user approval

- **Do not modify** `Engine/camera_math.py`, physics tuning, or any shader in `shaders/`
  — these are frozen; calibration took months; six headless sims in `Scripts/validation/`
  enforce invariants.
- **Do not change** `BUNDLE_ID = com.iris.parallaxwall` — macOS TCC uses this to remember
  the camera grant; changing it orphans existing permissions.
- **Do not edit `Info.plist` without re-signing** — macOS silently denies camera to an
  invalidly-signed bundle. The re-sign step in `Build/build_dmg.sh` must follow all plist edits.
- **Do not run** `pyinstaller Iris.spec` bare from the repo root — `./build` collides with
  `Build/` on macOS's case-insensitive filesystem. Always use `bash Build/build_dmg.sh`.
- **Never use `./build/` as the PyInstaller work dir** — use `.pyi_work/` (already configured).

---

## Git & GitHub

- **Remote:** `git@github.com:Iris-App-Release/IRIS.git` (SSH)
- **Branch:** `main`
- **SSH key:** `~/.ssh/id_ed25519` (passphrase-protected; load with `ssh-add ~/.ssh/id_ed25519`)
- After meaningful changes: `git add <files> && git commit -m "..." && git push`
- Before a release build: commit source first so git log == changelog
- Tag releases: `git tag v<version> && git push origin v<version>`

---

## Project skills

- `/bug-fix` — investigate and fix something broken; front-loads debugging wisdom
- `/new-world` — scaffold a new world (`Worlds/<name>/world.json`); checks renderer compatibility
- `/verify` — run the app and observe behaviour to confirm a change works

---

## Key file locations

| What | Where |
|---|---|
| Master frame loop | `Launcher/app_engine.py` |
| Off-axis camera math (frozen) | `Engine/camera_math.py` |
| Renderer + world draw calls | `Engine/renderer.py` |
| Head tracker | `Tracking/face_tracker.py` |
| World definitions | `Worlds/*/world.json` |
| Build script | `Build/build_dmg.sh` |
| Headless validation sims | `Scripts/validation/sim_*.py` |
| Runtime field log | `~/.iris/iris.log` |
| Wiki master index | `obsidian-docs/index.md` |
