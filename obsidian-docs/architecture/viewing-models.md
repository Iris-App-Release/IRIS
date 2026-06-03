---
title: Viewing Models — the two illusion methods
type: architecture
related:
  - off-axis-projection
  - world-system
  - worlds-index
  - constraints
  - design-decisions
  - earth
  - the-watcher
  - gem
  - grid-room
last_updated: 2026-06-02
sources:
  - Launcher/app_engine.py
  - Engine/camera_math.py
  - Worlds/world_runtime.py
  - Scripts/validation/sim_viewing.py
  - Scripts/validation/sim_vertical.py
  - Scripts/validation/sim_envelop.py
---

# Viewing Models — one camera, two world styles

IRIS turns head-depth into an on-screen depth response with **one shared camera
model**: the frozen off-axis "window" core ([[off-axis-projection]]), telephoto
eye-distance scaling, and a proximity-gated rotational look. Every world — object or
enclosure — uses it identically, so they all **zoom the same way and the look fades in
over the same head-z distances.**

What differs is **world style**, not camera math:
- **Object / open worlds** ([[earth]], [[the-watcher]]) — a hero body floating in empty
  or atmospheric space, no front boundary; the look pans freely.
- **Rim-anchored enclosure worlds** ([[grid-room]], [[gem]]) — geometry whose front rim
  sits on the glass at `z = 0`, bezel-locked to the screen edges as a hard anchor;
  because a pan would shear that visible rim, the look **amplitude is capped**.

The switch is one declarative flag, `rendering.enveloping` (default `false`), read by
[[world-system]] (`WorldRuntime.enveloping`) and branched on in
`Launcher/app_engine.py`. **No camera math changes between the two** —
`Engine/camera_math.py` stays frozen; the *only* engine difference is a single
post-multiply that caps the enclosure look pan (`LOOK_ENCLOSURE_AMP`).

> [!note] History — there used to be two depth responses
> Through 2026-06-02 the enclosure worlds used a genuinely different depth mechanism: a
> **forward dolly** (held `cam_z` constant and translated the scene toward the eye, so
> leaning in "moved you into the room" and grew a hero object ~3.6×). The user rejected
> it — they wanted the grid worlds to behave **exactly** like the sphere worlds (same
> zoom, same look distances, gem the same size as Earth), just anchored. So the dolly
> was removed; enclosures now share Earth's telephoto camera and differ only by the rim
> anchor + the capped look. (log: 2026-06-02 "revert+resimplify".)

---

## The geometry, and why the enclosure caps the look

The monitor is a **fixed rectangle** at world `z = 0` (the glass); the scene lives
behind it; the eye is the tracked head at `z = +cam_z`. Two consequences matter:

1. **Telephoto zoom (shared).** A foreground object at `z = −10` has on-screen size
   proportional to `cam_z / (cam_z + 10)`. Leaning in pushes the eye *back* (larger
   `cam_z` via `BASE_Z·e^(+ZOOM_K·hz)`), narrowing the frustum and **magnifying** the
   scene. Every world uses this, so a body at the anchor is the same size in every world.
2. **The z = 0 plane is always the screen.** Geometry exactly on the window plane maps
   to the screen edges for *any* eye position or zoom. So an enclosure's front rim
   (drawn at `z = 0`) is **bezel-locked at every distance** — a free, exact anchor.

The catch is rotation: the look pans by rotating the modelview about the eye, which
rotates that still-visible rim and **shears** it off the screen border. Object worlds
have no rim, so they pan at full amplitude. Enclosure worlds cap the pan
(`LOOK_ENCLOSURE_AMP`) so the rim's on-screen shift stays a gentle settle. That cap is
the entire difference between the two styles. *(A 2026-06-02 forward-dolly model carried
the rim off-screen so the look could be uncapped once "enveloped"; it was removed because
it made the hero object diverge from Earth's size — see the note above and [[known_issues]].)*

---

## Method A — Object / Telephoto window

> **Mental model:** the monitor is a window onto a single hero body floating behind
> the glass. You explore it by leaning (telephoto magnify) and, up close, by turning
> your head (peeking around it).

**Worlds:** [[earth]], [[the-watcher]]. **Flag:** `enveloping: false` (the default).

**Depth response.** Eye-to-glass distance scales exponentially with head depth:
`cam_z = BASE_Z · e^(+ZOOM_K·hz)` (`ZOOM_K = 0.95`, clamped `[CAM_Z_MIN, CAM_Z_MAX]
= [5, 34]`).
- Lean **in** → larger `cam_z` → narrower frustum → the body **magnifies**; parallax weakens.
- Lean **out** → smaller `cam_z` → wider frustum → the body recedes; parallax strengthens.

**Rotational look.** Frozen proximity gate `proximity(hz)` over `[0.0, 0.8]`, plus a
larger near-field **vertical** gain (`ROT_MAX_PITCH_DEG = 40`, clamped to 46°
anti-nausea) so up close you can peer up/down far enough to push the body off the
top/bottom of the screen — the deliberate near-field exploration.

**Best for:** a single scenic subject with empty/atmospheric surroundings — a
planet, an eye, a creature, an artifact. The subject should sit at the scene anchor
(`z = −10`, footprint ~`R = 2.6`) so it shares the calibrated framing.

**Guarded by:** `sim_viewing.py`, `sim_vertical.py` (these are the *calibrated feel*
guards — treat them as frozen; an enclosure change must leave them byte-identical).

---

## Method B — Rim-anchored enclosure

> **Mental model:** the monitor is a window with a visible frame on the glass, looking
> into a box. The frame stays pinned to the screen edges (sealed); leaning in zooms
> into the box exactly as Earth zooms; up close you can glance around inside it, but
> only gently — the frame must not warp.

**Worlds:** [[grid-room]], [[gem]]. **Flag:** `enveloping: true`.

**Depth response — identical to Method A (telephoto).** `cam_z = BASE_Z · e^(+ZOOM_K·hz)`,
same constants, same clamps. There is **no dolly**. A body at the anchor (`z = −10`)
subtends the **same on-screen size it would in an object world** at every head-z. This
is the point of the 2026-06-02 revert: the grid worlds zoom *exactly* like the sphere
worlds, so the gem matches Earth's size initially and at full lean-in.

**The anchor.** The enclosure's front rim is drawn on the glass at `z = 0`, so the
off-axis projection pins it to the screen edges at **every** distance and eye offset —
a hard bezel anchor, with no special code (it falls out of the window geometry).

**Rotational look — Earth's gate, capped amplitude.** The look uses the frozen
`proximity(hz)` over `[0.0, 0.8]` — *identical* to Method A, so it engages over the same
distances and just as smoothly. The pan target is then scaled by one constant before
smoothing:

```
prox        = proximity(hz)                 # same as the object worlds
yaw_target  = yaw   * ROT_MAX_RAD       * prox
pitch_tgt   = pitch * ROT_MAX_PITCH_RAD * prox
if world.enveloping:
    yaw_target *= LOOK_ENCLOSURE_AMP        # 0.35 — the one difference
    pitch_tgt  *= LOOK_ENCLOSURE_AMP
```

Because `prox · cap` is a smoothstep × constant, the pan is **≈ 0 at rest** (rim
rock-solid) and grows to a small bounded max as you lean in — a gentle look that never
shears the rim. `LOOK_ENCLOSURE_AMP` is the single live-feel knob: toward 1.0 = more
Earth-like pan (more rim shift); lower = tighter anchor; `0.0` = a pure anchored window.

**Best for:** a hero object presented *inside* a framed space, or a spatial-reference
scaffold — a jewel in a box, a grid room, a diorama with a sealed window frame. Draw the
enclosure in **world space** with its front rim on the glass (`z = 0`) — see how
`GridRoom.draw` / `Gem.draw_box` are called *before* the scene-anchor translate in
`app_engine.py`. (Note: this style does **not** envelop the viewer — leaning in zooms,
it does not move you bodily into the room. If you want true envelopment, that is a new
depth mechanism and a design conversation, not this flag.)

**Guarded by:** `sim_envelop.py` (enclosure zoom IS the object telephoto law; a `z = −10`
body is the same size under both paths and grows on lean-in; the rim is bezel-locked at
every head-z & eye offset; the look uses the frozen `proximity` gate; enclosure pan =
object pan × `LOOK_ENCLOSURE_AMP`, ≤ object pan, monotone + C¹; object path uncapped →
byte-identical).

---

## How to choose (decision guide)

| Question | → Method A (object/open) | → Method B (rim-anchored) |
|---|---|---|
| Does the world have a **front rim / frame** on the glass that should bezel-lock to the screen edges? | no | yes |
| Is the subject **one body** in empty/atmospheric space, or geometry **inside a framed box**? | one body, open | inside a framed box |
| Do you want **full near-field look** (push the body off-screen up close)? | yes (full amplitude) | no — the look is capped to protect the rim |
| Zoom & look-gate timing | telephoto + `proximity(hz, [0.0, 0.8])` | **identical** — same telephoto + same gate |
| `rendering.enveloping` | `false` (default) | `true` |
| Geometry drawn at | scene anchor `z = −10` (anchor translate) | world space, front rim on glass `z = 0` (before the anchor translate) |
| Calibrated guards | `sim_viewing`, `sim_vertical` | `sim_envelop` |

**Rule of thumb:** the camera feels the same either way (same zoom, same look
distances) — choose Method B **only** when the world draws a front rim/frame on the
glass that must stay bezel-locked, since that is the sole reason to cap the look. With
no such rim, use Method A and get the full-amplitude look. The two are mutually
exclusive per world.

## Authoring a new world with this in mind

1. Decide the style from the table above; set `rendering.enveloping` accordingly.
2. Method A: anchor the body at `z = −10`; copy [[earth]]/[[the-watcher]] flags.
3. Method B: draw the enclosure in world space with its rim on the glass (`z = 0`),
   like [[grid-room]]/[[gem]]; reuse `grid_depth` / `grid_divisions`. You inherit Earth's
   exact zoom and look gate for free; the engine just caps the pan (`LOOK_ENCLOSURE_AMP`)
   so the rim doesn't shear.
4. Do **not** add new camera/zoom logic. If a world genuinely needs a *different* depth
   behaviour (e.g. true envelopment — moving bodily into a space), that is a design
   conversation and a new sim guard, not a quiet edit to the frozen core. (The
   forward-dolly envelopment model was tried and removed — see [[known_issues]].)
5. Run the sims (at least `sim_envelop` for enclosure worlds; the object guards must
   stay byte-identical). See [[new-world]] / [[headless-simulation]].

## Related

[[off-axis-projection]] · [[world-system]] · [[worlds-index]] · [[constraints]] ·
[[earth]] · [[the-watcher]] · [[gem]] · [[grid-room]] · [[design-decisions]]
