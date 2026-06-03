---
title: "2026-05-31 — Feature: The Gem — third world, rotating brilliant-cut gemstone"
type: log-entry
date: 2026-05-31
category: feature
---

# The Gem — third world, rotating brilliant-cut gemstone

**Scope.** Implemented [[gem]], the third IRIS world: a brilliant hot-pink
faceted gemstone rotating in pure white space. This activates the pre-existing
`Gem` class and `gem` shader that were already in the renderer but not wired into
the world system.

## Pre-implementation review

Full vault review before any code change. Key findings from reading
[[rendering-engine]], [[world-system]], [[worlds-index]], [[design-decisions]],
[[off-axis-projection]], [[head-tracking]], [[constraints]], and [[system-interactions]]:

- `Gem` class and `gem.vert/frag` shaders already existed in `Engine/renderer.py`
  and `shaders/` — functional but unexposed.
- `make_gem(n=8)` generated only 32 flat-shaded triangles; increasing to n=32
  gives 128 for a much richer brilliant-cut appearance.
- `Gem` had no `update()` method (no rotation); needed to add one.
- No `Worlds/gem/world.json` → world system couldn't discover or select the gem.
- `app_engine.py` only dispatched `primary_mesh == "eye"` and `earth`; a `gem`
  branch was needed.
- **Bloom conflict**: the vignette in the post-composite (VIGNETTE=0.42) would
  darken the pure-white background edges. Bloom must be off for The Gem.
- Fill light (`u_fill_eye`): the gem shader already accepted it, but the engine
  never computed a fill direction. Added `fill_world` alongside `sun_world`.

## Changes made

**`Engine/renderer.py`:**
- `make_gem(n=8 → n=32)`: 128 flat-shaded triangles (4× more facets). Geometry
  dimensions unchanged (r_girdle=1.45, h_crown=0.52, h_pav=1.85).
- `Gem.__init__`: added `self._spin_y = 0.0`, `self._spin_x = 0.0`.
- `Gem.update(dt)`: new method — spins `_spin_y` at 22°/s (primary yaw) and
  `_spin_x` at 7°/s (slow tilt).
- `Gem.draw()`: wrapped `glPushMatrix / glRotatef(_spin_y, Y) / glRotatef(_spin_x, X)
  / … / glPopMatrix`. Rotation is model-space only; camera math is untouched.

**`shaders/gem.frag`:**
- Base color: `vec3(0.88, 0.10, 0.55)` → `vec3(1.0, 0.06, 0.48)` (true hot pink).
- Key specular shininess: 96 → 256 (narrow diamond flash).
- Fill specular shininess: 64 → 128; cooler blue-white tint.
- Key spec weight: 1.4 → 2.2; fill: 1.1 → 1.2.
- Fresnel power: 3.2 → 4.5 (tighter, more saturated rim glow).
- Emissive: stronger hot-pink centre `vec3(1.0, 0.12, 0.55)`, cooler edge `vec3(0.95, 0.50, 0.75)`.
- Iridescence: shifted to blue-violet `vec3(0.35, 0.05, 0.80)` for more contrast
  against the pink body.

**`Worlds/gem/world.json` (new):**
- `primary_mesh: "gem"`, `background: "void"`, `clear_color: [1, 1, 1]`,
  `use_bloom: false`, `show_icons: false`.

**`Launcher/app_engine.py`:**
- Added `Gem` to renderer import.
- Added `fill_world = [-0.72, -0.30, 0.65]` (left-low-front, ~120° from key),
  normalized; computed once at startup.
- Added per-frame `fill_eye = (view_rot @ fill_world).tolist()` after `sun_eye`.
- Added `gem = None` lazy handle alongside `eye = None`.
- Added `gem.update(dt)` in the animation block.
- Added `elif world.primary_mesh == "gem"` dispatch branch with the same lazy-init
  + fallback pattern as `eye`.

## Validation

- All 6 headless sims (`sim_orbit`, `sim_offaxis`, `sim_viewing`, `sim_latency`,
  `sim_vertical`, `sim_overlay`) still print "RESULT: all checks passed".
- `make_gem(n=32)` geometry check: 384 vertices / 128 flat-shaded triangles;
  Y range [-1.85, 0.52], XZ radius max 1.45. Correct.
- Python syntax check on `Engine/renderer.py` and `Launcher/app_engine.py`: OK.
- `Worlds/gem/world.json` parses correctly as JSON.
- GL compilation can only be verified in a live GUI session (camera / GL shader
  restriction from agent shell — same constraint as all prior renderer work).

## Architecture notes

- The gem sits at the Earth anchor (`z = -10, pf = 0`) and inherits the **full
  off-axis parallax, zoom, and rotation pipeline** unchanged.
- The gem's model rotation (`glRotatef`) is layered on top of the camera math,
  not substituting for it. Normals include the model rotation via `gl_NormalMatrix`,
  so per-facet lighting is physically correct as the gem spins.
- The fill light is computed per-frame (`view_rot @ fill_world`) so it tracks the
  camera orientation correctly as the viewer moves.
- The gem is fully procedural — no texture assets required.

**Wiki updated.** New [[gem]] page (full world reference); [[worlds-index]]
(third world added to comparison table, "Not yet a world" section removed);
[[rendering-engine]] (`Gem` entry updated — now a real world with n=32);
[[design-decisions]] (The Gem design rationale added); `index.md` (third world
in prose + worlds table); and this log entry.
