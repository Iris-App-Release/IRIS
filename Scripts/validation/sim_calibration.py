#!/usr/bin/env python3
"""
sim_calibration.py — Headless validation of the opt-in METRIC calibration layer.

No OpenGL, no camera, no display. Exercises the SAME functions the engine drives
(Engine/camera_math.off_axis_frustum + Engine/calibration) and proves two things:

  A. BACKWARD COMPATIBILITY (the freeze is preserved). The new optional `half_h`
     argument defaults to the frozen WINDOW_HALF_H, so every existing call —
     every other sim, the engine's default path — is byte-for-byte unchanged.
     Calibration DISABLED returns half_h→None and shift_scale→1.0.

  B. METRIC CORRECTNESS (the new capability). With calibration enabled the window
     subtends the TRUE physical angle of the user's screen at the neutral eye
     distance; the cinematic↔metric blend is monotone; and the frustum is still a
     real "hole" (window corners land on the screen border) for any half_h.

Run:  .venv/bin/python Scripts/validation/sim_calibration.py
Exit code 0 = all checks pass, 1 = a check failed.
"""

from __future__ import annotations

# --- reorg path shim (validation harness) ---
import sys as _s
from pathlib import Path as _P
_root = str(_P(__file__).resolve().parents[2])
if _root not in _s.path:
    _s.path.insert(0, _root)

import json
import math
import sys
import tempfile

import numpy as np

from Engine import camera_math as om
from Engine import calibration as cal

VP_W, VP_H = 2560.0, 1600.0
ASPECT     = VP_W / VP_H
BASE_Z     = om.CAM_BASE_Z

_fail = 0
def check(name: str, ok: bool, detail: str = "") -> None:
    global _fail
    mark = "PASS" if ok else "FAIL"
    if not ok:
        _fail += 1
    line = f"  [{mark}] {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)


def true_fov_deg(screen_h_cm: float, dist_cm: float) -> float:
    return 2.0 * math.degrees(math.atan((0.5 * screen_h_cm) / dist_cm))


def main() -> int:
    print("metric calibration validation")
    print(f"  frozen WINDOW_HALF_H={om.WINDOW_HALF_H:.4f}  FOVY={om.FOVY_DEG}°  "
          f"CAM_BASE_Z={BASE_Z}")
    print()

    # ── A1. Backward compat: half_h=None reproduces the frozen matrix ─────────
    print("A1. half_h=None is byte-identical to the frozen call (freeze preserved)")
    worst = 0.0
    for (cx, cy, cz) in [(0, 0, BASE_Z), (3.5, -2.0, 6.0), (-4.0, 1.5, 3.0), (1.0, 0.0, 20.0)]:
        a = om.off_axis_frustum(cx, cy, cz, ASPECT, om.NEAR, om.FAR)              # frozen signature
        b = om.off_axis_frustum(cx, cy, cz, ASPECT, om.NEAR, om.FAR, half_h=None)  # new arg, default
        worst = max(worst, float(np.max(np.abs(a - b))))
    check("off_axis_frustum(half_h=None) == off_axis_frustum(...)", worst == 0.0,
          f"max element diff {worst:.2e}")
    we_a = om.window_half_extents(ASPECT)
    we_b = om.window_half_extents(ASPECT, None)
    check("window_half_extents(aspect, None) == window_half_extents(aspect)",
          we_a == we_b, f"{we_a} vs {we_b}")

    # ── A2. Disabled calibration is the frozen path ───────────────────────────
    print("\nA2. Disabled calibration → frozen framing (half_h=None, shift×1.0)")
    c_off = cal.Calibration(enabled=False)
    check("disabled half_h() is None", c_off.half_h() is None, f"{c_off.half_h()}")
    check("disabled shift_scale == 1.0", c_off.shift_scale == 1.0, f"{c_off.shift_scale}")
    check("disabled subtended FOV == FOVY_DEG",
          abs(c_off.subtended_fov_deg() - om.FOVY_DEG) < 1e-6,
          f"{c_off.subtended_fov_deg():.3f}° vs {om.FOVY_DEG}°")

    # ── A3. strength=0 (enabled) is still exactly the cinematic look ──────────
    print("\nA3. parallax_strength=0 (enabled) == cinematic half-height exactly")
    c0 = cal.Calibration(enabled=True, screen_height_cm=19.0, viewing_distance_cm=60.0,
                         parallax_strength=0.0)
    check("strength 0 → half_h == frozen WINDOW_HALF_H",
          abs(c0.blended_half_h() - om.WINDOW_HALF_H) < 1e-9,
          f"{c0.blended_half_h():.6f} vs {om.WINDOW_HALF_H:.6f}")

    # ── B1. Centred reduction holds for ANY half_h (correct perspective) ──────
    print("\nB1. Centred eye with custom half_h == perspective(true subtended FOV)")
    worst = 0.0
    for H in [3.0, om.WINDOW_HALF_H, 8.0]:
        off = om.off_axis_frustum(0.0, 0.0, BASE_Z, ASPECT, half_h=H)
        fov = 2.0 * math.degrees(math.atan(H / BASE_Z))
        per = om.perspective(fov, ASPECT, om.NEAR, om.FAR)
        worst = max(worst, float(np.max(np.abs(off - per))))
    check("off_axis(centred, half_h=H) == perspective(2·atan(H/BASE_Z))",
          worst < 1e-9, f"max element diff {worst:.2e}")

    # ── B2. Metric subtense matches the real screen geometry ──────────────────
    print("\nB2. Enabled+metric → window subtends the TRUE physical angle")
    for (w, h, d) in [(34.0, 19.0, 60.0), (60.0, 34.0, 70.0), (28.0, 18.0, 45.0)]:
        c = cal.Calibration(enabled=True, screen_width_cm=w, screen_height_cm=h,
                            viewing_distance_cm=d, parallax_strength=1.0)
        want = true_fov_deg(h, d)
        got  = c.subtended_fov_deg()
        check(f"screen {h}cm @ {d}cm → subtended FOV ≈ {want:.1f}°",
              abs(got - want) < 1e-6, f"got {got:.3f}°")

    # ── B3. Cinematic↔metric blend is monotone in strength ────────────────────
    print("\n3. blend is monotone from cinematic (s=0) to metric (s=1)")
    # A close, large screen → metric FOV is NARROWER than the 58° cinematic, so
    # half_h should DECREASE monotonically as strength rises.
    base = dict(enabled=True, screen_height_cm=19.0, viewing_distance_cm=60.0)
    hs = [cal.Calibration(parallax_strength=s, **base).blended_half_h()
          for s in (0.0, 0.25, 0.5, 0.75, 1.0)]
    metric = cal.Calibration(parallax_strength=1.0, **base).metric_half_h()
    check("s=0 is cinematic, s=1 is metric",
          abs(hs[0] - om.WINDOW_HALF_H) < 1e-9 and abs(hs[-1] - metric) < 1e-9,
          f"{hs[0]:.3f} → {hs[-1]:.3f}")
    check("half_h changes monotonically with strength",
          all(hs[i] >= hs[i + 1] - 1e-12 for i in range(len(hs) - 1)),
          f"{[round(x,3) for x in hs]}")

    # ── B4. Still a real "hole": corners on the screen border for any half_h ──
    print("\nB4. Window corners map to the screen border for a calibrated half_h")
    H = cal.Calibration(enabled=True, screen_height_cm=19.0,
                        viewing_distance_cm=45.0, parallax_strength=1.0).blended_half_h()
    half_w, half_h = om.window_half_extents(ASPECT, H)
    worst = 0.0
    for (cx, cy, cz) in [(0, 0, BASE_Z), (3.0, -1.5, 6.0), (-2.5, 2.0, 9.0)]:
        view = om.view_translate(cx, cy, cz)
        proj = om.off_axis_frustum(cx, cy, cz, ASPECT, om.NEAR, om.FAR, half_h=H)
        for sx in (-half_w, half_w):
            for sy in (-half_h, half_h):
                r = om.project_point([sx, sy, 0.0], view, proj, VP_W, VP_H)
                ex = min(abs(r[0] - 0.0), abs(r[0] - VP_W))
                ey = min(abs(r[1] - 0.0), abs(r[1] - VP_H))
                worst = max(worst, ex, ey)
    check("calibrated window corners sit on the border for every eye",
          worst < 1e-6, f"max border error {worst:.2e}px")

    # ── B5. Safety clamps on malformed / extreme input ────────────────────────
    print("\nB5. Malformed / extreme settings clamp to a safe, finite frustum")
    bad = cal.from_dict({"enabled": True, "screen_height_cm": -5.0,
                         "viewing_distance_cm": 0.0, "parallax_strength": 9.0,
                         "parallax_gain": 999.0})
    hh = bad.blended_half_h()
    check("blended half_h stays finite and bounded",
          math.isfinite(hh) and 0.0 < hh <= om.WINDOW_HALF_H * 1.5 + 1e-9,
          f"half_h={hh:.4f}")
    check("shift_scale clamped to a sane range", 0.1 <= bad.shift_scale <= 4.0,
          f"{bad.shift_scale}")

    # ── B6. Runtime load/poll round-trip ──────────────────────────────────────
    print("\nB6. CalibrationRuntime: missing→disabled, written file loads enabled")
    with tempfile.TemporaryDirectory() as td:
        p = _P(td) / "calibration.json"
        rt = cal.CalibrationRuntime(p)         # file absent
        check("absent file → disabled (frozen path)",
              rt.enabled is False and rt.half_h() is None and rt.shift_scale == 1.0)
        p.write_text(json.dumps({"enabled": True, "screen_height_cm": 19.0,
                                 "viewing_distance_cm": 50.0, "parallax_strength": 1.0,
                                 "parallax_gain": 1.5}))
        changed = rt.poll()
        want = true_fov_deg(19.0, 50.0)
        got  = rt.cal.subtended_fov_deg()
        check("poll() picks up the written file",
              changed and rt.enabled and abs(got - want) < 1e-6 and rt.shift_scale == 1.5,
              f"FOV {got:.2f}° (want {want:.2f}°), shift×{rt.shift_scale}")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
