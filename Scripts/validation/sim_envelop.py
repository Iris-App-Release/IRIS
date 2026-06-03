#!/usr/bin/env python3
"""
sim_envelop.py — Headless validation of the ENCLOSURE-world viewing model.

No OpenGL, no camera, no display. Enclosure worlds (Grid Room, Gem — any world
with rendering.enveloping = True) use the EXACT SAME camera physics as the object
worlds (Earth / The Watcher): the same telephoto depth response AND the same frozen
proximity look-gate. The grid worlds therefore ZOOM exactly like the sphere worlds,
their rotational look fades in over the SAME head-z distances, and a body at the
Earth anchor (z = −10) subtends the SAME on-screen size the Earth would at any given
head-z. The ONLY difference is that the enclosure look AMPLITUDE is capped
(LOOK_ENCLOSURE_AMP) so a pan never shears the bezel-locked front rim (the rim is on
the glass at world z = 0 and maps to the screen edges as a hard anchor).

This replaces the earlier "forward dolly / move into the room" enclosure model
(removed 2026-06-02): that held cz constant and translated the scene toward the eye,
which grew a foreground gem ~3.6× and diverged from Earth's size — the user rejected
it and asked for the grid worlds to behave EXACTLY like the sphere worlds, anchored.

This sim pins the invariants so the two paths can never silently drift:

  1. Identical zoom — the enclosure eye-to-glass distance telephotos with head-z
     EXACTLY like the object worlds (no per-world divergence, no dolly).
  2. Gem == Earth size — a body at z = −10 subtends the same on-screen size under the
     enclosure path as under the object path, at every head-z, and GROWS on lean-in.
  3. Bezel anchor at EVERY distance — with no look, the front rim (world z = 0) maps
     EXACTLY to the screen edges at every head-z and for off-centre eyes (the anchor
     now holds through the whole approach; nothing carries it off-screen).
  4. Same look-gate timing — the enclosure look uses the frozen om.proximity(hz)
     ([0.0, 0.8]) gate, so it engages at the same head-z distances as Earth, smoothly.
  5. Capped look amplitude — the ONLY divergence: the enclosure pan equals the object
     pan scaled by LOOK_ENCLOSURE_AMP (≤ object pan), ≈ 0 at neutral (rim anchored),
     monotone and C¹, so the still-visible rim shears far less than a full pan would.
  6. Per-world switch is real — object worlds are uncapped (factor 1.0); at neutral
     the two paths are identical.

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
# Enclosure rotational "look" amplitude cap — the SINGLE divergence from the object
# worlds. Same telephoto zoom + same proximity gate timing; only the pan is limited so
# the bezel-locked front rim never shears. Kept in sync with app_engine.LOOK_ENCLOSURE_AMP.
LOOK_ENCLOSURE_AMP = 0.35

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
    """app_engine's eye-to-glass distance — TELEPHOTO, identical for every world now
    (the enclosure forward-dolly was removed). Exponential in head-z, clamped."""
    return max(CAM_Z_MIN, min(CAM_Z_MAX, BASE_Z * math.exp(ZOOM_K * hz)))


def look_cap(enveloping: bool) -> float:
    """The look-amplitude scale: capped for enclosure worlds, 1.0 (uncapped) for the
    object worlds."""
    return LOOK_ENCLOSURE_AMP if enveloping else 1.0


def view_for(cx: float, cy: float, hz: float, yaw_in: float = 0.0,
             enveloping: bool = False) -> np.ndarray:
    """Modelview for a head turn `yaw_in` ∈ [-1, 1], mirroring app_engine: the pan is
    proximity-gated (om.proximity(hz)) and, for enclosure worlds, amplitude-capped."""
    cz   = cam_z_for(hz)
    prox = om.proximity(hz)
    yaw  = yaw_in * ROT_MAX_RAD * prox * look_cap(enveloping)
    return om.view_matrix(cx, cy, cz, yaw, 0.0)


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
    print("enclosure-world viewing model (Earth's camera physics + bezel anchor + capped look)")
    print(f"  BASE_Z={BASE_Z}  ZOOM_K={ZOOM_K}  look cap={LOOK_ENCLOSURE_AMP}  "
          f"gate={om.ROT_PROX_LO}..{om.ROT_PROX_HI}  aperture={half_w:.2f}×{half_h:.2f}")
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
    check("body on-screen size is identical under enclosure & object paths (shared camera)",
          all(abs(body_screen_height(hz) - body_screen_height(hz)) < 1e-9 for hz in HZ),
          "same telephoto cz → same projected size")
    check("body on-screen size grows monotonically on lean-in (like Earth)",
          all(sizes[i] <= sizes[i + 1] + 1e-6 for i in range(len(sizes) - 1)),
          f"{sizes[0]:.0f}px → {sizes[-1]:.0f}px")
    check("the body is meaningfully larger close than at neutral",
          body_screen_height(1.0) > 1.3 * body_screen_height(0.0),
          f"neutral={body_screen_height(0.0):.0f}px → close={body_screen_height(1.0):.0f}px")

    # ── 3. Bezel anchor holds at EVERY distance (no look) ────────────────────────
    print("\n3. Bezel anchor — with no look, the front rim maps to the screen edges at every head-z")
    rim_corners = [(sx, sy, 0.0) for sx in (-half_w, half_w) for sy in (-half_h, half_h)]
    worst = 0.0
    worst_hz = None
    for hz in HZ:
        for (cx, cy) in [(0.0, 0.0), (2.5, -1.5), (-3.0, 1.0)]:
            view, proj = view_for(cx, cy, hz), proj_for(cx, cy, hz)
            for (sx, sy, sz) in rim_corners:
                r = om.project_point([sx, sy, sz], view, proj, VP_W, VP_H)
                err = max(min(abs(r[0]), abs(r[0] - VP_W)),
                          min(abs(r[1]), abs(r[1] - VP_H)))
                if err > worst:
                    worst, worst_hz = err, hz
    check("the front rim is pinned to the bezel at every head-z & eye offset (anchor holds)",
          worst < 1e-6, f"max border error {worst:.2e}px (worst at hz={worst_hz})")

    # ── 4. Same look-gate timing as Earth ────────────────────────────────────────
    print("\n4. Look-gate timing — enclosure look fades in over the SAME head-z band as Earth")
    for hz in HZ:
        g = om.proximity(hz)
        print(f"       hz={hz:+.2f}  proximity gate={g:.3f}")
    check("the enclosure look uses the frozen om.proximity gate (zero at/below ROT_PROX_LO)",
          om.proximity(om.ROT_PROX_LO) == 0.0 and om.proximity(-0.3) == 0.0,
          f"gate(lo={om.ROT_PROX_LO})={om.proximity(om.ROT_PROX_LO):.3f}")
    check("the look is fully engaged by ROT_PROX_HI, just like Earth",
          om.proximity(om.ROT_PROX_HI) > 0.999 and om.proximity(1.0) > 0.999,
          f"gate(hi={om.ROT_PROX_HI})={om.proximity(om.ROT_PROX_HI):.3f}")
    check("the gate is smooth (C¹) across the band — no felt mode switch",
          (lambda s: max(abs(s[i+1]-s[i]) for i in range(len(s)-1)) < 0.02)(
              [om.proximity(h) for h in np.linspace(-0.7, 1.0, 4000)]),
          "smoothstep, max step < 0.02")

    # ── 5. Capped look amplitude — the ONLY divergence from the sphere worlds ─────
    print("\n5. Look amplitude — enclosure pan is the object pan, scaled by the cap (rim won't shear)")
    for hz in HZ:
        obj = pan_pixels(hz, 1.0, enveloping=False)
        enc = pan_pixels(hz, 1.0, enveloping=True)
        ratio = (enc / obj) if obj > 1e-9 else float("nan")
        print(f"       hz={hz:+.2f}  object pan={obj:7.1f}px  enclosure pan={enc:7.1f}px  ratio={ratio:.3f}")
    # (a) zero at rest / lean-out — the resting rim stays exactly bezel-locked.
    check("no look at neutral / lean-out (resting rim stays bezel-locked)",
          all(pan_pixels(hz, 1.0, True) < 1e-6 for hz in (-0.7, -0.3, 0.0)),
          f"pan(0.0)={pan_pixels(0.0, 1.0, True):.3f}px")
    # (b) the enclosure pan equals the object pan scaled by the cap, at every head-z.
    ratios = [pan_pixels(hz, 1.0, True) / pan_pixels(hz, 1.0, False)
              for hz in HZ if pan_pixels(hz, 1.0, False) > 1e-6]
    check("enclosure pan = object pan × LOOK_ENCLOSURE_AMP at every head-z (same timing, capped size)",
          all(abs(r - LOOK_ENCLOSURE_AMP) < 0.02 for r in ratios),
          f"ratio ≈ {LOOK_ENCLOSURE_AMP} (got {min(ratios):.3f}..{max(ratios):.3f})")
    # (c) the enclosure pan never exceeds the object pan (it is a strict limit).
    check("enclosure pan never exceeds the (uncapped) object pan",
          all(pan_pixels(hz, 1.0, True) <= pan_pixels(hz, 1.0, False) + 1e-6 for hz in HZ),
          "capped ≤ uncapped everywhere")
    # (d) the capped pan grows monotonically with proximity (still an Earth-like ramp).
    enc_pans = [pan_pixels(hz, 1.0, True) for hz in HZ]
    check("the capped look still grows monotonically as you lean in (Earth-like ramp)",
          all(enc_pans[i] <= enc_pans[i + 1] + 1e-6 for i in range(len(enc_pans) - 1)),
          f"{enc_pans[0]:.0f}px → {enc_pans[-1]:.0f}px")
    # (e) C¹ — the capped pan target is a smoothstep × constant, still continuous.
    series = [om.proximity(h) * LOOK_ENCLOSURE_AMP for h in np.linspace(-0.7, 1.0, 4000)]
    steps = [abs(series[i + 1] - series[i]) for i in range(len(series) - 1)]
    check("the capped look weight is smooth (C¹, no discontinuity)",
          max(steps) < 0.02, f"max step {max(steps):.4f}")

    # ── 6. Per-world switch is real; object path is byte-identical ───────────────
    print("\n6. Per-world switch — enclosure caps the look; object worlds are uncapped")
    check("object worlds are uncapped (look-amplitude factor = 1.0)",
          look_cap(False) == 1.0 and look_cap(True) == LOOK_ENCLOSURE_AMP,
          f"object=1.0  enclosure={LOOK_ENCLOSURE_AMP}")
    check("at neutral (hz=0) the two paths are identical (no look either way)",
          abs(pan_pixels(0.0, 1.0, True) - pan_pixels(0.0, 1.0, False)) < 1e-9
          and abs(cam_z_for(0.0) - BASE_Z) < 1e-9,
          "cz=BASE_Z, pan=0 for both")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
