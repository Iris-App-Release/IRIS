---
title: The Grid Room (World)
type: world
related: [world-system, rendering-engine, off-axis-projection, head-tracking, worlds-index, gem, design-decisions, constraints, grid-api-customization]
last_updated: 2026-06-02
sources: [Worlds/grid_room/world.json, Engine/renderer.py, Launcher/app_engine.py]
---

# The Grid Room

## What it is

> *"A wireframe shadow-box room: the monitor becomes a window into receding holographic grid lines — pure spatial reference, the strongest fish-tank depth cue."*

The Grid Room is IRIS's spatial **reference world** and the foundation of the [[grid-api-customization]] safe-customization API. It is not a visual destination (no floating objects, no scenic moment) but a **calibration tool and asset-placement scaffold**: users (and Claude) see the coordinate system directly on screen and can reason about object placement in grid cells. The receding grid lines converge to a vanishing point — exactly the depth scaffold the parallax illusion needs — and the rigid box gives the visual system a texture to distinguish real head motion from tracking jitter. Moving your head sees the front rim (on the glass at z = 0) stay fixed while the back wall (at z = −depth) recedes, a powerful motion-parallax depth cue.

It uses the `GridRoom` renderer class: a wireframe "shadow-box" drawn in WORLD space (not anchored to a floating object), with per-vertex alpha fade from front (bright) to back (faint) and no shaders — only fixed-function `GL_LINES`.

## World definition

| Field | Value |
|---|---|
| `name` | Grid Room |
| `primary_mesh` | `room` |
| `secondary_elements` | *(none)* |
| `background` | `void` (black clear color) |
| `lighting.sun_direction` | `[0.0, 0.0, 1.0]` (unused; unlit wireframe) |
| `lighting.ambient_intensity` | `0.0` |
| `use_bloom` | `false` |
| `use_parallax` | `true` |
| `enveloping` | `true` (enclosure viewing model — see below) |
| `show_icons` | `false` |
| `grid_color` | `[0.30, 0.72, 1.0]` (cyan-blue) |
| `grid_depth` | `18.0` (world units; room recedes 18 units behind the glass) |
| `grid_divisions` | `8` (grid cells per face edge; 8×8 on floor, 8×8 on back wall, etc.) |
| `clear_color` | `[0.01, 0.012, 0.022]` (near-black, slightly warm) |

## How it renders

The `GridRoom` class draws a wireframe box with **five interior faces** (floor, ceiling, back wall, left/right walls; the front is the viewing glass) as cyan-blue `GL_LINES` in the fixed-function pipeline.

**Dimensions (at 16:9 aspect, live aperture):**
- **X-axis** (left/right): ±11.33 world units
- **Y-axis** (up/down): ±6.375 world units  
- **Z-axis** (depth): 0 (glass) to −18.0 (back wall)
- **Grid cells per edge**: 8 (so each cell is ~2.83 W × 1.59 H × 2.25 D world units)

**Grid lines:**
Each face is subdivided into `grid_divisions` × `grid_divisions` cells by lines running parallel to its axes. The **back wall** has a full vertical + horizontal grid. The **floor and ceiling** have grids in X (left-right) and Z (depth), running from the glass (z=0) to the far wall (z=−depth). The **left and right walls** have grids in Y (up-down) and Z (depth), same depth span.

**Alpha fade & depth sorting:**
Per-vertex RGBA color blending: the front rim (z = 0, on the glass) draws bright (`alpha = 0.78`), the back wall (z = −depth) draws faint (`alpha = 0.06`), and intermediate lines fade linearly. Depth writes are off (so wireframe does not occlude geometry), but depth *testing* is on (so the wireframe respects z-ordering of other objects). This creates a semi-transparent effect where lines vanish into the background as they recede.

**Mesh caching:**
The line mesh is cached and rebuilt only when `(half_w, half_h, depth, divisions, color)` change — never per frame. This is key for performance: the box can have hundreds of line segments, but they are computed and buffered once, then reused frame after frame.

**Front rim anchor (window frame):**
A brighter frame (`alpha = 0.78`) drawn on the glass (z = 0) marks the edges of the window aperture. Under the off-axis frustum, this rim maps exactly to the screen border, anchoring the illusion: the viewer knows the box interior extends behind the monitor.

## Integration with parallax

The Grid Room is drawn in **WORLD space**, before the Earth-anchor translate (just like [[gem]] draws its box there). The front rim sits on the glass at z = 0 *by construction* — it is NOT subject to parallax. The back wall and side walls recede into world space (z = −depth) and therefore *do* experience off-axis parallax and motion parallax: as the viewer's head moves, the converging grid lines shift on screen, creating a powerful sense of depth. This is exactly the design: the zero-parallax front rim anchors the viewer to the glass, while the receding grid teaches the 3D coordinate system.

## Enclosure viewing model (`enveloping: true`)

The Grid Room sets `rendering.enveloping = true`, but as of **2026-06-02 (final)** that
flag no longer means "forward dolly / enter the room." It now means just one thing: the
Grid Room uses the **exact same camera physics as [[earth]]** — same telephoto zoom,
same frozen proximity look-gate — and differs only by **capping the look amplitude** so
its bezel-locked front rim never shears. Per the user's directive: the grid worlds'
zoom and look should "operate EXACTLY the same as the spherical worlds," anchored.

- **Zoom — identical to Earth (telephoto).** Head depth drives the eye-to-glass
  distance exactly as in the object worlds: `cz = BASE_Z·e^(+ZOOM_K·hz)`. Leaning IN
  pushes the eye back, the off-axis frustum narrows, and the whole room magnifies
  (zoom in); leaning OUT recedes it. There is no separate dolly. A body at the Earth
  anchor (z = −10) subtends the **same on-screen size Earth would** at any head-z.
  *(An earlier 2026-06-02 model held `cz` constant and dollied the scene forward to
  read as "entering the room"; it grew foreground objects ~3.6× and diverged from
  Earth's size, so it was removed.)*
- **Bezel anchor — the rim stays on the screen edges at every distance.** The front
  rim is drawn on the glass at world z = 0. Under the off-axis projection, geometry
  exactly on the z = 0 window plane maps to the screen edges for *any* eye position or
  zoom — so the rim is pinned to the bezel throughout the whole approach (verified to
  machine precision across all head-z in `sim_envelop.py`). This is the "good part of
  the grid worlds," and it now holds at every distance because nothing carries the rim
  off-screen.
- **Rotational look — Earth's gate, capped amplitude.** The look uses the frozen
  `om.proximity(hz)` ([0.0, 0.8]) gate, identical to Earth, so it fades in over the
  **same head-z distances** and just as smoothly. The catch: a pan rotates the
  still-visible rim about the eye and would shear it. So the enclosure pan is scaled by
  a single constant, `LOOK_ENCLOSURE_AMP = 0.35`, in `app_engine.py`. Because the look
  is also proximity-gated, the pan is ≈ 0 at rest (rim rock-solid) and grows to a small,
  bounded max as you lean in / get "in the room" — a gentle look that never warps the
  grid. Raise `LOOK_ENCLOSURE_AMP` toward 1.0 for a more Earth-like pan (more rim
  shift); lower it for a tighter anchor. (See [[what-makes-perspective-optimal]] /
  [[viewing-models]].)

Pinned by the headless guard `Scripts/validation/sim_envelop.py` (enclosure zoom IS the
object telephoto law; a z = −10 body is the same size under both paths and grows on
lean-in; the rim is bezel-locked at every head-z & eye offset; the look uses the frozen
`om.proximity` gate; the enclosure pan = object pan × `LOOK_ENCLOSURE_AMP`, ≤ object pan,
monotone + C¹; object path uncapped → Earth byte-identical).

## Minimal assets

The Grid Room is **entirely procedural** — no texture files, no models. The `GridRoom` class generates all line vertices in `_rebuild()` based on `(half_w, half_h, depth, divisions)`. The color is a parameterized RGB triple. Geometry lives only in RAM until the dimensions change; no persistent mesh is built or cached to disk.

## Constraints & tradeoffs

- **Wireframe only** → no filled surfaces, no shading. The room is a visual scaffold, not a scenic backdrop. This keeps rendering cost minimal and keeps the visual focus on foreground floating objects (the gem, future assets).
- **8 divisions per edge** (by default, configurable) → 64 cells per face, enough detail to resolve individual cells for asset placement without overwhelming visual clutter. Increasing to 16 makes the grid denser but harder to read; decreasing to 4 makes cells too large.
- **Fixed cyan color `[0.30, 0.72, 1.0]`** (configurable via `grid_color`) → chosen to complement the white backgrounds of [[gem]] and the blue starfield of [[earth]]. Cool blue-cyan reads as "artificial reference frame" rather than a scenic element.
- **Front rim brighter than walls** (`alpha: 0.78 vs 0.55 front / 0.06 back`) → the frame pops as a visual anchor; the walls fade into depth. This hierarchy clarifies the structure.
- **No bloom** → sharp lines, no glow halo (bloom was removed engine-wide 2026-06-01; the wireframe benefits from this).
- **Fixed-function `GL_LINES`** → frozen shaders are never touched. No shader compilation, no risk of breaking parallax or physics.
- **Aperture-coupled dimensions** → `half_w, half_h` are always derived from the **live aperture** (WINDOW_HALF_H × aspect), not hardcoded. So if the user calibrates the framing via Camera Calibration, the grid immediately re-scales to the new viewport.

## Systems used

[[off-axis-projection]] · [[head-tracking]] · [[rendering-engine]] · [[world-system]]

## Related

[[earth]] · [[the-watcher]] · [[gem]] · [[worlds-index]] · [[grid-api-customization]] · [[design-decisions]]
