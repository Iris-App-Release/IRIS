---
title: IRIS — Project State of the Union
type: strategy / operating-manual
related: [productification, Handover, version-history, current-focus, grid-creator-tool-plan, constraints, design-decisions, FINANCIAL_PROJECTION]
status: living document — definitive strategic reference
last_updated: 2026-06-06
author: compiled as lead product strategist / technical architect / startup advisor / project historian
sources:
  - Docs/IRIS_OVERVIEW.txt (2026-05-30)
  - obsidian-docs/productification.md (2026-06-02)
  - obsidian-docs/Handover.md (2026-06-01)
  - obsidian-docs/releases/version-history.md (2026-06-01)
  - obsidian-docs/development/current-focus.md (2026-06-03)
  - obsidian-docs/architecture/grid-creator-tool-plan.md (2026-06-03)
  - obsidian-docs/world-builder/{SCAN_IMPORT_ARCHITECTURE,TEXT_TO_3D_RESEARCH}.md (2026-06-05)
  - git log (2026-06-01 → 2026-06-05)
---

# IRIS — Project State of the Union

> **What this document is.** The definitive strategic operating manual for IRIS as of
> 2026-06-06. It is the single reference a future collaborator, investor, or returning
> founder can read cold to understand what IRIS is, how it got here, exactly how close it
> is to being a real product, what decisions remain open, and what realistically happens
> next. It is grounded in the project's own records and git history. Where it extrapolates
> beyond the evidence, it says so explicitly with an **[ASSUMPTION]** tag.
>
> **Two honesty constraints govern this document:** (1) it does not rewrite history —
> including the parts that went sideways; (2) it avoids hype. IRIS is a genuinely
> impressive piece of engineering that has **not yet shipped to a single external user and
> has earned $0**. Both halves of that sentence are true and the document holds them
> together throughout.

---

## SECTION 1: Executive Summary

### What IRIS is

IRIS is a macOS application that turns an ordinary monitor into a **window into a live 3D
world**. A webcam tracks the user's head position in real time; a geometrically correct
off-axis projection (the Kooima "fish-tank VR" frustum) re-renders the scene from the
viewer's actual vantage point. When you move your head, the world behind the glass shifts
with correct parallax — your brain reads genuine depth, with no headset.

It runs in two modes:
- an **interactive demo** with a liquid-glass heads-up display (the showroom), and
- an always-on, click-through **desktop wallpaper daemon** (the product in daily use).

On top of this frozen engine sits a **content layer of "worlds"** (declarative JSON, not
code) and an emerging **World Builder** — a Claude-assisted tool that lets a user describe
a scene in natural language and watch placeable objects appear inside a spatial grid, live.

### The core problem it solves

Spatial depth on a flat display normally requires a VR/AR headset — which is isolating,
fatiguing, requires setup, and cuts you off from your real environment. IRIS delivers a
real, felt 3D effect using hardware every Mac already has (a webcam), with zero friction
and zero isolation. It is **ambient spatial computing without the headset tax.** The
honest framing of the problem is less "a pain point users are searching to solve" and more
"a latent delight" — it is a *want*, not a *need*, which is an important strategic fact
(see Sections 7 and 10).

### The current vision

A polished, shippable macOS ambient experience with:
1. a **frozen, calibrated parallax engine** (done);
2. a **growing catalogue of swappable worlds** (the moat — currently 2 shipping, a 3rd built but unshipped);
3. a **World Builder** that lets users author their own scenes via natural language (built through an authoring-UI milestone, not yet live-verified or monetized); and
4. a future premium tier built on **importable 3D content** — text-to-3D mesh generation and **iPhone room/object scans** that turn *your* space into a portal world.

### Why the concept is potentially valuable

- **It demos itself.** Head-tracked parallax is visually arresting in a 10-second screen
  recording. This is the single most important strategic asset: the product *is* its own
  marketing, which collapses customer-acquisition cost and creates a genuine (if
  probabilistic) viral ceiling that most utilities don't have.
- **Near-zero marginal content cost.** Worlds are JSON + textures, not engine code. The
  catalog can grow without touching the calibrated core.
- **A privacy posture that ages well.** All processing is local; no video is stored or
  transmitted. As always-on cameras normalize, "the spatial app that never sends your face
  anywhere" is a real positioning advantage.
- **An Apple-ecosystem moat in the roadmap.** iPhone LiDAR (RoomPlan) and Object Capture
  produce USDZ scans that IRIS could turn into personal portal worlds — a feature a generic
  webcam-parallax competitor cannot easily match.

### What differentiates it from existing AI products

IRIS is **not** an AI workspace tool and should not be marketed as a competitor to
ChatGPT, Cursor, or v0 (see Section 8 for the full, deflationary comparison). Its AI
surface — describe-a-world → generated scene — is a *feature that lowers content-creation
friction*, not the product itself. The differentiation that matters is categorical:

- It is **embodied and ambient**, not a chat window. The output lives on your desktop and
  responds to your body, continuously, in the background.
- It is **spatial-first**: the unit of value is a 3D world you look *into*, not text or a
  2D image you look *at*.
- It is **local and private** by architecture, not policy.

> **One-line investor framing [ASSUMPTION about positioning]:** "IRIS is fish-tank VR for
> your Mac — a webcam turns your monitor into a window into 3D worlds you can build by
> describing them, or by scanning your own room. No headset, nothing leaves your machine."

---

## SECTION 2: Complete Development History

> Chronology reconstructed from `version-history.md` (pre-git era), the full `git log`
> (2026-06-01 onward), `current-focus.md`, and the two overview docs. Pre-git dates are
> best-effort per the project's own version record; git-era events are exact.

### Era 0 — The frozen engine (pre-productization, through ~2026-05-29)

**Change.** Built and calibrated the core head-tracked parallax engine, then deliberately froze it.
**Previous approach.** Nothing — greenfield.
**New approach.** Three-component camera blend (off-axis translation frustum, distance scaling, proximity-gated rotation); MediaPipe FaceLandmarker tracking at ~30 fps with a velocity-adaptive (1€-style) smoothing filter; OpenGL 2.1 / GLSL 120 renderer (Earth with day/night/clouds/atmosphere, star layers, nebula); bloom post-processing; six headless validation sims (`sim_*.py`) enforcing the physics invariants.
**Why.** "Parallax calibration takes months to get right; once right, every experiment after breaks something. Lock it in now, iterate on UI/UX/worlds instead." (from `IRIS_OVERVIEW.txt`, Decision History).
**Impact.** Established the project's defining engineering discipline: a calibrated core that *cannot* be casually modified, protected by automated sims. This is the foundation everything else safely builds on, and the single best decision in the project's history.

### Era 1 — Productization restructure & the "demo behind glass" model (2026-05-30, builds v0.0–1.3)

**Change.** Reorganized into a production folder hierarchy; replaced the old dark 2D launcher with an in-process "demo behind glass UI"; added an explicit `demo` engine mode; stood up PyInstaller + DMG packaging.
**Previous approach.** A standalone dark 2D launcher; ad-hoc structure.
**New approach.** One entry point (`Launcher/app_entry.py`) routing to demo or daemon; UI drawn *into the same GL context* as the scene (liquid-glass HUD); centralized strings in `Config/Strings.json`; the three-state machine (Floating Preview → Live Tracked → Desktop Mode).
**Why.** To make it a coherent product with a first-run story, and shippable as a single `.app`/`.dmg`.
**Impact.** v0.0 shipped (~262 MB). The "scripted idle floating preview" (the demo that needs no camera) emerged here as the most important UX asset — the magic lands *before* any permission prompt.

> **Notable abandoned plan.** `IRIS_OVERVIEW.txt` proposed a settings UI in **GTK or PyQt**.
> This was never pursued — the project instead built settings/HUD natively into the GL
> overlay and via file-based flags. A correct call (a second UI toolkit in a PyInstaller
> bundle would have been a packaging nightmare), but worth recording as a discarded branch.

### Era 2 — Bundle slimming & the Intel-support regression (2026-05-30, v1.1–1.3)

**Change.** Bundle size roughly halved (~262 MB → ~134 MB); build narrowed to a single architecture.
**Previous approach.** `IRIS_OVERVIEW.txt` repeatedly promised **"arm64 + Intel x86_64"** universal distribution, with an `arch -x86_64` wrapper and a GitHub Releases plan hosting both.
**New approach.** **arm64-only**, leaner dependencies (likely `opencv-python-headless`, single-arch).
**Why.** Pragmatic slimming for size and build simplicity on the developer's Apple-Silicon machine.
**Impact.** A genuine **scope regression**, honestly re-labeled later: `productification.md` lists "arm64-only binary" as a **High-severity gap** excluding all Intel Mac users. The aspiration ("Intel support coming via arch wrapper") quietly became a deferred liability. This is the clearest example in the history of an early promise silently narrowing — recorded here rather than smoothed over.

### Era 3 — The camera-permission saga (2026-05-31, v1.4–1.5)

**Change.** Fixed "Live status on, but no head tracking," then fixed a re-enable bug.
**Previous approach (the bug).** `build_dmg.sh` edited `Info.plist` *after* PyInstaller signed the bundle; macOS TCC silently denies camera to an invalidly-signed app (auto-deny in ~52 ms, no dialog). Separately, the Settings re-enable path was guarded by `not tracker_started`, permanently true after first enable.
**New approach.** Re-sign ad-hoc *after* plist edits and verify (fail loudly); `OPENCV_AVFOUNDATION_SKIP_AUTH=1` so the app owns auth on the main thread; tri-state `request_camera_access()` the start path actually acts on; honest UI status; field logging to `~/.iris/iris.log`. The re-enable guard was split into first-start vs. resume branches.
**Why.** A failed camera grant on first run = uninstall. This is existential for a camera app.
**Impact.** v1.4 and v1.5 (128 MB) shipped; camera flow **verified live** on 2026-05-31. Produced four of the project's hardest-won "never break these" rules (bundle ID stability, re-sign ordering, the OpenCV auth flag, pyobjc `--collect-all`).

### Era 4 — The second world: The Watcher (2026-05-31)

**Change.** Added a horror world — a giant bloodshot eye that tracks the viewer's head.
**Previous approach.** Single-world (Earth) — effectively a tech demo.
**New approach.** `Eye.update(dt, hx, hy)` reuses the existing head-position feed (no second tracking pipeline); gaze smoothed (`GAZE_LERP = 0.10`), clamped to ±15° yaw / ±10° pitch; jaundiced sclera, arterial veins, hemorrhage blotches.
**Why.** To exercise the world system as a *true content layer*, and to prove range of mood (cinematic Earth vs. visceral horror) on identical physics.
**Impact.** Validated the "worlds are content, not code" thesis in practice. Notably, the planned catalog shifted: `IRIS_OVERVIEW.txt` imagined "Mars, abstract, space"; what actually shipped was **Earth + The Watcher**, with **Gem** as the built-but-unshipped third renderer. The catalog crystallized around *emotional differentiation*, not planetary variety.

### Era 5 — Version control adopted (2026-06-01) — the catastrophic risk closed

**Change.** `git init`, `.gitignore`, initial commit (160 files, 17,134 insertions), pushed to a private GitHub remote; `CLAUDE.md` added for LLM session bootstrapping.
**Previous approach.** **No version control at all.** The Obsidian wiki was the *only* persistent project record.
**New approach.** Git is the authoritative changelog from v1.5 onward; the wiki documents the pre-git era as best-effort reconstruction.
**Why.** `productification.md` ranked "source loss (no git)" as the **#1 catastrophic risk** — a single disk failure would have erased the entire project.
**Impact.** The most important *risk-reduction* event in the history. That a months-deep, calibration-heavy project ran this long with no backup is itself a significant founder-discipline finding (Section 11).

### Era 6 — Performance & latency hardening; bloom removed (2026-06-01)

**Change.** Multiple perf wins, and bloom post-processing removed entirely.
**Previous approach.** 60 fps full-screen wallpaper; bloom FBO pipeline (bright-extract → blur → composite with tonemap/vignette/chromatic aberration); per-frame `glGetFloatv` GPU→CPU stalls; client-array vertex streaming (~190k verts/frame); fixed per-frame `CAM_LAG = 0.55` lerp.
**New approach.** 30 fps cap for wallpaper/fullscreen (demo stays 60); **bloom removed** (renders straight to the default framebuffer — which, as a side benefit, finally made MSAA actually apply); static meshes migrated to VBOs; `glGetFloatv` stalls removed; `CAM_LAG` made **frame-rate-independent** (`alpha = 1 − e^(−dt/τ)`) — this last one *touched frozen smoothing, with explicit user approval and a new `sim_camlag` guard*.
**Why.** "Opening other apps stuttered while IRIS ran." Profiling found **no physics cost** (camera math ~7 µs/frame); the real cost was compositing a native-Retina full-screen surface at 60 fps when head input is only ~30 Hz — half the frames were duplicate redraws. The per-frame `CAM_LAG` also *doubled* perceived latency at the 30 fps cap.
**Impact.** Halved GPU/compositor load; real anti-aliasing; lower latency. Demonstrated the validation-sim discipline working as intended — even an approved change to the frozen layer was gated by a new sim.

### Era 7 — The three-tab HUD and the head-tracking speed upgrade (2026-06-01 → 06-02)

**Change.** Reorganized the demo HUD into an app-like three-tab layout (Worlds · Community · Settings); added predictive head tracking + 1€ jitter filter ("Tier 1 speed upgrade"); made hover instant.
**Previous approach.** Bottom-clustered HUD with scattered corner pills and a vertical world-picker; ~0.15–0.3 s hover easing (read as sluggish).
**New approach.** Top-center tab bar; Worlds tab with a name pill + edge nav arrows + a bottom action group; a world-preview *suspend* signal (engine skips the 3D draw on Settings/Community); binary (instant) hover.
**Why.** Move from "tech demo HUD" toward "app." Instant hover was the user's explicit top-priority quality fix. Frozen visual language (white pills, corner radii) was preserved.
**Impact.** The product began to *feel* like software rather than a graphics demo — a prerequisite for charging money.

### Era 8 — The enclosure-viewing model: three attempts converging on "grids don't pan" (2026-06-02)

**Change.** Settled how enclosure worlds (Grid Room, Gem) handle depth and look-around — after two discarded attempts.
**Previous approaches (both abandoned same day).** (a) A "forward dolly" (lean in = move into the room); (b) a "grid + sphere merge" giving enclosures Earth's blended look with a capped amplitude (`LOOK_ENCLOSURE_AMP`).
**New approach.** Enclosure worlds keep Earth's telephoto **zoom** + **parallax** + **anchored rim**, with rotational look held at **exactly zero** (`if world.enveloping: yaw_target = pitch_tgt = 0.0`). Sphere worlds remain byte-identical and still pan.
**Why (decisive founder call).** *"The panning works so well on earth because of its lack of anchored walls — we're trying to invent something that doesn't exist."* A bezel-locked rim and a rotational pan are a geometric contradiction — any pan shears the anchored rim.
**Impact.** Resolved a genuine conceptual knot with a principled answer (verified to 4.6e-13 px in `sim_envelop`). A model case of *subtractive* problem-solving — the fix was deleting code (`LOOK_ENCLOSURE_AMP`, `draw_proscenium`, `behind_cells`), not adding it.

### Era 9 — World Builder: from concept to authoring UI (2026-06-02 → 06-03)

**Change.** Designed and built World Builder — a safe, Claude-assisted way to place objects in the Grid Room without touching the frozen core.
**Previous approach.** Worlds were authored by hand-editing JSON; no in-app creation; the "grid as coordinate system" existed only as the `grid-api-customization` design note.
**New approach.** Phases 1–6 (engine): `placeable_objects[]` schema, `grid_to_world` transform, allowlist + clamp + count-cap sanitation, mtime hot-reload, `sim_grid_api.py`. Phases 7–8 (UI): a top-bar World Builder tab, a 30° oblique **Canvas Cube** stage, a **Send → Preview → Save** workflow, a `generate_world_objects` Claude call (cached system prompt, `builtin:*` allowlist, sanitized twice), and a `/world-builder` skill + CLI for key-free dev authoring. A `Licensing/entitlement.py` freemium scaffold was added.
**Why.** This is the intended **revenue hook** and the productification path's "platform" milestone — a content flywheel that grows the catalog without founder authoring time.
**Impact.** The biggest *conceptual* expansion in the project: IRIS shifted from "a wallpaper with worlds" toward "a platform for making worlds." Crucially, it was built **additively** — no frozen module touched; all 12 sims green.

> **UX revision (2026-06-03).** The flow was revised to two-step (Send previews to the
> Canvas Cube + live scratch world; Save commits a *new* `Worlds/<slug>/world.json`), the
> freemium gate was set to **unlimited** (`FREE_CUSTOMIZATION_LIMIT = math.inf`) with the
> entitlement scaffolding retained on disk, and a safe **Delete World** flow was added
> (refuses built-ins and path escapes). Monetization was deliberately *deferred*, not removed.

### Era 10 — The world→portal rebrand, its revert, and the recovery incident (2026-06-03 → 06-05)

> This is the messiest chapter and it is recorded in full because the spec forbids rewriting history.

**Change.** A wholesale rename of "world" → "portal" throughout the codebase — then a complete revert — then a recovery of work the revert had orphaned.
**Sequence (from git):** `f50c88e` rename world→portal → follow-up fixes (`3c5ee1c`, `ba4586d`, `6c2c723`) → **four reverts** (`14cbffb`, `b27834e`, `9b4c761`, `ffa3d22`) undoing the entire rename → `ae25ee7` "Recover World Builder Phase 7-8 authoring UI (orphaned by portal revert)" → `dfb2ace` "Recover full newer work (perf upgrade + new World Builder UI), un-branded" → `6735174` "Document the world→portal resurrection (incident record)." The work continues on a branch literally named **`recover-newer-work`.**
**Why the rename.** [ASSUMPTION] A branding/conceptual bet that "portal" better captured the window-into-a-world metaphor than the generic "world."
**Why the revert.** [ASSUMPTION] The rename touched too much surface (schema keys, file names `world.json`→`portal.json`, tab keys, comments, scripts) for too little benefit, and entangled with the in-flight World Builder UI — reverting it was cleaner than maintaining it.
**Impact.** A real **execution cost**: a cosmetic rename churned the codebase, the revert orphaned genuine feature work (the Phase 7-8 authoring UI), and recovering it required a dedicated branch and an incident record. **Net product value created by this entire episode: ~zero.** It is the clearest cautionary example in the history of cosmetic/naming work crowding out shipping (see Section 11, "habits to stop"). To the founder's credit, it was caught, recovered cleanly, and *documented as an incident* rather than buried.

### Era 11 — Grid ↔ parallax unification (2026-06-05, current HEAD)

**Change.** Unified the oblique Canvas Cube grid and the live parallax preview into a single source of truth.
**Previous approach.** Two disconnected representations of the same world: the oblique grid hardcoded `D=8`, **inverted the depth axis**, and read a *different source* (`_wb_preview_objects`) than the parallax (`grid_room/world.json`) — so a CLI/skill edit updated the parallax but not the grid (the reported symptom).
**New approach.** Both renderers route through one transform pair in `Worlds/placeable.py` — `grid_to_world` (3D) + new `grid_to_canvas_cell` (oblique) — and the grid now reads the same `world.json` the parallax renders. `sim_grid_api.py` §6 pins the sync (27-cell direction sweep + monotonic-depth check). 12/12 sims green; no frozen module touched.
**Why.** Two sources of truth for one world is a latent bug factory; the symptom had already surfaced.
**Impact.** Removed a *class* of future bugs and proved it with a guard. Alongside it landed a research bundle (`world-builder/`): a pipeline audit, a unified world schema, a generation-determinism review, and forward research on **text-to-3D** (cloud APIs; Tripo best fit; no on-device generation on Apple Silicon) and **3D scan import** (GLB/USDZ; iPhone RoomPlan/Object Capture as the Apple-native hook).

### Cross-cutting evolution: the business model

| Dimension | `IRIS_OVERVIEW.txt` (05-30) | `productification.md` (06-02) | Net shift |
|---|---|---|---|
| Price | $4.99 one-time **or** $1.99/mo | **$7.99 one-time Pro** (freemium); subscription de-emphasized | Toward one-time; subscription gated behind a proven release cadence |
| Goals | "100K users / $50K MRR in 12 months" | Grounded milestone ladder; "100+ downloads in first two weeks" as a *soft* baseline | From aspiration/hype → realism |
| Worlds | Earth, Mars, abstract, space | Earth, The Watcher, Gem | Emotional differentiation over variety |
| Architecture | arm64 + Intel universal | arm64-only (Intel = a gap) | Scope narrowed |
| AI/creation | not present | World Builder + text-to-3D + scan import | Major new conceptual axis |
| Version control | not flagged | catastrophic gap → resolved 06-01 | Risk closed |

---

## SECTION 3: Current Product Definition

### Product Mission

Make a flat Mac display feel like a window into a real 3D space — and let people fill that
space with worlds they choose, build by describing, or scan from their own surroundings —
all locally, privately, with no headset and no special hardware.

### Target User

Primary (stated): creative professionals and productivity enthusiasts who personalize their
desktops and value novel, beautiful software. Secondary: demo-seekers and the technically
curious. **[ASSUMPTION]** The true early-adopter beachhead is narrower and sharper than
"creative professionals": it is *Mac power users who follow indie-app and tech communities*
(the people who surface things on Hacker News, r/macapps, Product Hunt) — because the
product's acquisition engine is virality among exactly that crowd, not enterprise sales.

### Core User Journey

1. **Discover** via a self-demoing GIF/video (the parallax sells itself in a screen recording).
2. **Download** the DMG; drag to Applications.
3. **Floating Preview (no camera):** the world moves with a scripted idle animation — the magic lands before any permission ask.
4. **Enable Camera → Live Tracked:** real head motion drives parallax; the "window" effect becomes real.
5. **Enable Desktop Mode:** a click-through wallpaper daemon takes over the background; the demo reverts to a preview.
6. **Browse Worlds:** switch between Earth, The Watcher (and future worlds) via the Worlds tab.
7. **(Emerging) World Builder:** describe a scene → Send → see objects appear on the Canvas Cube and live preview → Save as a new world.
8. **(Future) Pro:** unlock the full catalog, unlimited builds, and importable 3D content (generated meshes / room & object scans).

### Main Features

- Head-tracked off-axis parallax ("window into 3D"), frozen and calibrated.
- Two shipping worlds (Earth, The Watcher); a third (Gem) built but unshipped.
- Three-state demo (Floating Preview → Live Tracked → Desktop Mode) with a liquid-glass HUD.
- Click-through always-on wallpaper daemon; `parallaxctl` CLI.
- JSON world system with live hot-reload and a Worlds-tab cycle.
- World Builder authoring UI (Send/Preview/Save, Delete World) — built, not yet live-verified or monetized.
- Local-only processing; no video stored or transmitted.

### Interface Philosophy

"App, not graphics demo." A liquid-glass HUD drawn *into the same GL context* as the scene
(no second UI toolkit). A frozen visual language — white pills, fixed corner radii, instant
(non-eased) hover — that the founder treats as settled and protected. Onboarding is
state-machine-based with **no loading screens or resets**: the same window transitions
instantly between preview, live, and desktop modes. The guiding principle is that the first
impression must be magical *before* any friction (hence the camera-free scripted idle).

### Technical Architecture

- **Entry:** `Launcher/app_entry.py` selects `PARALLAX_MODE` (demo / wallpaper).
- **Loop:** `Launcher/app_engine.py` — master frame loop (60 fps demo / 30 fps wallpaper).
- **Tracking:** `Tracking/face_tracker.py` — MediaPipe FaceLandmarker (468 landmarks) → smoothed `(hx, hy, hz, yaw, pitch)`; Haar-cascade fallback; daemon thread + lock-free read.
- **Camera math (FROZEN):** `Engine/camera_math.py` — Kooima off-axis frustum, view matrices, 3-component blend.
- **Renderer:** `Engine/renderer.py` (+ GLSL 120 shaders, frozen) — Earth, Eye, Gem, Stars, Nebula, GridRoom, PlaceableObjects.
- **Worlds:** `Worlds/world_loader.py` (JSON load), `Worlds/world_runtime.py` (active-world selector + typed accessors + mtime hot-reload), `Worlds/placeable.py` (the shared `grid_to_world` / `grid_to_canvas_cell` transforms).
- **UI:** `UI/demo_overlay.py` (glass HUD, tabs, World Builder), `UI/world_builder_api.py` (Claude call).
- **IPC:** polled flag files (`~/.iris/*`, `~/.parallax_*`) — no sockets; any writer (UI, CLI, hand-edit) takes effect live.
- **Build:** `Build/build_dmg.sh` → PyInstaller (`.pyi_work/`) → plist patch → **re-sign** → DMG.
- **Validation:** 12 headless sims (`Scripts/validation/sim_*.py`) protecting frozen invariants.
- **Stack rationale:** OpenGL 2.1 / GLSL 120 for the widest macOS compatibility; in-process single GL context (UI + engine share it); file-based IPC for restart-survivability.

### AI Systems

One AI system exists today: **World Builder generation** (`UI/world_builder_api.py`). A
user's natural-language prompt + the grid's cell convention + the `builtin:*` allowlist are
sent to Claude (`claude-sonnet-4-6`, cached system prompt, `max_tokens≈1500`); the model
returns a JSON object array; the result is parsed and run through `sanitize_objects` (clamp
+ allowlist + count-cap) **twice** (in the API and again at the write site) so the on-disk
write is provably safe. Any failure (no key, no SDK, parse error) returns `[]` and toasts —
never crashes. **Two future AI systems are researched but unbuilt:** text-to-3D mesh
generation (cloud API, Tripo as first integration) and scan-to-world (RoomPlan/Object
Capture USDZ ingestion). Both are explicitly gated behind a shared GLB→VBO mesh-import
pipeline that does not yet exist.

### World Generation System

The world is the unit of content: a declarative `world.json` (`environment`, `rendering`,
`assets`) mapped to a renderer class (`primary_mesh: earth → Earth`, `eye → Eye`,
`room → GridRoom`). Worlds hot-reload on file mtime change and are byte-stable when
untouched (an empty `placeable_objects` default means existing worlds are unaffected by the
World Builder additions). New *visual experiences* with a novel mesh require renderer +
shader work; new *arrangements* of existing primitives are pure data. The design target is
"100+ worlds without recompiling."

### Desktop Mode

The product in daily use: a separate daemon process (`PARALLAX_MODE=wallpaper`) renders
full-screen, **click-through** (doesn't steal focus or block input), always-on, at 30 fps.
It survives app restarts; a PID file (`~/.iris/daemon.pid`) lets the demo detect a running
daemon and skip onboarding. Toggled via the HUD or `parallaxctl`/flag files. The known UX
gap: once in desktop mode the user can feel "trapped in the wallpaper," which the planned
**menu-bar UI** is meant to solve (always-visible camera toggle / exit / settings).

### Camera Mode

"Live Tracked" — real head tracking drives the parallax. Camera ownership is
single-threaded and explicitly handed off: enabling Desktop Mode releases the camera
(`tracker.stop()`) before the daemon acquires it. Camera permission is the highest-risk
moment in the journey (a failed grant = uninstall); it is now hardened (app-owned
main-thread auth, re-signed bundle, honest UI states, field logging) and verified live on
Apple Silicon — **but unverified on Intel and older macOS.**

### Cube Canvas (the "Canvas Cube")

The World Builder's authoring stage: a 30° oblique-projected representation of the Grid Room
drawn in the HUD. When a user clicks **Send**, generated objects are painted onto this
canvas (sphere → disc, cube → rounded square, cylinder → capsule), honoring color / scale /
emissive, depth-sorted back-to-front. As of 2026-06-05 it reads the *same* `world.json` and
the *same* transform (`grid_to_canvas_cell`) as the live 3D parallax, so the oblique preview
and the real render can no longer disagree. It is the visual bridge between "describe a
scene" and "see it in the world."

### Asset Generation

Today: **three built-in fixed-function primitives** (`builtin:cube`, `builtin:sphere`,
`builtin:cylinder`) — chosen because they *always* render (no shader compile, no import,
no failure mode that kills the illusion mid-demo). Reliability over expressiveness is a
deliberate stance. Future (researched, unbuilt): **generated meshes** via cloud text-to-3D
(GLB → `Mesh` VBO via a `mesh:<asset_id>` allowlist extension) and **scanned meshes**
(GLB/USDZ from iPhone). Both share one unbuilt prerequisite — the mesh-import pipeline —
and both are intended to live *behind the paywall* (their per-call vendor cost makes them a
natural Pro differentiator).

### UI Framework

No third-party UI toolkit. The HUD is **hand-drawn into the GL context** (pygame/OpenGL),
with a custom button system (grayscale-minimal, de-blued palette), a top-center tab bar
(Worlds · Community · Settings, plus the World Builder surface), signature-cached rendering
(no per-frame allocation), and instant hover. State lives in `demo_overlay` fields and in
`~/.iris/*` flag files. This is lean and dependency-free but means every UI control is
bespoke — there is no free accessibility, text input, or layout system.

### Future Platform Vision

The roadmap's end state (`productification.md` Milestone 6) is a **creator platform**: a
published, versioned world schema; a creator tool producing compliant worlds without engine
code; a community submission pipeline; importable 3D content (generated + scanned); and
eventually a non-Mac reach (Windows via a renderer rewrite, or a browser/WebGL variant — a
different product category). The strategic spine is the **world-as-moat + content flywheel**:
each world is differentiated, cheap to make, and a reason to return and upgrade; AI-assisted
and community authoring grow the catalog without founder time.

---

## SECTION 4: Productification Analysis

> Status / Risk / Completion% / Required Work per area. Completion % is an **estimate**
> against "ready for a paid public launch," not against "exists at all."

| Area | Status | Risk | Completion | Required work |
|---|---|---|---|---|
| **UI** | Strong; app-like 3-tab HUD, frozen visual language, instant hover | Low | **80%** | Menu-bar UI (exit/camera/settings); a real Settings panel (today: flag files); World Builder UI live-verify polish. |
| **User Experience** | Excellent core (camera-free magic moment; no-reset state machine) | Medium | **70%** | Solve "trapped in wallpaper" (menu bar); first-run polish on non-dev machines; World Builder discoverability. |
| **Stability** | Core engine very stable (12 sims); field stability unknown | **High** | **55%** | Crash reporting; long-running daemon memory testing; **Intel/old-macOS verification**; World Builder live `/verify`. |
| **Performance** | Good on M1/M2 (30 fps wallpaper cap, VBOs, stalls removed) | Low–Med | **80%** | Verify on 8 GB / older Apple Silicon and (if supported) Intel; perf cap audit with full object sets / future meshes. |
| **Branding** | Weak/unsettled — see the world→portal churn; "Iris" vs "Parallax Wall" split | Medium | **40%** | Lock a name and one-line positioning **and stop revisiting it**; logo, icon, color/voice; press kit. |
| **Monetization** | Designed, scaffolded (`Licensing/entitlement.py`), **switched off** (`limit = ∞`); $0 earned | **High** | **20%** | Pick model (lean one-time $7.99); wire a payment channel (Paddle/Gumroad or App Store IAP); world-gating logic; COGS plan for AI features. Hard-blocked by signing. |
| **Onboarding** | Strong in-app; nothing for *acquisition* | Medium | **65%** | Landing page; demo video/GIF; privacy explainer surfaced; Intel/no-webcam graceful paths verified. |
| **Asset Pipeline** | Primitives reliable; no mesh import; no generated/scanned assets | Medium | **30%** | Build GLB→VBO mesh-import core (the shared gate for text-to-3D *and* scans); decimation/size caps; guard sim. |
| **Documentation** | Exceptional (wiki + sims + CLAUDE.md + incident records) | **Very Low** | **95%** | Maintain; resist *over*-documentation crowding out shipping (Section 11). |
| **Infrastructure** | Git ✅; build pipeline ✅; **no signing/notarization**; no telemetry; no crash reporting | **High** | **35%** | Apple Developer ID + notarization (the master unblocker); GitHub Releases; anonymous telemetry; crash reporting. |
| **Scalability** | Content scales (JSON); team does not (bus factor = 1) | Medium | **50%** | Published schema + capability matrix for creators; AI COGS architecture (proxy vs BYOK); the platform pieces are *post-revenue*. |
| **Community Features** | "Community" tab is a "Coming Soon" placeholder | Low (now) | **5%** | Deferred — correctly. Needs a paid user base first; no work until then. |
| **Distribution** | None public; arm64-only; right-click-to-open workaround required | **Critical** | **15%** | Notarized DMG + GitHub Releases + landing page; later App Store; resolve Intel scope decision. |

**Overall honest readout:** the **product core is ~75–80% of the way** to a paid launch;
the **go-to-market and commercial wrapper are ~20–30%**. The remaining work is dominated by
*unglamorous, finite* tasks (signing, notarization, a third world, a landing page, a
payment channel), not hard engineering. The single highest-leverage unblock is **Apple
Developer ID + notarization** — nearly every "Critical/High" gap above is gated on it.

---

## SECTION 5: Major Strategic Decisions Remaining

### Decision 1 — Distribution channel: Direct vs App Store vs both
**Options.** (a) Direct download (notarized DMG + GitHub Releases + landing page); (b) Mac App Store; (c) both (direct primary, App Store secondary).
**Pros.** Direct: keeps ~90%+ margin, no review latency, full control, fits a video-driven acquisition model. App Store: discovery + trust + clean IAP.
**Cons.** Direct: you own discovery entirely; manual update/license plumbing. App Store: 30% (15% under the small-business program), camera-app review scrutiny, slow IAP iteration.
**Recommendation.** **(c) with direct as primary.** The product's acquisition is virality among indie/tech communities, not store search — so direct + landing page first; add App Store later for trust and the long tail. Either way, notarization is required.
**Consequences of waiting.** Nothing ships; $0; no user feedback. This is the gating decision under all others.

### Decision 2 — Pricing & monetization model
**Options.** (a) One-time $7.99 Pro (freemium, free Earth); (b) subscription $4.99–7.99/mo; (c) hybrid (one-time core + subscription for AI/scan features); (d) world marketplace.
**Pros/Cons.** One-time: zero churn, fits an ambient wallpaper, impulse-priced — but caps LTV and doesn't fund recurring AI COGS. Subscription: recurring revenue and funds AI features — but a novelty wallpaper has brutal churn risk. Marketplace: per-world friction (the docs already reject this).
**Recommendation.** **Launch (a) one-time $7.99.** Introduce **(c)** later — a subscription tier *only* for the genuinely recurring-cost, sticky features (text-to-3D generation, scan import), once retention data justifies it. The free tier must deliver the full core illusion.
**Consequences of waiting.** Acceptable short-term — monetization is *correctly* deferred until the reliability gate is met and signing exists. But indefinite deferral means a beautiful free toy that never tests willingness-to-pay.

### Decision 3 — AI model provider & COGS architecture (for generation features)
**Options.** (a) Dev-funded proxy (your backend holds the key, meters per device); (b) BYOK (user supplies their own key); (c) hybrid (free = BYOK/primitives; Pro = N proxied generations).
**Pros/Cons.** Proxy: cleanest UX, but you eat COGS and must run a server. BYOK: zero COGS, but niche appeal (only devs have keys). Hybrid: matches freemium, caps free-tier COGS.
**Recommendation.** **(c) hybrid.** Free tier = primitives only (zero COGS); Pro = metered proxied generations. The Pro price must provably clear `expected generations × unit cost`. Mesh generation (costlier) belongs behind Pro from day one.
**Consequences of waiting.** Low urgency — this only bites when text-to-3D/scan ships. But choosing it *before* building the feature avoids re-architecting the call path.

### Decision 4 — Local vs cloud processing
**Options.** (a) Keep everything local except optional AI authoring; (b) move more to cloud.
**Recommendation.** **(a), firmly.** Local processing of the camera/tracking is the privacy differentiator and a marketing asset — it must never move to cloud. Only *opt-in content generation* (which inherently needs cloud GPUs; on-device 3D gen is non-viable on Apple Silicon) touches the network, and that boundary should be explicit in the UI.
**Consequences of waiting.** None — this is already the de facto architecture; the decision is just to *commit and message it*.

### Decision 5 — Intel support (the unresolved scope regression)
**Options.** (a) arm64-only forever (label clearly); (b) universal binary; (c) arm64 now, universal later.
**Pros/Cons.** arm64-only: simplest, but excludes a shrinking-but-real installed base and was an *unkept original promise*. Universal: broader reach, but new GPU/webcam bug surface and build complexity.
**Recommendation.** **(c).** Ship arm64-only, labeled honestly, to launch *now*; revisit universal only if telemetry/demand shows meaningful Intel interest. Don't let Intel block launch.
**Consequences of waiting.** Low — but be honest in marketing copy to avoid bad reviews from Intel users hitting a wall.

### Decision 6 — Subscription/marketplace for community generations
**Options.** (a) No community features until post-revenue (current stance); (b) build a submission pipeline early.
**Recommendation.** **(a).** The "Community" tab should stay a placeholder until there is a paid user base and a content-volume problem worth solving. Building a creator economy before having creators is a classic premature-platform trap.
**Consequences of waiting.** None — this is correctly deferred.

### Decision 7 — Storage / asset architecture (for generated & scanned content)
**Options.** (a) Per-world local asset dirs + content-hash cache (as researched); (b) cloud asset storage / sync.
**Recommendation.** **(a).** Cache generated/scanned meshes per world by content hash, locally — consistent with the privacy story and zero hosting cost. Cloud sync is a much later, opt-in convenience.
**Consequences of waiting.** Low; only relevant once mesh import exists.

### Decision 8 — Mobile / cross-platform strategy
**Options.** (a) macOS-only indefinitely; (b) iOS/iPadOS (ARKit tracking) as a companion; (c) Windows (renderer rewrite); (d) browser/WebGL.
**Recommendation.** **(a) for the foreseeable future**, with iOS as the most *strategically coherent* later bet (it strengthens the iPhone-scan moat). Windows is a full renderer rewrite (DirectX/Vulkan vs GL 2.1) — high cost, defer hard. Browser is a *different product* (no always-on daemon).
**Consequences of waiting.** None near-term; cross-platform is a post-product-market-fit question.

### Decision 9 — Growth strategy
**Options.** (a) Organic/viral (self-demoing video on HN/Reddit/PH/social); (b) paid acquisition; (c) B2B/kiosk (galleries, retail, trade shows).
**Recommendation.** **(a) primary, (c) opportunistic.** Build a one-click "record a 10-second demo" export — it weaponizes the product's biggest asset. Paid acquisition makes no sense pre-PMF for an impulse-priced app. A single B2B/installation deal is an asymmetric bonus, not a strategy.
**Consequences of waiting.** The longer there's no shareable artifact (landing page + video), the more every other effort is throttled.

### Decision 10 — Open source considerations
**Options.** (a) Closed; (b) open the engine, sell worlds/Pro; (c) open the world schema only.
**Recommendation.** **(c).** Keep the calibrated engine closed (it's the moat and took months), but publish the *world schema* + a capability matrix to enable community authoring without giving away the core. Full open-sourcing would surrender the only defensible asset.
**Consequences of waiting.** None — this is a deliberate, reversible choice best made once there's a community to court.

### Decision 11 — Branding/name (implicit but urgent)
**Options.** (a) Commit to "IRIS"; (b) revisit (as the portal episode shows the founder is tempted to).
**Recommendation.** **(a) — and freeze it.** The world→portal churn cost real work for zero value. Pick the product name, the internal vs. external naming split (Iris vs. the "parallax" working title in flag files is fine), and *stop touching it*. Naming is not where this product wins or loses.
**Consequences of waiting.** Every re-litigation of the name is pure churn that delays launch.

---

## SECTION 6: Critical Success Requirements

> Brutally realistic. These are necessary conditions, not nice-to-haves.

### Product Requirements
- The **magic moment must land in <10 seconds** of first run, before any camera grant (the scripted floating preview already delivers this — protect it above all else).
- **≥3 worlds at launch.** A one- or two-world product reads as a demo, not a $7.99 purchase. Gem is built; ship it.
- **The camera must work on the first try** on the user's actual hardware — including at least a verified graceful path on Intel/old macOS/no-webcam.
- **A reason to return.** An ambient app users forget about doesn't convert or retain. Worlds (and eventually World Builder) must give recurring reasons to re-engage.

### Technical Requirements
- **Notarized, Gatekeeper-clean install.** Any right-click-to-open friction = abandonment. Non-negotiable.
- **Field stability:** crash reporting + a long-running daemon that doesn't leak or stutter the desktop.
- **Never regress the frozen core.** The 12 sims must stay green on every change; the discipline that protects the calibration is the discipline that protects the product.
- **A working payment + license-gating path** that lives *far* from the frozen engine.

### Design Requirements
- A **landing experience** (page + video) as polished as the in-app magic moment — the acquisition surface is currently absent.
- **Honest, simple privacy communication**, front-and-center (it's a camera app; trust is the gate to install).
- A **settled visual identity** (name, icon, one-liner) that stops moving.

### Business Requirements
- **A committed distribution channel and price**, live, taking real money — the only way to learn willingness-to-pay.
- **COGS discipline** before shipping any AI feature: Pro price must clear generation cost.
- **Telemetry**, or every roadmap decision is a guess.

### Marketing Requirements
- A **shareable, self-demoing artifact** and a deliberate launch sequence across the indie/tech communities where this product's audience actually lives (HN, r/macapps, Product Hunt, relevant subreddits, X).
- **Multiple at-bats at virality** — each new world / the scan feature / a fresh video is another lottery ticket; consistency = more tickets (this is the *mechanism* by which sustained effort pays off for a non-network-effects product).

### Founder Requirements
- **Ship over polish.** The defining risk is not capability — it's a beautiful unlaunched artifact. The founder must cross the unglamorous finishing line (signing, page, payment) that is far less fun than engine work.
- **Resist cosmetic churn** (the portal rename is the cautionary tale).
- **Tolerate the post-launch quiet.** The modal outcome is a modest reception that must be *iterated on*, not a viral explosion. Emotional durability through that is a real requirement.
- **Sustain a solo project's motivation** across the boring last mile — the explicit, current risk (the founder has voiced low motivation; this document exists partly to make the remaining distance legible and finite).

---

## SECTION 7: Biggest Risks

> Ranked by severity (likelihood × impact), highest first, with reasoning.

1. **Execution / "never ships" risk — SEVERITY: CRITICAL.** The dominant risk. The product is ~80% done and the remaining 20% is the *least enjoyable* work (signing, landing page, payment, a third world). History shows the founder gravitating to engine/refactor work (and even cosmetic renames) over the finishing line. A months-deep project that never reaches one external user is the single most likely failure mode. *Why #1:* it's both high-likelihood (motivation is already flagging) and total-impact (nothing else matters if it doesn't ship).

2. **Founder / bus-factor & motivation risk — SEVERITY: HIGH.** Solo developer; bus factor = 1. The founder has explicitly voiced low motivation. Documentation mitigates the bus factor for *resumption*, not for *momentum*. *Why:* high likelihood, high impact — the project's velocity is entirely one person's sustained will.

3. **Market / "vitamin not painkiller" risk — SEVERITY: HIGH.** IRIS is a *want*, not a *need*. Novelty can fade; an ambient wallpaper's retention is unproven; willingness to pay $7.99 for a delight (vs. a tool) is real but soft. *Why:* moderate likelihood, high impact on revenue — it caps the realistic conversion ceiling even if acquisition works.

4. **Distribution / Gatekeeper & platform risk — SEVERITY: HIGH (but fully mitigable).** Without notarization, no one outside the dev's Mac can install cleanly; App Store review scrutinizes camera apps. *Why:* certain to bite if unaddressed, but the fix is known and finite (Apple Developer ID + notarization), so it's high-but-solvable.

5. **Technical field-stability risk — SEVERITY: MEDIUM-HIGH.** The engine is verified on Apple Silicon only. Intel/older-macOS/diverse-webcam behavior is unknown; a camera failure on a new user = uninstall and a bad review. *Why:* high likelihood of *some* field bugs, medium impact (mitigable via labeling + beta).

6. **Financial risk — SEVERITY: LOW-MEDIUM.** Uniquely low *downside*: total committed cost is ~$150/yr (Apple Developer + domain); COGS is gated behind the paywall; no team to fund. *Why low:* you are betting time, not capital. The financial risk is opportunity cost (time spent here vs. elsewhere), not ruin.

7. **Product-scope / premature-platform risk — SEVERITY: MEDIUM.** The roadmap's gravity pulls toward exciting *platform* features (World Builder, text-to-3D, scan import) that sit *ahead* of the launch line. Building the platform before validating the product is a classic trap and a motivation sink (it makes the mountain look infinite). *Why:* moderate likelihood (the docs show this pull), moderate impact (it delays, rather than kills).

8. **Competitive / "big platform eats it" risk — SEVERITY: LOW-MEDIUM.** Apple or another player could ship system-level head-tracked depth. *Why low-ish:* possible but not imminent; IRIS's privacy-local + scan-your-room angle would still differentiate, and a big-platform entry would also *validate the category*.

---

## SECTION 8: Competitive Positioning

> **Framing caveat (important and deflationary):** IRIS is **not** in the same category as
> the products below. It is an ambient spatial-display app with an AI authoring *feature*;
> they are AI content/coding/design tools. Comparing them is useful for *conceptual
> positioning* and to locate IRIS's AI surface in the landscape — but marketing IRIS as a
> rival to any of these would be hype and would invite an unwinnable feature comparison.
> The comparison is about *product concepts*, as requested.

| Product | What it is | Where IRIS is **weaker** | Where IRIS is **stronger / different** |
|---|---|---|---|
| **ChatGPT** | General conversational AI | Not general-purpose; tiny capability surface; no ecosystem | Embodied & ambient output; spatial, not textual; runs locally; a *felt* experience, not a Q&A |
| **Claude** | General conversational AI / agentic coding | Same as above; IRIS *uses* Claude as a component, not a competitor | IRIS is a vertical application of an LLM (describe→world), not a general assistant; the LLM is invisible plumbing |
| **Midjourney** | Text→image generation | No mature generative pipeline yet (text-to-3D unbuilt); no community/gallery; far smaller output diversity | Output is a *navigable 3D space you inhabit on your desktop*, not a flat image you download; head-tracked, living |
| **Cursor** | AI code editor | Entirely different domain; no developer workflow value | Not competing — different universe; only conceptual overlap is "AI lowers a creation barrier" |
| **Lovable** | AI app/site builder | No web-app generation; far narrower creative scope | "Describe it and it appears" applied to *spatial scenes* rather than web apps; the artifact is ambient, not a deployed site |
| **v0** | AI UI generation | No component/code output; tiny creative surface | Spatial composition vs. 2D UI composition; output is experiential |
| **Figma AI** | AI in a collaborative design tool | No collaboration, no design-tool depth, no team workflow | Single-user, ambient, experiential; not a productivity surface but a delight surface |
| **Emerging AI workspace products** | Agentic, multi-tool work surfaces | IRIS has no workspace/productivity function at all | IRIS is *anti-workspace*: it's the calm, ambient, non-productive layer — a deliberate counter-position |

**Where IRIS could become genuinely unique (the defensible white space):**
- **AI-generated spatial worlds you *live inside* on your desktop.** Not an image or a UI — a persistent, head-tracked 3D environment authored by description. No mainstream product occupies "ambient generative 3D for the desktop."
- **Scan-your-own-space portals.** "Point your iPhone at your room → your monitor becomes a window into it." This leans on Apple's LiDAR/RoomPlan/Object Capture stack — a moat that text/image AI tools structurally cannot reach and that webcam-only rivals can't either.
- **Privacy-local spatial computing.** As cloud-based spatial/AI products proliferate, "the spatial app whose camera feed never leaves your machine" is a clean, ownable position.

**Honest competitive verdict:** IRIS's competition is not these AI giants — it's *other Mac
ambient/wallpaper and novelty apps*, the user's own attention/novelty budget, and the
possibility of a platform-level feature from Apple. Its durable advantages are the
calibrated engine (hard to replicate), the self-demoing virality, and the Apple-scan moat —
none of which are about AI feature parity.

---

## SECTION 9: Recommended Next 90 Days

> Today is 2026-06-06. This roadmap runs to ~2026-09-04. It is sequenced strictly by
> dependency and leverage, and it is deliberately **launch-biased** — the platform/AI work
> is held *after* a real public launch on purpose (the #1 risk is never shipping).
> Each item: Purpose · Difficulty · Dependencies · Expected impact.

### Immediate Priorities (Weeks 1–2 · ~through 2026-06-20)
1. **Apple Developer Program enrollment ($99).** *Purpose:* unblock signing + notarization (the master gate). *Difficulty:* trivial (≈1 day to activate). *Dependencies:* none. *Impact:* unblocks essentially every Critical/High gap.
2. **Developer ID signing + notarization in `build_dmg.sh`** (`codesign` → `notarytool` → `stapler`, re-sign after any plist edit). *Purpose:* Gatekeeper-clean install on any Mac. *Difficulty:* medium (a few hours; fiddly). *Dependencies:* #1. *Impact:* the difference between "demo on my machine" and "a product strangers can install."
3. **Ship the Gem world (`Worlds/gem/world.json` + textures).** *Purpose:* reach the 3-world "feels like a product" threshold. *Difficulty:* low (renderer exists; needs JSON + one live GL compile check). *Dependencies:* none. *Impact:* high — single highest-leverage content action.
4. **Live `/verify` pass on World Builder + Gem.** *Purpose:* confirm parallax, anchored rim, 30 fps, hot-reload, and Send/Preview/Save all hold in a real GUI session. *Difficulty:* low-medium. *Dependencies:* #3. *Impact:* converts "built" into "trusted."

### Next Milestones (Weeks 3–5 · ~through 2026-07-11)
5. **Landing page + 15-second demo video/GIF (GitHub Pages).** *Purpose:* the acquisition surface; weaponize the self-demoing property. *Difficulty:* medium (needs a clean GUI capture). *Dependencies:* #2–3. *Impact:* very high — without this, every growth effort is throttled.
6. **GitHub Releases with the notarized DMG.** *Purpose:* a real, linkable download channel. *Difficulty:* low. *Dependencies:* #2. *Impact:* high.
7. **Menu-bar UI (camera toggle / exit desktop / settings).** *Purpose:* fix "trapped in the wallpaper" — the top in-product UX gap. *Difficulty:* medium. *Dependencies:* none (uses existing flag IPC). *Impact:* high for retention/usability.
8. **Anonymous, opt-out telemetry (launch count, world selected, session length).** *Purpose:* stop guessing. *Difficulty:* medium. *Dependencies:* privacy copy. *Impact:* compounding — informs every later decision.

### Product-Readiness Milestones (Weeks 5–7 · ~through 2026-07-25)
9. **Crash reporting (PyInstaller-compatible, opt-in).** *Purpose:* don't be blind in the field. *Difficulty:* medium (hidden-import fragility, like pyobjc). *Dependencies:* none. *Impact:* high once real users exist.
10. **Privacy policy (camera use, all-local, nothing transmitted).** *Purpose:* trust + App Store prerequisite. *Difficulty:* low. *Dependencies:* none. *Impact:* medium-high (gate to install + listing).
11. **LaunchAgent ("Launch at login").** *Purpose:* the final step from "app" to "ambient OS feature." *Difficulty:* low-medium. *Dependencies:* settings surface. *Impact:* medium (retention).
12. **Intel/old-macOS graceful-path verification (or explicit, labeled arm64-only).** *Purpose:* avoid first-run failures + bad reviews. *Difficulty:* medium. *Dependencies:* hardware/VM access. *Impact:* medium (protects reputation at launch).

### Beta-Readiness Milestones (Weeks 7–9 · ~through 2026-08-08)
13. **Private beta: 10–30 testers across hardware/webcams/macOS versions.** *Purpose:* surface field bugs and break founder assumptions about webcam quality/lighting/distance. *Difficulty:* medium (recruiting + triage). *Dependencies:* #5–9. *Impact:* high — the first real-world signal.
14. **A feedback channel (Discord or a mailing list).** *Purpose:* structured input + an early-adopter nucleus. *Difficulty:* low. *Dependencies:* beta. *Impact:* medium.
15. **One-click "record a demo" export.** *Purpose:* turn every user into a marketer (free acquisition). *Difficulty:* medium. *Dependencies:* core. *Impact:* high (this is the viral flywheel's ignition).

### Launch-Readiness Milestones (Weeks 9–13 · ~through 2026-09-04)
16. **Wire payments + freemium world-gating (one-time $7.99 via Paddle/Gumroad; gate lives far from the engine).** *Purpose:* test willingness-to-pay. *Difficulty:* medium-high. *Dependencies:* signing, a stable build, the reliability gate. *Impact:* revenue begins here.
17. **Public launch sequence** (Show HN, r/macapps, Product Hunt, relevant subreddits, X), staggered for multiple at-bats. *Purpose:* acquisition + the viral lottery tickets. *Difficulty:* medium (preparation + timing). *Dependencies:* #5–6, #16. *Impact:* the moment of truth — the first external validation.
18. **(Optional, post-launch) App Store submission.** *Purpose:* trust + long-tail discovery. *Difficulty:* medium-high (review). *Dependencies:* privacy policy, assets. *Impact:* medium (secondary channel).

> **Explicitly deferred beyond 90 days (and why):** the mesh-import pipeline, text-to-3D,
> scan import, community submission, and cross-platform. These are the *exciting* threads —
> and exactly why they must wait. They are post-launch, post-validation bets; pulling them
> forward is the premature-platform trap (Section 7, risk #7). Launch first, *then* let
> revenue and real users decide which of these is worth building.

---

## SECTION 10: Potential Future Outcomes

> Multi-year scenarios assuming *consistent* execution. Consistent with the financial model
> already shared with the founder: bounded downside, an unusually fat viral upside tail for
> this category, and a near-guaranteed skill/portfolio floor. No hype.

### Failure Scenario — "the beautiful unlaunched artifact"
**What causes it.** The most likely failure isn't technical — it's the finishing line. The
founder, motivation fading, never crosses the unglamorous gap (signing, page, payment), or
keeps disappearing into engine/platform work and cosmetic churn (cf. the portal episode).
The product stays a personal marvel that no stranger ever experiences. Secondary paths:
camera fails on diverse hardware and early reviews kill it; or it launches but is a pure
novelty with no retention and converts near zero. **Financial result:** ~$0; the only return
is the (real) skills gained. **Probability [ASSUMPTION]:** meaningful — this is the base
rate for solo passion projects, and the current motivation dip makes it the live risk.

### Modest Success Scenario — "a real, small product"
**What it looks like.** Ships notarized with 3+ worlds and a landing page. A couple of
community posts land; the self-demoing GIF earns a novelty burst. ~10k–40k downloads in
year one; ~3% convert at $7.99 → roughly **low-to-mid four figures cumulative** in year one,
a run-rate of perhaps **$700–1,400/mo** if growth holds. World Builder is a fun differentiator
but a minor revenue driver. **Meaning:** validated that strangers want it; real (if modest)
side income; a strong portfolio piece. **Probability [ASSUMPTION]:** the realistic *median*
if the founder ships and stays consistent.

### Strong Startup Scenario — "it catches"
**What it looks like.** A demo video hits a nerve (this category periodically goes viral);
press picks up the scan-your-room angle. Hundreds of thousands of downloads in year one;
5%+ conversion; **five-to-low-six-figures**, with a run-rate that could become a job
(~$7k–20k/mo at peak). The scan-import + text-to-3D Pro tier turns it from a wallpaper into
a *personal spatial platform*, justifying a subscription with real retention. The founder
plausibly goes full-time. **What's required:** shipping the scan moat, *and* a genuine viral
moment (partly luck, but consistency = more lottery tickets), *and* solving novelty-retention.
**Probability [ASSUMPTION]:** a real, non-trivial slice — far higher than for a typical
utility, *because the product self-demos* — but still a minority outcome.

### Exceptional Outcome Scenario — "a category, or an acquisition"
**What would need to happen.** The scan-your-room portal becomes a defining, press-defining
feature; IRIS becomes the reference product for ambient desktop spatial computing on Mac.
Either it sustains a large paying base (a creator ecosystem materializes, the catalog
flywheels, an iOS companion deepens the Apple-scan moat), or it attracts acquisition
interest from a company wanting the calibrated engine + Apple-spatial expertise + the brand.
**What's required:** everything in "Strong" *plus* durable retention, a real content
flywheel, and likely a second person/some capital to escape the solo bus-factor ceiling.
**Probability [ASSUMPTION]:** low — the genuine lottery-ticket tail. But it is a *real*
ticket (sharp insight, real moat), not a fantasy.

**Cross-scenario truth:** the downside is bounded at ~$150/yr and a finite stretch of
unglamorous work; the upside tail is unusually fat for this category; and the
skills/portfolio return is nearly guaranteed *the moment it ships and demos well*. The job
of "consistent execution" is to move probability mass from *Failure* → *Modest* and to keep
the founder holding tickets when a viral/press/B2B moment shows up.

---

## SECTION 11: Founder Reflection

> Execution-focused, honest, and constructive. Drawn from the documented record, not flattery.

### Strengths demonstrated
- **Exceptional engineering discipline.** A frozen, calibrated core protected by headless
  sims, with even *approved* changes gated by new sims (`sim_camlag`). This is senior-level
  rigor and the project's deepest asset.
- **Principled, often *subtractive*, problem-solving.** The "grids don't pan" resolution and
  the bloom removal show a founder who will *delete* complexity to reach the right answer,
  not just pile on.
- **Outstanding documentation & self-honesty.** A wiki, incident records (including for the
  founder's own missteps), and a productification doc that ranks its own catastrophic risks.
  The willingness to *write down* the portal-revert as an incident rather than hide it is rare.
- **Real product taste.** The camera-free magic moment, instant hover, the no-reset state
  machine — these are the instincts of someone who feels how software should *feel*.
- **Risk-awareness once surfaced.** Closed the catastrophic git gap; hardened the camera
  path properly rather than patching.

### Weaknesses demonstrated
- **A shipping gap.** Months of deep work; **zero external users; $0 earned; not launched.**
  The hardest 90% is done and the easy-but-boring 10% is unfinished. This is *the* pattern to confront.
- **Susceptibility to cosmetic churn.** The world→portal rename → revert → recovery created
  zero product value and orphaned real work. A signal that energy can flow to *feeling
  productive* (refactors, renames) over *being productive* (shipping).
- **Quietly narrowing scope without re-deciding.** The Intel-support promise lapsed into a
  liability without an explicit decision. Promises should be kept or *consciously retired*,
  not allowed to rot.
- **Gravity toward the exciting frontier.** The pull to design text-to-3D and scan import
  (genuinely cool) *before* launching risks making the mountain feel infinite — which feeds
  the motivation dip the founder is currently in.

### Opportunities currently available
- **A finite, mostly-boring runway to launch** (~weeks, not months) — the project is far
  closer to "real" than the founder's current motivation suggests.
- **A self-demoing product** in a category that periodically goes viral — an acquisition
  advantage most builders would kill for.
- **An Apple-ecosystem scan moat** that is both a genuine differentiator and a press hook.
- **Near-guaranteed portfolio/career value** the moment it ships and demos well, independent
  of revenue.

### Habits that should continue
- The frozen-core + validation-sim discipline. **Never stop running the sims before commit.**
- Writing down decisions and rationale (including failures).
- Subtractive problem-solving; principled "no" to scope (sphere creation, marketplace, panning grids).
- Protecting the magic-first onboarding.

### Habits that should stop
- **Polishing/refactoring/renaming in lieu of shipping.** No cosmetic renames; freeze the
  name (Section 5, Decision 11). Before any non-shipping task, ask: "does this move me toward
  one external user, or away?"
- **Building ahead of the launch line.** Put text-to-3D and scan import *down* until after a
  public launch. They are rewards for shipping, not prerequisites.
- **Letting scope promises rot silently.** Decide Intel (Section 5, Decision 5) explicitly,
  then move on.
- **Treating "more documentation" as progress.** The docs are already exceptional (95%);
  further documentation has steeply diminishing returns against the one thing that's missing:
  a shipped product. *(The irony that this very document is more documentation is noted —
  its job is to make the remaining distance finite and legible, then get out of the way.)*

### The one-sentence reflection
The founder has already done the hard, rare, defensible part — and is one short stretch of
unglamorous work away from letting it touch another human being; the entire game now is
**finishing, not building.**

---

## Appendix: Confidence & Assumptions Ledger

- **High confidence (grounded in project records/git):** development history, technical
  architecture, what's built vs. unbuilt, the frozen-core discipline, the gaps in
  distribution/monetization/telemetry, the portal-rename incident, current build state (v1.5,
  arm64, ad-hoc signed, World Builder authoring UI built and unlaunched).
- **Medium confidence (reasoned from evidence):** completion percentages in Section 4,
  risk rankings, the recommendation set in Section 5.
- **Explicit assumptions (tagged [ASSUMPTION] inline):** the true early-adopter beachhead;
  the motives behind the portal rename and its revert; all financial figures and probabilities
  in Section 10; investor-framing language. These are *judgments*, not records — pressure-test
  them with real launch data.
- **The biggest single unknown:** post-launch *retention* of an ambient novelty app. No data
  exists yet; it is the hinge between the Modest and Strong scenarios and the first thing
  telemetry should measure.

> **How to use this document.** Re-read Sections 6, 7, and 9 before each work session as a
> compass; update Section 4's percentages and Section 10's probabilities as real data
> arrives; and treat Section 11's "habits that should stop" as the standing check on where
> the next hour of effort goes.

## Related

[[productification]] · [[Handover]] · [[version-history]] · [[current-focus]] · [[grid-creator-tool-plan]] · [[constraints]] · [[design-decisions]] · [[FINANCIAL_PROJECTION]]
