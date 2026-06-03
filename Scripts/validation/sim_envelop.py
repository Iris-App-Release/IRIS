#!/usr/bin/env python3
"""
sim_envelop.py — Headless validation of the ENCLOSURE / GRID-world viewing model.

No OpenGL, no camera, no display. Enclosure worlds (Grid Room, Gem — any world
with rendering.enveloping = True) share the object worlds' (Earth / The Watcher)
telephoto depth response and parallax window shift — the grid worlds ZOOM exactly
like the sphere worlds, and a body at the Earth anchor (z = −10) subtends the SAME
on-screen size the Earth would at any given head-z. The ONE difference: enclosure
worlds DO NOT PAN. Their rotational "look" is held at ZERO.

Why no pan: the front rim sits on the glass at world z = 0 and maps to the screen
edges as a HARD bezel anchor — that anchor is the grid's whole purpose (it
communicates real cm² of digital space, a box behind the glass). A rotational look
pans the view about the eye, which rotates that still-visible rim and SHEARS it.
An anchored wall and a pan are a direct contradiction, so clean panning is
exclusive to the open SPHERE worlds (no anchored walls). A forward-dolly model and
then a capped look (LOOK_ENCLOSURE_AMP) were both tried and removed 2026-06-02 —
any non-zero pan still shears the anchored rim.

This sim pins the invariants so the two paths can never silently drift:

  1. Identical zoom — the enclosure eye-to-glass distance telephotos with head-z
     EXACTLY like the object worlds (no per-world divergence, no dolly).
  2. Gem == Earth size — a body at z = −10 subtends the same on-screen size under the
     enclosure path as under the object path, at every head-z, and GROWS on lean-in.
  3. Bezel anchor at EVERY distance — the front rim (world z = 0) maps EXACTLY to the
     screen edges at every head-z and for off-centre eyes (parallax shifts the eye,
     the rim stays pinned — the anchor holds through the whole approach).
  4. NO enclosure pan — the enclosure rotational look is identically zero at every
     head-z and every head turn (the rim never shears).
  5. Sphere worlds untouched — the object worlds keep the full proximity-gated look,
     so they pan freely; only enclosure worlds are zeroed.

These head→camera constants are kept in sync with Launcher/app_engine.py.

Run:  .venv/bin/python sim_envelop.py
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

# app_engine.py head→camera mapping (kept in sync with app_engine.py).
ZOOM_K      = 0.95
BASE_Z      = om.CAM_BASE_Z
CAM_Z_MIN   = 5.0
CAM_Z_MAX   = 34.0
ROT_MAX_RAD       = math.radians(om.ROT_MAX_DEG)
ROT_MAX_PITCH_RAD = math.radians(40.0)

GEM_ANCHOR_Z = -10.0   # the gem / room body anchor (OBJECTS["earth"][2])
GEM_HALF     = 2.2     # gem girdle radius (renderer.Gem) — a foreground-size probe

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
    """app_engine's eye-to-glass distance — TELEPHOTO, identical for every world
    (the enclosure forward-dolly was removed). Exponential in head-z, clamped."""
    return max(CAM_Z_MIN, min(CAM_Z_MAX, BASE_Z * math.exp(ZOOM_K * hz)))


def look_yaw(hz: float, yaw_in: float, enveloping: bool) -> float:
    """The rotational-look yaw applied to the modelview, mirroring app_engine:
    object worlds get the proximity-gated look; ENCLOSURE worlds get ZERO (no pan)."""
    if enveloping:
        return 0.0
    return yaw_in * ROT_MAX_RAD * om.proximity(hz)


def view_for(cx: float, cy: float, hz: float, yaw_in: float = 0.0,
             enveloping: bool = False) -> np.ndarray:
    cz = cam_z_for(hz)
    return om.view_matrix(cx, cy, cz, look_yaw(hz, yaw_in, enveloping), 0.0)


def proj_for(cx: float, cy: float, hz: float) -> np.ndarray:
    return om.off_axis_frustum(cx, cy, cam_z_for(hz), ASPECT, om.NEAR, om.FAR)


def pan_pixels(hz: float, yaw_in: float, enveloping: bool) -> float:
    """How far a deep background point shifts on screen when the head turns `yaw_in`."""
    back = np.array([0.0, 0.0, -60.0])
    proj = proj_for(0, 0, hz)
    v0 = view_for(0, 0, hz, 0.0, enveloping)
    v1 = view_for(0, 0, hz, yaw_in, enveloping)
    return abs(om.project_point(back, v1, proj, VP_W, VP_H)[0]
               - om.project_point(back, v0, proj, VP_W, VP_H)[0])


def body_screen_height(hz: float) -> float:
    """On-screen height (px) of a GEM_HALF-radius body at the z = −10 anchor — the
    camera is world-agnostic, so this is the size for BOTH the gem and Earth."""
    view, proj = view_for(0, 0, hz), proj_for(0, 0, hz)
    top = om.project_point([0.0,  GEM_HALF, GEM_ANCHOR_Z], view, proj, VP_W, VP_H)
    bot = om.project_point([0.0, -GEM_HALF, GEM_ANCHOR_Z], view, proj, VP_W, VP_H)
    return abs(top[1] - bot[1])


def main() -> int:
    half_w, half_h = om.window_half_extents(ASPECT)
    print("enclosure / grid viewing model (Earth's zoom + parallax + bezel anchor, NO pan)")
    print(f"  BASE_Z={BASE_Z}  ZOOM_K={ZOOM_K}  enclosure look=0 (no pan)  "
          f"sphere gate={om.ROT_PROX_LO}..{om.ROT_PROX_HI}  aperture={half_w:.2f}×{half_h:.2f}")
    print()

    HZ = [-0.7, -0.3, 0.0, 0.3, 0.6, 0.8, 0.9, 1.0]   # far → close

    # ── 1. Identical zoom — enclosure telephotos EXACTLY like the sphere worlds ──
    print("1. Zoom — enclosure eye-to-glass distance telephotos exactly like the object worlds")
    czs = [cam_z_for(hz) for hz in HZ]
    for hz, cz in zip(HZ, czs):
        fov = 2.0 * math.degrees(math.atan(half_h / cz))
        print(f"       hz={hz:+.2f}  eye_z={cz:6.2f}  vertical FOV={fov:6.1f}°")
    check("eye-to-glass distance is BASE_Z at the neutral pose (resting framing unchanged)",
          abs(cam_z_for(0.0) - BASE_Z) < 1e-9, f"cz(0)={cam_z_for(0.0):.2f}")
    check("eye distance telephotos monotonically with head-z (lean in → world grows)",
          all(czs[i] < czs[i + 1] for i in range(len(czs) - 1)),
          f"{czs[0]:.1f} → {czs[-1]:.1f}")
    check("the enclosure zoom IS the object-world zoom (no per-world divergence, no dolly)",
          all(abs(cam_z_for(hz) - max(CAM_Z_MIN, min(CAM_Z_MAX, BASE_Z * math.exp(ZOOM_K * hz)))) < 1e-12
              for hz in HZ), "single telephoto law for every world")

    # ── 2. Gem == Earth size, and grows on lean-in ──────────────────────────────
    print("\n2. Gem subtends the same on-screen size Earth would, and grows on lean-in")
    sizes = [body_screen_height(hz) for hz in HZ]
    for hz, sz in zip(HZ, sizes):
        print(f"       hz={hz:+.2f}  body on-screen height={sz:7.1f}px")
    check("body on-screen size grows monotonically on lean-in (like Earth)",
          all(sizes[i] <= sizes[i + 1] + 1e-6 for i in range(len(sizes) - 1)),
          f"{sizes[0]:.0f}px → {sizes[-1]:.0f}px")
    check("the body is meaningfully larger close than at neutral",
          body_screen_height(1.0) > 1.3 * body_screen_height(0.0),
          f"neutral={body_screen_height(0.0):.0f}px → close={body_screen_height(1.0):.0f}px")

    # ── 3. Bezel anchor holds at EVERY distance (no look at all) ─────────────────
    print("\n3. Bezel anchor — the front rim maps to the screen edges at every head-z & eye offset")
    rim_corners = [(sx, sy, 0.0) for sx in (-half_w, half_w) for sy in (-half_h, half_h)]
    worst = 0.0
    worst_hz = None
    for hz in HZ:
        for (cx, cy) in [(0.0, 0.0), (2.5, -1.5), (-3.0, 1.0)]:
            view, proj = view_for(cx, cy, hz, 0.0, enveloping=True), proj_for(cx, cy, hz)
            for (sx, sy, sz) in rim_corners:
                r = om.project_point([sx, sy, sz], view, proj, VP_W, VP_H)
                err = max(min(abs(r[0]), abs(r[0] - VP_W)),
                          min(abs(r[1]), abs(r[1] - VP_H)))
                if err > worst:
                    worst, worst_hz = err, hz
    check("the front rim is pinned to the bezel at every head-z & eye offset (anchor holds)",
          worst < 1e-6, f"max border error {worst:.2e}px (worst at hz={worst_hz})")

    # ── 4. NO enclosure pan — the rotational look is identically zero ────────────
    print("\n4. No pan — the enclosure rotational look is zero at every head-z (rim never shears)")
    for hz in HZ:
        enc = pan_pixels(hz, 1.0, enveloping=True)
        print(f"       hz={hz:+.2f}  enclosure pan={enc:7.3f}px  (must be 0)")
    check("the enclosure look yaw is identically zero for every head-z & head turn",
          all(look_yaw(hz, yi, enveloping=True) == 0.0
              for hz in np.linspace(-0.7, 1.0, 200) for yi in (-1.0, -0.3, 0.5, 1.0)),
          "look_yaw(enveloping=True) ≡ 0")
    check("a full head turn produces zero on-screen pan in enclosure worlds (anchored)",
          all(pan_pixels(hz, 1.0, enveloping=True) < 1e-6 for hz in HZ),
          f"max enclosure pan {max(pan_pixels(hz, 1.0, True) for hz in HZ):.2e}px")

    # ── 5. Sphere worlds untouched — they still pan with the proximity gate ──────
    print("\n5. Sphere worlds untouched — the object look still pans (only enclosures are zeroed)")
    for hz in HZ:
        obj = pan_pixels(hz, 1.0, enveloping=False)
        print(f"       hz={hz:+.2f}  object pan={obj:7.1f}px")
    check("object worlds pan zero at/below the gate's low end (far field unchanged)",
          all(pan_pixels(hz, 1.0, enveloping=False) < 1e-6 for hz in (-0.7, -0.3, 0.0)),
          f"pan(0.0)={pan_pixels(0.0, 1.0, False):.3f}px")
    check("object worlds pan a meaningful amount up close (sphere look preserved)",
          pan_pixels(1.0, 1.0, enveloping=False) > 100.0,
          f"object pan at hz=1.0 = {pan_pixels(1.0, 1.0, False):.0f}px")
    check("object pan grows monotonically with proximity (Earth-like ramp, untouched)",
          (lambda p: all(p[i] <= p[i + 1] + 1e-6 for i in range(len(p) - 1)))(
              [pan_pixels(hz, 1.0, enveloping=False) for hz in HZ]),
          "0px → full pan")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
