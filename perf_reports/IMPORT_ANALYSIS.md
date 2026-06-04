# IMPORT_ANALYSIS.md

**Phase 2 — Import / Dependency Analysis**
Method: `-X importtime` cumulative timing + static import-graph extraction over
first-party packages. Numbers measured (Apple M2, Py 3.11.15).

---

## 1. Dependency graph (first-party)

```
launcher.py
 └─ Launcher.app_entry
     └─ Launcher.app_engine ........... MASTER (frame loop)
         ├─ Tracking.face_tracker
         │   ├─ cv2                     (199 ms)
         │   ├─ mediapipe  ───────────► matplotlib.pyplot (395 ms)  [UNUSED]
         │   │                          sounddevice       (159 ms)  [UNUSED]
         │   └─ Tracking.filters        (One-Euro / gated predict)
         ├─ Engine.renderer            (all scene classes)
         │   ├─ Engine.camera_math      (frozen off-axis math)
         │   ├─ Engine.shader_loader ─► OpenGL.GL (93 ms)
         │   └─ Worlds.placeable        (grid_to_world, sanitize_objects)
         ├─ Engine.camera_math
         ├─ Engine.calibration ───────► Engine.camera_math
         ├─ Worlds.world_runtime
         │   └─ Worlds.world_loader
         └─ UI.demo_overlay            [demo mode only]
             ├─ UI.buttons
             ├─ UI.theme
             ├─ Worlds.world_loader / placeable
             ├─ UI.world_builder_api   [lazy: Send click]
             └─ UI.canvas_mesh_renderer[lazy: canvas draw]
```

Out-of-graph: `Engine.bloom_postfx` (dead), `Engine.orbital_icons` (separate process).

---

## 2. Top modules by dependency importance

Ranked by **(import cost × centrality to the running frame loop).** This is the
"what to care about" list, not raw line count.

| # | Module | Import cost | Runs per frame? | Why it matters |
|--:|---|---:|:---:|---|
| 1 | **mediapipe** | **600 ms** | yes (inference) | Heaviest import in the app; over-imports matplotlib+sounddevice. |
| 2 | **cv2** | 199 ms | yes (capture/convert) | Camera frames; also a 2nd SDL2 copy. |
| 3 | numpy | 102 ms | yes (every matrix) | Backbone of camera math + buffers. |
| 4 | OpenGL.GL (PyOpenGL) | 93 ms | yes (every GL call) | Per-call ctypes marshaling cost (see CPU report). |
| 5 | pygame | 89 ms | yes (clock/events/flip) | Window, GL context, event pump. |
| 6 | matplotlib.pyplot | **395 ms** (within mp) | **no** | **Pure dead-weight import.** |
| 7 | sounddevice | **159 ms** (within mp) | **no** | **Pure dead-weight import.** |
| 8 | Engine.renderer | 4 ms own | yes (draws) | Hosts all 8 scene classes. |
| 9 | Engine.camera_math | <1 ms | yes (2 mat4 builds) | Tiny code, hot path. |
| 10 | Engine.shader_loader | (OpenGL) | startup | GLSL compile + texture upload. |
| 11 | Worlds.world_runtime | <1 ms | yes (`poll`) | mtime-cached world switch. |
| 12 | Tracking.face_tracker | 1 ms own | yes (`head`) | Owns the tracker thread. |
| 13 | Tracking.filters | <1 ms | yes | One-Euro smoothing per axis. |
| 14 | Worlds.placeable | <1 ms | only room world | sanitize/transform placeables. |
| 15 | Engine.calibration | <1 ms | yes (`poll`, no-op) | Opt-in; disabled by default. |
| 16–24 | UI.demo_overlay, buttons, theme, world_builder_api, canvas_mesh_renderer, world_loader | ≤2 ms each | demo only | Not in wallpaper daemon. |

(The remaining first-party modules are sub-millisecond and demo/lazy; the app has
nowhere near 50 meaningful runtime modules — the real list is ~24.)

---

## 3. Findings

### 3.1 Heavy imports
- **mediapipe (600 ms)** is the single heaviest. **~550 ms is avoidable** —
  `matplotlib.pyplot` (395 ms) + `sounddevice` (159 ms) are pulled by
  `mediapipe.tasks.python.vision.drawing_utils` and `...python.audio`, neither of
  which IRIS uses (verified: 0 first-party references).
- **cv2 (199 ms)** is required for capture but ships a **duplicate libSDL2** alongside
  pygame's (objc class-collision warnings at import time).

### 3.2 Slow startup imports
- Total import wall time **1.09 s**, of which **~0.9 s is the 5 native deps**.
- First-party code is **negligible** (<10 ms total) — startup is entirely third-party.

### 3.3 Circular dependencies
- **None found** among first-party modules. The graph is a clean DAG
  (camera_math is a leaf depended on by renderer/calibration/orbital_icons;
  no back-edges).

### 3.4 Duplicate / redundant
- **Duplicate native SDL2**: `cv2/.dylibs/libSDL2` and `pygame/.dylibs/libSDL2`
  both load. cv2 only needs SDL for `cv2.imshow`/HighGUI, which IRIS never calls.
- **No duplicate first-party utility modules** — filters/camera_math/world_loader
  are each single-sourced.

### 3.5 Eager-vs-lazy mismatch
- `mediapipe` is imported **eagerly at module scope** (`face_tracker.py:93-95`,
  inside a top-level `try`). So **every launch pays the full 600 ms even when the
  camera is disabled** (`~/.iris/camera_off`) or never granted. The tracker worker
  is started lazily, but its import is not — a structural mismatch.

---

## 4. Actionable (cross-ref PERFORMANCE_ROADMAP P1)

1. **Strip mediapipe's unused subimports** (matplotlib/sounddevice). Options, in
   order of safety: (a) lazy-import mediapipe inside `FaceTracker.start()` so a
   camera-off / demo-pre-grant launch pays 0 ms; (b) block the transitive imports
   via an import shim before `import mediapipe`; (c) import only
   `mediapipe.tasks.python.vision` symbols needed. Expected: **−0.4 to −0.6 s startup.**
2. **Drop cv2's SDL2** or replace cv2 capture with AVFoundation — removes a whole
   duplicate native lib from the process. Lower priority (correctness risk).
