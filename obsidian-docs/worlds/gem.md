---
title: The Gem (World)
type: world
related: [world-system, rendering-engine, off-axis-projection, head-tracking, worlds-index, grid-room, design-decisions, constraints]
last_updated: 2026-06-02
sources: [Worlds/gem/world.json, Engine/renderer.py, shaders/gem.vert, shaders/gem.frag, Launcher/app_engine.py]
---

# The Gem (World)

## What it is

> *"A brilliant hot-pink gemstone floating inside a pink-and-white checkered box, rotating endlessly as light dances across its facets."*

The Gem is IRIS's third world: a physically consistent brilliant-cut gemstone floating inside a **pink-and-white checkered enclosure box**, with no distractions — just the gem, the checker room, and the light. (As of 2026-06-02 the old single flat checkered floor was promoted to a full box.) It is a demonstration of the renderer's faceted geometry, per-facet flat shading, and multi-light specular physics. Moving your head shifts your view of the gem — and the receding checker walls — through the window parallax exactly as the Earth world shifts the globe; the box's converging checks are a strong fish-tank depth cue.

It is intentionally **not** a visual reskin of an existing mesh: it uses the `Gem` renderer class, distinct from `Earth` and `Eye`, with its own flat-shaded facet geometry and dedicated `gem` shader.

## World definition

| Field | Value |
|---|---|
| `name` | The Gem |
| `primary_mesh` | `gem` |
| `secondary_elements` | *(none)* |
| `background` | `sky` |
| `lighting.sun_direction` | `[0.85, 0.52, 0.85]` |
| `lighting.ambient_intensity` | `0.06` |
| `use_bloom` | `false` |
| `use_parallax` | `true` |
| `show_icons` | `false` |
| `grid_depth` | `18.0` (box depth into the screen — matches [[grid-room]]) |
| `grid_divisions` | `8` (grid cells per face edge = checks per face edge) |
| `clear_color` | `[1.0, 1.0, 1.0]` (pure white; only shows if the box doesn't fill the frustum, which it does) |

**Bloom is off — and as of 2026-06-01 it is off everywhere** (bloom was removed engine-wide; the `use_bloom: false` flag is now moot but still correctly describes the result). This always suited the gem: the old bloom composite's vignette (`VIGNETTE = 0.42`) would have darkened the white background edges into an ugly ring, and the gem's sharp facet specular (`shininess = 256`) delivers diamond-flash brilliance that bloom would only soften. Note: `sky` is used as the background type, which renders nothing (the white clear color is the scene).

## How it renders

The `Gem` class draws a single brilliant-cut faceted mesh built by `make_gem(n=16)`. The mesh has **64 flat-shaded triangles** — 16 table facets (fan from the crown centre), 32 crown facets (trapezoids split into coplanar pairs), and 16 pavilion facets (converging to the culet). The girdle radius is 2.2 world units (matched to Earth's approximate footprint), crown height 0.79, pavilion depth 2.80. Each triangle has its own flat normal computed at build time, so every facet reflects light at a distinct angle and produces an independent specular flash as the gem rotates.

**Rotation:** Two independent axes. The Y-axis spins continuously at 22°/s. The X-axis tilt **oscillates sinusoidally** between −25° and +25° (period ≈ 16.5 s, rate 0.38 rad/s), so the gem never approaches sideways and always stays close to upright. Both are applied as `glRotatef` calls inside `Gem.draw()`. As the gem spins, each facet's eye-space normal changes relative to the fixed sun and fill lights in world space, producing the continuously shifting highlights that make the gem feel physically alive.

**Checkered enclosure box:** The gem floats inside a five-face room (floor, ceiling, back wall, left/right walls — the front is the viewing glass) drawn in WORLD space by `Gem.draw_box(half_w, half_h, depth, divisions)`, *before* the Earth-anchor translate, exactly like [[grid-room]]. The box shares the Grid Room's dimensions: width/height are the live aperture half-extents (`half_w = WINDOW_HALF_H·aspect ≈ 11.33` at 16:9, `half_h ≈ 6.375`), depth = `grid_depth` (18), with `grid_divisions` (8) grid cells per face edge. The front rim sits on the glass at z = 0; the back wall at z = −18. Each face is a textured quad whose UVs run `0..(divisions / 8)`, so the **8×8 pink/white `GL_REPEAT` checker** lays down exactly `divisions` checks across the `divisions` cells of every face → **one checker square per grid cell** (`_build_box_mesh`). The checks are stretched to each face's cell aspect: ≈2.83 (X) × 2.25 (Z) on the floor/ceiling, ≈2.83 (X) × 1.59 (Y) on the back wall, ≈2.25 (Z) × 1.59 (Y) on the side walls. The box mesh is rebuilt + cached on a `(half_w, half_h, depth, divisions)` key, so it is regenerated only when the aperture or grid changes — never per frame. Faces are flat, unlit fixed-function quads with `GL_CULL_FACE` off (interior faces always visible).

**Shadow:** A flat soft-edged disk drawn by `draw_box` onto the checker floor (`y = −half_h`), directly beneath the gem anchor (`z = −10`). Radius 3.50, a 48-segment triangle-fan with vertex colours fading centre `(0, 0, 0, 0.28)` → transparent edge, depth writes off. It grounds the floating gem on the checker floor and reinforces the parallax depth illusion. (Before 2026-06-02 the disk sat at a fixed `y = −3.30` over an infinite flat floor; it now rides the actual box floor.)

**Lighting model (`gem.frag`, GLSL 120):**

- **Diffuse** — hot pink base `vec3(1.0, 0.06, 0.48)` with a two-light blend (key + fill). Very low ambient (0.06) so the unlit back-facets read as deep shadow, maximising the front-back depth contrast.
- **Key specular** — `shininess = 256`: extremely narrow, intense white-pink sparkle from the key light. Produces sharp, single-facet diamond flashes as each crown or pavilion facet swings into alignment.
- **Fill specular** — `shininess = 128`: slightly broader blue-white tint from the fill light. Gives the gem a second flash source so multiple facets can illuminate simultaneously.
- **Fresnel rim** — power 4.5 → tight, vivid hot-pink glow at the silhouette edges. Separates the gem from the white background at the limb.
- **Emissive core** — radial gradient pulsing at ~1.4 Hz (78% base + 18% swing). The centre glows hot pink; the outer edge bleeds to a cooler pink-white. Pulse is driven by a sine on `u_time`, passed from `Gem.draw()` alongside `u_sun_eye` and `u_fill_eye`.
- **Iridescence** — subtle blue-violet hue shift at glancing angles via a view-dot-normal blend, weighted by the Fresnel. Gives the gem a supernatural depth that pure diffuse + spec cannot.

**Fill light:** A second world-space light direction `[-0.72, -0.30, 0.65]` (left-low-front, ~120° from the key) is computed once in `app_engine.py` and rotated into eye space per frame alongside `sun_eye`. It is passed as `u_fill_eye` to the gem shader and is not used by any other renderer.

**Off-axis parallax:** The gem sits at the same world anchor as Earth (`z = -10, pf = 0`). The Kooima off-axis frustum and view_matrix are applied identically — moving the head shifts the view of the gem through the window just like the planet. The gem's own model rotation is independent of and layered on top of the camera math.

## Minimal assets

Unlike Earth (five textures) and The Watcher (three procedural textures), The Gem is **fully** procedural — no texture files are loaded. `make_gem()` generates the gem geometry at startup; the `gem` shader handles all colour, lighting and emissive; the pink/white checker for the enclosure box is generated in-memory at construction (`_build_checker_texture`, an 8×8 `GL_REPEAT` checkerboard, pink `(255,182,193)` / white `(255,255,255)`); and the grounding shadow disk uses vertex-colour alpha (no texture). The old `floor_texture: "floor_checkered.png"` world-JSON key was removed — it was already unused.

## Constraints & tradeoffs

- **No bloom** → sharp specular, no glow bleed. Diamond-flash feel rather than jewel-glow feel. The correct tradeoff for a white background.
- **Flat shading** → sharp facet edges, no smooth interpolation. This is intentional: each flat-shaded facet has a constant normal, so the specular either fires or doesn't — producing the distinct, count-able flashes of a real cut gemstone.
- **n=16, 64 triangles** → 16-sided girdle, visually distinct facets without feeling busy. Higher n (32 was tried) makes the gem feel overwhelming and reduces per-facet legibility; n=16 balances facet count against clarity.
- **Sinusoidal tilt ±25°** → gem never goes sideways. A continuously accumulating X-axis rotation was rejected because it eventually tilts the gem 90° and breaks the "upright jewel" read. The oscillating tilt rocks the gem gently while keeping it recognisably vertical.
- **One check per grid cell** → the checker IS the grid. UVs are mapped per face as `divisions / 8` so the 8×8 texture gives `divisions` checks across `divisions` cells. With `divisions = 8`, every face maps the texture UV 0..1 exactly once (perfectly aligned, seamless). Checks are intentionally rectangular (matching the non-square cells), not forced square — that is what "fits one grid square" means here.
- **Box drawn in world space (not anchored)** → like [[grid-room]], `draw_box` runs before the Earth-anchor translate so the front rim lands on the glass at z = 0. The gem itself still rides the z = −10 anchor and floats inside. Coupling: `_GEM_ANCHOR_Z = −10` in `Gem` must match `OBJECTS["earth"]` in `app_engine.py`.
- **Shadow flat on the floor** → the grounding disk is drawn (depth-writes off) on the box floor beneath the gem, always horizontal regardless of gem tilt. Physically a simplification, but reads correctly and avoids a projected shadow that would need to track the tilt angle.
- **GL 2.1 / GLSL 120** constraint applies. The gem shader uses only varying/uniform/built-in matrix conventions from GLSL 120; the box faces and shadow use the fixed-function pipeline (textured quads / vertex-colour arrays — no shader needed).

## Integration with head tracking and projection

The gem uses the **identical** camera math, parallax, and head-tracking pipeline as every other world:

- [[off-axis-projection]] `off_axis_frustum` + `view_matrix` set per frame from the head 5-tuple.
- [[head-tracking]] `hx`, `hy`, `hz`, `yaw`, `pitch` drive the window parallax, zoom, and proximity-gated rotation exactly as for Earth.
- The gem's own spin is a model transform (inside the anchor push/pop); it does not touch the camera or frustum.

No new tracking pipeline, no new camera code, no new post-processing.

## Systems used

[[off-axis-projection]] · [[head-tracking]] · [[rendering-engine]] · [[world-system]]

## Related

[[earth]] · [[the-watcher]] · [[worlds-index]] · [[design-decisions]] · [[rendering-engine]]
