---
title: "2026-06-02 — Grids don't pan: enclosure rotational look set to zero (panning is sphere-only)"
type: log-entry
date: 2026-06-02
category: revert
---

# An anchored wall and a rotational pan are a direct contradiction — enclosure / grid worlds now have NO pan; clean panning is exclusive to the open sphere worlds

**Trigger (user, decisive).** "I wanted the gem to pan like the earth, but it simply
can't. The panning works so well on earth because of its lack of anchored walls — we're
trying to invent something that doesn't exist. Revert all complex changes to the grid
type of world, keep the smooth zoom feature and obviously the anchored grid and parallax.
But NO panning on the grid worlds… The spherical worlds (and more to come) are for
exploring the void; grids are for communicating the parallax illusion in the most direct
way. Keep the sphere worlds exactly the same, don't touch them."

**The contradiction, named.** Earth pans cleanly *because* it has no anchored walls. An
enclosure draws a front rim on the glass at world z = 0, which the off-axis projection
pins to the screen edges as a hard **bezel anchor** — and that anchor is the grid's whole
purpose: it communicates real cm² of digital space, a box behind the screen. A rotational
look pans the view about the eye, which rotates that still-visible rim and **shears** it.
You cannot both anchor the rim and rotate past it. Every attempt to "allow panning in the
grid while keeping the anchor" was inventing something geometrically impossible.

**What was reverted (all of it).**
- **The capped look** (`LOOK_ENCLOSURE_AMP = 0.35`) — a non-zero cap only made the shear
  *smaller*, never clean. Constant + its block deleted from `app_engine.py`.
- **The screen-space proscenium** (a same-session attempt: a camera-locked feathered edge
  to hide the shear so the cap could be raised) — added then reverted entirely
  (`renderer.draw_proscenium`, the `proscenium_feather` world property, the call site).
  Hiding the shear is the wrong direction when the shear shouldn't exist.
- **The dormant `behind_cells` wrap grid** in `GridRoom._rebuild` (a shelved
  behind-the-glass grid meant to mask pan shear) — dead code removed.

**What shipped — the simple, honest model.** For `world.enveloping` worlds the rotational
look is held at **zero**:

```python
if world.enveloping:
    yaw_target = 0.0
    pitch_tgt  = 0.0
```

Enclosures keep everything that *is* real: the smooth telephoto **zoom**
(`cz = BASE_Z·e^(+ZOOM_K·hz)`, identical to Earth — gem stays Earth-sized), the **parallax**
window shift (`cam_x`/`cam_y` off-axis), and the **bezel-anchored rim**. They simply do not
rotate. Panning is now exclusive to the SPHERE worlds (Earth, The Watcher, future void
worlds), which have no walls to shear.

**Sphere worlds: byte-identical.** They never set `enveloping`, so the zeroing branch is
skipped and the full proximity-gated look is unchanged. `camera_math.py` and all shaders
untouched. The user's constraint ("don't touch them") is satisfied.

**Validation.** `sim_envelop.py` rewritten to pin the NEW invariant: (1) enclosure zoom IS
the object telephoto law; (2) a z = −10 body is Earth-sized and grows on lean-in
(205→413 px); (3) the bezel rim maps to the screen edges to 4.6e-13 px at every head-z &
off-centre eye; (4) **the enclosure look is identically zero — a full head turn produces 0
px of pan at every head-z**; (5) the sphere worlds still pan (0 → 1358 px), proving only
enclosures were zeroed. **All 10 headless sims pass** (`sim_viewing` / `sim_vertical`
confirm the sphere worlds byte-identical); modules import clean.

**Files.** `Launcher/app_engine.py` (deleted `LOOK_ENCLOSURE_AMP` + comment block; the
enclosure branch now zeroes the look), `Engine/renderer.py` (removed `draw_proscenium` and
the dormant `behind_cells` wrap), `Worlds/world_runtime.py` (removed `proscenium_feather`;
`enveloping` docstring rewritten to "no pan"), `Scripts/validation/sim_envelop.py`
(rewritten to pin zero enclosure pan). World JSONs unchanged.

**Wiki updated.** [[what-makes-perspective-optimal]] (superseded note), [[the-gem]],
[[grid-room]], and this log entry.
