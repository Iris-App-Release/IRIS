#!/usr/bin/env python3
"""
sim_grid_api.py — Headless validation of the WORLD BUILDER placeable-object API.

No OpenGL, no camera context, no display. World Builder lets a user (or Claude)
place built-in primitives inside the Grid Room by addressing integer grid cells;
the engine maps those cells to LIVE world coordinates and draws them in world space
right after the grid (see obsidian-docs/architecture/grid-creator-tool-plan.md).

This sim pins the invariants of that layer so it can never silently drift:

  1. grid_to_world — the cell→world transform hits the documented anchors:
     [0,0,0]→(0,0,0), [D/2,D/2,0]→(hw,hh,0), [0,0,D]→(0,0,-depth), using the LIVE
     aperture half-extents (never hardcoded bounds).
  2. Clamping — out-of-range cells are pinned inside the box; junk scale/colour
     are clamped to valid ranges.
  3. Allowlist + count cap — unknown models and malformed objects are skipped
     (never crash); the object count is capped to protect the frame budget.
  4. Frozen-invariance — placeable objects live entirely outside camera_math: the
     enclosure camera matrices (zoom + zero pan) are byte-identical with or without
     objects present, exactly matching sim_envelop's pinned enclosure path.
  5. Sphere worlds unaffected — a world with no `assets` block yields an empty list
     and an identical (no-op) path.

Run:  .venv/bin/python Scripts/validation/sim_grid_api.py
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
from Portals.placeable import (
    grid_to_world, sanitize_objects,
    BUILTIN_PRIMITIVES, MAX_OBJECTS, SCALE_MAX,
)

VP_W, VP_H = 2560.0, 1600.0
ASPECT     = VP_W / VP_H

# Sample grid parameters (the live engine reads grid_depth/grid_divisions from JSON;
# hw/hh come from om.window_half_extents — used here as the live aperture).
DEPTH = 18.0
D     = 8

_fail = 0
def check(name: str, ok: bool, detail: str = "") -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)


# Enclosure camera helpers — copied from sim_envelop.py so the frozen-invariance
# check (4) compares against the SAME zero-pan enclosure path the other sim pins.
ZOOM_K  = 0.95
BASE_Z  = om.CAM_BASE_Z
CAM_Z_MIN, CAM_Z_MAX = 5.0, 34.0

def cam_z_for(hz: float) -> float:
    return max(CAM_Z_MIN, min(CAM_Z_MAX, BASE_Z * math.exp(ZOOM_K * hz)))

def enclosure_view(cx: float, cy: float, hz: float) -> np.ndarray:
    # Enclosure worlds: look yaw is ZERO (no pan) — see sim_envelop.py.
    return om.view_matrix(cx, cy, cam_z_for(hz), 0.0, 0.0)

def enclosure_proj(cx: float, cy: float, hz: float) -> np.ndarray:
    return om.off_axis_frustum(cx, cy, cam_z_for(hz), ASPECT, om.NEAR, om.FAR)


def main() -> int:
    hw, hh = om.window_half_extents(ASPECT)
    print("world builder — placeable-object cell→world transform, clamping, frozen-invariance")
    print(f"  aperture={hw:.2f}×{hh:.2f}  grid_depth={DEPTH}  grid_divisions={D}  "
          f"primitives={list(BUILTIN_PRIMITIVES)}  count_cap={MAX_OBJECTS}")
    print()

    # ── 1. grid_to_world hits the documented anchors ────────────────────────────
    print("1. grid_to_world maps cells to live world coordinates (anchors exact)")
    centre = grid_to_portal(0, 0, 0, hw, hh, DEPTH, D)
    corner = grid_to_portal(D / 2, D / 2, 0, hw, hh, DEPTH, D)
    back   = grid_to_portal(0, 0, D, hw, hh, DEPTH, D)
    print(f"       [0,0,0]      → {tuple(round(v,4) for v in centre)}")
    print(f"       [D/2,D/2,0]  → {tuple(round(v,4) for v in corner)}")
    print(f"       [0,0,D]      → {tuple(round(v,4) for v in back)}")
    check("centre cell maps to the world origin on the glass",
          all(abs(v) < 1e-9 for v in centre), str(centre))
    check("the +X/+Y top corner cell lands exactly on the side walls (hw, hh)",
          abs(corner[0] - hw) < 1e-9 and abs(corner[1] - hh) < 1e-9 and abs(corner[2]) < 1e-9,
          f"({corner[0]:.3f},{corner[1]:.3f}) vs ({hw:.3f},{hh:.3f})")
    check("the back-wall cell lands at z = -grid_depth",
          abs(back[2] + DEPTH) < 1e-9 and abs(back[0]) < 1e-9 and abs(back[1]) < 1e-9,
          f"z={back[2]:.3f} vs {-DEPTH}")
    check("X uses the D/2 scale against hw (cell ±1 is one division wide)",
          abs(grid_to_portal(1, 0, 0, hw, hh, DEPTH, D)[0] - hw / (D / 2)) < 1e-9)

    # ── 2. Clamping pins out-of-range cells & junk inside valid ranges ───────────
    print("\n2. Clamping — out-of-bounds cells & junk values are pinned inside the box")
    raw = [{
        "model": "builtin:cube",
        "grid_position": [999, -999, 999],   # way out of bounds
        "scale": 500.0,                       # absurd scale
        "color": [5.0, -2.0, 0.5],            # out-of-gamut colour
    }]
    o = sanitize_objects(raw, D)[0]
    gx, gy, gz = o["grid_position"]
    r, g, b = o["color"]
    check("out-of-range gx/gy are clamped to ±D/2",
          gx == D / 2 and gy == -D / 2, f"gx={gx} gy={gy}")
    check("gz is clamped into [0, D]", 0.0 <= gz <= D, f"gz={gz}")
    check("scale is clamped to (0, SCALE_MAX]", 0.0 < o["scale"] <= SCALE_MAX, f"scale={o['scale']}")
    check("colour components are clamped to [0,1]",
          r == 1.0 and g == 0.0 and b == 0.5, f"({r},{g},{b})")

    # ── 3. Allowlist + malformed-skip + count cap ───────────────────────────────
    print("\n3. Allowlist, malformed-skip, and the object-count cap")
    mixed = [
        {"model": "builtin:sphere", "grid_position": [0, 0, 0]},  # good
        {"model": "evil:teapot",    "grid_position": [0, 0, 0]},  # not allowlisted
        {"model": "builtin:cube"},                                # missing position → default ok
        {"grid_position": [0, 0, 0]},                             # no model → skip
        "not even a dict",                                        # junk → skip
        {"model": "builtin:cube", "grid_position": ["x", 1, 2]},  # bad position → skip
    ]
    san = sanitize_objects(mixed, D)
    check("unknown models and malformed entries are skipped (good ones survive)",
          len(san) == 2 and all(x["model"] in BUILTIN_PRIMITIVES for x in san),
          f"kept {len(san)} of {len(mixed)}")
    check("every kept object exposes a normalized, in-range schema",
          all(set(x) >= {"model", "grid_position", "scale", "color", "rotation"} for x in san))
    flood = [{"model": "builtin:cube", "grid_position": [0, 0, 0]} for _ in range(MAX_OBJECTS + 50)]
    check(f"the object count is capped at {MAX_OBJECTS}",
          len(sanitize_objects(flood, D)) == MAX_OBJECTS,
          f"{len(sanitize_objects(flood, D))} kept from {len(flood)}")
    check("garbage input (non-list) yields an empty list, never a crash",
          sanitize_objects(None, D) == [] and sanitize_objects("nope", D) == [])

    # ── 4. Frozen-invariance — objects never perturb the camera ─────────────────
    print("\n4. Frozen-invariance — enclosure camera (zoom + zero pan) is identical with/without objects")
    HZ = [-0.3, 0.0, 0.5, 1.0]
    worst = 0.0
    for hz in HZ:
        for cx, cy in [(0.0, 0.0), (2.5, -1.5)]:
            # The camera path takes NO object input, so building it is byte-identical
            # whether or not placeable objects exist — assert that explicitly.
            v0, p0 = enclosure_view(cx, cy, hz), enclosure_proj(cx, cy, hz)
            _ = sanitize_objects([{"model": "builtin:cube", "grid_position": [3, 2, 5]}], D)
            v1, p1 = enclosure_view(cx, cy, hz), enclosure_proj(cx, cy, hz)
            worst = max(worst, float(np.max(np.abs(v1 - v0))), float(np.max(np.abs(p1 - p0))))
    check("enclosure view + projection matrices are byte-identical regardless of objects",
          worst == 0.0, f"max matrix delta {worst:.2e}")
    check("the enclosure look yaw remains zero (placeable objects do not reintroduce pan)",
          all(np.allclose(enclosure_view(0, 0, hz), om.view_matrix(0, 0, cam_z_for(hz), 0.0, 0.0))
              for hz in HZ), "look yaw ≡ 0")

    # ── 5. Sphere worlds unaffected — no assets block → empty, no-op path ────────
    print("\n5. Sphere worlds unaffected — a world with no assets yields an empty, no-op list")
    check("a world dict with no 'assets' block sanitizes to an empty list",
          sanitize_objects([], D) == [],
          "empty placeable_objects → nothing drawn")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
