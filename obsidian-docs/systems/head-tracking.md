---
title: Head Tracking
type: system
related: [off-axis-projection, engine-loop-and-daemon, ui-overlay, headless-simulation, constraints, asset-pipeline, known_issues]
last_updated: 2026-05-31
sources: [Tracking/face_tracker.py, Tracking/models/face_landmarker.task, Launcher/app_engine.py, launcher.py, Build/build_dmg.sh, Scripts/validation/sim_latency.py]
---

# Head Tracking

## Purpose

Head tracking is the *input* half of IRIS. It turns a webcam feed into the one
piece of data the rest of the app needs: where the viewer's head is, and which
way it is turned. That result is a smoothed five-tuple —
`(hx, hy, hz, yaw, pitch)` — handed to [[off-axis-projection]] every frame.

The defining requirement is **latency and stability over raw accuracy**. The
illusion is far stronger at a smooth 60 fps with low lag than at high precision
with jitter, so almost all of the complexity here is about *filtering* a noisy
signal without adding perceptible delay.

(The module is `Tracking/face_tracker.py`; it tracks the *head*, not the eyes —
"head tracking" is the accurate name.)

## What it outputs

| Field | Range | Meaning |
|---|---|---|
| `hx` | −1 … +1 | Head **position** left/right. `+1` = viewer to the **left** (frame is mirrored) |
| `hy` | −1 … +1 | Head position down/up |
| `hz` | −0.7 … +1.0 | Head **distance** from the face's apparent size. `+1` ≈ 2× baseline (close), `−0.7` ≈ 30% (far) |
| `yaw` | −1 … +1 | Head **orientation** turn right/left |
| `pitch` | −1 … +1 | Head orientation up/down |

Position, distance, and orientation are **independent** signals: position/size
come from the nose landmark and face bounding box; orientation comes from
MediaPipe's true 3-D facial transformation matrix. Keeping them separate is what
lets [[off-axis-projection]] blend translation and rotation as distinct inputs.

## Two engines (graceful degradation)

1. **MediaPipe FaceLandmarker** (preferred) — the Tasks API in **VIDEO** running
   mode, 468 3-D landmarks, single face, with the facial transformation matrix
   enabled for head pose. Needs `Tracking/models/face_landmarker.task` (~3.6 MB);
   if missing it is auto-downloaded (float16, from Google's MediaPipe model
   storage) on first run.
2. **OpenCV Haar cascade** (fallback) — used if MediaPipe is unavailable or the
   model can't be obtained. It has no head pose, so it reports `yaw = pitch = 0`
   (translation and distance still work).

**VIDEO mode is a deliberate latency choice.** IMAGE mode re-runs the full face
*detector* every frame (measured ≈76 ms mean / 182 ms p95, ~13 fps, with
half-second stalls). VIDEO mode detects once and then *tracks*, only re-detecting
when tracking is lost (≈34 ms mean / 68 ms p95, ~30 fps) — a −55% mean / −63%
p95 cut with far lower variance, so the head feels attached with *less* jitter.

## Threading & camera lifecycle

- A **daemon thread** owns the camera and continuously writes the latest head
  values behind a lock. The render loop calls `head()` and reads the cached
  values without ever blocking — if tracking lags, the scene still renders at
  full frame rate from the last known position.
- `start()` **settles camera authorization on the main thread** before spawning
  the worker, via `request_camera_access()`, which returns a tri-state
  (`authorized` / `denied` / `unavailable`). For a *NotDetermined* status it calls
  `AVCaptureDevice.requestAccessForMediaType:` and **pumps the main run loop**
  (`NSRunLoop.runUntilDate_`) until the user answers the macOS camera-permission
  (TCC) dialog — AVFoundation can present that dialog only from the thread that
  owns the main run loop, and `requestAccess` is asynchronous, so the loop must be
  pumped for both the prompt and the answer. `start()` then **acts on the result**:
  on `denied` it does *not* spawn a worker (which would only spin forever); it
  records `tracker.permission` so the engine/[[ui-overlay]] can show an honest
  status instead of a false "Live".
- **OpenCV must not do its own authorization.** `OPENCV_AVFOUNDATION_SKIP_AUTH=1`
  is set before any `cv2` import (`launcher.py` + `Tracking/face_tracker.py`). The
  capture runs on the worker thread, where OpenCV's own AVFoundation request
  *"can not spin main run loop from other thread"* and fails forever; with
  SKIP_AUTH the worker trusts the grant we already settled and opens cleanly (or
  fails fast if access was denied).
- **The bundle's code signature must be valid.** macOS TCC *silently denies* the
  camera to an app with an invalid signature — the dialog never appears and the
  request auto-denies in tens of milliseconds. The build re-signs the `.app`
  **after** its `Info.plist` edits for exactly this reason (see
  [[dmg-build-process]]); this invalid-signature auto-deny was the ultimate cause
  of the 2026-05-31 "Live, but no tracking" regression — see [[known_issues]].
- The whole flow is logged to `~/.iris/iris.log` (the `--windowed` bundle discards
  stdout), so a field failure is diagnosable from the log alone.
- `set_tracking(False)` releases the camera within ≤0.3 s; `set_tracking(True)`
  reopens it. **Single-camera ownership** is the rule that makes the demo →
  wallpaper handoff work (see [[engine-loop-and-daemon]]): the demo must release
  the camera before the daemon can take it.
- The camera is opened at 640×480, 60 fps requested, with `BUFFERSIZE = 1` so the
  backend hands back only the newest frame (stale queued frames would be pure
  added latency). macOS may ignore the buffer hint; that's harmless.

## The smoothing stack

All filtering only ever *reduces* motion lag at rest — it can never add jitter.
Layers, applied per frame:

- **Base smoothing** — exponential lerp toward the new measurement
  (`LERP_XY = 0.55`, `LERP_Z = 0.22`, `LERP_ROT = 0.40`), with dead-zones that
  ignore sub-threshold jitter.
- **Near-field adaptive smoothing** — when the viewer is very close (`hz` high),
  the lerp is dialled down (xy → 0.15, rotation → 0.10) because small motions are
  visually magnified up close.
- **Edge-zone adaptive smoothing** — within 15% of a frame border, the lerp is
  halved to stabilise the less-reliable tracking there.
- **Velocity-adaptive responsiveness (1€-filter principle)** — the lerp is raised
  toward a snappy ceiling (xy → 0.85, rotation → 0.75) as the measured speed
  rises. Deliberate motion has low lag; a still head keeps the heavy smoothing.
  The boost is exactly zero at rest, so it can never introduce jitter.
- **Drift-back** — with no face detected or tracking disabled, the values relax
  smoothly toward centre (`RETURN_SPD = 0.04`) instead of snapping.

A subtlety MediaPipe forces: VIDEO mode requires **strictly increasing**
millisecond timestamps or it raises (and would kill the thread), so timestamps
are clamped to `last + 1` when the monotonic clock hasn't advanced a full ms.

Head orientation is extracted from the 3×3 rotation block of the facial
transformation matrix (`yaw = atan2(R[0,2], R[2,2])`, `pitch = asin(−R[1,2])`),
normalised by `ROT_NORM_RAD ≈ 0.52` (~30° → full deflection), then dead-zoned and
smoothed like the rest.

## Constraints

- Requires a webcam and macOS camera permission.
- Runs at ~30 fps; end-to-end latency ~30–50 ms (perceptually invisible). See
  [[constraints]].
- MediaPipe gives full 6-DoF-ish input; Haar fallback gives position + distance
  only.

## Data flow

| Consumes | Produces | Destination | Purpose |
|----------|----------|-------------|---------|
| Webcam feed (640×480@60fps) | `(hx, hy, hz, yaw, pitch)` — smoothed 5-tuple | [[off-axis-projection]] | parallax + zoom + rotation |
| (same) | `(hx, hy)` (position only) | [[the-watcher]] Eye.update() | iris gaze tracking |
| (same) | Live/denied status | [[ui-overlay]] | "Camera access needed" / "Live · head tracking on" |
| (same) | Latency stats | [[headless-simulation]] | validation via `sim_latency.py` |
| MediaPipe FaceLandmarker model | Head pose (yaw, pitch) + position | [[off-axis-projection]] via rotation gate | proximity-gated view pan |

## Dependencies

- **Consumes:** Webcam (macOS AVFoundation), MediaPipe FaceLandmarker model (see [[asset-pipeline]]).
- **Feeds:** [[off-axis-projection]] (the head 5-tuple), [[engine-loop-and-daemon]]
  (which polls `head()` each frame and owns the camera handoff), [[ui-overlay]]
  (which reflects "live" vs "preview" state), and **[[the-watcher]]** (the eye
  tracking gaze system — `hx`/`hy` are passed to `Eye.update()` each frame so the
  iris follows the viewer without a second tracking pipeline).
- **Verified by:** [[headless-simulation]] (`sim_latency` checks smoothing
  latency/jitter without a camera).

## Eye tracking integration

`hx` and `hy` from `tracker.head()` are now consumed by **two** systems in
`app_engine.py`'s frame loop:

1. **Off-axis frustum** (existing) — translates `cam_x`/`cam_y` via `CAM_LAG`
   lerp to produce the parallax window shift.
2. **Eye gaze** (new, 2026-05-31) — passed as `eye.update(dt, hx, hy)` to the
   `Eye` renderer, which smooths them with its own `GAZE_LERP = 0.10` and rotates
   the eyeball sphere so the iris points toward the viewer.

The two consumers are **independent** — each has its own smoothing and clamping.
The camera grant, tracking thread, and smoothing stack are shared unchanged.
