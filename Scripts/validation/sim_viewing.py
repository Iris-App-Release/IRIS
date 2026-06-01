#!/usr/bin/env python3
"""
sim_viewing.py — Headless validation of the THREE-component viewing model.

No OpenGL, no camera, no display. Drives the SAME orbital_math functions main.py
uses and asserts that translation, distance scaling and rotation behave as three
independent, blended channels matching the design spec:

                    TRANSLATION        DISTANCE SCALING      ROTATION
    Far             strong             world small/deep      weak
    Mid             strong-decreasing  growing               increasing
    Close           reduced            large                 dominant
    Very close      subtle             maximum               primary

Concretely it checks, all measured through the off-axis projection:
  1. Distance scaling NOT inverted — leaning IN makes the Earth BIGGER on screen,
     leaning OUT makes it smaller. (The bug this revision fixes.)
  2. Translation parallax is STRONG when far and REDUCED when close (the cz
     coupling), yet always present (> 0) at every distance.
  3. Rotation is gated by proximity — turning the head reveals ~nothing far away
     and a lot up close, with a smooth (C¹) ramp and no mode switch.
  4. Rotation sense is correct & OPPOSITE to translation — turning right pans the
     view right (reveals the scene's right); moving right reveals the left.
  5. Independence — each input moves only its own channel: changing head
     distance does not pan the view; turning the head does not rescale the world.
  6. Earth stays finite/stable across a combined jittery far→close sweep with
     simultaneous translation, distance change and head turning.

Run:  .venv/bin/python sim_viewing.py
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

# main.py head→camera mapping (kept in sync with main.py).
MAX_SHIFT   = 4.5
ZOOM_K      = 0.95
BASE_Z      = om.CAM_BASE_Z
CAM_Z_MIN   = 5.0
CAM_Z_MAX   = 34.0
ROT_MAX_RAD = math.radians(om.ROT_MAX_DEG)

EARTH_W = np.array(om.EARTH_BASE, dtype=np.float64)   # fixed world position
EARTH_R = om.R_SURFACE

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


# ── main.py head→camera replicas ────────────────────────────────────────────
def cam_x_for(hx: float) -> float:        return -hx * MAX_SHIFT
def cam_y_for(hy: float) -> float:        return  hy * MAX_SHIFT * 0.55
def cam_z_for(hz: float) -> float:
    return max(CAM_Z_MIN, min(CAM_Z_MAX, BASE_Z * math.exp(ZOOM_K * hz)))


def rig(hx=0.0, hy=0.0, hz=0.0, yaw=0.0, pitch=0.0):
    """Build (eye, view, proj) for a full head state, as main.py does."""
    cx, cy, cz = cam_x_for(hx), cam_y_for(hy), cam_z_for(hz)
    prox = om.proximity(hz)
    view = om.view_matrix(cx, cy, cz, yaw * ROT_MAX_RAD * prox, pitch * ROT_MAX_RAD * prox)
    proj = om.off_axis_frustum(cx, cy, cz, ASPECT, om.NEAR, om.FAR)
    return np.array([cx, cy, cz]), view, proj


def earth_screen_radius(view, proj) -> float:
    """Approx on-screen pixel radius of the Earth disk."""
    right = view[0, :3]
    c = om.project_point(EARTH_W, view, proj, VP_W, VP_H)
    e = om.project_point(EARTH_W + right * EARTH_R, view, proj, VP_W, VP_H)
    return math.hypot(e[0] - c[0], e[1] - c[1])


def earth_screen_x(view, proj) -> float:
    return om.project_point(EARTH_W, view, proj, VP_W, VP_H)[0]


def star_screen_x(view, proj, depth=-60.0) -> float:
    return om.project_point([0.0, 0.0, depth], view, proj, VP_W, VP_H)[0]


def main() -> int:
    print("three-component viewing model")
    print(f"  CAM_Z∈[{CAM_Z_MIN},{CAM_Z_MAX}]  ZOOM_K={ZOOM_K}  "
          f"ROT_MAX={om.ROT_MAX_DEG}°  prox∈[{om.ROT_PROX_LO},{om.ROT_PROX_HI}]")
    print()

    HZ = [-0.6, -0.3, 0.0, 0.4, 0.8, 1.0]   # far → very close

    # ── 1. Distance scaling NOT inverted (closer = bigger) ───────────────────
    print("1. Distance scaling — leaning IN enlarges the world (not inverted)")
    sizes = []
    for hz in HZ:
        _, v, p = rig(hz=hz)
        sizes.append(earth_screen_radius(v, p))
        print(f"       hz={hz:+.2f}  eye_z={cam_z_for(hz):6.2f}  Earth r={sizes[-1]:6.1f}px")
    check("Earth grows monotonically as the viewer leans in",
          all(sizes[i] < sizes[i + 1] for i in range(len(sizes) - 1)),
          f"{sizes[0]:.0f}px (far) → {sizes[-1]:.0f}px (very close)")
    check("close Earth is clearly larger than far Earth",
          sizes[-1] > sizes[0] * 1.4, f"{sizes[-1]/sizes[0]:.2f}× over the range")

    # ── 2. Translational parallax: strong far, reduced close, never zero ─────
    print("\n2. Translation parallax — strong far, reduced close, always present")
    DX = 0.04   # small lateral head move
    pars = []
    for hz in HZ:
        _, v0, p0 = rig(hx=-DX, hz=hz)
        _, v1, p1 = rig(hx=+DX, hz=hz)
        pars.append(abs(earth_screen_x(v1, p1) - earth_screen_x(v0, p0)))
        print(f"       hz={hz:+.2f}  Earth parallax={pars[-1]:6.1f}px")
    check("parallax is non-zero at every distance", all(px > 0.5 for px in pars),
          f"min {min(pars):.1f}px")
    check("parallax is STRONGER far than close (cz coupling)",
          pars[0] > pars[-1] * 1.4, f"far {pars[0]:.0f}px vs close {pars[-1]:.0f}px")

    # ── 3. Rotation gated by proximity (weak far, dominant close, smooth) ────
    print("\n3. Rotation — proximity-gated reveal (weak far → dominant close)")
    YAW = 0.6   # fixed head turn to the right
    rots = []
    for hz in HZ:
        _, v0, p0 = rig(hz=hz, yaw=0.0)
        _, v1, p1 = rig(hz=hz, yaw=YAW)
        # how much the far background sweeps when the head turns (pure rotation)
        rots.append(abs(star_screen_x(v1, p1) - star_screen_x(v0, p0)))
        print(f"       hz={hz:+.2f}  prox={om.proximity(hz):.2f}  "
              f"rotation reveal={rots[-1]:7.1f}px")
    check("rotation reveal is ~zero far away", rots[0] < 2.0, f"{rots[0]:.2f}px far")
    check("rotation reveal grows monotonically toward close",
          all(rots[i] <= rots[i + 1] + 1e-6 for i in range(len(rots) - 1)),
          f"{rots[0]:.0f}px → {rots[-1]:.0f}px")
    check("rotation is significant up close", rots[-1] > 50.0, f"{rots[-1]:.0f}px close")
    # Smoothness: proximity is C¹ (smoothstep), so finite-difference steps grow
    # then shrink — never a single discontinuous jump.
    prox_series = [om.proximity(h) for h in np.linspace(-0.7, 1.0, 200)]
    steps = [abs(prox_series[i + 1] - prox_series[i]) for i in range(len(prox_series) - 1)]
    check("proximity gate is smooth (no step discontinuity)",
          max(steps) < 0.05, f"max step {max(steps):.4f}")

    # ── 4. Rotation sense is correct and OPPOSITE to translation ─────────────
    print("\n4. Sense — move right reveals LEFT; turn right reveals RIGHT")
    _, vbase, pbase = rig(hz=0.8)
    sx_base = star_screen_x(vbase, pbase)
    # Both are a RIGHTWARD head action, compared at the same proximity. In the
    # tracker's convention hx=+1 is viewer-LEFT, so a rightward TRANSLATION is
    # hx<0; a rightward head TURN is yaw>0. The spec's defining contrast is that
    # these reveal opposite sides → the background shifts in opposite directions.
    _, vt, pt = rig(hx=-0.3, hz=0.8)    # translate right → window reveals LEFT
    _, vr, pr = rig(hz=0.8, yaw=+0.6)   # turn right      → portal reveals RIGHT
    d_trans = star_screen_x(vt, pt) - sx_base
    d_rot   = star_screen_x(vr, pr) - sx_base
    check("translation and rotation move the scene in OPPOSITE directions",
          d_trans * d_rot < 0.0, f"Δtrans={d_trans:+.0f}px  Δrot={d_rot:+.0f}px")

    # ── 5. Independence of the three channels ────────────────────────────────
    print("\n5. Independence — each input drives only its own channel")
    # Changing distance must NOT pan the view (Earth x stays centred at hx=0).
    _, va, pa = rig(hz=-0.6)
    _, vb, pb = rig(hz=1.0)
    check("distance change does not pan the view (Earth stays centred)",
          abs(earth_screen_x(va, pa) - VP_W / 2) < 1.0 and
          abs(earth_screen_x(vb, pb) - VP_W / 2) < 1.0,
          f"x@far={earth_screen_x(va,pa):.0f}  x@close={earth_screen_x(vb,pb):.0f}  (centre {VP_W/2:.0f})")
    # Turning the head must NOT rescale the world (Earth radius unchanged by yaw).
    _, vc, pc = rig(hz=0.8, yaw=0.0)
    _, vd, pd = rig(hz=0.8, yaw=0.7)
    rc, rd = earth_screen_radius(vc, pc), earth_screen_radius(vd, pd)
    check("head turn does not rescale the world (Earth size ~unchanged)",
          abs(rc - rd) / rc < 0.05, f"r={rc:.0f}px vs {rd:.0f}px ({abs(rc-rd)/rc*100:.1f}%)")

    # ── 6. Stability under a combined far→close jittery sweep ────────────────
    print("\n6. Stability — combined translation+distance+rotation stays finite")
    rng = np.random.default_rng(3)
    prev = None
    max_jump = 0.0
    finite = True
    for i in range(600):
        hz = -0.7 + 1.7 * (i / 599)
        hx = 0.6 * math.sin(i * 0.11) + rng.uniform(-0.05, 0.05)
        yaw = 0.7 * math.sin(i * 0.07)
        _, v, p = rig(hx=hx, hz=hz, yaw=yaw)
        r = om.project_point(EARTH_W, v, p, VP_W, VP_H)
        if r is None or not all(math.isfinite(c) for c in r[:2]):
            finite = False
            break
        if prev is not None:
            max_jump = max(max_jump, math.hypot(r[0] - prev[0], r[1] - prev[1]))
        prev = r
    check("Earth projection stays finite across the whole sweep", finite)
    check("frame-to-frame Earth motion stays bounded", finite and max_jump < VP_W,
          f"max step {max_jump:.0f}px (< {VP_W:.0f}px)")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
