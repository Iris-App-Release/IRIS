---
title: Handover — LLM Project Context Packet
type: metadata
related: [index, current-focus, known_issues, design-decisions, system-interactions, constraints, dmg-build-process, world-system, productification]
last_updated: 2026-06-01
sources: []
---
ww
# IRIS — LLM Handover Packet

> **Purpose:** Self-contained context transfer. An LLM reading this file cold can immediately continue work. No prior chat history required.

---

## 1. Project Overview

**IRIS** (internal alias: "Parallax Wall") is a macOS wallpaper app that creates a real-time fish-tank VR illusion. A webcam tracks the user's head position; a geometrically-correct off-axis OpenGL frustum re-renders a 3D world (currently: Earth or a giant eye) so the monitor appears to be a window into actual 3D space. The app ships as a signed, drag-to-install `.app` / `.dmg` built from Python (PyInstaller). It runs in two modes: an interactive onboarding demo with a floating glass HUD, and an always-on click-through wallpaper daemon.

**End goal:** A polished, shippable macOS ambient experience — multiple swappable worlds, robust camera permission flow, a reliable build pipeline, and eventually Developer ID signing for Gatekeeper-clean distribution.

---

## 2. Current Focus

→ See [[current-focus]] for the live task list.

**As of 2026-05-31, all three tracked items are RESOLVED:**

| Item | Status |
|---|---|
| Settings camera toggle re-enable | RESOLVED |
| Camera permission / TCC / code signature | RESOLVED & live-verified |
| The Watcher eye tracking + visual upgrade | COMPLETE |

**Immediate next tasks (no active ticket — infer from context):**
1. Consider Developer ID signing to stabilise TCC grants across rebuilds (currently ad-hoc; grant may re-prompt after each new `Iris.app`).
2. Explore new world ideas now that the world system is proven with two worlds.
3. Pupil dilation / sclera blood-fill animation in The Watcher (noted as future opportunity in [[current-focus]]).

**Do NOT touch yet:**
- The frozen camera math, physics, shaders — these are intentionally locked ([[design-decisions]]).
- The `~/.parallax_*` flag-file IPC scheme — changing this breaks the daemon.

---

## 3. System Architecture

### Components

| Component | Language / Layer | Responsibility |
|---|---|---|
| `launcher.py` | Python (entry) | Sets `sys.path`, `MEIPASS`, env vars; delegates to `app_entry.py` |
| `Launcher/app_entry.py` | Python | Selects `PARALLAX_MODE` (default `"demo"`) |
| `Launcher/app_engine.py` | Python | **Master frame loop** (60 fps demo / 30 fps wallpaper) — orchestrates all subsystems |
| `Tracking/face_tracker.py` | Python | Webcam → smoothed 5-tuple `(hx, hy, hz, yaw, pitch)` via MediaPipe |
| `Engine/camera_math.py` | Python | Off-axis Kooima frustum → projection + view matrices (FROZEN) |
| `Engine/renderer.py` | Python + GLSL 120 | Draws Earth, Eye, Stars, Nebula, IconOrbit |
| `Engine/bloom_postfx.py` | Python + GLSL | Half-res bloom post-process |
| `Worlds/world_loader.py` | Python | Reads `Worlds/<name>/world.json` from disk |
| `Worlds/world_runtime.py` | Python | Active-world selector; polls `~/.iris/preferences.json` each frame |
| `UI/demo_overlay.py` | Python | Liquid-glass onboarding HUD drawn into the same GL context |
| `Build/build_dmg.sh` | Bash | Freezes → patches plist → re-signs → packages DMG |
| `Scripts/validation/sim_*.py` | Python | Headless sims (no GPU, no camera) protecting frozen physics |
| `parallaxctl` (`parallaxctl.py`) | Python CLI | `parallaxctl` daemon control (start/stop/status) |
| `obsidian-docs/` | Markdown vault | **Source of truth for all design knowledge** |

### Data Flow (per frame)

```
Webcam → face_tracker → (hx,hy,hz,yaw,pitch)
                              ↓
                  app_engine (60 fps demo / 30 fps wallpaper)
                         ├─ camera_math  → proj/view matrices
                         ├─ world_runtime → active world flags
                         ├─ renderer     → GL draw calls
                         ├─ bloom_postfx → post-process
                         └─ demo_overlay → HUD (demo mode only)
                                              ↓
                                           Screen
```

### File-Based IPC (the message bus)

IRIS uses polled flag files — **no sockets**. Any writer (UI, CLI, hand-edit) takes effect live.

| File | Writers | Readers | Meaning |
|---|---|---|---|
| `~/.iris/preferences.json` | UI overlay, `parallaxctl` | world-runtime, UI | Active world + onboarding/camera state |
| `~/.parallax_off` | UI overlay, `parallaxctl` | engine loop | Master pause (hide + release camera) |
| `~/.parallax_icons_off` | UI overlay, `parallaxctl` | engine, orbital-icons | Hide orbital icons |
| `~/.iris/camera_off` | UI overlay | engine loop | Camera-access toggle |
| `~/.iris/daemon.pid` | `parallaxctl` / spawn | UI overlay | Detect running wallpaper daemon |
| `~/.parallax_earth_state.json` | engine loop (≤30 Hz, throttled) | orbital-icons Cocoa app | Live camera state for 2-D icon alignment |
| `~/.iris/iris.log` | `face_tracker` | human / debugging | Camera/permission events (stdout lost in windowed bundle) |

### Source of Truth

> **The Obsidian Markdown vault (`obsidian-docs/`) is the authoritative design reference.** The project has no git history. When source and wiki conflict, investigate source — but the wiki was compiled from source and is considered current as of 2026-05-31.

---

## 4. File / Data Structure

### Vault Layout

```
obsidian-docs/
├── index.md                  ← master index (start here)
├── Handover.md               ← this file
├── log.md                    ← append-only ingestion log
├── architecture/
│   ├── constraints.md        ← hard limits and calibrated values
│   ├── design-decisions.md   ← the WHY behind every major choice
│   └── system-interactions.md ← import chain, per-frame flow, IPC diagrams
├── development/
│   ├── current-focus.md      ← active tasks (update this first on new work)
│   ├── known_issues.md       ← durable bug records (newest-first)
│   └── Claude-Interrupted.md ← mid-session investigation notes (archive when resolved)
├── docs/
│   └── docs-index.md         ← annotated map of 12 hand-written source docs
├── releases/
│   ├── dmg-build-process.md  ← how to build Iris.app / Iris.dmg
│   ├── distribution-checklist.md
│   └── version-history.md    ← v0.0 → 1.5 arc
├── systems/                  ← one page per subsystem (see index.md table)
└── worlds/
    ├── worlds-index.md       ← side-by-side world comparison
    ├── earth.md
    └── the-watcher.md
```

### Naming Conventions

- Wiki pages use `kebab-case` filenames matching their Obsidian `[[wiki-link]]` slug.
- Source packages use `TitleCase/` dirs; PyInstaller bundles them as `lowercase/`.
- Flag files use `~/.parallax_*` (legacy) and `~/.iris/*` (newer); both are active.

### Cross-References

- Obsidian `[[wiki-link]]` syntax — bidirectional; every page's frontmatter lists `related:` slugs.
- Every page lists `sources:` — the actual Python/bash files read to produce that page.
- Tables cross-link to both wiki pages and source paths.

### `world.json` Schema

```json
{
  "name": "string",
  "description": "string",
  "version": "1.0",
  "environment": {
    "primary_mesh": "earth | eye",
    "secondary_elements": ["clouds", "atmosphere"],
    "background": "stars | void",
    "lighting": { "sun_direction": [x, y, z], "ambient_intensity": 0.0–1.0 }
  },
  "rendering": {
    "use_bloom": true,
    "use_parallax": true,
    "rotation_speed": 0.01,
    "show_icons": true,
    "clear_color": [r, g, b]
  },
  "assets": {
    "asset_dir": "optional_subdir",
    "textures": { "day": "filename.jpg" },
    "background": { "stars": "filename.jpg" }
  }
}
```

> **CONSTRAINT:** `primary_mesh` must map to an existing renderer class. `"earth"` → `Earth`; `"eye"` → `Eye`. A new mesh type requires renderer + shader work, not just JSON.

---

## 5. Rules & Constraints

### Hard Rules — Never Break

| Rule | Reason |
|---|---|
| **Do not modify the camera math, physics tuning, or shaders** | These are frozen; calibration took months; headless sims enforce invariants. Any change here requires re-running all `sim_*.py` validation. |
| **Do not change `BUNDLE_ID = com.iris.parallaxwall`** | macOS TCC uses this to remember the camera grant. Changing it orphans existing grants. |
| **Re-sign the bundle AFTER any `Info.plist` edit** | macOS TCC silently denies camera to an invalidly-signed app (no dialog, instant auto-deny). Build step 7 handles this; never remove or reorder it. |
| **Never use PyInstaller work dir `./build`** | On macOS's case-insensitive FS, `./build` == `Build/` (source). Cleaning it deletes the build script. Use `.pyi_work`. |
| **Do not run `pyinstaller Iris.spec` from repo root bare** | Same case-collision risk. Use `bash Build/build_dmg.sh`. |
| **Set `OPENCV_AVFOUNDATION_SKIP_AUTH=1` before any `cv2` import** | OpenCV's off-thread auth request crashes ("can not spin main run loop from other thread"). The app owns auth; OpenCV must not attempt it. |
| **Camera permission must be requested on the main thread** | `request_camera_access()` in `face_tracker.py` pumps `NSRunLoop` — only valid on main thread. Worker thread camera opens must happen after auth is settled. |
| **`tracker_started` flag must not be used as a re-enable guard** | Post-fix: the outer guard no longer includes `not tracker_started`; resume path calls `set_tracking(True)` on the already-running worker. |
| **Force-collect pyobjc in PyInstaller** | `AVFoundation`, `Foundation`, `objc` use lazy `try/except` imports invisible to static analysis. Missing `--collect-all` produces a bundle that silently falls through to `except` and never prompts for camera. |

### Formatting Rules (Markdown / Vault)

- Every page must have YAML frontmatter with `title`, `type`, `related`, `last_updated`, `sources`.
- Cross-references use `[[slug]]` not bare filenames.
- `related:` lists are bidirectional — if you add A → B, add B → A.
- `sources:` lists the actual source files read to produce that wiki page (not wiki cross-refs).
- `known_issues.md` — newest entry first; use `[RESOLVED date]` or `[SUPERSEDED date]` prefix.
- `current-focus.md` — keep short; move durable conclusions to system pages or `known_issues`.
- `Claude-Interrupted.md` — investigation-in-progress only; archive entries once resolved.
- **Do not add entries directly to `index.md` tables without creating the corresponding page.**

### Consistency Rules

- All world pages must have a matching entry in `worlds-index.md`.
- Any new system added to the import chain must appear in `system-interactions.md`.
- Any new build step that mutates the bundle must precede the re-sign step.

---

## 6. Skills / Commands (Claude Code Workflows)

These are Claude Code skills invocable in this project context:

### `/bug-fix`
**What:** Front-loads accumulated debugging wisdom (known issues, constraints, relevant system docs) before touching source. Runs headless sims post-fix to validate.
**When:** Something is broken, a regression appeared, camera/tracking fails, build fails, rendering glitches.
**Output:** Root cause in `known_issues.md`, fix applied to source, validation result noted.

### `/new-world`
**What:** Scaffolds a new IRIS world. Loads the `world.json` schema, the two proven examples (`earth`, `the-watcher`), and the constraints a new world must respect. Creates `Worlds/<name>/world.json`.
**When:** Adding a new visual experience / scene to the wallpaper.
**Output:** `Worlds/<name>/world.json` created; flags whether new renderer/shader code is needed (if `primary_mesh` doesn't exist yet).

### `/verify`
**What:** Runs the app and observes behaviour to confirm a change works.
**When:** After a fix, before declaring it resolved; after a new world or feature.
**Output:** Live observation report; promotes findings to `current-focus.md` or `known_issues.md`.

### `/code-review`
**What:** Reviews changed code for correctness bugs and simplification opportunities.
**When:** Before shipping a new DMG or after a non-trivial change.
**Output:** Inline findings; apply with `--fix` or comment with `--comment`.

> **Note:** No `/mathsim`, `/organize`, or `/expand` commands are defined for this project as of 2026-05-31.

---

## 7. Known Issues

→ See [[known_issues]] for the full durable record.

**Summary as of 2026-05-31 — all tracked bugs resolved:**

| ID | Status | Summary |
|---|---|---|
| Camera TCC silent-deny | RESOLVED | `build_dmg.sh` edited `Info.plist` after signing; re-sign step added. |
| pyobjc not bundled | RESOLVED (prerequisite) | Lazy `try/except` imports missed by PyInstaller; `--collect-all` added. |
| `tracker_started` re-enable guard | RESOLVED | Outer `not tracker_started` guard removed; resume branch added. |
| "Enable Camera" dead code | SUPERSEDED | `_request_camera_permission()` was never called; now wired into `start()`. |

**Areas to watch:**
- Ad-hoc signatures change each rebuild → macOS may re-prompt for camera. Requires `tccutil reset Camera com.iris.parallaxwall` if previously denied.
- Source-only runs (`python launcher.py`) cannot self-authorize (no bundle identity) — bundled `.app` is the supported path for camera testing.
- Duplicate `cv2`/`pygame` SDL2 dylib warning at startup — pre-existing, harmless.
- No Developer ID / notarization → Gatekeeper warns on other Macs (single-user posture).

---

## 8. Next Steps

Prioritized from highest to lowest:

1. **Developer ID signing** — makes TCC grants stable across rebuilds and removes Gatekeeper warnings. Requires an Apple Developer account. Document in [[dmg-build-process]] and [[distribution-checklist]].
2. **New world** — the world system is proven; expand the catalog. Use `/new-world` skill. If `primary_mesh` is `"earth"` or `"eye"`, no engine changes needed.
3. **The Watcher enhancements** — pupil dilation keyed to `hz` (viewer depth), sclera blood-fill animation on world activate. These are content additions, not physics changes.
4. **Head orientation → gaze blending** — MediaPipe provides `yaw`/`pitch`; currently only `hx`/`hy` (position) drives the eye. Blending orientation in at close range would enrich tracking.
5. **Notarization** — follow-on to Developer ID; required for clean distribution to other Macs.

> **Productification.** For the full commercial progression path (milestones, business model, risks, immediate actions), see [[productification]].

---

## 9. Reference Links

| Resource | Path / Location |
|---|---|
| **Main Obsidian vault** | `~/Documents/IRIS APP/obsidian-docs/` |
| **Master index** | [[index]] — `obsidian-docs/index.md` |
| **Known issues** | [[known_issues]] — `obsidian-docs/development/known_issues.md` |
| **Current focus** | [[current-focus]] — `obsidian-docs/development/current-focus.md` |
| **Architecture notes** | [[design-decisions]], [[system-interactions]], [[constraints]] |
| **Build process** | [[dmg-build-process]] — `Build/build_dmg.sh` |
| **World schema** | [[world-system]] — `Worlds/world_loader.py`, `Worlds/*/world.json` |
| **Headless validation** | [[headless-simulation]] — `Scripts/validation/sim_*.py` |
| **Field log** | `~/.iris/iris.log` (runtime; not in vault) |
| **Interrupted sessions** | [[Claude-Interrupted]] — `obsidian-docs/development/Claude-Interrupted.md` |

---

## 10. Handoff Summary

**Current system state:**

- IRIS v1.5 is the latest build (`dist/Iris-1.5.dmg`, 128 MB, arm64).
- Camera permission flow is fully working end-to-end in the `.app` (verified live 2026-05-31).
- Two worlds ship: Earth (flagship) and The Watcher (giant eye, eye-tracked).
- The Watcher's eye tracks head position (`hx`/`hy`) with `GAZE_LERP = 0.10`, ±15°/±10° clamp, drift preserved.
- All headless sims (`sim_overlay`, `sim_latency`, others) pass.
- No git history — wiki is the only persistent project record.

**Key decisions already made (do not revisit without strong reason):**

- Off-axis Kooima frustum over `gluPerspective` — geometrically correct parallax, not faked.
- Worlds are JSON content, not code — engine is frozen; new experiences extend the catalog.
- File-based IPC (`~/.parallax_*`, `~/.iris/`) — no sockets; survives restarts; engine polls each frame.
- OpenGL 2.1 / GLSL 120 — widest macOS compatibility (old Intel + Apple Silicon Metal-GL).
- In-process Desktop Mode — UI and engine share one GL context; no cross-process compositing.
- `OPENCV_AVFOUNDATION_SKIP_AUTH=1` + app-owned main-thread auth — the only safe camera path.
- PyInstaller work dir is `.pyi_work` — the `build/` name collides with `Build/` on HFS+.

**Must NOT change going forward:**

- Camera math, physics tuning, shaders (frozen; enforced by headless sims).
- `BUNDLE_ID = com.iris.parallaxwall` (TCC grant stability).
- Re-sign step ordering in `build_dmg.sh` (must follow all `Info.plist` edits).
- `OPENCV_AVFOUNDATION_SKIP_AUTH=1` flag placement (before any `cv2` import).
- PyInstaller `--collect-all` for `objc`, `Foundation`, `AVFoundation` (lazy imports, invisible to static analysis).
