# TRACKING_PIPELINE_REPORT.md

**Phase 6 — Tracking Pipeline Investigation**
Method: static trace of `Tracking/face_tracker.py` + live MediaPipe inference
timing on Apple M2 (`Scripts/perf/track_probe.py`). The webcam cannot be opened
in this profiling session (macOS TCC), so inference is measured on synthetic
640×480 frames; capture cadence is read from the code. In-code measured numbers
(authors') are cited where they reflect the real-face path.

---

## 1. Pipeline architecture — the key fact

```
   [ Background daemon thread: FaceTracker._run ]        [ Main render thread ]
   cv2.VideoCapture(0) 640×480@60, BUFFERSIZE=1
        │  cap.read()  (blocks at camera rate)
        ▼
   cv2.flip (mirror)  ──►  cv2.cvtColor BGR→RGB
        ▼
   mp.FaceLandmarker.detect_for_video (VIDEO mode)
        ▼
   landmark → head pose (x,y,z, yaw, pitch)
        ▼
   OneEuroFilter ×5  +  gated predictive lead (70 ms)
        ▼
   _publish() under lock ─────────────────────────────►  tracker.head()  (lock-read)
                                                          0.2 % of frame
```

**Tracking runs entirely off the render thread.** The render loop only does a
locked read of the last published value (`head_cam` stage = **0.009 ms/frame,
0.2 %**). So no matter how heavy inference is, **it cannot drop render frames** —
it only limits how *fresh* the head pose is (~30 Hz input vs 30/60 Hz render,
bridged by the predictive filter).

---

## 2. Per-stage cost (measured on M2)

| Stage | Cost | Source | Notes |
|---|---:|---|---|
| `FaceLandmarker` build | **312 ms** | measured | One-time, on worker start (XNNPACK CPU delegate) |
| `cv2.VideoCapture(0)` open | ~camera-dependent | — | One-time per enable; released on disable |
| `cap.read()` | ~16 ms (60 fps cap) | camera-bound | Blocks worker; `BUFFERSIZE=1` avoids backlog |
| `cv2.flip` | <0.1 ms | derived | 640×480 |
| `cv2.cvtColor` BGR→RGB | **0.057 ms** | measured | Negligible |
| `detect_for_video` (no-face / detect-reject) | **2.7 ms** mean (p95 2.9) | measured M2 | Detection CNN, fast-reject path |
| `detect_for_video` (tracking a real face) | **34 ms** mean, 68 ms p95 (authors, code:599-602) | cited | Full landmark mesh; hardware-dependent |
| OneEuro ×5 + predict | <0.05 ms | derived | Closed-form scalar filters |
| `_publish` (locked) | <0.01 ms | derived | 5 floats under a lock |

**Reading the two inference numbers:** 2.7 ms is the floor (CNN runs, finds no
face, skips landmark regression). The authors' 34 ms is the steady tracking path
on their reference hardware. Even at 34 ms the worker sustains ~30 Hz, **matched
to the render's needs** — the predictive 70 ms lead (`_PREDICT_LEAD`) interpolates
between samples so 30 Hz input feels smooth at 60 fps render.

---

## 3. Frequency analysis

| Quantity | Value | Evidence |
|---|---|---|
| Camera capture rate | 60 fps requested (`CAP_PROP_FPS=60`) | face_tracker:437 |
| Effective tracking rate | ~30 Hz (inference-bound) | code comment 602 + 34 ms inference |
| Render rate | 30 fps wallpaper / 60 fps demo | app_engine FPS_* |
| Input:render ratio | 1:1 (wallpaper) to 1:2 (demo) | — |
| Driver queue depth | 1 (`CAP_PROP_BUFFERSIZE=1`) | face_tracker:445 — **latency-optimal** |

The original design note (app_engine:92-103) already identified that at 60 fps the
render redraws each ~30 Hz head sample twice, and **capped the wallpaper to 30 fps
for exactly this reason** — a shipped optimization.

---

## 4. Redundant calculations / interpolation opportunities

1. **VIDEO mode already chosen over IMAGE mode** — authors measured −55 %
   inference (76 ms→34 ms) by letting MediaPipe *track* between detections rather
   than re-detect every frame (code:599-602). Already optimal.
2. **Predictive lead already bridges the input/render rate gap** (`gated_predict`,
   70 ms). No additional render-side interpolation needed.
3. **Frame downscaling:** capture is already 640×480 (low). The MediaPipe face
   detector internally works at ~192×192; feeding 640×480 is fine. No win.
4. **cvtColor:** 0.057 ms — not worth removing. (Could request RGB from the
   capture directly, but the saving is sub-0.1 ms and adds backend-format risk.)
5. **One real opportunity:** the FaceLandmarker is configured with
   `output_facial_transformation_matrixes=True` (needed for yaw/pitch). If a
   world doesn't use rotation (all enclosure worlds hold pan at 0), that output is
   computed but discarded. Minor — the cost is inside the graph and small.

---

## 5. Conclusions

1. **Tracking is architecturally correct** — off-thread, camera-released-on-pause,
   queue-depth 1, VIDEO mode, predictive bridging. It is **not** a render
   bottleneck (0.2 % of frame).
2. **Inference is cheap on M2** (2.7 ms reject / ~34 ms cited tracking) and
   self-throttles to ~30 Hz. The only one-time cost is the **312 ms landmarker
   build**, which happens on the worker thread at enable and does not block render.
3. **No redundant per-stage work worth removing.** The pipeline was already tuned
   (the code comments cite the before/after measurements). The CPU it consumes is
   a steady ~30 Hz of camera + 2.7–34 ms inference on a background core.
