# PERFORMANCE_ROADMAP.md

**Phase 12 — Performance Roadmap**
Optimizations ranked for **maximum gain / minimum change**. Every "Expected
saving" is anchored to a measured number (file cross-refs in brackets). Apple M2
baseline; gains are larger on weaker Macs.

Baseline measured state:
- Cold start ≈ **3.1 s** (1.09 s imports [IMPORT] + ~2.0 s scene build [ASSET]).
- Resident memory ≈ **1,073 MB** (Earth world) [MEMORY].
- Frame: **231 fps** Earth / **460 fps** Grid Room, vs 30 fps cap [FRAME_TIMING].
- Continuous idle background I/O: 30 Hz disk write + 1 Hz rescan [BACKGROUND].

---

## PRIORITY 1 — do these first (high impact · low risk · low effort)

### P1.1 — Lazy-build Earth / Nebula / Stars per active world
- **Cross-ref:** MEMORY §3, ASSET §3, BOTTLENECK #1/#2
- **Description:** `app_engine.py:380-383` builds `Nebula()`, `Stars()`, `Earth()`
  unconditionally. Make them lazy like Eye/Gem/Room — construct on first draw,
  gated on `world.primary_mesh`/`world.background`. Earth-bearing worlds unchanged;
  Grid Room / Gem / Watcher skip them.
- **Expected saving:** **up to −727 MB RAM** (Earth) **+ −147 MB** (Nebula) for
  non-Earth worlds [MEMORY §1]; **−~2.0 s cold start** for those worlds [ASSET §2].
- **Difficulty:** Low (mirror the existing lazy pattern; ~20 lines).
- **Risk:** Low — first-draw guard already proven for 4 other meshes; falls back to
  Earth on failure as elsewhere.

### P1.2 — Stop mediapipe pulling matplotlib + sounddevice
- **Cross-ref:** IMPORT §3.1/§4, RUNTIME_MAP §1, BOTTLENECK #3
- **Description:** `import mediapipe` eagerly loads
  `tasks.python.vision.drawing_utils`→`matplotlib.pyplot` (395 ms) and
  `tasks.python.audio`→`sounddevice` (159 ms), **neither used by IRIS** (verified 0
  refs). Two options: (a) **lazy-import mediapipe inside `FaceTracker.start()`** so
  a camera-off/pre-grant launch pays 0 ms and the rest defer to worker start; and/or
  (b) import only the needed `mediapipe.tasks.python.vision` symbols / shim out the
  matplotlib+sounddevice submodules before importing mediapipe.
- **Expected saving:** **−0.4 to −0.55 s startup** [IMPORT §1]; also trims part of
  mediapipe's +36.7 MB RSS [MEMORY §1].
- **Difficulty:** Low (option a is moving one import); shim (option b) slightly more.
- **Risk:** Low — landmarker still builds on the worker thread as today.

### P1.3 — Skip the 30 Hz state-file write when no consumer
- **Cross-ref:** BACKGROUND §2/§4, BOTTLENECK #5
- **Description:** `EARTH_STATE_FILE.write_text(...)` runs 30×/s to feed the
  *separate* `orbital_icons.py` process. Gate it on that process/overlay being
  present (e.g. skip when `~/.parallax_icons_off` exists or no reader PID).
- **Expected saving:** removes **30 synchronous SSD writes/s** for the common case
  (icons overlay not installed); reduces idle wakeups/power.
- **Difficulty:** Low (one guard).
- **Risk:** Low (icons overlay simply uses last snapshot; it already tolerates 30 Hz).

### P1.4 — Disable PyOpenGL auto error-checking in release builds
- **Cross-ref:** CPU §3, RENDER_AUDIT #1, BOTTLENECK #6
- **Description:** `glCheckError` runs 224×/frame. Set `OpenGL.ERROR_CHECKING=False`
  (+`ERROR_LOGGING=False`) before `import OpenGL.GL`, gated on a `not DEBUG` env so
  dev keeps checks.
- **Expected saving:** **−10 to −28 % of per-stage draw CPU** (measured: `primary`
  0.153→0.110 ms, `icons` 0.244→0.210 ms, `bg_nebula` 0.114→0.085 ms) [CPU §3].
  Frees main-thread CPU that competes with WindowServer.
- **Difficulty:** Low (2 lines + env gate).
- **Risk:** Low — only suppresses checks in release; keep ON in dev.

**P1 total: ~−870 MB RAM, ~−0.5 to −2.5 s cold start (world-dependent), less idle
I/O and main-thread CPU — all reversible, isolated changes.**

---

## PRIORITY 2 — high impact, moderate effort / needs care

### P2.1 — Occlusion / display-sleep–aware render pause
- **Cross-ref:** BACKGROUND §3, BOTTLENECK #4
- **Description:** Observe `NSWindowOcclusionState` (and display-sleep / app-active)
  and drop to the master-pause path (sleep + stop drawing) when the wallpaper is
  fully covered or the display is asleep — instead of always rendering at 30 fps.
- **Expected saving:** eliminates GPU/compositor work when nothing is visible —
  directly targets the **"stutter when other apps open"** symptom [BACKGROUND §3]
  and idle battery draw. ~3 ms GPU/frame × 30 fps reclaimed when occluded.
- **Difficulty:** Medium (Cocoa observer + state machine; reuse existing pause).
- **Risk:** Medium — must reliably resume on re-expose; test multi-display/Spaces.

### P2.2 — Async / progressive Earth texture load
- **Cross-ref:** ASSET §5, CPU §2
- **Description:** Show the void/stars immediately; decode+upload the four 8K Earth
  JPEGs on a worker (or load a small mip first, then refine). Removes the ~2 s
  black-screen stall before first Earth frame.
- **Expected saving:** **−~2.0 s perceived launch** for Earth worlds [ASSET §2]
  (moves work off the critical path rather than eliminating it).
- **Difficulty:** Medium (GL uploads must happen on the GL thread; stage decode on
  worker, upload in small per-frame chunks).
- **Risk:** Medium — GL context threading; guard partial-texture frames.

### P2.3 — Right-size Earth textures (8K→4K or GPU-compressed)
- **Cross-ref:** ASSET §5, MEMORY §6, BOTTLENECK #8
- **Description:** 8192×4096 is over-spec for a ~2.6-unit sphere on a 5.6 MPix
  screen. Ship 4096×2048 (¼ memory + decode) or GPU-compressed `.ktx` (BC/ASTC,
  ~4–6× smaller VRAM, near-zero decode).
- **Expected saving:** **−~400 MB RAM** (4K) and **−~1.5 s** of the decode time
  [ASSET §2, MEMORY §2]; `.ktx` also slashes decode to a memcpy.
- **Difficulty:** Low-Med (asset pipeline + loader format).
- **Risk:** Medium — needs art/visual sign-off (the Earth is the hero asset).

---

## PRIORITY 3 — low impact / polish

### P3.1 — IconOrbit: pass CPU modelview instead of `glGetFloatv` readback
- **Cross-ref:** RENDER_AUDIT #2, BOTTLENECK #7 — removes 1 GPU→CPU stall/frame.
  Difficulty Low, Risk Low. Saving: small on M2, helps pipelining/weak GPUs.

### P3.2 — Throttle Orbital-Apps rescan 1 Hz → 5–10 s or FSEvents
- **Cross-ref:** BACKGROUND §4. Difficulty Low, Risk Low. Saving: removes ~1 fs
  scan/s.

### P3.3 — Reduce Nebula fillrate (full-screen quad / cubemap)
- **Cross-ref:** RENDER_AUDIT #4, FRAME_TIMING §2 — up to −0.5 ms/frame GPU
  [FRAME_TIMING §2]. Difficulty Medium, Risk Medium (art). **Low priority on M2.**

### P3.4 — Bundle/runtime hygiene
- **Cross-ref:** ASSET §4, MEMORY §5, RUNTIME_MAP §4. Set sampler uniforms once
  (RENDER_AUDIT #6); preallocate icon matrices (#3); drop unused `earth_normal.jpg`
  / Watcher `source/` / `milky_way_8k` fallback from the DMG; investigate removing
  cv2's bundled SDL2. All Low/Low; cosmetic runtime gain, smaller download.

---

## What NOT to do (evidence-based non-goals)

- **Do not optimize physics** — there is no physics engine; motion is 0.07 ms/frame
  closed-form [PHYSICS].
- **Do not micro-optimize the per-frame render compute** beyond P1.4/P3.1 — there is
  7–15× headroom on M2 [FRAME_TIMING].
- **Do not touch the tracking pipeline for speed** — it is off-thread and already
  tuned (VIDEO mode, queue-depth 1, predictive lead) [TRACKING].
- **Do not chase the "370 k lines"** — 343 k are in `dist/`; the live surface is
  8.3 k lines and the hot path is already well-engineered (VBOs, cached uniforms,
  mtime polling, readback elimination) [RUNTIME_MAP §0, RENDER_AUDIT].

---

## Expected end state after P1 (+P2.1)

| Metric | Before | After P1 (+P2.1) |
|---|---:|---:|
| Resident RAM, Grid Room/Gem/Watcher | ~1,073 MB | **~200–350 MB** (no eager Earth/Nebula) |
| Resident RAM, Earth world | ~1,073 MB | ~1,073 MB (or ~670 MB with P2.3) |
| Cold start, non-Earth world | ~3.1 s | **~0.6–1.0 s** |
| Cold start, Earth world | ~3.1 s | ~2.5 s (≈0 with P2.2 perceived) |
| Idle disk writes | 30 Hz | **0** (no consumer) |
| Render while occluded | 30 fps | **paused** (P2.1) |
| Per-frame main-thread CPU | baseline | −10–28 % draw CPU (P1.4) |

All P1 items are low-risk, reversible, and target the **measured** cost centers —
memory and startup — rather than the already-healthy frame loop.
