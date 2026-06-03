---
title: "2026-06-02 — Feature: The Gem — checkered enclosure box"
type: log-entry
date: 2026-06-02
category: feature
---

# The Gem — checkered enclosure box (floor → full grid box)

**Scope.** First of two requested Gem updates. Replaced the Gem world's single
flat checkered floor with a full **checkered enclosure box** — the pink gem now
floats inside a pink-and-white checker room that shares the [[grid-room]]'s
dimensions, with each checker square sized to exactly one grid cell ("the checker
IS the grid"). No camera math, physics, or shader code touched.

## What changed

**`Engine/renderer.py` — `Gem` class.**
- Removed the old infinite flat floor (`_build_floor_mesh` / `_draw_floor`,
  `_FLOOR_HALF=600`, `_FLOOR_DIVS`, `_FLOOR_TILE`, `_FLOOR_Y`).
- Renamed `_build_floor_texture` → `_build_checker_texture` (unchanged pink/white
  8×8 `GL_REPEAT` checker; pink `(255,182,193)`, white `(255,255,255)`).
- New `_build_box_mesh(half_w, half_h, depth, divisions)`: five interior faces —
  floor, ceiling, back wall, left/right walls — as textured quads in WORLD space
  (front rim on the glass at z = 0, back wall at z = −depth, floor/ceiling at
  y = ∓half_h, walls at x = ±half_w). Each face's UVs run `0..(divisions/8)`, so
  the 8×8 checker lays down exactly `divisions` checks across the `divisions`
  cells of every face → **one check per grid cell**, the checks stretched to match
  each face's (non-square) cell aspect. 30 verts / 30 UVs, rebuilt + cached on a
  dimension key like [[grid-room]].
- New `draw_box(...)`: draws the cached faces (flat, unlit, fixed-function,
  `GL_CULL_FACE` off so interior faces always show) + the grounding shadow.
- Shadow disk rebuilt in the `y = 0` plane and re-positioned by `draw_box` onto
  the box floor (`y = −half_h`) directly beneath the gem anchor (`_GEM_ANCHOR_Z =
  −10`), instead of the old fixed `y = −3.30` mid-air disk.
- `Gem.draw()` is now gem-mesh-only (spin + tilt + shader unchanged).

**`Launcher/app_engine.py`.** The gem world builds the gem lazily and calls
`gem.draw_box(hw, hh, world.grid_depth, world.grid_divisions)` in WORLD space
**before** the Earth-anchor translate (like the Grid Room), then draws the gem at
the z = −10 anchor so it floats inside the box. The in-translate gem branch is now
draw-only.

**`Worlds/gem/world.json`.** Added `grid_depth: 18.0` + `grid_divisions: 8`
(explicit; they also match the `WorldRuntime` defaults and the [[grid-room]]).
Removed the now-unused `floor_texture` key (the checker is generated in-memory).
Bumped to v1.1.

## Dimensions

Aperture-derived: `half_w = WINDOW_HALF_H·aspect ≈ 11.33` (16:9), `half_h =
WINDOW_HALF_H ≈ 6.375`, `depth = 18`, `divisions = 8`. Per-cell (= per-check)
sizes: X 2.833, Y 1.594, Z 2.250 world units. The gem (girdle r = 2.2, y ∈
[−2.80, 0.79], z = −10) sits fully inside the box, floating ≈3.57 u above the
checker floor.

## Validation

- `py_compile` clean on `renderer.py` + `app_engine.py`; `gem/world.json` parses.
- All **9** headless sims pass (`sim_calibration/camlag/latency/offaxis/orbit/
  overlay/predict/vertical/viewing` — RESULT: all checks passed), run under the
  `.venv` (pygame).
- Standalone numeric check of `_build_box_mesh`: 30 verts, UV span 0..1 at
  divisions = 8 (exactly one check per cell), box extents ±11.33 × ±6.375 ×
  0..−18, gem fully enclosed.
- The GL/visual result needs a live GUI session to confirm (standing renderer
  constraint); the path is the proven fixed-function textured-quad + client-array
  shadow already used by the old floor.

**Wiki updated.** [[gem]] / [[the-gem]] (floor → checkered box), [[worlds-index]]
(floor/shadow rows), and this log entry.
