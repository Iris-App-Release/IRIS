"""
calibration.py — Optional per-user METRIC calibration for the off-axis window.

Pure math + a small JSON load/poll: NO OpenGL, camera, threads or Cocoa, so the
geometry can be validated headlessly (Scripts/validation/sim_calibration.py),
exactly the way camera_math and filters are.

WHY THIS EXISTS
───────────────
IRIS's off-axis frustum is, by deliberate design, framed for a single
"cinematic" 58° vertical subtense at the neutral eye distance — geometrically
exact only at one assumed screen size / seating distance (see [[constraints]],
"one true viewing distance"). A reference web implementation (off-axis-sneaker)
showed the value of grounding the frustum in the user's REAL screen height and
viewing distance, so the monitor subtends its true physical angle and the
"window" illusion is correct for that person's setup — the per-user adaptivity
IRIS lacked.

WHAT IT DOES (and does NOT do)
──────────────────────────────
This module turns (screen_height_cm, viewing_distance_cm) into the window
half-height that reproduces the true subtended angle, blended against the frozen
cinematic framing by a 0..1 `parallax_strength` knob. It also exposes a
`parallax_gain` multiplier on the engine's lateral-shift constant for taste.

It changes NOTHING by default:
  • The neutral eye distance (world units) stays CAM_BASE_Z — the scene contents
    (Earth at z=-10, nebula, stars) are anchored to it, so it is NOT moved.
  • When `enabled` is False (the default) every accessor returns the frozen
    value (half_h → None ⇒ camera_math uses WINDOW_HALF_H; shift_scale → 1.0),
    so the engine path is byte-for-byte the pre-calibration behaviour.
  • The frozen matrix algebra in camera_math is untouched; the metric framing is
    realised purely through off_axis_frustum's opt-in `half_h` argument plus the
    engine's existing MAX_SHIFT knob.

CALIBRATION FILE  (~/.iris/calibration.json), all fields optional:
  {
    "enabled": false,
    "screen_width_cm": 34.0,
    "screen_height_cm": 19.0,
    "viewing_distance_cm": 60.0,
    "parallax_strength": 1.0,   # 0 = cinematic (frozen look) … 1 = fully metric
    "parallax_gain": 1.0        # multiplier on the lateral head-shift gain
  }
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from Engine import camera_math as om

# Frozen cinematic framing the metric value blends against.
CINEMATIC_HALF_H = om.WINDOW_HALF_H          # = CAM_BASE_Z · tan(FOVY/2)
BASE_Z           = om.CAM_BASE_Z             # world-unit neutral eye distance (fixed)

# Sane bounds so a hand-edited / malformed file can never produce a degenerate
# frustum (a zero/huge window half-height) or a runaway shift.
_MIN_HALF_H      = 0.5
_MAX_HALF_H      = CINEMATIC_HALF_H * 1.5    # never WIDER than the cinematic look
_MIN_DIST_CM     = 15.0
_MAX_DIST_CM     = 200.0
_MIN_SCREEN_CM   = 5.0
_MAX_SCREEN_CM   = 200.0


@dataclass
class Calibration:
    """Immutable snapshot of the user's calibration settings."""
    enabled: bool              = False
    screen_width_cm: float     = 34.0
    screen_height_cm: float    = 19.0
    viewing_distance_cm: float = 60.0
    parallax_strength: float   = 1.0
    parallax_gain: float       = 1.0

    # ── Derived geometry ──────────────────────────────────────────────────────
    def metric_half_h(self) -> float:
        """Window half-height (world units) reproducing the TRUE subtended
        vertical angle of the physical screen, at the fixed neutral eye distance.

            θ_v        = 2·atan( (screen_h_cm/2) / viewing_distance_cm )
            half_h_m   = CAM_BASE_Z · tan(θ_v / 2)
                       = CAM_BASE_Z · (screen_h_cm/2) / viewing_distance_cm

        (The tan/atan collapse because both describe the same right triangle.)
        Clamped to a safe range so the matrix can never degenerate.
        """
        h    = _clamp(self.screen_height_cm,    _MIN_SCREEN_CM, _MAX_SCREEN_CM)
        dist = _clamp(self.viewing_distance_cm, _MIN_DIST_CM,   _MAX_DIST_CM)
        half_h_m = BASE_Z * (0.5 * h) / dist
        return _clamp(half_h_m, _MIN_HALF_H, _MAX_HALF_H)

    def blended_half_h(self) -> float:
        """Cinematic↔metric blend by `parallax_strength` (0 → frozen look)."""
        s = _clamp(self.parallax_strength, 0.0, 1.0)
        return CINEMATIC_HALF_H * (1.0 - s) + self.metric_half_h() * s

    def subtended_fov_deg(self) -> float:
        """Vertical FOV (deg) the blended window subtends at the neutral eye —
        for UI/telemetry. Equals FOVY_DEG when disabled / strength 0."""
        hh = self.blended_half_h() if self.enabled else CINEMATIC_HALF_H
        return 2.0 * math.degrees(math.atan(hh / BASE_Z))

    # ── Engine-facing accessors (frozen-safe when disabled) ────────────────────
    def half_h(self) -> float | None:
        """Window half-height to feed camera_math.off_axis_frustum(half_h=…).
        None when disabled ⇒ the frozen WINDOW_HALF_H path (no behaviour change)."""
        return self.blended_half_h() if self.enabled else None

    @property
    def shift_scale(self) -> float:
        """Multiplier on the engine's lateral head-shift gain (1.0 when disabled)."""
        return _clamp(self.parallax_gain, 0.1, 4.0) if self.enabled else 1.0


def _clamp(x: float, lo: float, hi: float) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, x))


def from_dict(d: dict) -> Calibration:
    """Build a Calibration from a (possibly partial / dirty) dict, tolerantly."""
    if not isinstance(d, dict):
        return Calibration()
    defaults = Calibration()
    return Calibration(
        enabled             = bool(d.get("enabled", defaults.enabled)),
        screen_width_cm     = _clamp(d.get("screen_width_cm",     defaults.screen_width_cm),     _MIN_SCREEN_CM, _MAX_SCREEN_CM),
        screen_height_cm    = _clamp(d.get("screen_height_cm",    defaults.screen_height_cm),    _MIN_SCREEN_CM, _MAX_SCREEN_CM),
        viewing_distance_cm = _clamp(d.get("viewing_distance_cm", defaults.viewing_distance_cm), _MIN_DIST_CM,   _MAX_DIST_CM),
        parallax_strength   = _clamp(d.get("parallax_strength",   defaults.parallax_strength),   0.0, 1.0),
        parallax_gain       = _clamp(d.get("parallax_gain",       defaults.parallax_gain),       0.1, 4.0),
    )


def load(path: Path | str) -> Calibration:
    """Load calibration from JSON; return safe defaults (disabled) if missing
    or unreadable. Never raises — a bad file must not break the engine."""
    try:
        return from_dict(json.loads(Path(path).read_text()))
    except Exception:
        return Calibration()


class CalibrationRuntime:
    """Live, mtime-cached calibration — re-read only when the file changes on
    disk, mirroring WorldRuntime / the ~/.parallax_* flag polling. So a Settings
    UI (or a hand edit) takes effect live in both the demo and the daemon.

    When disabled (default), half_h() → None and shift_scale → 1.0, so the engine
    is byte-identical to the pre-calibration pipeline.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._mtime = None
        self.cal = load(self.path)

    def poll(self) -> bool:
        """Reload iff the file changed. Returns True when settings changed."""
        try:
            m = self.path.stat().st_mtime
        except OSError:
            m = None
        if m == self._mtime:
            return False
        self._mtime = m
        self.cal = load(self.path)
        return True

    # Convenience pass-throughs the engine uses each frame.
    def half_h(self) -> float | None:
        return self.cal.half_h()

    @property
    def shift_scale(self) -> float:
        return self.cal.shift_scale

    @property
    def enabled(self) -> bool:
        return self.cal.enabled
