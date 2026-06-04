# FRAME_TIMING_REPORT.md

**Phase 4 — Frame Timing Analysis**
Method: `Scripts/perf/harness.py`, real render path, hidden GL context on Apple
M2 @ 2940×1912, 600 frames/scenario. `--timing` runs `glFinish()` each frame so
the measured frame time **includes GPU completion**. Percentages are share of
mean frame time. All numbers measured.

---

## 1. Frame-time distribution (GPU-inclusive, uncapped)

| World | mean | median | p95 | p99 | max | sustained |
|---|---:|---:|---:|---:|---:|---:|
| **Earth** | 4.33 ms | 2.58 ms | 8.01 ms | 16.39 ms | 450.9 ms¹ | **231 fps** |
| **Grid Room** | 2.17 ms | 2.04 ms | 2.92 ms | 3.81 ms | 25.8 ms¹ | **460 fps** |

¹ `max` is the **first frame** (shader warmup / first texture upload / pipeline
prime). Steady-state p99 is the honest tail: Earth 16 ms, Grid Room 3.8 ms.

**Budget context:** at the shipped **30 fps wallpaper cap** the frame budget is
**33.3 ms**. Earth's p99 (16 ms) uses **49 %** of budget; median uses **8 %**.
At the 60 fps demo cap (16.7 ms) the median still fits with room to spare.

---

## 2. Per-stage breakdown — Earth world (% of frame)

Two columns: **GPU-inclusive** (glFinish on — `flip` absorbs all submitted GPU
work) and **CPU-submit** (glFinish off — isolates main-thread cost).

| Stage | GPU-incl ms | GPU-incl % | CPU-submit ms | CPU-submit % | What it is |
|---|---:|---:|---:|---:|---|
| `flip` (present + GPU drain) | 2.995 | **69.2 %** | 1.184 | 50.4 % | Buffer swap; GPU completes here |
| `bg_nebula` | 0.627 | 14.5 % | 0.114 | 4.9 % | Full-screen inside-sphere — **fillrate** |
| `icons` | 0.261 | 6.0 % | 0.244 | 10.4 % | 10 billboards + 1 modelview readback |
| `primary` (Earth) | 0.197 | 4.6 % | 0.153 | 6.5 % | 3 spheres, atmosphere blend |
| `proj_view` | 0.098 | 2.3 % | 0.539 | 22.9 %² | glClear + frustum + load matrices |
| `bg_stars` | 0.074 | 1.7 % | 0.056 | 2.4 % | 4600 point sprites, 1 draw |
| `world_poll` | 0.047 | 1.1 % | 0.036 | 1.5 % | 2× mtime `stat()` |
| `animate` | 0.009 | 0.2 % | 0.006 | 0.2 % | Earth/cloud/icon update |
| `head_cam` | 0.009 | 0.2 % | 0.007 | 0.3 % | Camera smoothing (exp lerp ×5) |
| `sun` | 0.007 | 0.2 % | 0.006 | 0.2 % | 2 mat3·vec3 (sun/fill → eye space) |

² Under glFinish-off, `glClear` at the top of `proj_view` blocks on the previous
frame's GPU work, so the sync cost is *attributed* there — it is pipeline
back-pressure, not CPU compute. With glFinish-on it correctly lands in `flip`.

## 3. Per-stage breakdown — Grid Room world (% of frame)

| Stage | ms | % | Notes |
|---|---:|---:|---|
| `flip` (present + GPU) | 2.015 | **92.8 %** | Wireframe box is trivial; present dominates |
| `primary` (room+placeables) | 0.064 | 2.9 % | Line draws |
| `proj_view` | 0.053 | 2.5 % | clear + matrices |
| `world_poll` | 0.023 | 1.1 % | stat() |
| everything else | <0.02 | <1 % | — |
| `bg_nebula`/`bg_stars`/`icons` | 0.000 | 0 % | **Not drawn** (void background, no icons) |

Grid Room draws almost nothing — its frame is **pure present cost**.

---

## 4. Where the frame goes — the percentages you asked for

**Earth world, GPU-inclusive (the honest "real" frame):**

```
  Present / GPU drain (flip) .............. 69.2 %
  Nebula fillrate ........................ 14.5 %
  Orbital icons .......................... 6.0 %
  Earth (3 spheres + atmosphere) ......... 4.6 %
  Projection/view/clear .................. 2.3 %
  Stars .................................. 1.7 %
  World poll (disk stat) ................. 1.1 %
  Tracking input read .................... 0.2 %   (head_cam; live tracker runs off-thread)
  Animation .............................. 0.2 %
  Sun/light transform .................... 0.2 %
  ─────────────────────────────────────────────
  "Physics" (smoothing+animate+poll) ..... 1.5 % total   (see PHYSICS_REPORT)
  Rendering (everything GPU+submit) ...... 96.0 %
  UI overlay ............................. 0 %   (wallpaper daemon has no overlay)
  Asset updates .......................... 0 %   (textures static after load)
```

**Tracking is ~0 % of the frame** because head-pose inference runs on a separate
daemon thread; the render thread only *reads* the latest smoothed value
(`head_cam` = 0.2 %). See TRACKING_PIPELINE_REPORT.

---

## 5. Conclusions

1. **Present (`flip`) is 69–93 % of every frame** and is intrinsic (vsync + GPU
   drain). The app cannot make it cheaper except by **not drawing** (when
   occluded/idle) or lowering resolution.
2. **Nebula fillrate (14.5 %)** is the single largest *drawable* GPU cost in the
   Earth world — a full-screen blended sphere drawn behind everything. Candidate
   for cheaper background (see RENDER_LOOP_AUDIT #4).
3. **Application logic (camera math, animation, world poll, tracking read) is
   <2 % combined.** There is no logic-side frame bottleneck.
