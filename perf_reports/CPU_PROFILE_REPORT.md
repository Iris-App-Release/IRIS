# CPU_PROFILE_REPORT.md

**Phase 3 — CPU Profiling**
Profilers: `cProfile` (function-level) + custom per-stage `perf_counter`
instrumentation, run against the **real render path** on the **real Apple M2 GPU**
via a hidden GL context (`Scripts/perf/harness.py`). 600 frames per scenario,
2940×1912 (true Retina). Startup numbers from `-X importtime` + ctor timing.
No estimates — every number is measured on this machine.

> **Scenarios.** Active-tracking mode cannot open the webcam here (macOS TCC),
> so head input is a synthetic motion path feeding the *identical* camera math.
> The render/CPU path is byte-for-byte what the live app runs; only the input
> source differs. Tracking inference is profiled separately (TRACKING_PIPELINE_REPORT).

---

## 1. Headline

**The render loop is not CPU-bound on this hardware.** The Earth world sustains
**231 fps** (4.33 ms/frame) and the Grid Room **460 fps** (2.17 ms) against a
**30 fps cap** — a 7–15× headroom. The dominant per-frame CPU cost is **PyOpenGL's
Python-side call marshaling + automatic error checking**, not the app's own logic
or the GPU. The real CPU cost is at **startup** (imports 1.09 s + scene build
~2.0–2.6 s).

---

## 2. Startup CPU (cProfile, cumulative)

```
   cumtime   calls   function
   2.310 s       —   build_scene (whole scene)
   1.938 s       5   shader_loader.load_texture_2d   ← 5 textures
     0.590 s     5     pygame.image.load             (JPEG decode)
     0.261 s     5     pygame.image.tostring         (surface→bytes)
     0.152 s     5     Surface.convert
     0.351 s    15     glTexImage2D/mipmap (wrapperCall)  ← GL upload
   0.508 s     600   IconOrbit.draw (cum, incl children)
   0.391 s       1   pygame.display.set_mode         (context create)
   0.313 s       1   pygame.base.init
```

Startup CPU is **dominated by decoding + uploading the Earth's four 8192×4096
JPEGs** (`load_texture_2d`, 1.94 s). See ASSET_LOADING_REPORT / MEMORY_ANALYSIS.

---

## 3. Per-frame CPU (render loop) — ranked

cProfile self-time over 600 Earth frames, **render-loop functions only**
(startup excluded). Rank thresholds: CRITICAL >0.5 ms/frame, HIGH 0.1–0.5,
MEDIUM 0.02–0.1, LOW <0.02.

| Rank | Function | Module | self ms/frame | calls/frame | Notes |
|---|---|---|---:|---:|---|
| **CRITICAL** | `pygame.display.flip` | pygame (native) | 2.05 | 1 | Buffer swap / present — vsync-bound, intrinsic. |
| **HIGH** | `OpenGL.error.glCheckError` | PyOpenGL | 0.13 | **224** | `glGetError` after **every** GL call. Pure overhead. |
| **HIGH** | `IconOrbit.draw` (self) | renderer:990 | 0.31 | 1 | 10 icons; **1 GL_MODELVIEW readback/frame** (stall). |
| **HIGH** | `latebind.__call__` | PyOpenGL | ~0.10 | 33 | Per-call dispatch wrapper. |
| **MEDIUM** | `Earth.draw` (self) | renderer:341 | 0.06 | 1 | 3 spheres, 3 programs, 6 texture binds. |
| **MEDIUM** | `Mesh.draw` | renderer:243 | 0.06 | 4 | VBO bind+draw per mesh. |
| **MEDIUM** | `calculate_pyArgs` | PyOpenGL | 0.10 | 124 | Argument marshaling. |
| **MEDIUM** | `numpy.array` | numpy | 0.05 | **35** | Most from IconOrbit per-icon mat alloc. |
| **MEDIUM** | `Stars.draw` | renderer:693 | 0.09 | 1 | 4600 points, 1 draw call. |
| **MEDIUM** | `camera_math.view_matrix` | camera_math:260 | 0.06 | 1 | 2 rot mats + multiply. |
| **LOW** | `Nebula.draw` (CPU submit) | renderer:780 | 0.11 | 1 | 1 mesh; GPU fillrate is the real cost (§4). |
| **LOW** | `world.poll` | world_runtime:99 | 0.04 | 1 | 2 `stat()` (mtime-cached). |
| **LOW** | camera smoothing | app_engine | 0.009 | 1 | exp lerp, 5 axes. |
| **LOW** | `earth.update`+`icons.update` | renderer | 0.006 | 1 | spin += / fade. |

### PyOpenGL overhead is the #1 controllable CPU cost
`glCheckError` is invoked **134,198 times across 600 frames = 224×/frame** — once
after every GL call. Disabling PyOpenGL's auto error-checking
(`OpenGL.ERROR_CHECKING=False`) was measured to cut the per-stage draw CPU by
**10–28 %** (`primary` 0.153→0.110 ms, `bg_nebula` 0.114→0.085 ms, `icons`
0.244→0.210 ms). Free, low-risk. See RENDER_LOOP_AUDIT #1 and ROADMAP P1.

---

## 4. CPU vs GPU split (measured via glFinish toggle)

| | Earth (glFinish ON = GPU-incl) | Earth (glFinish OFF = CPU submit) |
|---|---:|---:|
| mean frame | 4.33 ms | 2.35 ms |
| `flip`+sync | 3.00 ms (69 %) | 1.18 ms |
| CPU draw submit (sum) | ~1.2 ms | ~1.0 ms |

The ~3 ms in `flip` under glFinish is **GPU completion** (fillrate: full-screen
nebula + atmosphere blends at 5.6 MPix Retina). CPU main-thread work to *submit*
a frame is **~1 ms**. Both are far under the 33 ms budget at 30 fps.

---

## 5. Conclusions

1. **No per-frame CPU bottleneck on M2.** 7–15× headroom vs the 30 fps cap.
2. **Biggest controllable per-frame CPU = PyOpenGL** (error-check + marshaling),
   ~0.2–0.3 ms/frame, removable for free.
3. **Real CPU spend is startup** (imports + 1.94 s texture decode/upload).
4. **`pygame.display.flip` (present)** is the largest single frame cost and is
   intrinsic; the only lever is the **fps cap** (already 30) and **not rendering
   when occluded** (BACKGROUND_ACTIVITY_REPORT).
