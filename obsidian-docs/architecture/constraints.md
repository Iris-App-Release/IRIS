---
title: Constraints & Performance Limits
type: architecture
related:
  - off-axis-projection
  - head-tracking
  - rendering-engine
  - engine-loop-and-daemon
  - dmg-build-process
  - asset-pipeline
  - design-decisions
  - system-interactions
last_updated: 2026-06-01
sources:
  - Engine/camera_math.py
  - Tracking/face_tracker.py
  - Launcher/app_engine.py
  - Engine/bloom_postfx.py
  - Engine/renderer.py
  - Build/build_dmg.sh
  - Docs/IRIS_OVERVIEW.txt
---

# Constraints & Performance Limits

The hard limits, calibrated values, and platform quirks discovered building IRIS.
These are the boundaries the design lives inside; many are enforced or protected
by [[headless-simulation]].

## Viewing geometry

- **One true viewing distance.** The off-axis parallax is geometrically exact
  only at the neutral eye distance (`CAM_BASE_Z = 11.5` world units, tuned for
  ~600 mm / forearm length). Further away the perspective is slightly off — this
  is physics-accurate, not a bug; users learn the "sweet spot." See
  [[off-axis-projection]].
- **Distance range.** Head depth `hz ∈ [−0.7, +1.0]` maps to eye distance
  `cz = 11.5·e^(0.95·hz)`, clamped to `[5.0, 34.0]`. Lateral shift gain
  `MAX_SHIFT = 4.5` (vertical ×0.55).
- **Rotation gains.** Yaw pan max 20°; vertical pan gain 40° hard-clamped to 46°
  (anti-nausea); proximity gate fades rotation in over `hz ∈ [0.0, 0.8]`; a
  proximity-scaled `LOOK_PITCH_OFFSET = 0.25` re-zeroes the resting gaze onto the
  planet (the webcam sits above the screen). See [[engine-loop-and-daemon]].

## Latency & frame rate

- **Tracking ~30 fps** (MediaPipe VIDEO mode: ~34 ms mean / 68 ms p95). IMAGE
  mode was ~76/182 ms — rejected.
- **Render caps: 60 fps demo / 30 fps wallpaper+fullscreen+desktop-active**
  (`FPS_DEMO` / `FPS_WALLPAPER` in `app_engine.py`). The head input updates at
  only ~30 Hz, so a 60 Hz wallpaper redrew every parallax frame *twice* from
  identical head data — wasted GPU + WindowServer compositing that was the main
  cause of "opening other apps stutters." The interactive onboarding demo keeps
  60 fps for crisp cursor/hover feedback. End-to-end head-to-pixel latency
  ~30–50 ms (perceptually invisible). See [[engine-loop-and-daemon]] and the
  2026-06-01 perf pass in [[log]].
- **Decoupled threads.** Tracking runs in a daemon thread; the render loop reads
  the latest head value without blocking, so tracking lag never drops frames.
- **Camera buffer = 1 frame** so `read()` never returns a stale frame (macOS may
  ignore the hint). See [[head-tracking]].
- The priority is explicitly **latency/stability over accuracy** — smooth at the
  capped rate beats precise-but-jittery (see [[design-decisions]]).
- **`CAM_LAG` smoothing is frame-rate dependent (known latency quirk).** The
  engine's second smoothing layer (`cam_x += CAM_LAG·(target − cam_x)`, etc.,
  `CAM_LAG = 0.55`) is applied **per frame, not dt-normalised**, so its
  time-constant scales with frame rate: ~57 ms to 90 % at the 60 fps demo but
  **~113 ms at the 30 fps wallpaper/desktop cap**. The illusion therefore feels
  measurably laggier once Desktop Mode drops to 30 fps. This sits on top of the
  tracker's own (frozen) velocity-adaptive lerp and MediaPipe's ~34 ms/68 ms p95.
  `CAM_LAG`/smoothing is **frozen physics** — making it dt-aware is the right fix
  but needs explicit approval and a fresh `sim_latency` guard. See the 2026-06-01
  audit in [[log]].

## Performance posture (it is a *wallpaper*)

IRIS is a desktop-level layer that the macOS WindowServer must composite under
every other window, so per-frame render cost is a *system-wide* tax, not just an
in-app one. The boundaries that keep it cheap:

- **Match render rate to input rate** (30 Hz, above) — the single biggest lever;
  it ~halves GPU + compositor load with no visible parallax change.
- **No per-frame `glGet*` in principle.** `glGetFloatv(GL_MODELVIEW_MATRIX)`
  forces a GPU→CPU pipeline stall. The two that remained were removed on
  2026-06-01: `_view_rot_3x3` now slices the CPU-built `mv` matrix
  (`view_rot = mv[:3,:3]`), and `IconOrbit.draw` ([[orbital-icons]]) now reads the
  modelview **once** and builds each billboard on the CPU (per-icon read-back
  gone — N stalls/frame → 1). Both are pixel-identical to the read-back. Do not
  reintroduce a `glGet*` in the per-frame path.
- **Keep streamed geometry small.** All meshes use client-side vertex arrays (no
  VBOs), re-uploaded every frame, so vertex count is a direct per-frame cost. The
  [[the-gem]] floor was a flat plane over-subdivided to 21,600 verts; it is now 6
  (`_FLOOR_DIVS = 1`) — pixel-identical, since perspective-correct UV
  interpolation handles the convergence.
- **State export is throttled to ≤30 Hz** (`~/.parallax_earth_state.json`) —
  writing faster just re-serialised identical 30 Hz head data to disk in the
  render thread.

## Camera & permissions (macOS)

- **Single AVFoundation owner** at a time — the camera must be released by one
  consumer before another opens it (drives the demo↔daemon handoff).
- The macOS camera (TCC) prompt **only appears** for a properly bundled `.app`,
  **with a valid code signature**, launched from the GUI — never from a bare
  `python …` (no bundle identity → auto-denied). So live camera behaviour is only
  testable from the built app in a real session.
- **A valid code signature is mandatory.** macOS TCC *silently denies* the camera
  to an app whose signature is invalid (no prompt; auto-deny in tens of ms). The
  build must therefore re-sign the bundle **after** any `Info.plist` edit — see
  [[dmg-build-process]]. This was the 2026-05-31 "Live, but no tracking" root
  cause ([[known_issues]]).
- Authorization is settled **on the main thread** in `start()` via
  `request_camera_access()` (which pumps the run loop for the dialog), and
  `OPENCV_AVFOUNDATION_SKIP_AUTH=1` stops OpenCV from issuing its own request from
  the worker thread (where it "cannot spin main run loop from other thread").
- `NSCameraUsageDescription` is **required**, and the bundle id must be **stable**
  across rebuilds (`com.iris.parallaxwall`). Note ad-hoc signatures change each
  rebuild, so the grant may still need re-approval after a fresh build until a
  Developer ID signature is used. See [[dmg-build-process]].

## Graphics

- **OpenGL 2.1 / GLSL 120 only** — the compatibility profile shared by old Macs
  and Apple-Silicon Metal-translated GL. Shaders rely on fixed-function matrix
  uniforms; client-side vertex arrays (no VBOs).
- Renders at the **native Retina drawable** size (read from the live GL
  viewport), not the window size.
- **Anti-bloom alpha convention:** objects that must stay crisp (orbital icons,
  the eye) write `alpha = 0` so the bloom bright-pass skips them. Bloom params:
  threshold 0.68, half-res downscale, exposure 1.22 (see [[rendering-engine]]).
- Scene scale anchors: Earth surface `R = 2.6`, clouds 2.625, atmosphere 2.85,
  Earth/Eye at world `z = −10`, nebula shell `R = 95`, orbit ring radius 4.2 at
  63° tilt.

## Platform

- **macOS only.** Desktop-level window pinning, Dock hiding, click-through, and
  camera all use Cocoa/Quartz/AVFoundation (PyObjC). Non-Mac falls back
  gracefully but loses the wallpaper/camera behaviours.
- Builds are **arm64-only** (built on Apple Silicon); macOS 10.13+ for MediaPipe.
- **No code signing / notarization** → Gatekeeper warns on other Macs.
  Single-user / personal-use posture. See [[distribution-checklist]].

## Memory (8 GB M2 target)

- The machine is memory-constrained, so:
  - Asset-generation tools are fully **vectorised** (no large per-pixel Python
    loops) — an earlier `make_earth_icon.py` OOM-killed at 2048² in pure Python.
    See [[asset-pipeline]].
  - The PyInstaller build is RAM-hungry (~2–3 min, large bundle); build with
    little else running. See [[dmg-build-process]].
  - Icon textures (~10 × 256² RGBA ≈ 2.6 MB) are comfortably within budget.

## Filesystem

- **Case-insensitive macOS** means PyInstaller's default `./build` work dir
  collides with the source `Build/` folder; the build uses `.pyi_work` instead.
  This collision once deleted the original `parallaxctl.py` (now reconstructed at
  the project root). See [[dmg-build-process]] and [[daemon-control]].
- Resource paths are resolved tolerating both source casing (`Worlds/`, `assets/`)
  and the lowercase layout PyInstaller bundles.

## Content

- A world's `primary_mesh` must map to an existing renderer class (`earth` →
  `Earth`, `eye` → `Eye`); new looks need renderer + shader work, not just JSON.
  See [[world-system]].

## Eye tracking (The Watcher)

- **Gaze range:** ±15° horizontal (yaw), ±10° vertical (pitch). These are the
  realistic limits of natural eye rotation before the look appears forced. Clamped
  before the lerp so overshooting is never possible even on very fast head moves.
- **Gaze smoothing:** `GAZE_LERP = 0.10` per frame (~0.3 s to 90% of target at
  60 fps). Head tracking is already pre-smoothed, so this is a *second* layer that
  gives movement its organic, deliberate quality.
- **No performance cost:** The gaze update is two lerp operations and two clamp
  operations per frame; entirely negligible. No additional GPU work.
- **Drift preserved:** The existing ±1.6° gaze drift sinusoids are preserved and
  blended on top of the tracked gaze angle. Both contribute to the final
  `glRotatef` call so neither is lost.
- **Haar fallback:** If MediaPipe is unavailable (Haar cascade), `hx`/`hy` still
  come from face bounding-box position, so eye tracking degrades gracefully to
  position-only (no head-orientation input needed for gaze).

## Related

[[design-decisions]] · [[system-interactions]]
