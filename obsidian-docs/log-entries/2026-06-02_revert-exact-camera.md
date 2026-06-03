---
title: "2026-06-02 — Revert+Resimplify: Enclosures use Earth's EXACT camera with capped look"
type: log-entry
date: 2026-06-02
category: revert
---

# Enclosures drop the forward dolly + merged look — grid worlds now use Earth's EXACT camera physics (telephoto zoom + frozen proximity gate), with only a capped look to anchor the rim

**Trigger (user, emphatic).** "THE GRID WORLDS zooming and looking camera should
operate EXACTLY the same as the spherical worlds. The rotational exploration should
transition smoothly at the same exact distances. The gem should initially and finally
appear the same exact size as the earth would from the same distance… However, on the
grid worlds, anchor the grid to the bezel… just make sure I'm fully 'in the room'
before I'm able to look… if it's an issue, just limit the amount of distance I can
look/pan in the grids." Also: do **not** touch the Earth or Watcher worlds.

**What this overturns.** The whole 2026-06-02 enclosure line of work made the grid
worlds *diverge* from the sphere worlds: a **forward dolly** depth model (held `cz` at
`BASE_Z` and translated the scene toward the eye) plus a **merged engage·amp look**
gate. The dolly grew a foreground gem ~3.6× on lean-in, so its size no longer tracked
Earth's. The user rejected that entirely — they want the grid worlds to *be* the sphere
worlds, camera-wise, differing only in that the bezel rim stays anchored.

**Fix — the consuming layer collapses back onto the object path; one capped knob is the
only difference (this is the "option 3 / hybrid gate" from
[[what-makes-perspective-optimal]]).**
- **Zoom.** Removed the per-world depth branch + the `DOLLY_*` constants + the modelview
  dolly translate. EVERY world (object and enclosure) now uses the telephoto
  `cz = BASE_Z·e^(+ZOOM_K·hz)`. A body at the Earth anchor (z = −10) therefore subtends
  the **same on-screen size Earth would** at any head-z — initially and at full lean-in.
- **Look-gate timing.** Removed the `engage·amp` split + the `LOOK_ENGAGE/PRELOOK/AMP`
  constants. EVERY world now uses the frozen `om.proximity(hz)` ([0.0, 0.8]) gate, so the
  enclosure look fades in over the **same head-z distances** as Earth, just as smoothly.
- **The one difference — capped look amplitude.** Enclosure worlds draw a front rim on
  the glass at world z = 0, which the off-axis projection pins to the screen edges at
  ANY eye/zoom — a hard bezel anchor. A pan rotates that still-visible rim and would
  shear it. So for `world.enveloping` worlds the look pan is scaled by a single constant
  `LOOK_ENCLOSURE_AMP = 0.35` (the user's "just limit the distance I can look/pan").
  Because the look is *also* proximity-gated, the product is ≈ 0 at rest (rim rock-solid)
  and grows to a small bounded max only as you lean in / get "in the room."

**Earth / The Watcher: byte-identical.** They never set `enveloping`, are never capped,
and the object zoom + gate code is unchanged (only the enclosure branches were deleted).
Confirmed: their `world.json` files were untouched (the user's explicit constraint).
`camera_math.py` untouched — the gate is the frozen `om.proximity`; the cap is a plain
post-multiply in `app_engine.py`.

**Validation.** Rewrote `Scripts/validation/sim_envelop.py` to pin the NEW invariants:
(1) enclosure zoom IS the object telephoto law (no per-world divergence, no dolly);
(2) a z = −10 body is the same on-screen size under both paths and GROWS on lean-in
(205→413 px); (3) the bezel rim maps to the screen edges to machine precision
(4.6e-13 px) at **every** head-z & off-centre eye — the anchor holds the whole approach;
(4) the look uses the frozen `om.proximity` ([0.0, 0.8]) gate; (5) the enclosure pan =
object pan × 0.35 at every head-z (≤ object pan, ≈ 0 at neutral, monotone, C¹);
(6) object worlds uncapped, identical at neutral. **All 10 headless sims pass**
(`sim_viewing` / `sim_vertical` confirm Earth byte-identical); `py_compile` clean. The
exact cap value is the live-feel knob — raise toward 1.0 for a more Earth-like pan (more
rim shear), lower for a tighter anchor.

**Files.** `Launcher/app_engine.py` (deleted the `DOLLY_*` + `LOOK_ENGAGE/PRELOOK/AMP`
blocks and the per-world depth/dolly branches; added the single `LOOK_ENCLOSURE_AMP`
cap), `Worlds/world_runtime.py` (`enveloping` docstring rewritten — now means "rim-
anchored enclosure: cap the look," not "forward dolly"), `Scripts/validation/sim_envelop.py`
(rewritten). World JSONs unchanged (`enveloping: true` retained, semantics changed).

**Wiki updated.** [[what-makes-perspective-optimal]], [[viewing-models]] (Method B),
[[off-axis-projection]], [[constraints]], [[grid-room]], [[the-gem]], [[worlds-index]],
[[current-focus]], [[known_issues]], `index.md`, and this log entry.
