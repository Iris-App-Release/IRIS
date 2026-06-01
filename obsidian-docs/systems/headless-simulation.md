---
title: Headless Simulation (Validation Harness)
type: system
related: [off-axis-projection, head-tracking, ui-overlay, orbital-icons, constraints, design-decisions]
last_updated: 2026-05-31
sources: [Scripts/validation/sim_offaxis.py, Scripts/validation/sim_viewing.py, Scripts/validation/sim_orbit.py, Scripts/validation/sim_latency.py, Scripts/validation/sim_vertical.py, Scripts/validation/sim_overlay.py]
---

# Headless Simulation (Validation Harness)

## Purpose

The headless sims are how IRIS keeps its "frozen physics" honest. The camera
math, input smoothing, orbital geometry, vertical exploration, and overlay state
machine are all delicate — months of calibration that any later change can
silently break. These six scripts in `Scripts/validation/` re-prove the expected
behaviour **without a GPU, a webcam, or a display**, so the invariants can be
checked instantly (and in CI) instead of by eyeballing the live app.

The defining design choice: each sim imports and drives the **exact same**
modules the live engine uses ([[off-axis-projection]], [[head-tracking]],
[[ui-overlay]]) — not a reimplementation. So a passing sim guarantees the *real*
render path behaves correctly; the live picture can't drift from the verified
math.

## Shared conventions

- Pure Python + numpy; no OpenGL, no camera, no window (the overlay sim uses
  SDL's `dummy` video driver and a temp config dir so it never touches `~/.iris`).
- A tiny `check(name, ok, detail)` helper prints `[PASS]`/`[FAIL]` per assertion.
- **Exit code 0 = all checks pass, 1 = something failed** — CI-friendly.
- Run any of them with the project interpreter, e.g.:
  `.venv/bin/python Scripts/validation/sim_offaxis.py`

## The six sims

### `sim_offaxis.py` — off-axis "window" projection
Proves the projection behaves like a real window into a fixed scene, not a panned
camera. Checks: a centred eye at `CAM_BASE_Z` reproduces `perspective(FOVY_DEG)`
exactly; the modelview is pure translation (no tilt-to-target); aperture parallax
(farther objects sweep the frame faster — the window rule); FOV depends only on
eye-to-glass distance (monotone); continuity/finiteness across the whole clamped
distance range; and the window corners always land on the frustum edges (it is
literally a hole).

### `sim_viewing.py` — the three-component viewing model
Proves translation, distance scaling, and rotation behave as independent, blended
channels. Checks: distance scaling isn't inverted (leaning in makes the Earth
*bigger*); translation parallax is strong far / reduced close / never zero;
rotation is proximity-gated with a smooth C¹ ramp; rotation sense is *opposite* to
translation (turn right reveals the right, move right reveals the left); each
input drives only its own channel; and the Earth stays finite under a combined
jittery sweep.

### `sim_orbit.py` — orbital-icon geometry
Proves the in-scene orbital icons ([[orbital-icons]]) are a rigid body with the
Earth. Checks: icon world-delta equals Earth world-delta for all ring angles (+
non-zero screen parallax); real occlusion (the top arc passes behind the globe,
the bottom and sides in front); the ring always clears the atmosphere shell;
projection sanity (occluded icons fall inside the Earth's screen disk, side icons
outside); near icons render larger than far; and positions stay finite/continuous
under a jumpy camera (the failure mode of the old two-process overlay).

### `sim_latency.py` — velocity-adaptive smoothing
Drives the real `FaceTracker._resp_boost` and `_LERP_`/`_RESP_` constants
([[head-tracking]]) on synthetic traces at 30 fps. Checks: at rest the adaptive
filter equals the old fixed lerp (adds **no** new jitter); during a fast move it
reaches 90% of the target meaningfully sooner (≈25%+ lower lag) without
overshoot; the boost is monotonic in speed and bounded to `[base, ceil]`; and the
rotation channel gets the same rest-safe / lower-lag guarantees.

### `sim_vertical.py` — near-field vertical exploration
Replicates the engine's exact pitch pipeline (planet-anchor offset → separate 40°
vertical gain → 46° pan clamp → proximity gate; see [[engine-loop-and-daemon]]).
Checks: far away, pitch barely moves the Earth; up close, a strong downward gaze
pushes the Earth off the bottom and an upward gaze off the top; a neutral gaze
resting on the planet stays centred; pitch never bleeds into horizontal motion;
and the reveal ramps smoothly far→near with no pop.

### `sim_overlay.py` — demo overlay state machine
Exercises the pure-logic layer of [[ui-overlay]] under the dummy SDL driver.
Checks the full state flow (floating default → Enable Camera → live → Enable
Desktop → floating + daemon → pause/resume), reopen routing when a daemon is
already running (no onboarding reset), bounded scripted idle motion, hit-testing
at scaled coordinates, and that `render_surface()` returns a physical-resolution
RGBA surface with content and is cached when nothing changes.

## Dependencies

- **Exercise:** [[off-axis-projection]] (offaxis, viewing, orbit, vertical),
  [[head-tracking]] (latency), [[ui-overlay]] (overlay), [[orbital-icons]] (orbit).
- **Protect:** the calibration documented in [[constraints]] and the rationale in
  [[design-decisions]].
