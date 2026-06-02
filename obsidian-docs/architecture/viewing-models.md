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

# Viewing Models — the two illusion methods

IRIS has **two distinct, fully-supported ways** of turning head-depth into an
on-screen depth response. Both ride the *same* frozen off-axis "window" core
([[off-axis-projection]]) and the same lateral parallax; they differ only in how
**leaning in / out** (head depth `hz`) is interpreted. Picking the right one is the
single most important authoring decision for a new world — it is what makes a world
feel like *an object you look at* versus *a space you move into*.

This page is the canonical reference for that choice. The switch is one declarative
flag, `rendering.enveloping` (default `false`), read by [[world-system]]
(`WorldRuntime.enveloping`) and branched on in `Launcher/app_engine.py`. **No camera
math changes between the two models** — `Engine/camera_math.py` stays frozen; the
difference lives entirely in the consuming layer (eye-distance scaling vs. a
modelview dolly, and the look-gate window).

---

## Why there must be two (the geometry)

The monitor is a **fixed rectangle** at world `z = 0` (the glass); the scene lives
behind it; the eye is the tracked head at `z = +cam_z`. Under this fixed-window
off-axis projection a foreground object at `z = −10` has on-screen size proportional
to `cam_z / (cam_z + 10)`. That single fact forces the split:

- Moving the eye **toward** the glass (smaller `cam_z`) *widens* the frustum — you
  see more of the surrounding scene (envelopment) — but it **shrinks** a foreground
  object. This is geometrically what a real window does.
- Moving the eye **away** from the glass (larger `cam_z`) *narrows* the frustum and
  **magnifies** a foreground object (telephoto), but kills envelopment.

So "the hero object grows as I approach" and "the space wraps around me as I
approach" **cannot both come from the `cam_z` term** — they pull it in opposite
directions. The two viewing models resolve this by getting depth from two different
mechanisms. A global one-size flip was explored and rejected (it inverts the
calibrated Earth zoom and guts near-field vertical exploration — see
[[known_issues]]), which is why the model is **per-world, not global**.

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

## Method B — Enclosure / Forward-dolly

> **Mental model:** the monitor is the open face of a box you lean *into*. Leaning in
> moves you forward through the opening; objects inside grow with honest perspective;
> the walls slide past until they surround you; only once you are inside do you turn
> your head to look around.

**Worlds:** [[grid-room]], [[gem]]. **Flag:** `enveloping: true`.

**Depth response — a forward dolly, not a lens zoom.** Eye-to-glass distance is
**held at `BASE_Z`** so the FOV is the calibrated **58° at every distance** (no zoom
trick). Depth instead comes from translating the whole scene toward the eye by
`dolly` world units along −z, baked into the modelview
(`mv = view_matrix(...) @ T(0, 0, dolly)`):
`dolly = clamp(DOLLY_GAIN·hz, [DOLLY_MIN, DOLLY_MAX])` with `DOLLY_GAIN = 13`,
`DOLLY_MAX = 14`, **`DOLLY_MIN = 0`**.
- Lean **in** → `dolly` grows → eye-to-object distance shrinks → the hero object
  **grows** with honest perspective (≈2.5× at full lean); the front rim expands past
  the screen edges and finally clears the near plane → the viewer is **enveloped**
  (rim out of sight, inside the space).
- Lean **out** → `dolly` clamps at **0**: the neutral, **bezel-locked** framing is a
  **hard zoom-out floor**. You can dolly in from there and back out *to* it, never
  past it — leaning back never pulls the camera behind the bezel-locked grid. (A
  deliberate UX limit, not a geometry constraint.)

**Rotational look — merged toward the Earth feel (2026-06-02).** The look now engages
**early and wide**, like the object world's `proximity(hz, [0.0, 0.8])` band, so
rotation blends with the dolly across the whole approach instead of waiting for full
envelopment (the old "first move in, then look around" sequential gate). The single
weight is split into two smoothstep factors, `prox = engage(hz)·amp(hz)`:
- `engage = proximity(hz, [LOOK_ENGAGE_LO, LOOK_ENGAGE_HI] = [0.35, 1.0])` — opens
  early/wide (zero at neutral, so the resting rim stays bezel-locked).
- `amp = LOOK_PRELOOK_AMP + (1−LOOK_PRELOOK_AMP)·proximity(hz, [LOOK_AMP_LO, LOOK_AMP_HI])`
  — caps the look amplitude to ~22 % while the front rim is still on screen, then
  ramps to full as the rim clears the near plane. `LOOK_AMP_LO` is *derived* from
  `DOLLY_GAIN` (the rim-clear head-z, ≈ 0.72), so cap-release always tracks the rim.

The bezel-locked rim leaves the *screen* the instant the dolly starts (hz ≈ 0.02),
well before the look engages (hz ≈ 0.35) — so the rim never shears on its way out —
and the amplitude cap keeps the only other still-visible geometry (the receding
interior grid) from swinging during partial envelopment. Full-strength look arrives
only once enveloped. Product of two smoothsteps ⇒ monotone + C¹, no felt mode switch.
This is the "take the good parts of both" merge: the sphere worlds' blended
eye-looking + the grid worlds' screen anchor. (what-makes-perspective-optimal.md)

**Best for:** an environment that surrounds the viewer, or a hero object presented
*inside* a space — a room, a corridor, a diorama, a jewel in a box. Draw the
enclosure in **world space** with its front rim on the glass (`z = 0`) — see how
`GridRoom.draw` / `Gem.draw_box` are called *before* the scene-anchor translate in
`app_engine.py`. The shared modelview dolly then carries the whole enclosure forward
as one rigid space.

**Guarded by:** `sim_envelop.py` (constant FOV; monotone forward dolly; foreground
body GROWS on lean-in; lean-out clamps at the bezel-locked floor; rim past the near
plane when enveloped and bezel-locked at neutral; the merged look — early/wide
engage, amplitude capped until the rim clears, full once enveloped, monotone + C¹;
object path untouched).

---

## How to choose (decision guide)

| Question | → Method A (object) | → Method B (enclosure) |
|---|---|---|
| Is the subject **one body** with empty surroundings, or a **space**? | one body | a space (or a body *inside* a space) |
| On lean-in, should the subject **magnify in place** or should you **move into** the scene? | magnify | move in |
| Do you want **near-field vertical exploration** (push the body off-screen)? | yes | no |
| Is there a **front rim / aperture** that should bezel-lock at rest? | no | yes |
| `rendering.enveloping` | `false` (default) | `true` |
| Geometry drawn at | scene anchor `z = −10` (anchor translate) | world space, front rim on glass `z = 0` (before the anchor translate) |
| Calibrated guards | `sim_viewing`, `sim_vertical` | `sim_envelop` |

**Rule of thumb:** start with Method A (it is the default and the lower-risk path).
Reach for Method B only when the experience is *being somewhere* rather than *looking
at something*. The two are mutually exclusive per world — a world is one or the other.

## Authoring a new world with this in mind

1. Decide the model from the table above; set `rendering.enveloping` accordingly.
2. Method A: anchor the body at `z = −10`; copy [[earth]]/[[the-watcher]] flags.
3. Method B: draw the enclosure in world space with its rim on the glass (`z = 0`),
   like [[grid-room]]/[[gem]]; reuse `grid_depth` / `grid_divisions`; expect the
   forward dolly + envelopment look for free (they are world-agnostic in the engine).
4. Do **not** add new camera/zoom logic — both models already exist behind the one
   flag. If a world seems to need a *third* depth behaviour, that is a design
   conversation (and a new sim guard), not a quiet edit to the frozen core.
5. Run the sims (at least `sim_envelop` for enclosure worlds; the object guards must
   stay byte-identical). See [[new-world]] / [[headless-simulation]].

## Related

[[off-axis-projection]] · [[world-system]] · [[worlds-index]] · [[constraints]] ·
[[earth]] · [[the-watcher]] · [[gem]] · [[grid-room]] · [[design-decisions]]
