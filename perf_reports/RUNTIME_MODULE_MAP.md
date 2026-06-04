# RUNTIME_MODULE_MAP.md

**Phase 1 — Runtime Execution Map**
Method: `python -X importtime`, sequential `perf_counter` import timing, and
static import-graph extraction. All numbers measured on this machine
(Apple M2, Python 3.11.15, `.venv`). No estimates.

---

## 0. Reality check — the codebase is small at runtime

The repository reports ~370 k Python lines, but **342,974 of those are in `dist/`**
(PyInstaller build output / bundled deps). First-party runtime code:

| Package | Lines | Role |
|---|---:|---|
| `UI/` | 3,092 | demo overlay, buttons, world-builder UI (demo-only) |
| `Engine/` | 2,968 | renderer, camera math, shaders, calibration |
| `Launcher/` | 961 | **master frame loop** (`app_engine.py`, 912 lines) |
| `Tracking/` | 844 | face tracker + filters |
| `Worlds/` | 382 | world runtime, loader, placeables |
| `Licensing/` | 94 | entitlement |
| **Total runtime** | **~8,300** | what actually executes |

The performance surface is therefore **tiny and fully tractable**.

---

## 1. Startup import cost (measured)

Sequential import of the full `app_engine` import set, deps shared:

```
   102.0 ms   numpy
   198.7 ms   cv2
   600.4 ms   mediapipe        ← dominates; eagerly loads matplotlib + sounddevice
    88.8 ms   pygame
    92.6 ms   OpenGL.GL
     4.0 ms   Engine.renderer
     0.0 ms   Engine.camera_math
     0.8 ms   Worlds.world_runtime
     1.6 ms   UI.demo_overlay
     1.3 ms   Tracking.face_tracker (own code; mediapipe/cv2 counted above)
  --------
  1090.4 ms   TOTAL import time before any window/scene work
```

`-X importtime` breakdown of the mediapipe 600 ms (cumulative µs → ms):

```
  611 ms  mediapipe
  414 ms   └ mediapipe.tasks.python.vision
  401 ms       └ ...vision.drawing_utils
  395 ms           └ matplotlib.pyplot      ← NEVER used by IRIS
  191 ms   └ mediapipe.tasks.python.audio
  159 ms       └ sounddevice                ← NEVER used by IRIS
```

**Verified:** `grep matplotlib|sounddevice` across all first-party code → **zero hits.**
mediapipe pulls them transitively (landmark-drawing helpers + audio tasks) and IRIS
uses neither. ~**550 ms of the 600 ms** mediapipe cost is dead weight for this app.

---

## 2. Module load map

Importance = how central to the running illusion (CRITICAL = every frame).

### Always resident — loaded at startup, every mode

| Module | Import time | Startup? | Later? | Importance |
|---|---:|:---:|:---:|---|
| `Launcher/app_engine` | host | ✅ | — | CRITICAL (frame loop) |
| `Engine/renderer` | 4 ms own | ✅ | — | CRITICAL (all draw calls) |
| `Engine/camera_math` | <1 ms | ✅ | — | CRITICAL (off-axis frustum/view per frame) |
| `Engine/shader_loader` | 87 ms* | ✅ | — | HIGH (GLSL compile/texture load) |
| `Worlds/world_runtime` + `world_loader` | <1 ms | ✅ | — | HIGH (per-frame `poll()`) |
| `Worlds/placeable` | <1 ms | ✅ (via renderer) | — | MEDIUM |
| `Engine/calibration` | <1 ms | ✅ | — | LOW (opt-in, disabled by default) |
| `Tracking/face_tracker` | 1 ms own | ✅ | — | CRITICAL (head input) |
| `Tracking/filters` | <1 ms | ✅ | — | MEDIUM (One-Euro smoothing) |
| `numpy` | 102 ms | ✅ | — | CRITICAL |
| `cv2` | 199 ms | ✅ | — | HIGH (camera capture) |
| `mediapipe` | 600 ms | ✅ | — | CRITICAL (landmarks) — **but over-imports** |
| `pygame` | 89 ms | ✅ | — | CRITICAL (window/GL/clock) |
| `PyOpenGL` (`OpenGL.GL`) | 93 ms | ✅ | — | CRITICAL (every GL call) |

\* `shader_loader` cost is largely the `OpenGL.GL` it pulls; counted once.

### Demo-mode only — loaded lazily when `PARALLAX_MODE=demo`

| Module | Trigger | Importance |
|---|---|---|
| `UI/demo_overlay` (2,051 lines) | onboarding window | HIGH (demo), **never in wallpaper daemon** |
| `UI/buttons` | imported by demo_overlay | MEDIUM (demo only) |
| `UI/theme` | demo_overlay | LOW (demo only) |
| `UI/world_builder_api` | only on Send click (line 1059) | LOW (rare, on demand) |
| `UI/canvas_mesh_renderer` | only on canvas draw (line 1940) | LOW (rare, on demand) |

### Lazy / on-first-use in the engine (guarded)

| Class | Built when | Notes |
|---|---|---|
| `Eye` (The Watcher) | first frame of that world | shader+texture skipped otherwise |
| `Gem` | first frame of that world | lazy |
| `GridRoom` | first frame of room world | lazy |
| `PlaceableObjects` | first placeable present | lazy |

### NEVER loaded by the running engine (dead or out-of-process)

| Module | Lines | Status — **evidence** |
|---|---:|---|
| `Engine/bloom_postfx.py` | 230 | **Dead at runtime.** `grep` → imported by nothing; bloom was removed (app_engine.py:404-413). |
| `Engine/orbital_icons.py` | 661 | **Separate process.** Standalone Cocoa app with own `__main__`/`main()` (line 535,660); the engine only references it in *comments* (app_engine.py:686). Not in the import chain. |
| `Scripts/validation/*` | ~3,700 | Headless test sims — never imported by the app. |

---

## 3. What actually runs in the common case (wallpaper daemon)

The shipped default (`PARALLAX_MODE=wallpaper`, the desktop daemon) loads **none**
of `UI/*`. Its resident set is: `app_engine` + `renderer` (+camera_math, shader_loader,
placeable) + `calibration` + `world_runtime` + `face_tracker` (+filters) + the four
heavy native deps (numpy, cv2, mediapipe, pygame, PyOpenGL).

**Per-frame resident, hot:** `camera_math.off_axis_frustum/view_matrix`,
`renderer.*.draw`, `world_runtime.poll`, `tracker.head`. Everything else is
construct-once or demo-only.

---

## 4. Phase-1 conclusions

1. **Startup is import-bound, not compute-bound:** ~1.09 s of imports, **55 % of it
   (600 ms) is mediapipe**, and **~550 ms of that is matplotlib + sounddevice that
   IRIS never calls.** Biggest single startup win in the codebase. → see
   `IMPORT_ANALYSIS.md` and `PERFORMANCE_ROADMAP.md` P1.
2. **891 lines of first-party code never run** at runtime (`bloom_postfx` 230 +
   `orbital_icons` 661 is a separate process). Not a perf cost in-process, but
   confirms the live surface is ~8.3 k lines.
3. **Two SDL2 copies are loaded** — `cv2` and `pygame` each bundle `libSDL2`
   (objc duplicate-class warnings at import). Memory + symbol-collision smell;
   see `MEMORY_ANALYSIS.md`.
