---
name: bug-fix
description: Investigate and fix a bug in the IRIS / Parallax Wall app. Front-loads the accumulated debugging wisdom (known issues, constraints, the relevant system doc) before touching source. Use when the user reports something broken, a regression, "X doesn't work", camera/tracking failures, build failures, or rendering glitches.
---

# Bug Fix — IRIS / Parallax Wall

You are debugging the IRIS head-tracked parallax wallpaper app. The Obsidian
vault at `obsidian-docs/` is the accumulated, hard-won record of how this code
actually behaves — **read it before guessing**. Many bugs here have subtle
root causes (the camera-permission saga took four interrelated fixes).

## Step 1 — Load the durable wisdom (always)

Read these first, in order:

1. `obsidian-docs/development/known_issues.md` — Has this (or a related bug)
   already been diagnosed? Each entry is meant to be the *durable* record so a
   root cause is never re-derived. **If the symptom matches a RESOLVED entry,
   the fix may have regressed** (e.g. ad-hoc signatures change each rebuild).
2. `obsidian-docs/development/current-focus.md` — What was most recently worked
   on? The bug may be fallout from the latest change.
3. `obsidian-docs/architecture/constraints.md` — The hard limits and platform
   quirks. Many "bugs" are actually documented constraints (one true viewing
   distance, source runs can't self-authorize the camera, etc.).

## Step 2 — Route to the right system doc

Match the symptom to the subsystem, then read that page (it has a **data-flow
table** showing exactly what feeds what, plus a `sources:` frontmatter list of
the real files):

| Symptom area | Read this doc | Likely source files |
|---|---|---|
| Camera / "Live but no tracking" / permission | `systems/head-tracking.md` + `releases/dmg-build-process.md` | `Tracking/face_tracker.py`, `Build/build_dmg.sh`, `launcher.py` |
| Parallax / zoom / rotation feels wrong | `systems/off-axis-projection.md` | `Engine/camera_math.py` |
| Jitter / lag / smoothing | `systems/head-tracking.md` | `Tracking/face_tracker.py` |
| Rendering / shader / texture / bloom | `systems/rendering-engine.md` | `Engine/renderer.py`, `shaders/`, `Engine/bloom_postfx.py` |
| The eye (gaze, eye texture) | `worlds/the-watcher.md` | `Engine/renderer.py` (Eye), `Scripts/tools/gen_eye_textures.py` |
| World won't load / switch / wrong world | `systems/world-system.md` | `Worlds/world_loader.py`, `Worlds/world_runtime.py`, `Worlds/*/world.json` |
| Window / wallpaper / daemon / mode | `systems/engine-loop-and-daemon.md` + `systems/daemon-control.md` | `Launcher/app_engine.py`, `Launcher/app_entry.py`, `parallaxctl.py` |
| HUD / overlay / status pill / onboarding | `systems/ui-overlay.md` | `UI/demo_overlay.py` |
| Icons / orbital ring | `systems/orbital-icons.md` | `Engine/renderer.py` (IconOrbit), `orbital_icons.py` |
| Build / packaging / DMG | `releases/dmg-build-process.md` | `Build/build_dmg.sh`, `Iris.spec` |

Follow `[[wiki-links]]` in the page if the bug spans systems.

## Step 3 — Investigate the source

Read the real files named in the doc's `sources:` frontmatter. Reproduce the
logic path. Confirm the root cause **before** editing — don't pattern-match a
symptom to a plausible-looking line.

## Step 4 — Respect the frozen core

The camera math, tracking smoothing, renderer math, and shaders are **declared
frozen** (`design-decisions.md`). If a fix would touch them, that's a red flag —
re-check whether the bug is really there or in a consuming layer. If you must
touch frozen code, say so explicitly and validate with the sims.

## Step 5 — Validate

- **Headless physics/logic** — run the relevant sim(s) from
  `Scripts/validation/` with `.venv/bin/python Scripts/validation/sim_<x>.py`
  (exit 0 = pass). At minimum run `sim_latency.py` (smoothing) and
  `sim_overlay.py` (UI state) if you touched those areas; `sim_offaxis.py` /
  `sim_viewing.py` / `sim_vertical.py` / `sim_orbit.py` for camera/geometry.
- **Live behavior (rendering, gaze, textures)** — `./preview.sh` runs from
  source instantly (no rebuild). Camera/wallpaper need the signed app — use
  `./hotswap.sh` for asset/shader changes or a full `bash Build/build_dmg.sh`
  for Python changes. **Source runs cannot self-authorize the camera** — that's
  a documented constraint, not a bug.

## Step 6 — Record the fix (mandatory)

Once fixed, update the vault so the knowledge is durable:

- Add/Update an entry in `obsidian-docs/development/known_issues.md`
  (symptom → root cause → fix → files → validation → remaining risks). Use the
  dated `[RESOLVED YYYY-MM-DD]` heading format already in the file.
- Update `obsidian-docs/development/current-focus.md`.
- If a *new* constraint was discovered, add it to
  `obsidian-docs/architecture/constraints.md`.
- If the data flow changed, update the affected system doc's data-flow table
  (the `[[links]]` in those tables also feed Obsidian's graph).
- Add a dated entry to `obsidian-docs/log.md`.

Today's date is available in the session context. The task is not done until
both the fix and the docs are updated.
