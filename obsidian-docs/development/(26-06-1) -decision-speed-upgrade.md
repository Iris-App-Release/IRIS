---
title: 7/1/26 — Decision to Implement Genuine Speed Upgrade
type: decision
related: [head-tracking, engine-loop-and-daemon, constraints, current-focus, headless-simulation, ui-overlay]
last_updated: 2026-06-01
sources: [Tracking/face_tracker.py, Tracking/filters.py, Launcher/app_engine.py, Engine/camera_math.py, Engine/renderer.py, Scripts/validation/]
---

# 26/06/1 — Decision to Implement Genuine Speed Upgrade

**Status:** Tier 1 items 1 & 2 complete & validated (2026-06-02). Item 3 (merge the
two smoothing stages) next. See execution log at the bottom.

## Context

The app feels increasingly laggy and jittery, and the parallax "physics" don't
feel fully nailed. A full re-architecture into a **C++/Metal native core +
Python/JSON scripting layer** (the Unreal/Unity/visionOS split) was proposed. This
doc records the evaluation of that proposal and the chosen path.

## Evidence (already measured in this repo, 2026-06-01 audit)

- **There is no physics engine.** `Engine/camera_math.py` is pure numpy 4×4 matrix
  algebra — measured **6.9 µs/frame**. No collision/raycast/rigid-body. What feels
  like "physics" is the **smoothing/tuning**, not computation.
- Total CPU main-loop overhead **~68 µs/frame** = **0.4% of a 16.7 ms frame**. Even
  infinitely fast Python saves 0.4%.
- **MediaPipe face inference ~34 ms mean / 68 ms p95** (VIDEO mode, ~30 Hz, own
  thread). This is native C++ already.
- Render is trivial: ~6 draw calls, ~190k verts, VBOs. Not CPU/GPU bound.
- Logged root cause of desktop sluggishness: a **full-screen native-Retina
  wallpaper composited by macOS WindowServer** under every window, at 60 fps vs a
  ~30 Hz input.

**Lag** ≈ 100–180 ms motion-to-photon, dominated by **MediaPipe inference** +
**two smoothing stages** (tracker lerp + engine `CAM_LAG`) + capture/display — not
by Python. **Jitter** = MediaPipe landmark noise (a *filtering* problem) + GIL/GC
frame-time variance (a *scheduling* problem) + WindowServer compositing (a
*platform* property).

## Decision

**Do NOT do the full native rewrite now.** It targets components that aren't the
bottleneck (projection math = 6.9 µs, "core" loop = 0.4% of frame), leaves the real
bottleneck untouched (**MediaPipe is already native** — a C++ port does not speed
up the 34 ms inference), and would cost months at high risk (re-deriving the
calibrated off-axis camera math, re-doing the macOS TCC camera dance natively,
invalidating the six headless validation sims) for an estimated **~10 % latency
gain**. The hybrid model's own principle says: *don't port the core until profiling
proves the core is hot — it isn't.* We already have the "scripting layer" (world
system, UI, config in Python/JSON with live hot-reload).

Instead, pursue the tiered plan below. **Decision rule: measure first; only port
the specific stage the profiler proves is hot.**

---

## Tier 1 — Days, pure Python, addresses the real symptoms

1. **Predictive head tracking** — extrapolate head position forward by the measured
   pipeline latency using velocity, to *hide* 80–120 ms of lag. The single biggest
   perceptual win; just math in the tracker. *(EXECUTING NOW.)*
2. **Better jitter filter** — replace the hand-rolled velocity-adaptive lerp's
   residual passthrough with a proper **One Euro filter** (low cutoff at rest →
   less jitter; cutoff rises with speed → low lag). Kills jitter without adding
   lag. *(EXECUTING NOW.)*
3. **Tune / merge the two smoothing stages** — smoothing exists in *both* the
   tracker and the engine's `CAM_LAG`. Collapsing to one well-tuned stage is the
   highest-leverage "feel" fix and is free. *(Next.)*

## Tier 2 — Moderate, still mostly Python

4. **Run MediaPipe in a separate process** (not thread) — eliminates GIL contention
   with the render loop → smoother frame pacing. Removes a real jitter source while
   keeping Python.
5. **Swap face tracking to Apple's Vision framework** (`VNDetectFaceLandmarksRequest`)
   via the already-bundled pyobjc — Metal/Neural-Engine accelerated at **~5–10 ms
   vs MediaPipe's ~34 ms**, roughly halving fresh-data latency, from Python. Biggest
   single latency lever available.

## Tier 3 — Future-proofing, genuinely native but targeted

6. **Metal rendering layer** — worth doing *eventually* because macOS OpenGL is
   deprecated and will break someday. But this is a **rendering migration** (can
   keep Python via Metal bindings), about longevity, **not** today's lag. It is NOT
   the "C++ core + Python scripting" re-architecture; the WindowServer composite
   cost is largely API-independent for a fullscreen desktop layer.

---

## Execution log

_(Updated as Tier 1 lands.)_

### 2026-06-02 — Tier 1.1 + 1.2 landed (predictive tracking + jitter filter)

**Status:** Tier 1 items 1 & 2 **complete and validated**. Item 3 (merge the two
smoothing stages) is the next step.

**What shipped**

- `Tracking/filters.py` — `OneEuroFilter` (adaptive low-pass + clean velocity) and
  `gated_predict` (velocity-gated forward extrapolation, identity at rest, clamped).
- `Tracking/face_tracker.py` — the 1€ filter is the final per-channel conditioning
  stage in `_publish`; `head()` extrapolates `value + velocity·lead` forward to hide
  pipeline latency. Filters live only on the worker thread; the lock guards just the
  published scalars + velocities + timestamp.
- `Scripts/validation/sim_predict.py` — new headless sim proving the latency/jitter
  trade. Runs alongside the other seven sims; **all 8 pass**.

**The overshoot bug and its real root cause (correcting the interrupted session)**

The interrupted 06-01 session left one failing check: a **post-stop overshoot of
0.127 units (42 % of the move)** and hypothesised the fix was to **raise
`_EURO_D_CUTOFF`** (velocity "decaying too slowly"). Verified against the sim — that
hypothesis is **wrong**: sweeping `d_cutoff` up made the overshoot *worse*
(0.127 → 0.159) while barely moving lag.

Frame-by-frame tracing found the true cause: the `OneEuroFilter` computed its
derivative as `(raw − filtered_prev)`. While the position low-pass is catching up
*after the head has already physically stopped*, that gap keeps the velocity
estimate pinned near its peak (≈2.4 u/s in the sim) — so the predictor extrapolates
a stale-high velocity into a large overshoot. `d_cutoff` can't fix it because the
velocity is inflated by the *position* filter's lag, not by derivative smoothing.

**Fix:** switch to the **canonical 1€ derivative** — difference of **raw samples**
`(x − x_raw_prev)` (Casiez 2012), so the velocity drops the instant the input stops.
Plus `_EURO_BETA`/`_EURO_BETA_ROT` 0.6 → 1.5 (position cutoff tracks faster in
motion; zero effect at rest, so rest jitter is unchanged).

**Measured result (sim_predict @ 30 Hz):**

| metric | before | after | check |
|---|---|---|---|
| post-stop overshoot | 126.6e-3 | **1.2e-3** | < 60e-3 ✓ |
| motion lag (predicted vs filtered-only) | 200 ms* | 233 vs 333 ms (100 ms sooner) | ✓ |
| rest jitter (1€ vs old lerp) | — | 0.00105 vs 0.00204 (≈half) | ✓ |
| 0.5 Hz sinusoid amplitude | 0.396 (amplified) | **0.288** (not amplified) | ✓ |

\* the old "200 ms" reach was itself the predictor blowing *past* the target then
settling back — i.e. the rubber-band we just removed. The honest 233 ms with zero
overshoot is the better feel.

`_PREDICT_LEAD` stays the primary live-calibration knob (0.070 s). The protected
`sim_latency.py` invariants (`_resp_boost` + the `_LERP_/_RESP_` constants) were not
touched and still pass.
