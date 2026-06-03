---
title: "2026-06-01 — Perf: Desktop-lag audit — frame-rate cap, gem-floor geometry, state-write throttle"
type: log-entry
date: 2026-06-01
category: perf
---

# Desktop-lag audit — frame-rate cap, gem-floor geometry, state-write throttle

**Trigger.** "Running IRIS makes opening other apps lag, desktop feels sluggish,
CPU looks high." Physics was the prime suspect; the brief asked for an
evidence-driven audit before any rewrite.

**Method.** Wiki-first: read [[engine-loop-and-daemon]], [[rendering-engine]],
[[head-tracking]], [[constraints]], [[known_issues]] before source, then read the
hot paths (`app_engine.py` main loop, `renderer.py`, `bloom_postfx.py`,
`camera_math.py`, `face_tracker.py`). **Measured** the CPU-side per-frame work in
the venv rather than guessing.

**Findings (evidence).**
- **There is no physics engine.** `camera_math.py` is pure matrix algebra —
  measured **6.9 µs/frame**. No collision/raycast/rigid-body work runs in the loop
  (`segment_hits_sphere` is only the *separate* icons app's hit-test). Suspicion
  retired.
- Total CPU-side main-loop overhead **~68 µs/frame** (~4 ms/s): state-file write
  **55 µs** (synchronous disk I/O, the largest), matrices 7 µs, flag stats 5 µs,
  prefs stat 1 µs. **CPU is not the bottleneck.**
- MediaPipe: 1.6 ms with no face / ~34 ms with a face (per [[head-tracking]]), on
  its own thread at ~30 Hz — real but secondary and necessary.
- **Root cause = a full-screen, native-Retina wallpaper rendered at 60 fps while
  the head input is only ~30 Hz.** Half the frames are duplicate-input redraws,
  and as a desktop-level layer the macOS WindowServer must recomposite it under
  every other window every frame (M2 runs GL translated to Metal). That is the
  desktop stutter.
- Active world at audit time was **[[the-gem]]**, whose checkered floor — a flat,
  unlit plane — was over-subdivided to **60×60 = 21,600 verts re-streamed every
  frame** through the client-side-array path.
- Per-frame `glGetFloatv(GL_MODELVIEW_MATRIX)` pipeline stalls: 1 in
  `_view_rot_3x3` + 1 per icon in `IconOrbit.draw` ([[orbital-icons]]).

**Changes shipped (low-risk, behaviour-preserving).**
- `Launcher/app_engine.py`: added `FPS_DEMO = 60` / `FPS_WALLPAPER = 30`;
  `clock.tick()` now caps wallpaper/fullscreen/`desktop_active` to 30 fps
  (demo stays 60). ~halves GPU + compositor load — **the primary fix**.
- `Engine/renderer.py` (`Gem`): `_FLOOR_DIVS 60 → 1` (21,600 → **6 verts**;
  perspective-correct UV interpolation makes a 2-triangle plane pixel-identical)
  and `_FLOOR_TILE 1.0 → 10.0` (checks ~10× larger — they read far too small).
  *(The larger checks were a user request that matched the profiling.)*
- `Launcher/app_engine.py`: `~/.parallax_earth_state.json` export **throttled to
  ≤30 Hz** (was a synchronous write every frame of values that only change at
  ~30 Hz).

**Recommended next (not done — would exceed "low-risk").** Replace the per-icon
`glGetFloatv` with a CPU-built billboard matrix (pass the modelview into
`IconOrbit.draw`); migrate static meshes (Earth spheres, stars, nebula) to VBOs;
optionally drop MSAA 4×→2× / increase bloom downscale in wallpaper mode.

**Industry grounding.** Avoid `glGet*` round-trips (Khronos: pipeline stall);
prefer VBOs over client-side arrays (OpenGL Wiki); match render rate to
input/sim rate; minimise compositor pressure for desktop-level layers.

**Validation.** `ast.parse` clean on both edited files; floor mesh re-derivation
confirms 6 verts and correct `GL_REPEAT` UVs (960 checks across the floor);
changes are localized. Live GPU-profiler confirmation needs a GUI session (same
constraint as all renderer work — see [[constraints]]).

**Wiki updated.** [[constraints]] (frame-rate caps + new "Performance posture"),
[[engine-loop-and-daemon]] (frame-rate section + throttled state export),
[[the-gem]] (floor plane description + fully-procedural note), [[current-focus]]
(perf entry), and this log entry.
