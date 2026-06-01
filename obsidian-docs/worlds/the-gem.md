---
title: The Gem (World)
type: world
related: [world-system, rendering-engine, off-axis-projection, head-tracking, worlds-index, design-decisions, constraints]
last_updated: 2026-06-01
sources: [Worlds/gem/world.json, Engine/renderer.py, shaders/gem.vert, shaders/gem.frag, Launcher/app_engine.py]
---

# The Gem (World)

## What it is

> *"A brilliant hot-pink gemstone suspended in pure white space, rotating endlessly as light dances across its facets."*

The Gem is IRIS's third world: a physically consistent brilliant-cut gemstone rotating in pure white space, with no distractions — just the gem and the light. It is a demonstration of the renderer's faceted geometry, per-facet flat shading, and multi-light specular physics. Moving your head shifts your view of the gem through the window parallax exactly as the Earth world shifts the globe.

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
| `clear_color` | `[1.0, 1.0, 1.0]` (pure white) |

**Bloom is deliberately off.** The bloom post-composite applies a vignette (`VIGNETTE = 0.42`) that would darken the white background edges into an ugly ring. Without bloom the background stays clean white, and the gem's sharp facet specular (`shininess = 256`) delivers the diamond-flash brilliance that bloom would soften. Note: `sky` is used as the background type, which renders nothing (the white clear color is the scene).

## How it renders

The `Gem` class draws a single brilliant-cut faceted mesh built by `make_gem(n=16)`. The mesh has **64 flat-shaded triangles** — 16 table facets (fan from the crown centre), 32 crown facets (trapezoids split into coplanar pairs), and 16 pavilion facets (converging to the culet). The girdle radius is 2.2 world units (matched to Earth's approximate footprint), crown height 0.79, pavilion depth 2.80. Each triangle has its own flat normal computed at build time, so every facet reflects light at a distinct angle and produces an independent specular flash as the gem rotates.

**Rotation:** Two independent axes. The Y-axis spins continuously at 22°/s. The X-axis tilt **oscillates sinusoidally** between −25° and +25° (period ≈ 16.5 s, rate 0.38 rad/s), so the gem never approaches sideways and always stays close to upright. Both are applied as `glRotatef` calls inside `Gem.draw()`. As the gem spins, each facet's eye-space normal changes relative to the fixed sun and fill lights in world space, producing the continuously shifting highlights that make the gem feel physically alive.

**Floor:** A flat, unlit checkered plane at `y = −3.30`, textured with a
procedurally-generated pink/white checker (`_build_floor_texture`) tiled via
`GL_REPEAT`. Because it is flat and unlit, it needs only **2 triangles** — OpenGL's
perspective-correct UV interpolation gives the one-point-perspective convergence
of the grid lines to the horizon for free. `_FLOOR_DIVS = 1` (6 verts; it was
over-subdivided to 60×60 = 21,600 verts streamed every frame before the 2026-06-01
perf pass — see [[log]] / [[constraints]]). `_FLOOR_TILE = 10.0` sets one full
texture repeat = 10 world units, so each check is ≈1.25 units (raised from a too-
small 0.125 at the old `_FLOOR_TILE = 1.0`).

**Shadow:** A flat soft-edged disk drawn directly below the gem in its position-translate space (before the gem's own rotation push), so it stays horizontal on the "floor" regardless of how the gem is tilting. The disk is centred at y = −3.30 (0.50 below the culet tip at −2.80), radius 3.50 (wider than the gem equator). It is a 48-segment triangle-fan with vertex colours: centre is `(0, 0, 0, 0.28)` fading to fully transparent at the edge. Drawn with depth writes off so the gem correctly renders over it; the result is a soft oval shadow that grounds the gem in the white space and reinforces the parallax depth illusion.

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

Unlike Earth (five textures) and The Watcher (three procedural textures), The Gem is **fully** procedural. `make_gem()` generates the gem geometry at startup; the `gem` shader handles all colour, lighting, and emissive; the checkered floor texture is generated in-memory at startup (`_build_floor_texture`), and the soft drop-shadow disk uses vertex-colour alpha (no texture). No texture files are loaded.

## Constraints & tradeoffs

- **No bloom** → sharp specular, no glow bleed. Diamond-flash feel rather than jewel-glow feel. The correct tradeoff for a white background.
- **Flat shading** → sharp facet edges, no smooth interpolation. This is intentional: each flat-shaded facet has a constant normal, so the specular either fires or doesn't — producing the distinct, count-able flashes of a real cut gemstone.
- **n=16, 64 triangles** → 16-sided girdle, visually distinct facets without feeling busy. Higher n (32 was tried) makes the gem feel overwhelming and reduces per-facet legibility; n=16 balances facet count against clarity.
- **Sinusoidal tilt ±25°** → gem never goes sideways. A continuously accumulating X-axis rotation was rejected because it eventually tilts the gem 90° and breaks the "upright jewel" read. The oscillating tilt rocks the gem gently while keeping it recognisably vertical.
- **Shadow drawn before rotation** → the shadow disk is always flat regardless of how the gem tilts. Physically a simplification, but reads correctly as a grounding shadow and avoids the complexity of a projected shadow that would need to track the tilt angle.
- **GL 2.1 / GLSL 120** constraint applies. The gem shader uses only varying/uniform/built-in matrix conventions from GLSL 120; the shadow uses the fixed-function pipeline with vertex colour arrays (no shader needed).

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
