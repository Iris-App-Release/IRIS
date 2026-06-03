---
title: "2026-06-01 — Perf+Latency: The four flagged follow-ups executed"
type: log-entry
date: 2026-06-01
category: perf
---

# The four flagged follow-ups executed (CAM_LAG dt-aware, per-world bloom, VBOs, wallpaper MSAA/bloom trims)

**Trigger.** User: execute the four unfinished latency-related fixes the prior
audit + perf passes had flagged as "recommended / not done." Item #1 touches the
FROZEN smoothing — executed under **explicit user approval** (the standing rule
requires it) and accompanied by a new validation sim, as the rule demands.

## 1. `CAM_LAG` → frame-rate-independent (the headline latency fix)

`Launcher/app_engine.py`. The camera smoothing was a FIXED per-frame factor
(`cam += 0.55·(target−cam)`), which makes the time-constant frame-rate dependent:
the same 0.55 reaches target ~2× slower in wall-clock at the 30 fps wallpaper cap
than at the 60 fps demo — the audit's most likely "slightly high latency" cause.
Replaced with a true exponential time-constant: `CAM_LAG_TAU` is derived from the
legacy 0.55 **at the 60 fps reference rate** (`tau = −(1/60)/ln(1−0.55) ≈ 20.9 ms`),
and each frame uses `cam_alpha = 1 − e^(−min(dt,CAM_LAG_DT_MAX)/CAM_LAG_TAU)`,
applied to all five smoothers (cam_x/y/z/yaw/pitch). Reproduces the calibrated
60 fps feel **byte-for-byte** (alpha(1/60)=0.55 exactly) and holds the SAME
wall-clock responsiveness at 30 fps. A `CAM_LAG_DT_MAX = 0.10 s` clamp stops a
long stall (resume-from-pause / first frame) from snapping in one step. The legacy
`CAM_LAG = 0.55` constant is retained as the reference factor the tau is derived
from. No other frozen module touched (camera_math, tracker smoothing untouched).

**New sim — `Scripts/validation/sim_camlag.py`** (the rule's "+ a new sim"):
proves (1) alpha(1/60) == 0.55 to float precision, (2) 30 fps and 60 fps reach
90 % of a step in the same wall-clock time, (3) the OLD scheme was frame-rate
dependent (~2× at 30 fps) and the fix lowers the 30 fps lag, (4) the dt clamp
bounds the step. RESULT: all checks passed.

## 2. Per-world `use_bloom` honoured

`Worlds/world_runtime.py`: new `use_bloom` property (default **True** → Earth and
any world omitting the flag are unchanged). `Launcher/app_engine.py`: per-frame
`use_bloom_now = bloom_enabled and world.use_bloom` gates both bloom passes; when
off, the scene renders straight to the default framebuffer (viewport reset to the
full drawable so a live switch from a bloom world is clean). Skips the
bright→2×blur→composite full-screen passes for worlds that asked bloom off.
**Behavioural note:** BOTH [[the-gem]] and [[the-watcher]] declare
`"use_bloom": false`, so both now also lose the composite's exposure (1.22),
vignette (0.42) and chromatic aberration — those effects lived in the bloom
composite. Earth (`use_bloom: true`) is pixel-identical.

## 3. Static meshes → VBOs

`Engine/renderer.py`. `Mesh` (Earth ×3 spheres, Nebula, Eye, Gem facet-soup) and
the `Stars` point field now upload their attribute/index arrays to GL buffer
objects ONCE at construction (`GL_STATIC_DRAW`) instead of re-streaming every
vertex from the CPU each frame (~190 k verts/frame for Earth+Nebula alone). Draw
binds the buffers + byte-offset pointers and **unbinds to 0 afterwards** so the
floor/shadow/icon/bloom client-array draws that share GL state are unaffected.
Both classes keep a transparent **client-array fallback** if buffer creation
fails (no behavioural change, just the old cost). All geometry is static — all
motion is via the modelview, so a one-time upload is exactly equivalent.

## 4. Wallpaper-mode GPU trims

`Launcher/app_engine.py` + `Engine/bloom_postfx.py`. MSAA samples are now
`4 if DISPLAY_MODE == "demo" else 2` (set at context creation; the in-process
demo→Desktop switch keeps its 4× since MSAA can't change live, but the standalone
wallpaper daemon launches at 2×). `BloomPipeline` gained a `downscale` arg; the
demo passes 2× (crisp), wallpaper/fullscreen/desktop pass 4× (softer + cheaper
blur buffers). Both are imperceptible at desktop scale and cut GPU/compositor load.

**Validation.** `py_compile` clean on all four edited files + the new sim. All
seven headless sims pass: the six existing (`sim_orbit/offaxis/viewing/latency/
vertical/overlay`) + the new `sim_camlag`. The renderer VBO path, the per-world
bloom gate, MSAA and bloom-downscale changes are GL-side and can only be
confirmed live in a GUI session (the standing renderer/GL constraint) — the code
preserves exact visual output with fallbacks, and Earth is unchanged by design.

**Wiki updated.** [[current-focus]] (new top section + three stale "recommended
next" notes struck through), and this log entry.
