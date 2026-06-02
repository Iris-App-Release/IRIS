#!/usr/bin/env python3
"""
sim_envelop.py — Headless validation of the ENCLOSURE-world viewing model.

No OpenGL, no camera, no display. Enclosure worlds (Grid Room, Gem — any world
with rendering.enveloping = True) respond to head-DEPTH with a FORWARD DOLLY, not
a lens zoom: the eye-to-glass distance is HELD at the neutral BASE_Z (so the FOV
is the calibrated 58° at every distance), and the whole scene is translated toward
the eye by `dolly` world units along −z (baked into the modelview in app_engine).
Leaning in therefore reads as physically MOVING INTO the room — the object of
interest grows with honest perspective, and the front rim slides off the screen
until the viewer is enveloped. This is the OPPOSITE of object worlds (Earth / The
Watcher, telephoto, guarded by sim_viewing / sim_vertical).

This sim pins the enclosure invariants so the two paths can never silently drift:

  1. Constant FOV — the enclosure eye-to-glass distance is BASE_Z at every head-z
     (no "illusory zoom trick"); only the dolly changes.
  2. Forward dolly — leaning IN (hz↑) translates the scene toward the eye
     (dolly↑, monotone), zero at neutral, negative on lean-out (backing out).
  3. The foreground object GROWS on lean-in — a gem-sized body at z = −10 subtends
     a monotonically LARGER on-screen size as the viewer leans in (the headline
     fix; the old enveloping model SHRANK it).
  4. Envelopment — at full lean-in the front rim (world z = 0) is pushed past the
     near plane (out of sight), and at neutral (hz = 0) it maps EXACTLY to the
     screen edges (bezel-locked) so the resting framing is unchanged.
  5. Merged look (sphere feel + grid anchor) — the rotational look engages EARLY and
     WIDE like the Earth object world (blended with the dolly across a broad band, not
     a sequential "first move in, then look around" hand-off), but its AMPLITUDE is
     capped while the front rim is still on screen and only ramps to full as the rim
     clears — so the early look never shears a still-visible grid edge. Zero at
     neutral / lean-out (the resting rim stays bezel-locked), monotone + C¹.
     (what-makes-perspective-optimal.md)
  6. The per-world switch is real — object worlds keep telephoto cz and dolly ≡ 0.

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
DOLLY_GAIN  = 15.5     # enclosure forward-dolly gain (world units / unit head-z)
DOLLY_MAX   = 16.0
DOLLY_MIN   = 0.0      # hard floor: never zoom out past the bezel-locked neutral
ROT_MAX_RAD = math.radians(om.ROT_MAX_DEG)
# Enclosure rotational "look" — MERGED model (engage early + wide like Earth, with an
# amplitude cap while the front rim is on screen). Kept in sync with app_engine.py LOOK_*.
LOOK_ENGAGE_LO   = 0.35
LOOK_ENGAGE_HI   = 1.0
LOOK_PRELOOK_AMP = 0.22
_RIM_CLEAR_HZ    = (BASE_Z - om.NEAR) / DOLLY_GAIN     # head-z at which the dolly clears the rim (≈0.72)
LOOK_AMP_LO      = _RIM_CLEAR_HZ
LOOK_AMP_HI      = min(1.0, _RIM_CLEAR_HZ + 0.20)

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


def cam_z_for(hz: float, enveloping: bool) -> float:
    """app_engine's per-world eye-to-glass distance. Enclosure worlds HOLD it at
    BASE_Z (constant FOV — depth comes from the dolly instead); object worlds use
    the telephoto exponential."""
    if enveloping:
        return BASE_Z
    return max(CAM_Z_MIN, min(CAM_Z_MAX, BASE_Z * math.exp(ZOOM_K * hz)))


def dolly_for(hz: float, enveloping: bool) -> float:
    """app_engine's per-world forward-dolly offset (world units, +z toward eye).
    Object worlds never dolly."""
    if not enveloping:
        return 0.0
    return max(DOLLY_MIN, min(DOLLY_MAX, DOLLY_GAIN * hz))


def enc_view(cx: float, cy: float, hz: float, yaw: float = 0.0, pitch: float = 0.0) -> np.ndarray:
    """Enclosure modelview: view_matrix at the held BASE_Z eye, then the forward
    dolly translate baked in (mirrors app_engine: mv = view_matrix(...) @ T(dolly))."""
    cz = cam_z_for(hz, True)
    mv = om.view_matrix(cx, cy, cz, yaw, pitch)
    T = np.identity(4, dtype=np.float64)
    T[2, 3] = dolly_for(hz, True)
    return mv @ T


def enc_proj(cx: float, cy: float, hz: float) -> np.ndarray:
    return om.off_axis_frustum(cx, cy, cam_z_for(hz, True), ASPECT, om.NEAR, om.FAR)


def enc_engage(hz: float) -> float:
    """Enclosure look ENGAGEMENT weight — opens early + wide, mirroring Earth's band."""
    return om.proximity(hz, lo=LOOK_ENGAGE_LO, hi=LOOK_ENGAGE_HI)


def enc_amp(hz: float) -> float:
    """Rotation-AMPLITUDE cap: LOOK_PRELOOK_AMP while the rim is on screen, ramping to
    1.0 as the rim clears the near plane."""
    return LOOK_PRELOOK_AMP + (1.0 - LOOK_PRELOOK_AMP) * om.proximity(hz, lo=LOOK_AMP_LO, hi=LOOK_AMP_HI)


def enc_prox(hz: float) -> float:
    """Merged enclosure look weight = engage(hz) · amp(hz) (monotone, C¹)."""
    return enc_engage(hz) * enc_amp(hz)


def main() -> int:
    half_w, half_h = om.window_half_extents(ASPECT)
    print("enclosure-world viewing model (forward dolly + merged look)")
    print(f"  BASE_Z={BASE_Z}  DOLLY_GAIN={DOLLY_GAIN}  dolly∈[{DOLLY_MIN},{DOLLY_MAX}]  "
          f"look engage hz∈[{LOOK_ENGAGE_LO},{LOOK_ENGAGE_HI}]  amp {LOOK_PRELOOK_AMP:.2f}→1.0 "
          f"over hz∈[{LOOK_AMP_LO:.2f},{LOOK_AMP_HI:.2f}]  aperture={half_w:.2f}×{half_h:.2f}")
    print()

    HZ = [-0.7, -0.3, 0.0, 0.3, 0.6, 0.8, 0.9, 1.0]   # far → enveloped

    # ── 1. Constant FOV — the enclosure never changes the eye-to-glass distance ─
    print("1. Constant FOV — eye-to-glass distance is BASE_Z at every head-z (no lens zoom)")
    czs = [cam_z_for(hz, True) for hz in HZ]
    fov0 = 2.0 * math.degrees(math.atan(half_h / czs[0]))
    for hz, cz in zip(HZ, czs):
        fov = 2.0 * math.degrees(math.atan(half_h / cz))
        print(f"       hz={hz:+.2f}  eye_z={cz:6.2f}  vertical FOV={fov:6.1f}°  dolly={dolly_for(hz, True):+6.2f}")
    check("enclosure eye-to-glass distance is constant (= BASE_Z) at every head-z",
          all(abs(cz - BASE_Z) < 1e-9 for cz in czs), f"all = {BASE_Z:.2f}")
    check("the vertical FOV is constant across the whole approach (no zoom trick)",
          all(abs(2.0 * math.degrees(math.atan(half_h / cz)) - fov0) < 1e-9 for cz in czs),
          f"{fov0:.1f}° throughout")

    # ── 2. Forward dolly — leaning IN translates the scene toward the eye ────────
    print("\n2. Forward dolly — leaning IN moves the camera INTO the room")
    dollies = [dolly_for(hz, True) for hz in HZ]
    check("dolly is non-decreasing across the whole head-z range",
          all(dollies[i] <= dollies[i + 1] + 1e-12 for i in range(len(dollies) - 1)),
          f"{dollies[0]:+.1f} → {dollies[-1]:+.1f}")
    check("dolly is strictly increasing once leaning IN (hz ≥ 0)",
          all(dolly_for(a, True) < dolly_for(b, True)
              for a, b in zip([0.0, 0.3, 0.6, 0.9], [0.3, 0.6, 0.9, 1.0])),
          f"0.0→{dolly_for(0.0, True):.1f} … 1.0→{dolly_for(1.0, True):.1f}")
    check("dolly is exactly zero at the neutral pose (hz=0)", abs(dolly_for(0.0, True)) < 1e-12)
    # The neutral, bezel-locked framing is the HARD zoom-out floor: leaning back
    # past neutral must NOT pull the camera further out (dolly clamps at 0).
    check("lean-OUT clamps at the neutral bezel-locked floor (dolly never < 0)",
          dolly_for(-0.3, True) == 0.0 and dolly_for(-0.7, True) == 0.0,
          f"out(-0.3)={dolly_for(-0.3, True):.1f}  out(-0.7)={dolly_for(-0.7, True):.1f}")

    # ── 3. The foreground object GROWS on lean-in (the headline fix) ─────────────
    print("\n3. Foreground gem GROWS on lean-in — on-screen size increases monotonically")
    def gem_screen_size(hz: float) -> float:
        view, proj = enc_view(0, 0, hz), enc_proj(0, 0, hz)
        top = om.project_point([0.0,  GEM_HALF, GEM_ANCHOR_Z], view, proj, VP_W, VP_H)
        bot = om.project_point([0.0, -GEM_HALF, GEM_ANCHOR_Z], view, proj, VP_W, VP_H)
        return abs(top[1] - bot[1])
    sizes = [gem_screen_size(hz) for hz in HZ]
    for hz, sz in zip(HZ, sizes):
        print(f"       hz={hz:+.2f}  gem on-screen height={sz:7.1f}px")
    check("gem on-screen size is non-decreasing across the head-z range",
          all(sizes[i] <= sizes[i + 1] + 1e-6 for i in range(len(sizes) - 1)),
          f"{sizes[0]:.0f}px → {sizes[-1]:.0f}px")
    check("gem on-screen size strictly GROWS once leaning IN (hz ≥ 0)",
          all(gem_screen_size(a) < gem_screen_size(b)
              for a, b in zip([0.0, 0.3, 0.6, 0.9], [0.3, 0.6, 0.9, 1.0])),
          f"neutral={gem_screen_size(0.0):.0f}px → enveloped={gem_screen_size(1.0):.0f}px")
    check("the gem is meaningfully LARGER enveloped than at neutral",
          sizes[-1] > 1.5 * gem_screen_size(0.0),
          f"{gem_screen_size(0.0):.0f}px → {sizes[-1]:.0f}px ({sizes[-1]/gem_screen_size(0.0):.2f}×)")
    check("lean-OUT cannot shrink the gem below the neutral framing (zoom-out floor)",
          abs(gem_screen_size(-0.7) - gem_screen_size(0.0)) < 1e-6,
          f"out={gem_screen_size(-0.7):.0f}px  neutral={gem_screen_size(0.0):.0f}px")

    # ── 4. Envelopment + neutral bezel-lock ──────────────────────────────────────
    print("\n4. Envelopment — rim clears the near plane at full lean; bezel-locked at neutral")
    rim_corners = [(sx, sy, 0.0) for sx in (-half_w, half_w) for sy in (-half_h, half_h)]
    # Neutral (hz=0): rim must map EXACTLY to the screen border (bezel-lock).
    worst = 0.0
    for (cx, cy) in [(0.0, 0.0), (2.5, -1.5), (-3.0, 1.0)]:
        view, proj = enc_view(cx, cy, 0.0), enc_proj(cx, cy, 0.0)
        for (sx, sy, sz) in rim_corners:
            r = om.project_point([sx, sy, sz], view, proj, VP_W, VP_H)
            worst = max(worst, min(abs(r[0]), abs(r[0] - VP_W)),
                               min(abs(r[1]), abs(r[1] - VP_H)))
    check("at neutral the front rim is pinned to the bezel (resting framing unchanged)",
          worst < 1e-6, f"max border error {worst:.2e}px")
    # Full lean-in: the rim is behind/at the near plane → not rendered (enveloped).
    view = enc_view(0, 0, 1.0)
    rim_eye_z = [(view @ np.array([sx, sy, sz, 1.0]))[2] for (sx, sy, sz) in rim_corners]
    check("at full lean-in the front rim is past the near plane (out of sight → enveloped)",
          all(ez > -om.NEAR for ez in rim_eye_z),
          f"rim eye_z={min(rim_eye_z):+.2f}..{max(rim_eye_z):+.2f}  (clipped when > {-om.NEAR})")

    # ── 5. Merged look — early + wide (Earth-like blend), amplitude-capped until the
    #       rim clears so the early look never shears the still-visible grid ──────────
    print("\n5. Merged look — engages early/wide (Earth-like), amplitude-capped until envelopment")
    back = np.array([0.0, 0.0, -60.0])   # deep probe: sweeps as the view pans
    def look_reveal(hz):
        p = enc_prox(hz)
        v0 = enc_view(0, 0, hz, 0.0, 0.0)
        v1 = enc_view(0, 0, hz, 0.6 * ROT_MAX_RAD * p, 0.0)
        proj = enc_proj(0, 0, hz)
        return abs(om.project_point(back, v1, proj, VP_W, VP_H)[0]
                   - om.project_point(back, v0, proj, VP_W, VP_H)[0])
    reveals = []
    for hz in HZ:
        reveals.append(look_reveal(hz))
        print(f"       hz={hz:+.2f}  engage={enc_engage(hz):.3f}  amp={enc_amp(hz):.3f}  "
              f"prox={enc_prox(hz):.3f}  look reveal={reveals[-1]:7.1f}px")

    # (a) Grid-world anchor preserved: zero look at neutral / lean-out and below the
    #     engage threshold, so the resting front rim stays exactly bezel-locked. (The
    #     rim leaves the screen the instant the dolly starts, hz≈0.02, with the look
    #     still zero — so it never shears on its way out either.)
    check("no look at neutral / lean-out (resting rim stays bezel-locked)",
          all(enc_prox(hz) == 0.0 for hz in (-0.7, -0.3, 0.0, 0.3)),
          f"prox(0.0)={enc_prox(0.0):.3f}  prox(0.3)={enc_prox(0.3):.3f}")
    # (b) The MERGE — sphere-world feel: the look engages EARLY and is BLENDED with the
    #     dolly across the approach (active well before full envelopment), unlike the
    #     old sequential enclosure gate which was exactly zero until hz = 0.75.
    old_gate_05 = om.proximity(0.5, lo=0.75, hi=1.0)
    check("look engages EARLY, blended with the dolly (old sequential gate = 0 here)",
          enc_prox(0.5) > 0.0 and enc_prox(0.6) > 0.0 and old_gate_05 == 0.0,
          f"prox(0.5)={enc_prox(0.5):.3f}  (old gate(0.5)={old_gate_05:.3f})")
    # (c) Grid anchor kept WHILE exploring: the look AMPLITUDE is capped to
    #     LOOK_PRELOOK_AMP until the rim clears the near plane, so the not-yet-enveloped
    #     pan stays gentle (the early look can't swing the still-visible grid).
    check("look amplitude is capped (≤ LOOK_PRELOOK_AMP) until the rim clears",
          all(enc_amp(hz) <= LOOK_PRELOOK_AMP + 1e-9 for hz in HZ if hz <= LOOK_AMP_LO + 1e-9),
          f"amp ≤ {LOOK_PRELOOK_AMP} for hz ≤ {LOOK_AMP_LO:.2f}; amp(0.6)={enc_amp(0.6):.3f}")
    check("the capped early pan is a small fraction of the enveloped pan",
          look_reveal(0.6) < 0.4 * reveals[-1] and reveals[-1] > 50.0,
          f"reveal(0.6)={look_reveal(0.6):.0f}px vs enveloped {reveals[-1]:.0f}px")
    # (d) Full freedom once enveloped — amplitude uncaps to 1.0 and the look reveals a
    #     significant slice of the room (a real look around it from inside).
    check("look reaches FULL amplitude once enveloped and is significant there",
          enc_amp(LOOK_AMP_HI) > 0.999 and enc_amp(1.0) > 0.999 and enc_prox(1.0) > 0.999,
          f"amp({LOOK_AMP_HI:.2f})={enc_amp(LOOK_AMP_HI):.3f}  amp(1.0)={enc_amp(1.0):.3f}  "
          f"enveloped reveal={reveals[-1]:.0f}px")
    # (e) Monotone reveal across the whole range.
    check("look reveal grows monotonically toward envelopment",
          all(reveals[i] <= reveals[i + 1] + 1e-6 for i in range(len(reveals) - 1)),
          f"{reveals[0]:.0f}px → {reveals[-1]:.0f}px")
    # (f) C¹ — the merged weight is a product of two smoothsteps, still continuous with
    #     no jump (no felt mode switch). Sample densely so a genuine discontinuity would
    #     still show up as an O(1) step at a single sample.
    series = [enc_prox(h) for h in np.linspace(-0.7, 1.0, 4000)]
    steps = [abs(series[i + 1] - series[i]) for i in range(len(series) - 1)]
    check("the merged look weight is smooth (C¹, no discontinuity)",
          max(steps) < 0.02, f"max step {max(steps):.4f}")

    # ── 6. The per-world switch genuinely differs from the object path ───────────
    print("\n6. Per-world switch — enclosure (dolly, constant FOV) vs object (telephoto)")
    check("object worlds never dolly (modelview unchanged from the frozen rig)",
          all(dolly_for(hz, False) == 0.0 for hz in HZ), "dolly ≡ 0 for object worlds")
    check("object eye distance still telephotos with head-z (the calibrated feel)",
          cam_z_for(0.5, False) > BASE_Z > cam_z_for(-0.5, False),
          f"in={cam_z_for(0.5, False):.1f}  out={cam_z_for(-0.5, False):.1f}")
    check("the two paths agree exactly at neutral (hz=0): cz=BASE_Z, dolly=0",
          abs(cam_z_for(0.0, True) - cam_z_for(0.0, False)) < 1e-9
          and dolly_for(0.0, True) == 0.0,
          f"both cz = {cam_z_for(0.0, True):.2f}")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
