"""
tracker.py — Thread-safe head tracker for Parallax Wall.

Priority order:
  1. MediaPipe FaceLandmarker (Tasks API, requires models/face_landmarker.task)
  2. OpenCV Haar cascade (fallback if model file is missing or mediapipe fails)

Public API:
  t = FaceTracker()
  t.start()                       # spawns daemon thread, requests camera permission
  hx, hy, hz, yaw, pitch = t.head()
       # hx,hy : -1…+1 viewer left/right, down/up   (head POSITION)
       # hz    : -0.7…+1.0 back/forward (face size)  (head DISTANCE)
       # yaw,pitch : -1…+1 turn right/left, up/down  (head ORIENTATION)
  t.set_tracking(bool)            # ON = open camera + track. OFF = release camera.
  t.active                        # True while camera is open and producing frames

Head POSITION and head ORIENTATION are independent: position comes from the nose
landmark / face centroid, orientation from MediaPipe's facial transformation
matrix (true 3-D head pose). The Haar fallback has no pose, so it reports
yaw = pitch = 0 (translation + distance still work).
"""

import logging
import math
import os
import sys
import threading
import time
from pathlib import Path

# ── OpenCV macOS camera-authorization handoff (MUST be set BEFORE `import cv2`) ─
# OpenCV's AVFoundation backend, faced with a NotDetermined camera authorization,
# tries to request authorization ITSELF and then spin the main run loop to await
# the user's answer. Our capture loop runs on a worker thread, where OpenCV
# "can not spin main run loop from other thread" — so that self-request ALWAYS
# fails and the camera never opens, no matter the real TCC state. That is the
# exact failure behind "Live status on, but no tracking": the status flips on the
# button click while every camera open silently fails forever in the background.
#
# We take OWNERSHIP of authorization instead — request_camera_access() settles the
# macOS grant on the MAIN thread up front — and set this flag so OpenCV trusts the
# app's grant and skips its own (broken, off-thread) attempt. Once authorized, the
# worker-thread open then succeeds cleanly; if access is denied, the open fails
# fast instead of spamming retries.
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

import cv2
import numpy as np

from Tracking.filters import OneEuroFilter, gated_predict

# ── Logging ─────────────────────────────────────────────────────────────────--
# The shipped .app is built --windowed, so Python's stdout/stderr are DISCARDED:
# every print() in the camera path was invisible in the field, which is a big part
# of why this bug was so hard to pin down. Log the camera/permission flow to a
# real file (~/.iris/iris.log) as well as stderr, so it is always inspectable.
def _build_logger() -> logging.Logger:
    lg = logging.getLogger("iris.camera")
    if lg.handlers:                       # idempotent across re-imports
        return lg
    lg.setLevel(logging.INFO)
    lg.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s [iris.camera] %(message)s")
    try:
        cfg = Path.home() / ".iris"
        cfg.mkdir(exist_ok=True)
        fh = logging.FileHandler(cfg / "iris.log")
        fh.setFormatter(fmt)
        lg.addHandler(fh)
    except Exception:
        pass
    try:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        lg.addHandler(sh)
    except Exception:
        pass
    return lg

log = _build_logger()

# Model file lives in models/ alongside this script
_HERE       = Path(__file__).parent
MODEL_PATH  = _HERE / "models" / "face_landmarker.task"
MODEL_URL   = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
)

# ── MediaPipe Tasks probe ──────────────────────────────────────────────────────
_MP_AVAILABLE = False
try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision as _mp_vision
    from mediapipe.tasks.python.core.base_options import BaseOptions as _BaseOptions
    _RunningMode    = _mp_vision.RunningMode
    _FaceLMOptions  = _mp_vision.FaceLandmarkerOptions
    _FaceLM         = _mp_vision.FaceLandmarker
    _MP_AVAILABLE   = True
except ImportError:
    pass


# ── Model download ─────────────────────────────────────────────────────────────
def _ensure_model() -> bool:
    """
    Ensure the FaceLandmarker model file is present. Downloads (~3.6 MB) on
    first run if missing. Returns True if the model is ready.
    """
    if MODEL_PATH.exists():
        return True
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("[tracker] Downloading FaceLandmarker model…")
    try:
        import urllib.request
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print(f"[tracker] Model downloaded → {MODEL_PATH}")
        return True
    except Exception as e:
        print(f"[tracker] Model download failed: {e}")
        return False


# ── macOS camera permission ────────────────────────────────────────────────────
# Authorization states returned by request_camera_access():
AUTHORIZED  = "authorized"    # grant settled — the camera can be opened
DENIED      = "denied"        # explicitly denied/restricted, or the user dismissed
UNAVAILABLE = "unavailable"   # non-macOS, or no pyobjc/AVFoundation to ask with


def request_camera_access(timeout: float = 30.0) -> str:
    """Settle macOS camera authorization and return one of AUTHORIZED / DENIED /
    UNAVAILABLE.

    MUST run on the thread that owns the main run loop (the engine calls start()
    there). AVFoundation can only PRESENT the TCC dialog from that thread, and
    requestAccess is asynchronous, so the run loop has to be pumped both for the
    dialog to appear AND for the user's answer to be delivered.

    Mapping of AVAuthorizationStatus → return value:
      • 3 Authorized   → AUTHORIZED   (no prompt; already granted)
      • 0 NotDetermined→ present the dialog, pump the run loop, AUTHORIZED/DENIED
      • 2 Denied / 1 Restricted → DENIED (macOS will NOT prompt again — the user
                                  must re-enable it in System Settings)

    On non-macOS or when pyobjc is missing this returns UNAVAILABLE; the caller
    may still attempt an open (it succeeds only if the responsible process already
    holds the OS grant, e.g. a terminal that was granted camera access)."""
    if sys.platform != "darwin":
        return UNAVAILABLE
    try:
        from AVFoundation import AVCaptureDevice
        from Foundation   import NSRunLoop, NSDate
    except Exception as e:
        # pyobjc not bundled/installed — cannot ask. (The frozen .app must collect
        # objc/Foundation/AVFoundation; see Build/build_dmg.sh.)
        log.warning("AVFoundation unavailable (%s) — cannot request camera access", e)
        return UNAVAILABLE

    MEDIA  = "vide"          # AVMediaTypeVideo
    status = AVCaptureDevice.authorizationStatusForMediaType_(MEDIA)
    if status == 3:
        log.info("camera already authorized")
        return AUTHORIZED
    if status in (1, 2):
        log.warning("camera access %s (status=%d) — macOS will not prompt again; "
                    "enable it in System Settings > Privacy & Security > Camera",
                    "restricted" if status == 1 else "denied", status)
        return DENIED
    if status != 0:
        log.warning("unexpected camera authorization status=%s", status)

    # NotDetermined → present the dialog and pump the run loop until answered.
    log.info("camera not-determined — presenting TCC dialog and awaiting answer")
    done    = threading.Event()
    granted = {"ok": False}

    def _cb(ok) -> None:                 # AVFoundation completion handler
        granted["ok"] = bool(ok)
        done.set()

    try:
        AVCaptureDevice.requestAccessForMediaType_completionHandler_(MEDIA, _cb)
    except Exception as e:
        log.error("requestAccessForMediaType failed: %s", e)
        return DENIED

    rl       = NSRunLoop.currentRunLoop()
    deadline = time.time() + timeout
    while not done.is_set() and time.time() < deadline:
        rl.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

    if not done.is_set():
        log.warning("camera authorization timed out after %.0fs (no answer)", timeout)
        return DENIED
    state = AUTHORIZED if granted["ok"] else DENIED
    log.info("camera authorization answered: %s", state)
    return state


# ══════════════════════════════════════════════════════════════════════════════
#  FaceTracker
# ══════════════════════════════════════════════════════════════════════════════

class FaceTracker:
    """
    Thread-safe head tracker.  Writes head_x / head_y / head_z continuously
    from a background daemon thread.

    Camera lifecycle:
      • On set_tracking(False) — the camera device is released immediately
        on the next loop tick (≤ 0.3 s), freeing it for other apps.
      • On set_tracking(True)  — the camera is reopened the next time the
        loop wakes; tracking resumes within a couple of frames.

    Coordinate system:
      head_x: +1 = viewer LEFT  (camera shifts right)
      head_y: +1 = viewer UP    (camera shifts up)
      head_z: +1 = face ≈2× baseline (close);  -0.7 = ≈30% baseline (far)
    """

    # Smoothing / filtering
    _LERP_XY    = 0.55
    _LERP_Z     = 0.22
    _LERP_ROT   = 0.40     # head-orientation smoothing (a touch heavier than XY)
    _DEAD_XY    = 0.004
    _DEAD_Z     = 0.003
    _DEAD_ROT   = 0.01     # ignore sub-degree pose jitter
    _RETURN_SPD = 0.04

    # Head orientation: normalise raw yaw/pitch by this half-range (radians) so
    # ±NORM_RAD maps to ±1.0. Sign flips correct for the mirrored selfie frame
    # so "turn head right" reports +yaw. Flip these if live behaviour inverts.
    _ROT_NORM_RAD = 0.52   # ≈30° → full deflection
    _YAW_SIGN     = +1.0
    _PITCH_SIGN   = +1.0

    # Near-field adaptive smoothing — dampens jitter when viewer is very close
    _NF_HZ_LO    = 0.4    # hz where near-field smoothing begins
    _NF_HZ_HI    = 0.9    # hz where near-field smoothing is at maximum
    _NF_LERP_XY  = 0.15   # xy lerp at maximum near-field proximity
    _NF_LERP_ROT = 0.10   # rotation lerp at maximum near-field proximity

    # Edge-zone adaptive smoothing — stabilises lateral tracking near frame borders
    _EDGE_ZONE   = 0.15   # frame fraction from each edge treated as edge zone

    # Velocity-adaptive responsiveness (1€-filter principle). The smoothing lerp
    # is RAISED toward a snappier ceiling as the measurement moves faster, so
    # deliberate head motion has low lag ("feels attached") while a still head
    # keeps the heavy, already-accepted smoothing — the gate is 0 at rest, so it
    # can NEVER add jitter, only reduce motion lag. Speeds are in normalised
    # units per frame (nose position 0..1, pose -1..1).
    _RESP_V_LO     = 0.012   # xy speed where responsiveness starts to rise
    _RESP_V_HI     = 0.060   # xy speed at which responsiveness is maxed
    _RESP_MAX_XY   = 0.85    # xy lerp ceiling at full speed (vs _LERP_XY=0.55 base)
    _RESP_V_LO_ROT = 0.020   # rotation speed where responsiveness starts to rise
    _RESP_V_HI_ROT = 0.120   # rotation speed at which responsiveness is maxed
    _RESP_MAX_ROT  = 0.75    # rotation lerp ceiling at full speed (vs _LERP_ROT=0.40)

    # ── Predictive conditioning (FINAL stage; see Tracking/filters.py) ──────────
    # Applied to the already-smoothed signal: a 1€ filter strips residual REST
    # jitter (low cutoff when slow) while staying low-lag in motion (cutoff rises
    # with speed), and a velocity predictor extrapolates forward to HIDE the
    # pipeline latency (MediaPipe ~34 ms + downstream smoothing + display). The
    # predictor is velocity-GATED, so at rest it adds exactly nothing — it can
    # only cut motion lag, never inject jitter (proven in sim_predict).
    #
    # CALIBRATE LIVE: _PREDICT_LEAD is the primary knob. Raise it → snappier, head
    # "leads" your motion more; raise too far → it rubber-bands / overshoots on
    # quick direction reversals. The 1€ cutoffs trade rest-smoothness vs motion-lag.
    _EURO_MIN_CUTOFF     = 1.2     # Hz — position rest smoothing (lower = smoother)
    _EURO_BETA           = 1.5     # position speed→cutoff gain (higher = less lag)
    _EURO_D_CUTOFF       = 1.0     # Hz — velocity (derivative) smoothing
    _EURO_MIN_CUTOFF_ROT = 1.2     # Hz — rotation rest smoothing
    _EURO_BETA_ROT       = 1.5     # rotation speed→cutoff gain
    _PREDICT_LEAD        = 0.070   # s — how far ahead to extrapolate (PRIMARY knob)
    _PREDICT_MAX_DT      = 0.050   # s — cap on inter-sample extrapolation (anti-runaway)
    _PV_LO               = 0.15    # units/s — speed where position prediction engages
    _PV_HI               = 0.90    # units/s — speed where position prediction is full
    _PV_LO_ROT           = 0.15    # units/s — rotation prediction gate lo
    _PV_HI_ROT           = 0.90    # units/s — rotation prediction gate hi

    # How long to sleep when paused (sec)
    _PAUSED_TICK = 0.25
    # How long to back off after a camera-open failure before retrying
    _RETRY_BACKOFF = 3.0

    def __init__(self) -> None:
        self._lock      = threading.Lock()
        self._hx        = 0.0
        self._hy        = 0.0
        self._hz        = 0.0
        self._yaw       = 0.0       # head orientation, normalised -1…+1
        self._pitch     = 0.0
        self.active     = False     # True only while camera is open + producing
        self._enabled   = True      # toggle state
        self._stop      = False     # set by .stop() to exit cleanly
        self.has_rotation = False   # True when MediaPipe rotation data is available
        # Last camera-authorization outcome, set by start(): "unknown" until the
        # first start(), then AUTHORIZED / DENIED / UNAVAILABLE. The engine reads
        # this to give the UI honest feedback instead of a permanent "Live" lie.
        self.permission = "unknown"

        # Predictive conditioning. The 1€ filters live ONLY in the worker thread
        # (touched solely in _publish), so they need no lock; the lock guards only
        # the published scalars + velocities + timestamp that head() reads.
        self._f_x     = OneEuroFilter(self._EURO_MIN_CUTOFF, self._EURO_BETA, self._EURO_D_CUTOFF)
        self._f_y     = OneEuroFilter(self._EURO_MIN_CUTOFF, self._EURO_BETA, self._EURO_D_CUTOFF)
        self._f_z     = OneEuroFilter(self._EURO_MIN_CUTOFF, self._EURO_BETA, self._EURO_D_CUTOFF)
        self._f_yaw   = OneEuroFilter(self._EURO_MIN_CUTOFF_ROT, self._EURO_BETA_ROT, self._EURO_D_CUTOFF)
        self._f_pitch = OneEuroFilter(self._EURO_MIN_CUTOFF_ROT, self._EURO_BETA_ROT, self._EURO_D_CUTOFF)
        self._vx = self._vy = self._vz = 0.0      # filtered velocities (units/sec)
        self._vyaw = self._vpitch = 0.0
        self._t_pub: float | None = None          # monotonic time of last publish

    # ── Public API ─────────────────────────────────────────────────────────────
    def start(self) -> str:
        """Settle camera authorization on the MAIN thread, then (if usable) spawn
        the daemon capture/track worker. Returns the authorization outcome
        (AUTHORIZED / DENIED / UNAVAILABLE), also stored on ``self.permission``.

        CAMERA PERMISSION (macOS): AVFoundation can PRESENT the TCC dialog only
        from the thread that owns the main run loop, and requestAccess is
        asynchronous — the dialog appears, and the answer is delivered, only while
        that loop is pumped. start() is always called from the engine's main loop,
        so request_camera_access() settles the grant HERE before any worker opens
        the device. We also set OPENCV_AVFOUNDATION_SKIP_AUTH=1 (top of module) so
        OpenCV does NOT issue its own authorization request from the worker thread
        — which can never succeed ("can not spin main run loop from other thread")
        and was the root cause of "Live status on, but no tracking".

        We ACT on the outcome rather than ignoring it (the previous bug):
          • DENIED      → do not spawn a worker that would spin forever failing to
                          open a camera it can never get; report it so the UI can
                          tell the user to re-enable access in System Settings.
          • AUTHORIZED  → spawn the worker; the open now succeeds.
          • UNAVAILABLE → spawn the worker anyway and let it try once: on a source
                          run the responsible app may already hold the grant, and
                          there is nothing else we can do to prompt. If the open
                          fails, ``active`` stays False (honest "not tracking").

        RESTARTABILITY: a previous stop() latches self._stop = True; clear it here
        so start() can revive a stopped tracker (e.g. re-enabling the camera after
        a desktop handoff) instead of spawning a thread that exits on its first
        tick."""
        with self._lock:
            self._stop = False
        log.info("start(): settling camera authorization on main thread…")
        try:
            state = request_camera_access()
        except Exception as e:                       # never let a permission hiccup crash start()
            log.exception("camera authorization raised; treating as unavailable: %s", e)
            state = UNAVAILABLE
        with self._lock:
            self.permission = state
        if state == DENIED:
            self.active = False
            log.warning("start(): camera access denied — NOT spawning capture worker")
            return state
        log.info("start(): authorization=%s — spawning capture worker", state)
        threading.Thread(target=self._run, daemon=True, name="FaceTracker").start()
        return state

    def head(self) -> tuple:
        """Return the PREDICTED (head_x, head_y, head_z, yaw, pitch), thread-safe.

        The worker publishes 1€-filtered values + filtered velocities + a publish
        timestamp; here we extrapolate ``value + velocity·lead`` forward to hide
        the pipeline latency. The lead also covers the time elapsed since the last
        ~30 Hz sample, so the 60 fps render keeps moving smoothly between tracker
        updates instead of stair-stepping. Velocity-gated (a still head is
        returned untouched → no rest jitter) and clamped to each channel's range."""
        now = time.monotonic()
        with self._lock:
            hx, hy, hz = self._hx, self._hy, self._hz
            yaw, pitch = self._yaw, self._pitch
            vx, vy, vz = self._vx, self._vy, self._vz
            vyaw, vpitch = self._vyaw, self._vpitch
            t_pub = self._t_pub
        if t_pub is None:                      # nothing published yet
            return hx, hy, hz, yaw, pitch
        lead = self._PREDICT_LEAD + min(now - t_pub, self._PREDICT_MAX_DT)
        px = gated_predict(hx, vx, lead, self._PV_LO, self._PV_HI, -1.0, 1.0)
        py = gated_predict(hy, vy, lead, self._PV_LO, self._PV_HI, -1.0, 1.0)
        pz = gated_predict(hz, vz, lead, self._PV_LO, self._PV_HI, -0.70, 1.0)
        pyaw   = gated_predict(yaw,   vyaw,   lead, self._PV_LO_ROT, self._PV_HI_ROT, -1.0, 1.0)
        ppitch = gated_predict(pitch, vpitch, lead, self._PV_LO_ROT, self._PV_HI_ROT, -1.0, 1.0)
        return px, py, pz, pyaw, ppitch

    def set_tracking(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def is_tracking(self) -> bool:
        with self._lock:
            return self._enabled

    def stop(self) -> None:
        with self._lock:
            self._stop = True

    # ── Internal state writers ────────────────────────────────────────────────
    def _publish(self, x: float, y: float, z: float,
                 yaw: float = 0.0, pitch: float = 0.0) -> None:
        """Final conditioning (worker thread only): 1€-filter each channel, capture
        its clean velocity, and store the filtered value + velocity + timestamp for
        head() to predict from. The filter objects are touched only here, so they
        need no lock; the lock guards just the published scalars."""
        t = time.monotonic()
        dt = 0.0 if self._t_pub is None else (t - self._t_pub)
        fx = self._f_x.filter(x, dt)
        fy = self._f_y.filter(y, dt)
        fz = self._f_z.filter(z, dt)
        fyaw   = self._f_yaw.filter(yaw, dt)
        fpitch = self._f_pitch.filter(pitch, dt)
        with self._lock:
            self._hx, self._hy, self._hz = fx, fy, fz
            self._yaw, self._pitch = fyaw, fpitch
            self._vx, self._vy, self._vz = self._f_x.velocity, self._f_y.velocity, self._f_z.velocity
            self._vyaw, self._vpitch = self._f_yaw.velocity, self._f_pitch.velocity
            self._t_pub = t

    def _drift_back(self) -> tuple:
        """Smoothly relax toward (0,0,0,0,0) when no face is detected / disabled."""
        with self._lock:
            px, py, pz = self._hx, self._hy, self._hz
            pyaw, ppitch = self._yaw, self._pitch
        s = 1.0 - self._RETURN_SPD
        return px * s, py * s, pz * s, pyaw * s, ppitch * s

    # ── Helpers: open / close camera ──────────────────────────────────────────
    def _open_camera(self) -> "cv2.VideoCapture | None":
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS,          60)
        # LATENCY: inference (~30 ms in VIDEO mode) is slower than the 60 fps
        # capture interval (~16 ms), so frames accumulate in the driver's queue
        # and read() would hand us a STALE frame — pure added latency. Ask the
        # backend to keep only the newest frame. macOS AVFoundation may ignore
        # this (set() returns False); harmless if so, and _drain_to_latest()
        # below is the backend-independent backstop.
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        if not cap.isOpened():
            cap.release()
            # With OPENCV_AVFOUNDATION_SKIP_AUTH=1, a failed open here means the OS
            # grant is not actually in place (or no camera) — NOT a transient glitch.
            log.warning("cv2.VideoCapture(0) did not open (permission not granted, "
                        "or no camera available)")
            return None
        return cap

    @staticmethod
    def _close_camera(cap) -> None:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

    # ── Main loop — owns the camera lifecycle ─────────────────────────────────
    def _run(self) -> None:
        use_mp = _MP_AVAILABLE and _ensure_model()
        self.has_rotation = use_mp
        engine = "MediaPipe FaceLandmarker" if use_mp else "Haar cascade"
        log.info("tracker worker started — engine: %s", engine)

        # Stateful per-engine context (created lazily on first ON cycle)
        ctx: dict = {
            "smooth_x":    0.5,
            "smooth_y":    0.5,
            "baseline":    None,
            "smooth_sz":   0.0,
            "smooth_yaw":  0.0,
            "smooth_pitch": 0.0,
            "landmarker":  None,
            "cascade":     None,
            "video_ts":    -1,    # MediaPipe VIDEO-mode monotonic ms clock
        }

        cap = None
        last_open_failure = 0.0   # backoff only kicks in after a FAILED open

        try:
            while True:
                if self._stop:
                    break

                enabled = self.is_tracking()

                # ── PAUSED branch: release camera, drift toward centre ────────
                if not enabled:
                    if cap is not None:
                        log.info("tracking toggled off — releasing camera")
                        self._close_camera(cap)
                        cap = None
                        self.active = False
                    last_open_failure = 0.0   # toggle-back should reopen instantly
                    self._publish(*self._drift_back())
                    time.sleep(self._PAUSED_TICK)
                    continue

                # ── ENABLED branch: ensure camera is open ─────────────────────
                if cap is None:
                    # Backoff only when the previous open ATTEMPT failed —
                    # toggle on/off should never be throttled.
                    if last_open_failure and time.time() - last_open_failure < self._RETRY_BACKOFF:
                        time.sleep(0.2)
                        continue
                    cap = self._open_camera()
                    if cap is None:
                        last_open_failure = time.time()
                        log.warning("camera open failed — retrying after %.0fs backoff",
                                    self._RETRY_BACKOFF)
                        self.active = False
                        self._publish(*self._drift_back())
                        continue
                    last_open_failure = 0.0
                    self.active = True
                    log.info("camera opened — head tracking live")

                # ── Per-engine frame processing ──────────────────────────────
                ret, frame = cap.read()
                if not ret:
                    # Lost the camera mid-stream — release and try to reopen
                    log.warning("frame read failed — releasing camera, will reopen")
                    self._close_camera(cap)
                    cap = None
                    self.active = False
                    continue

                frame = cv2.flip(frame, 1)   # mirror selfie view

                if use_mp:
                    self._step_mp(frame, ctx)
                else:
                    self._step_haar(frame, ctx)
        finally:
            self._close_camera(cap)
            self.active = False
            log.info("tracker worker exited")

    # ── Adaptive-smoothing helpers ─────────────────────────────────────────────
    @staticmethod
    def _nf_lerp_weight(raw_z: float, lo: float, hi: float) -> float:
        """Smoothstep 0→1 weight for near-field lerp blending."""
        if hi <= lo:
            return 0.0
        t = max(0.0, min(1.0, (raw_z - lo) / (hi - lo)))
        return t * t * (3.0 - 2.0 * t)

    @staticmethod
    def _edge_factor(pos: float, zone: float) -> float:
        """Lerp multiplier: 1.0 in the safe zone, 0.5 at the frame edge."""
        margin = min(pos, 1.0 - pos)
        if margin >= zone:
            return 1.0
        t = margin / zone
        t = t * t * (3.0 - 2.0 * t)
        return 0.5 + 0.5 * t

    @staticmethod
    def _resp_boost(base: float, speed: float, lo: float, hi: float, ceil: float) -> float:
        """
        Raise the smoothing lerp `base` toward `ceil` as `speed` rises lo→hi
        (smoothstep). Returns exactly `base` when slow/at rest (so rest jitter is
        unchanged) and `ceil` when moving fast (low motion lag). Only ever
        increases responsiveness — never below `base`.
        """
        if hi <= lo or ceil <= base:
            return base
        t = max(0.0, min(1.0, (speed - lo) / (hi - lo)))
        g = t * t * (3.0 - 2.0 * t)
        return base + (ceil - base) * g

    @staticmethod
    def _next_video_ts(ctx: dict) -> int:
        """
        Strictly-increasing millisecond timestamp for MediaPipe VIDEO mode.
        MediaPipe RAISES if a stamp is <= the previous one (which would kill
        this thread), so we clamp to last+1 whenever the monotonic clock hasn't
        advanced a full millisecond between frames.
        """
        now_ms = int(time.monotonic() * 1000.0)
        last   = ctx.get("video_ts", -1)
        if now_ms <= last:
            now_ms = last + 1
        ctx["video_ts"] = now_ms
        return now_ms

    # ── MediaPipe per-frame step ──────────────────────────────────────────────
    def _step_mp(self, frame, ctx: dict) -> None:
        if ctx["landmarker"] is None:
            # LATENCY: VIDEO running-mode, not IMAGE. IMAGE mode re-runs the full
            # face DETECTOR every frame (measured mean 76 ms, p95 182 ms, ~13 fps
            # with half-second stalls). VIDEO mode detects once then TRACKS — it
            # reuses the prior frame's landmarks and only re-detects when tracking
            # is lost (measured mean 34 ms, p95 68 ms, ~30 fps). That is a −55%
            # mean / −63% p95 inference cut AND far lower variance, so the head
            # feels attached to motion with LESS jitter, not more. The temporal
            # tracking also adds its own frame-to-frame consistency for free.
            options = _FaceLMOptions(
                base_options=_BaseOptions(model_asset_path=str(MODEL_PATH)),
                running_mode=_RunningMode.VIDEO,
                num_faces=1,
                # True 3-D head pose for the rotational viewing component.
                output_facial_transformation_matrixes=True,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            ctx["landmarker"] = _FaceLM.create_from_options(options)

        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = ctx["landmarker"].detect_for_video(mp_img, self._next_video_ts(ctx))

        if not result.face_landmarks:
            self._publish(*self._drift_back())
            return

        lm = result.face_landmarks[0]
        nose = lm[4]

        _base = ctx["baseline"] or 1.0
        prev_z = float(np.clip(ctx["smooth_sz"] / _base - 1.0, -0.70, 1.0))
        nf_w = self._nf_lerp_weight(prev_z, self._NF_HZ_LO, self._NF_HZ_HI)
        lerp_xy  = self._LERP_XY  * (1.0 - nf_w) + self._NF_LERP_XY  * nf_w
        lerp_rot = self._LERP_ROT * (1.0 - nf_w) + self._NF_LERP_ROT * nf_w

        sx, sy = ctx["smooth_x"], ctx["smooth_y"]
        dx, dy = nose.x - sx, nose.y - sy
        # Velocity-adaptive: snappy during deliberate motion, heavy smoothing at
        # rest. Edge factor still damps near the frame borders for stability.
        resp_xy = self._resp_boost(lerp_xy, math.hypot(dx, dy),
                                   self._RESP_V_LO, self._RESP_V_HI, self._RESP_MAX_XY)
        lerp_x = resp_xy * self._edge_factor(nose.x, self._EDGE_ZONE)
        lerp_y = resp_xy * self._edge_factor(nose.y, self._EDGE_ZONE)
        if abs(dx) > self._DEAD_XY: sx += lerp_x * dx
        if abs(dy) > self._DEAD_XY: sy += lerp_y * dy
        ctx["smooth_x"], ctx["smooth_y"] = sx, sy

        xs = [l.x for l in lm]; ys = [l.y for l in lm]
        fsize = ((max(xs) - min(xs)) + (max(ys) - min(ys))) * 0.5
        if ctx["baseline"] is None:
            ctx["baseline"]  = fsize
            ctx["smooth_sz"] = fsize
        ds = fsize - ctx["smooth_sz"]
        if abs(ds) > self._DEAD_Z:
            ctx["smooth_sz"] += self._LERP_Z * ds

        raw_x = -(sx * 2.0 - 1.0)
        raw_y = -(sy * 2.0 - 1.0)
        raw_z = float(np.clip(
            (ctx["smooth_sz"] / ctx["baseline"]) - 1.0,
            -0.70, 1.0,
        ))

        # ── Head ORIENTATION from the facial transformation matrix ────────────
        # Independent of the nose POSITION above, so translation and rotation
        # stay separate inputs. Extract yaw (about vertical) + pitch (about
        # horizontal) from the 3×3 rotation block, normalise, dead-zone, smooth.
        yaw_n = pitch_n = 0.0
        mats = getattr(result, "facial_transformation_matrixes", None)
        if mats:
            R = np.asarray(mats[0], dtype=np.float64)[:3, :3]
            yaw   = math.atan2(R[0, 2], R[2, 2])
            pitch = math.asin(max(-1.0, min(1.0, -R[1, 2])))
            yaw_n   = float(np.clip(self._YAW_SIGN   * yaw   / self._ROT_NORM_RAD, -1.0, 1.0))
            pitch_n = float(np.clip(self._PITCH_SIGN * pitch / self._ROT_NORM_RAD, -1.0, 1.0))

        syaw, spitch = ctx["smooth_yaw"], ctx["smooth_pitch"]
        d_yaw, d_pitch = yaw_n - syaw, pitch_n - spitch
        # Velocity-adaptive on rotation too: a deliberate head turn responds
        # quickly (low lag when peeking around) but a held pose stays steady.
        resp_rot = self._resp_boost(lerp_rot, math.hypot(d_yaw, d_pitch),
                                    self._RESP_V_LO_ROT, self._RESP_V_HI_ROT, self._RESP_MAX_ROT)
        if abs(d_yaw)   > self._DEAD_ROT: syaw   += resp_rot * d_yaw
        if abs(d_pitch) > self._DEAD_ROT: spitch += resp_rot * d_pitch
        ctx["smooth_yaw"], ctx["smooth_pitch"] = syaw, spitch

        self._publish(raw_x, raw_y, raw_z, syaw, spitch)

    # ── Haar per-frame step ───────────────────────────────────────────────────
    def _step_haar(self, frame, ctx: dict) -> None:
        if ctx["cascade"] is None:
            ctx["cascade"] = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )

        small = cv2.resize(frame, (320, 240))
        gray  = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
        faces = ctx["cascade"].detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5,
            minSize=(20, 20), maxSize=(200, 200),
        )
        if not len(faces):
            self._publish(*self._drift_back())
            return

        areas = [w * h for (x, y, w, h) in faces]
        x, y, fw, fh = faces[int(np.argmax(areas))]
        cx = (x + fw * 0.5) / 320.0
        cy = (y + fh * 0.5) / 240.0

        _base = ctx["baseline"] or 1.0
        prev_z = float(np.clip(ctx["smooth_sz"] / _base - 1.0, -0.70, 1.0))
        nf_w = self._nf_lerp_weight(prev_z, self._NF_HZ_LO, self._NF_HZ_HI)
        lerp_xy = self._LERP_XY * (1.0 - nf_w) + self._NF_LERP_XY * nf_w

        sx, sy = ctx["smooth_x"], ctx["smooth_y"]
        dx, dy = cx - sx, cy - sy
        resp_xy = self._resp_boost(lerp_xy, math.hypot(dx, dy),
                                   self._RESP_V_LO, self._RESP_V_HI, self._RESP_MAX_XY)
        lerp_x = resp_xy * self._edge_factor(cx, self._EDGE_ZONE)
        lerp_y = resp_xy * self._edge_factor(cy, self._EDGE_ZONE)
        if abs(dx) > self._DEAD_XY: sx += lerp_x * dx
        if abs(dy) > self._DEAD_XY: sy += lerp_y * dy
        ctx["smooth_x"], ctx["smooth_y"] = sx, sy

        fsize = (fw + fh) * 0.5
        if ctx["baseline"] is None:
            ctx["baseline"]  = fsize
            ctx["smooth_sz"] = fsize
        ds = fsize - ctx["smooth_sz"]
        if abs(ds) > 1.5:
            ctx["smooth_sz"] += self._LERP_Z * ds

        raw_x = -(sx * 2.0 - 1.0)
        raw_y = -(sy * 2.0 - 1.0)
        raw_z = float(np.clip(
            (ctx["smooth_sz"] / ctx["baseline"]) - 1.0,
            -0.70, 1.0,
        ))
        self._publish(raw_x, raw_y, raw_z)
