#!/usr/bin/env python3
"""
sim_vertical.py — Headless validation of NEAR-FIELD vertical exploration.

No camera, no GL. Replicates main.py's EXACT pitch pipeline (planet-anchor
offset → separate vertical gain → pan clamp → proximity gate) and drives the
real orbital_math projection to verify the Objective-#2 behaviour:

  • FAR field: head pitch barely moves the Earth (unchanged behaviour).
  • NEAR field: looking strongly UP pushes the Earth off the bottom of the
    screen; looking strongly DOWN pushes it off the top — "peer up/down through
    the window" with enough range that the Earth can leave the frame.
  • NEUTRAL gaze (resting on the planet) keeps the Earth ~centred — the
    planet-anchor offset still does its job.
  • Vertical exploration does NOT bleed into horizontal: yaw is untouched.
  • The transition is smooth (proximity-gated, C¹) — no pop, no far-field change.

These pitch constants are kept in sync with main.py.

Run:  .venv/bin/python sim_vertical.py
Exit 0 = all checks pass, 1 = a check failed.
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

# ── main.py head→camera mapping (kept in sync with main.py) ──────────────────
MAX_SHIFT          = 4.5
ZOOM_K             = 0.95
BASE_Z             = om.CAM_BASE_Z
CAM_Z_MIN, CAM_Z_MAX = 5.0, 34.0
ROT_MAX_RAD        = math.radians(om.ROT_MAX_DEG)          # yaw gain (20°)

# Near-field vertical-exploration constants (MUST match main.py):
LOOK_PITCH_OFFSET  = 0.25                                  # planet anchor (normalised)
ROT_MAX_PITCH_RAD  = math.radians(40.0)                    # vertical gain (> yaw)
PITCH_PAN_MAX_RAD  = math.radians(46.0)                    # pan clamp (anti-overrotate)

EARTH_W = np.array(om.EARTH_BASE, dtype=np.float64)
EARTH_R = om.R_SURFACE

_fail = 0
def check(name: str, ok: bool, detail: str = "") -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)


def cam_z_for(hz: float) -> float:
    return max(CAM_Z_MIN, min(CAM_Z_MAX, BASE_Z * math.exp(ZOOM_K * hz)))


def pitch_pan(pitch: float, prox: float, has_rotation: bool = True) -> float:
    """main.py's exact pitch→pan computation."""
    pitch_in = (pitch - LOOK_PITCH_OFFSET * prox) if has_rotation else pitch
    pan = pitch_in * ROT_MAX_PITCH_RAD * prox
    return max(-PITCH_PAN_MAX_RAD, min(PITCH_PAN_MAX_RAD, pan))


def rig(hz=0.0, yaw=0.0, pitch=0.0):
    """(eye, view, proj) for a head state, replicating main.py's pitch path."""
    cz = cam_z_for(hz)
    prox = om.proximity(hz)
    view = om.view_matrix(0.0, 0.0, cz,
                          yaw * ROT_MAX_RAD * prox,
                          pitch_pan(pitch, prox))
    proj = om.off_axis_frustum(0.0, 0.0, cz, ASPECT, om.NEAR, om.FAR)
    return np.array([0.0, 0.0, cz]), view, proj


def earth_screen_y(view, proj) -> float:
    return om.project_point(EARTH_W, view, proj, VP_W, VP_H)[1]


def earth_screen_x(view, proj) -> float:
    return om.project_point(EARTH_W, view, proj, VP_W, VP_H)[0]


def earth_screen_radius(view, proj) -> float:
    up = view[1, :3]
    c = om.project_point(EARTH_W, view, proj, VP_W, VP_H)
    e = om.project_point(EARTH_W + up * EARTH_R, view, proj, VP_W, VP_H)
    return math.hypot(e[0] - c[0], e[1] - c[1])


def earth_fully_off(view, proj) -> bool:
    """True iff the whole Earth disk is outside the vertical extent of the screen."""
    y = earth_screen_y(view, proj)
    r = earth_screen_radius(view, proj)
    return (y - r > VP_H) or (y + r < 0.0)


def main() -> int:
    print("near-field vertical exploration")
    print(f"  offset={LOOK_PITCH_OFFSET}  pitch_gain={math.degrees(ROT_MAX_PITCH_RAD):.0f}°  "
          f"clamp=±{math.degrees(PITCH_PAN_MAX_RAD):.0f}°  yaw_gain={om.ROT_MAX_DEG:.0f}°")
    print()

    # ── 1. Far field: pitch barely moves the Earth ───────────────────────────
    print("1. FAR field — head pitch barely moves the Earth (unchanged)")
    _, v0, p0 = rig(hz=-0.5, pitch=0.0)
    y_far_center = earth_screen_y(v0, p0)
    moved = []
    for pit in (-1.0, -0.5, 0.5, 1.0):
        _, v, p = rig(hz=-0.5, pitch=pit)
        moved.append(abs(earth_screen_y(v, p) - y_far_center))
    check("Earth vertical motion is small at far distance",
          max(moved) < 60.0, f"max |Δy|={max(moved):.0f}px over full pitch range")

    # ── 2. Near field, looking DOWN → Earth leaves the screen ────────────────
    print("\n2. NEAR field — looking DOWN reveals lower world, Earth leaves frame")
    rows = []
    off_down = None
    for pit in (0.3, 0.5, 0.7, 0.85, 1.0):
        _, v, p = rig(hz=1.0, pitch=pit)
        y = earth_screen_y(v, p); r = earth_screen_radius(v, p)
        gone = earth_fully_off(v, p)
        rows.append((pit, y, r, gone))
        if gone and off_down is None:
            off_down = pit
        print(f"       pitch=+{pit:.2f}  Earth y={y:7.0f}px  r={r:4.0f}px  off-screen={gone}")
    check("a strong downward gaze pushes the Earth fully off-screen",
          off_down is not None, f"clears at pitch≈+{off_down}" if off_down else "never clears")

    # ── 3. Near field, looking UP → Earth leaves the screen ──────────────────
    print("\n3. NEAR field — looking UP reveals upper world, Earth leaves frame")
    off_up = None
    for pit in (-0.3, -0.5, -0.7, -0.85, -1.0):
        _, v, p = rig(hz=1.0, pitch=pit)
        y = earth_screen_y(v, p); r = earth_screen_radius(v, p)
        gone = earth_fully_off(v, p)
        if gone and off_up is None:
            off_up = pit
        print(f"       pitch={pit:+.2f}  Earth y={y:7.0f}px  r={r:4.0f}px  off-screen={gone}")
    check("a strong upward gaze pushes the Earth fully off-screen",
          off_up is not None, f"clears at pitch≈{off_up}" if off_up else "never clears")

    # ── 4. Neutral gaze (resting on planet) keeps Earth ~centred ─────────────
    print("\n4. NEUTRAL gaze (pitch≈offset) keeps the Earth near screen centre")
    # Resting gaze on the planet reads as pitch≈+LOOK_PITCH_OFFSET (the anchor).
    _, v, p = rig(hz=1.0, pitch=LOOK_PITCH_OFFSET)
    y = earth_screen_y(v, p)
    check("planet-anchored neutral gaze stays roughly centred",
          abs(y - VP_H / 2) < 0.18 * VP_H,
          f"y={y:.0f}px (centre {VP_H/2:.0f}, ±{0.18*VP_H:.0f})")

    # ── 5. Vertical exploration does not move things horizontally ─────────────
    print("\n5. Independence — vertical gaze does not pan horizontally")
    _, v0, p0 = rig(hz=1.0, pitch=0.0)
    x0 = earth_screen_x(v0, p0)
    dxs = []
    for pit in (-1.0, -0.5, 0.5, 1.0):
        _, v, p = rig(hz=1.0, pitch=pit)
        dxs.append(abs(earth_screen_x(v, p) - x0))
    check("Earth horizontal position is unchanged by pitch",
          max(dxs) < 1.0, f"max |Δx|={max(dxs):.3f}px")

    # ── 6. Smoothness — vertical reveal ramps smoothly with proximity ────────
    print("\n6. Smoothness — downward reveal ramps smoothly far→near (no pop)")
    ys = []
    for hz in np.linspace(-0.7, 1.0, 120):
        _, v, p = rig(hz=float(hz), pitch=0.8)
        ys.append(earth_screen_y(v, p))
    steps = [abs(ys[i + 1] - ys[i]) for i in range(len(ys) - 1)]
    # finite-difference bound — a smooth (smoothstep-gated) ramp has no jump
    check("vertical reveal has no discontinuous jump across the distance sweep",
          max(steps) < 120.0, f"max step {max(steps):.0f}px")
    check("all projections finite across the sweep",
          all(math.isfinite(y) for y in ys))

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
