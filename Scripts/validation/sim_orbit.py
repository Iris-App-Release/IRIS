#!/usr/bin/env python3
"""
sim_orbit.py — Headless verification of the orbital icon math.

No OpenGL, no camera, no display. Exercises orbital_math.py (the SAME geometry
renderer.IconOrbit ships) and asserts the properties that the broken two-process
overlay could never satisfy:

  1. Rigid-body parallax lock — icons + Earth move together in world space.
  2. Real occlusion           — the far arc passes behind the Earth silhouette;
                                 the near arc and the sides do not.
  3. Atmosphere clearance      — no icon ever clips the Earth's glow shell.
  4. Projection sanity         — occluded icons land inside the Earth's projected
                                 disk; side icons land outside it.
  5. Perspective scaling       — nearer icons project larger than farther ones.
  6. Stability                 — a jumpy camera yields finite, continuous icon
                                 positions (no zero-state snap-to-center).

Run:  .venv/bin/python sim_orbit.py
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


def view_proj(cam_x: float, cam_y: float, cam_z: float):
    # Off-axis window rig (matches main.py): pure-translation modelview + an
    # asymmetric frustum keyed to the eye position. At a centred eye this is
    # identical to the old look_at + perspective rig, so the occlusion /
    # projection / scaling checks below are unaffected.
    eye  = om.camera_eye(cam_x, cam_y, cam_z)
    view = om.view_translate(cam_x, cam_y, cam_z)
    proj = om.off_axis_frustum(cam_x, cam_y, cam_z, ASPECT, om.NEAR, om.FAR)
    return eye, view, proj


def icon_world(angle: float, cam_x: float, cam_y: float, radius: float = om.ORBIT_RADIUS):
    return om.earth_world_center(cam_x, cam_y) + om.orbital_local_pos(angle, radius)


def earth_silhouette_radius_px(cam_x, cam_y, cam_z, view, proj):
    """Approx pixel radius of the Earth surface disk on screen."""
    center_w = om.earth_world_center(cam_x, cam_y)
    right    = view[0, :3]                       # camera right axis in world space
    edge_w   = center_w + right * om.R_SURFACE
    c = om.project_point(center_w, view, proj, VP_W, VP_H)
    e = om.project_point(edge_w,  view, proj, VP_W, VP_H)
    return math.hypot(e[0] - c[0], e[1] - c[1]), (c[0], c[1])


def main() -> int:
    print("orbital_math configuration")
    print(f"  ORBIT_RADIUS={om.ORBIT_RADIUS}  TILT={om.ORBIT_TILT_DEG}°  "
          f"R_SURFACE={om.R_SURFACE}  R_ATMOSPHERE={om.R_ATMOSPHERE}  "
          f"ICON_SIZE={om.ICON_WORLD_SIZE}")
    print()

    # ── 1. Rigid-body lock + window parallax ─────────────────────────────────
    print("1. Rigid-body lock (icons share Earth's world frame) + screen parallax")
    cam_a = (0.0, 0.0)
    cam_b = (3.0, -1.5)
    d_earth = om.earth_world_center(*cam_b) - om.earth_world_center(*cam_a)
    max_err = 0.0
    for k in range(12):
        ang = 2 * math.pi * k / 12
        # Same orbital angle => same local offset => world delta must equal Earth's.
        d_icon = icon_world(ang, *cam_b) - icon_world(ang, *cam_a)
        max_err = max(max_err, float(np.linalg.norm(d_icon - d_earth)))
    check("icon world-delta == Earth world-delta for all angles",
          max_err < 1e-9, f"max error {max_err:.2e} world units")
    # Off-axis window: the Earth is FIXED in world (delta ≈ 0); its parallax is
    # produced by the projection, so we assert the SCREEN shift is non-zero when
    # the eye translates — the physically correct restatement of the old check.
    _, va, pa = view_proj(*cam_a, om.CAM_BASE_Z)
    _, vb, pb = view_proj(*cam_b, om.CAM_BASE_Z)
    ec = om.earth_world_center(0.0, 0.0)
    sa = om.project_point(ec, va, pa, VP_W, VP_H)
    sb = om.project_point(ec, vb, pb, VP_W, VP_H)
    screen_par = math.hypot(sb[0] - sa[0], sb[1] - sa[1])
    check("Earth is fixed in world (no artificial follow)",
          float(np.linalg.norm(d_earth)) < 1e-9, f"|Δworld|={np.linalg.norm(d_earth):.2e}")
    check("Earth shows non-zero SCREEN parallax under eye translation",
          screen_par > 1.0, f"screen Δ={screen_par:.0f}px")

    # ── 2. Real occlusion via the depth buffer geometry ──────────────────────
    print("\n2. Occlusion (segment eye→icon crosses Earth surface sphere)")
    eye, view, proj = view_proj(0.0, 0.0, om.CAM_BASE_Z)
    center_w = om.earth_world_center(0.0, 0.0)
    back  = icon_world(+math.pi / 2, 0.0, 0.0)   # TOP of ring → recedes behind
    front = icon_world(-math.pi / 2, 0.0, 0.0)   # BOTTOM of ring → swings in front
    side0 = icon_world(0.0,          0.0, 0.0)
    side1 = icon_world(math.pi,      0.0, 0.0)
    check("TOP arc (angle +90°) is OCCLUDED by Earth (passes behind)",
          om.segment_hits_sphere(eye, back, center_w, om.R_SURFACE))
    check("BOTTOM arc (angle -90°) is NOT occluded (passes in front)",
          not om.segment_hits_sphere(eye, front, center_w, om.R_SURFACE))
    check("side (angle 0°) is NOT occluded",
          not om.segment_hits_sphere(eye, side0, center_w, om.R_SURFACE))
    check("side (angle 180°) is NOT occluded",
          not om.segment_hits_sphere(eye, side1, center_w, om.R_SURFACE))
    # Sweep: there must exist a contiguous occluded arc AND a visible arc.
    occluded = [om.segment_hits_sphere(eye, icon_world(2 * math.pi * k / 72, 0, 0),
                                       center_w, om.R_SURFACE) for k in range(72)]
    check("orbit has both occluded and visible arcs",
          any(occluded) and not all(occluded),
          f"{sum(occluded)}/72 samples occluded")

    # ── 3. Atmosphere clearance ──────────────────────────────────────────────
    print("\n3. Atmosphere clearance (no icon clips the glow shell)")
    min_r = min(om.icon_radius(t, 0.0) for t in np.linspace(0, 30, 300))
    check("min icon distance from Earth center > R_ATMOSPHERE",
          min_r > om.R_ATMOSPHERE, f"min {min_r:.3f} vs atmo {om.R_ATMOSPHERE}")

    # ── 4. Projection sanity vs the Earth silhouette ─────────────────────────
    print("\n4. Projection (occluded icons land inside Earth's screen disk)")
    sil_r, (ecx, ecy) = earth_silhouette_radius_px(0, 0, om.CAM_BASE_Z, view, proj)
    pb = om.project_point(back,  view, proj, VP_W, VP_H)
    ps = om.project_point(side0, view, proj, VP_W, VP_H)
    db = math.hypot(pb[0] - ecx, pb[1] - ecy)
    ds = math.hypot(ps[0] - ecx, ps[1] - ecy)
    check("back icon projects INSIDE Earth disk", db < sil_r,
          f"icon {db:.0f}px from center, disk r={sil_r:.0f}px")
    check("side icon projects OUTSIDE Earth disk", ds > sil_r,
          f"icon {ds:.0f}px from center, disk r={sil_r:.0f}px")
    check("back icon is deeper (more negative eye-z) than Earth center",
          pb[3] < om.project_point(center_w, view, proj, VP_W, VP_H)[3],
          f"back eye_z={pb[3]:.2f} vs earth eye_z="
          f"{om.project_point(center_w, view, proj, VP_W, VP_H)[3]:.2f}")

    # ── 5. Perspective scaling (near bigger than far) ────────────────────────
    print("\n5. Perspective scaling (near icon renders larger than far icon)")
    def screen_size_px(world_pos):
        right = view[0, :3]
        c = om.project_point(world_pos, view, proj, VP_W, VP_H)
        e = om.project_point(world_pos + right * om.ICON_WORLD_SIZE, view, proj, VP_W, VP_H)
        return math.hypot(e[0] - c[0], e[1] - c[1])
    near_px = screen_size_px(front)
    far_px  = screen_size_px(back)
    check("near icon screen size > far icon screen size", near_px > far_px,
          f"near {near_px:.0f}px  far {far_px:.0f}px  (ratio {near_px/far_px:.2f}×)")

    # ── 6. Stability under a jumpy camera (the old zero-state-snap failure) ───
    print("\n6. Stability (jumpy head input -> continuous, finite icon motion)")
    rng = np.random.default_rng(1)
    prev = None
    max_jump = 0.0
    finite = True
    cx = cy = cz = 0.0
    for f in range(600):
        # Simulated noisy head target + the CAM_LAG=0.55 smoothing main.py uses.
        tx, ty = rng.uniform(-4.5, 4.5), rng.uniform(-2.5, 2.5)
        cx += 0.55 * (tx - cx); cy += 0.55 * (ty - cy)
        cz  = om.CAM_BASE_Z
        _, v, p = view_proj(cx, cy, cz)
        pos = om.project_point(icon_world(om.icon_angle(0.0, f / 60.0), cx, cy),
                               v, p, VP_W, VP_H)
        if pos is None or not all(math.isfinite(c) for c in pos[:2]):
            finite = False
            break
        if prev is not None:
            max_jump = max(max_jump, math.hypot(pos[0] - prev[0], pos[1] - prev[1]))
        prev = pos
    check("all projected positions finite (no NaN / zero-state snap)", finite)
    # Frame-to-frame jump is bounded by the camera lag — never the full-screen
    # snap-to-center the JSON-IPC overlay produced on a missed read.
    check("frame-to-frame screen jump stays bounded", finite and max_jump < VP_W * 0.5,
          f"max jump {max_jump:.0f}px (< {VP_W*0.5:.0f}px)")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
