#!/usr/bin/env python3
"""
sim_offaxis.py — Headless validation of the off-axis "window" projection.

No OpenGL, no camera, no display. Exercises the off-axis (Kooima generalized
perspective) math in orbital_math.py — the SAME functions main.py drives — and
asserts that the rendered geometry behaves like a real window into a fixed
scene rather than a panned/tilted camera.

Checks:
  1. Centred reduction   — an on-axis eye at CAM_BASE_Z reproduces the original
                           gluPerspective(FOVY_DEG) framing exactly.
  2. No view rotation     — the modelview is pure translation (a window reveals
                           by eye POSITION, never by tilting toward a target).
  3. Aperture parallax    — a fixed object shifts on screen when the eye moves
                           laterally, and (through a FIXED aperture) FARTHER
                           objects sweep across the frame faster than near ones.
                           This is window geometry, not free-field parallax:
                           image-on-glass shift = |z|/(half_w·(cz+|z|)), which
                           rises with depth |z|. Verified by ray/glass geometry.
  4. FOV vs eye distance  — the subtended FOV is a monotone function of the
                           eye-to-glass distance alone (2·atan(half_h/cz)); the
                           neutral distance reproduces the original FOVY_DEG. The
                           viewer-proximity POLICY that drives cz (and the three-
                           component blend) lives in sim_viewing.py.
  5. Continuity           — projected motion stays finite and bounded across the
                           whole clamped eye-distance range (no pops / NaNs).
  6. Edge sanity          — the window corners always sit on the frustum edges
                           (NDC ±1) for any eye position: it is literally a hole.

Run:  .venv/bin/python sim_offaxis.py
Exit code 0 = all checks pass, 1 = a check failed.
"""

from __future__ import annotations

# --- reorg path shim (validation harness) ---
import sys as _s
from pathlib import Path as _P
_root = str(_P(__file__).resolve().parents[2])
if _root not in _s.path:
    _s.path.insert(0, _root)

import math
import sys

import numpy as np

from Engine import camera_math as om

VP_W, VP_H = 2560.0, 1600.0
ASPECT     = VP_W / VP_H

# main.py head→camera mapping constants (kept in sync with main.py).
ZOOM_K     = 0.95
BASE_Z     = om.CAM_BASE_Z
CAM_Z_MIN  = 5.0
CAM_Z_MAX  = 34.0

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


def cam_z_for(hz: float) -> float:
    """Replica of main.py's depth mapping: leaning IN (hz↑) → larger eye-glass
    distance → narrower frustum → larger world. Exponential, no clamping in range."""
    return max(CAM_Z_MIN, min(CAM_Z_MAX, BASE_Z * math.exp(ZOOM_K * hz)))


def screen_x(world, cam_x, cam_y, cam_z) -> float | None:
    view = om.view_translate(cam_x, cam_y, cam_z)
    proj = om.off_axis_frustum(cam_x, cam_y, cam_z, ASPECT, om.NEAR, om.FAR)
    r = om.project_point(world, view, proj, VP_W, VP_H)
    return None if r is None else r[0]


def lateral_reveal_px(world, cam_z, d_eye=0.25) -> float:
    """Screen-x shift of a fixed world point for a small lateral eye move."""
    a = screen_x(world, -d_eye, 0.0, cam_z)
    b = screen_x(world, +d_eye, 0.0, cam_z)
    return abs(b - a)


def main() -> int:
    half_w, half_h = om.window_half_extents(ASPECT)
    print("off-axis window configuration")
    print(f"  FOVY={om.FOVY_DEG}°  CAM_BASE_Z={BASE_Z}  window half-extents "
          f"= {half_w:.2f} × {half_h:.2f} world units")
    print()

    # ── 1. Centred reduction to the original perspective ─────────────────────
    print("1. Centred eye reproduces the original gluPerspective framing")
    off = om.off_axis_frustum(0.0, 0.0, BASE_Z, ASPECT)
    per = om.perspective(om.FOVY_DEG, ASPECT, om.NEAR, om.FAR)
    err = float(np.max(np.abs(off - per)))
    check("off_axis_frustum(centred) == perspective(FOVY_DEG)", err < 1e-9,
          f"max matrix element error {err:.2e}")

    # ── 2. Modelview is pure translation (no tilt-to-target) ─────────────────
    print("\n2. View is pure translation (a window does not rotate to a target)")
    v = om.view_translate(2.0, -1.0, 7.0)
    rot_err = float(np.max(np.abs(v[:3, :3] - np.identity(3))))
    check("modelview 3×3 is identity (zero rotation)", rot_err < 1e-12,
          f"max off-identity {rot_err:.2e}")
    check("modelview translation == -eye",
          np.allclose(v[:3, 3], [-2.0, 1.0, -7.0]), f"col={v[:3,3].tolist()}")

    # ── 3. Aperture parallax, depth-ordered (far sweeps faster than near) ────
    print("\n3. Aperture parallax (fixed objects shift; FAR sweeps faster)")
    near_obj = np.array([0.0, 0.0,  -6.0])   # just behind the glass
    mid_obj  = np.array([0.0, 0.0, -10.0])   # Earth depth
    far_obj  = np.array([0.0, 0.0, -80.0])   # near the nebula shell
    rn = lateral_reveal_px(near_obj, BASE_Z)
    rm = lateral_reveal_px(mid_obj,  BASE_Z)
    rf = lateral_reveal_px(far_obj,  BASE_Z)
    check("a fixed object shows non-zero screen parallax", rm > 1.0, f"{rm:.1f}px")
    # Through a fixed window: shift = |z|/(half_w·(cz+|z|)) rises with depth, so
    # the far object sweeps the frame faster than the near one (verified by the
    # ray/glass derivation, not free-field 'near moves more' intuition).
    check("farther objects sweep the frame faster than nearer (aperture rule)",
          rf > rm > rn, f"far {rf:.0f} > mid {rm:.0f} > near {rn:.0f} px")

    # ── 4. FOV is a monotone function of eye-to-glass distance (policy-free) ──
    print("\n4. Subtended FOV depends only on eye-to-glass distance (smaller=wider)")
    czs = [4.0, 6.0, BASE_Z, 20.0, 40.0]
    fov_vals = [2.0 * math.degrees(math.atan(half_h / cz)) for cz in czs]
    for cz, fov in zip(czs, fov_vals):
        print(f"       eye_z={cz:6.2f}  vertical FOV={fov:6.1f}°")
    check("smaller eye-to-glass distance → wider FOV (monotone)",
          all(fov_vals[i] > fov_vals[i + 1] for i in range(len(fov_vals) - 1)),
          f"{fov_vals[0]:.0f}° (near glass) → {fov_vals[-1]:.0f}° (far from glass)")
    # The neutral eye distance must reproduce the original framing exactly.
    fov_neutral = 2.0 * math.degrees(math.atan(half_h / BASE_Z))
    check("neutral-distance FOV == original FOVY_DEG", abs(fov_neutral - om.FOVY_DEG) < 1e-6,
          f"{fov_neutral:.2f}° vs {om.FOVY_DEG}°")

    # ── 5. Continuity / finiteness across the clamped distance range ─────────
    print("\n5. Continuity (finite, bounded screen motion across all distances)")
    prev = None
    max_jump = 0.0
    finite = True
    for i in range(400):
        hz = -0.7 + 1.7 * i / 399          # sweep full clamp range
        cz = cam_z_for(hz)
        sx = screen_x(mid_obj, 1.0, 0.0, cz)   # off-axis eye, swept distance
        if sx is None or not math.isfinite(sx):
            finite = False
            break
        if prev is not None:
            max_jump = max(max_jump, abs(sx - prev))
        prev = sx
    check("all projections finite across the eye-distance sweep", finite)
    check("frame-to-frame screen motion stays bounded", finite and max_jump < VP_W,
          f"max step {max_jump:.0f}px (< {VP_W:.0f}px)")

    # ── 6. The window corners are always on the frustum edges ────────────────
    print("\n6. Window corners map to the frustum edges for any eye (a real hole)")
    worst = 0.0
    for (cx, cy, cz) in [(0, 0, BASE_Z), (3.5, -2.0, 6.0), (-4.0, 1.5, 3.0)]:
        view = om.view_translate(cx, cy, cz)
        proj = om.off_axis_frustum(cx, cy, cz, ASPECT, om.NEAR, om.FAR)
        for sx in (-half_w, half_w):
            for sy in (-half_h, half_h):
                r = om.project_point([sx, sy, 0.0], view, proj, VP_W, VP_H)
                # corner should land on the screen edge: x∈{0,VP_W}, y∈{0,VP_H}
                ex = min(abs(r[0] - 0.0), abs(r[0] - VP_W))
                ey = min(abs(r[1] - 0.0), abs(r[1] - VP_H))
                worst = max(worst, ex, ey)
    check("window rect corners sit on the screen border for every eye",
          worst < 1e-6, f"max border error {worst:.2e}px")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
