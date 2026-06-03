---
title: Off-Axis Projection (Camera Math)
type: system
related: [head-tracking, rendering-engine, headless-simulation, orbital-icons, constraints, design-decisions, system-interactions, viewing-models]
last_updated: 2026-06-02
sources: [Engine/camera_math.py, Scripts/validation/sim_offaxis.py, Scripts/validation/sim_viewing.py, Scripts/validation/sim_orbit.py]
---

# Off-Axis Projection (Camera Math)

## Purpose

This is the heart of the IRIS illusion. It answers one question every frame:
*given where the viewer's head is, what does the scene look like through the
monitor?* The monitor is treated as a fixed sheet of glass — a window — and the
3D world lives behind it. When you move your head, the view through that window
shifts exactly as a real window would. This is the "fish-tank VR" effect, and
getting the geometry right is what makes a flat screen read as depth.

The module (`Engine/camera_math.py`) is deliberately **pure geometry** — no
OpenGL, no pygame, no camera, no Cocoa. That isolation is intentional: the same
math can be unit-tested headlessly (see [[headless-simulation]]) and reused by
the renderer without duplication, so the live picture can never silently drift
from the verified math.

## The physical model

- The **monitor** is a fixed rectangle (the "window") lying in the world `z = 0`
  plane.
- The **scene** lives behind the glass at `z < 0` (the Earth sits at `z = -10`).
- The **eye** is a tracked point *in front* of the glass at `z = +cam_z`.

What the eye sees is the scene projected through the window aperture — an
asymmetric, sheared frustum whose apex is the eye and whose base is the window
rectangle. This is the **Kooima generalized perspective projection**. Unlike a
normal symmetric perspective camera, this is geometrically what a real window
does: moving the eye sideways shears the frustum (true motion parallax), and
moving the eye *closer* widens the subtended angle (the scene reveal grows as
you approach). Critically, **no camera rotation is involved** in the parallax —
a window reveals the scene by where the eye *is*, never by where it points.

## The three blended viewing components

The view is the smooth blend of three independent inputs from
[[head-tracking]]:

1. **Translation → off-axis frustum shear** (head position `hx`, `hy`). Lateral
   head motion shears the frustum, producing true motion parallax. Objects at
   the screen edge appear to "stick" to real-world coordinates as you move.
   *Sense:* moving right reveals the **left** of the scene (window parallax).

2. **Depth response → on-screen scale** (head depth `hz`). **Telephoto, identical for
   every world** (as of 2026-06-02 final): `cz = CAM_BASE_Z·e^(+ZOOM_K·hz)`. Leaning in
   lengthens `cam_z`, narrowing the frustum so the scene **magnifies** on approach (the
   calibrated feel pinned by `sim_viewing` / `sim_vertical`), and it keeps the near-field
   "push the planet off-screen" vertical exploration. Enclosure worlds (Grid Room, Gem)
   use this **same** response, so a body at the `z = −10` anchor is the same on-screen
   size in every world. *(An earlier per-world FORWARD DOLLY mechanism — held `cz` at
   `CAM_BASE_Z` and translated the scene toward the eye to "move into the room" — was
   removed: in a fixed-window rig it grew a foreground object ~3.6× and diverged from
   Earth's size, which the user rejected. See [[viewing-models]] / [[known_issues]].)*

3. **Rotation → proximity-gated view pan** (head orientation `yaw`, `pitch`).
   A real observer explores a *far* scene by moving (translation, above) and a
   *near* scene by turning the head. Rotation is therefore **gated by how close
   the viewer is**: weak far away, dominant up close, with a smoothstep blend so
   there is no perceptible mode switch. *Sense:* turning the head right reveals
   the **right** of the scene (panning a portal) — deliberately the opposite of
   translation. **Every world** uses the frozen gate window `proximity(hz)` =
   `[ROT_PROX_LO, ROT_PROX_HI] = [0.0, 0.8]`, so the look fades in over the same
   distances on the **object/sphere worlds**. **Enclosure worlds**
   (`rendering.enveloping = true`) draw a front rim on the glass at `z = 0` that the
   projection pins to the screen edges as a bezel anchor; a pan would shear that visible
   rim, so as of **2026-06-02 (final)** the enclosure rotational look is held at **zero —
   grids do not pan** (`if world.enveloping: yaw_target = pitch_tgt = 0.0` in
   `app_engine.py`). *(An earlier capped pan `LOOK_ENCLOSURE_AMP = 0.35` was removed: any
   non-zero pan still shears the anchor.)* Object worlds keep the full look → byte-identical.
   `camera_math.py` untouched. See [[viewing-models]], [[what-makes-perspective-optimal]]
   and log [[2026-06-02_grids-dont-pan]].

## Key constants

| Constant | Value | Meaning |
|---|---|---|
| `FOVY_DEG` | 58.0° | Reference vertical field of view |
| `NEAR` / `FAR` | 0.3 / 200.0 | Clip planes |
| `CAM_BASE_Z` | 11.5 | Neutral eye distance from the glass (world units) |
| `EARTH_BASE` | (0, 0, −10) | Scene anchor depth behind the window |
| `WINDOW_HALF_H` | `CAM_BASE_Z · tan(FOVY/2)` | Window half-height |
| `EARTH_PARALLAX` | 0.0 | Scene is *fixed*; all parallax comes from the frustum |
| `ROT_PROX_LO` / `HI` | 0.0 / 0.8 | Head-z range over which rotation fades in |
| `ROT_MAX_DEG` | 20.0° | Max view pan at full proximity + full head turn |

The window half-height is chosen so that an on-axis eye at the neutral distance
`CAM_BASE_Z` reproduces the original `gluPerspective(58°)` framing **exactly**.
So at rest the view is identical to a plain perspective camera; only off-centre
or near eyes change anything. `EARTH_PARALLAX = 0` because the off-axis frustum
now produces *all* the parallax — an older rig added an artificial camera-follow
that would double the motion under this projection.

## Entry points (key functions)

- `off_axis_frustum(cam_x, cam_y, cam_z, aspect)` — the `glFrustum`-form
  projection matrix. The left/right/bottom/top edges are the window corners
  shifted by the eye offset and scaled by `near / cam_z`. Reduces to
  `perspective(FOVY_DEG)` when the eye is centred at `CAM_BASE_Z`.
- `view_matrix(cam_x, cam_y, cam_z, yaw, pitch)` — the modelview. `M = R · T(−eye)`,
  so the eye maps to the origin and rotation pivots *about the eye* (panning the
  portal, not orbiting the scene). With `yaw = pitch = 0` it equals
  `view_translate(...)`, the pure-parallax case.
- `proximity(hz)` — smoothstep 0→1 proximity weight that gates the rotation
  component.
- `look_at`, `perspective`, `project_point`, `segment_hits_sphere` — numpy
  replicas of the GL fixed-function pipeline, used for headless screen-projection
  and occlusion checks.

This module also owns the **orbital-icon geometry** (`earth_world_center`,
`orbital_local_pos`, `icon_angle`, `icon_radius`, and the `ORBIT_*` constants:
radius 4.2, tilt 63°, icon size 0.85, speed 0.22 rad/s) so the live render in
[[orbital-icons]] is identical to the headless checks in `sim_orbit.py`.

## Data flow

| Consumes | Produces | Destination | Purpose |
|----------|----------|-------------|---------|
| Head 5-tuple from [[head-tracking]] | `cam_x`, `cam_y`, `cam_z` (eye position) | [[engine-loop-and-daemon]] + [[rendering-engine]] | translate/scale camera |
| (same) | `cam_yaw`, `cam_pitch` (view rotation) | [[engine-loop-and-daemon]] | proximity-gated rotation |
| (same) | Projection matrix from `off_axis_frustum()` | [[rendering-engine]] | shear frustum for parallax |
| (same) | Modelview matrix from `view_matrix()` | [[rendering-engine]] | position + rotate view |
| Head `hz` (distance) | `proximity()` — 0→1 blend | [[engine-loop-and-daemon]] | gate rotation strength |
| Orbital constants | Icon geometry (radius, position, angle) | [[orbital-icons]] | draw clickable icons |

## Constraints

- The illusion is calibrated for one viewing distance (~600 mm / forearm
  length). Further away, the perspective is slightly off — this is physics, not
  a bug. See [[constraints]].
- The blend must stay smooth; the proximity gate uses smoothstep specifically to
  keep a zero first-derivative transition (no felt "mode switch").

## Dependencies

- **Consumes:** the head 5-tuple `(hx, hy, hz, yaw, pitch)` from [[head-tracking]].
- **Feeds:** [[rendering-engine]] (projection + modelview matrices each frame),
  [[orbital-icons]] (shared orbital geometry).
- **Verified by:** [[headless-simulation]] (`sim_offaxis`, `sim_viewing`,
  `sim_orbit`, `sim_vertical`, and `sim_envelop` for the enclosure path).
- **Orchestrated by:** [[engine-loop-and-daemon]].
