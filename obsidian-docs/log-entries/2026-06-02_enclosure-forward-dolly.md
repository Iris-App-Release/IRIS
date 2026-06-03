---
title: "2026-06-02 — Change: Enclosure depth model → forward dolly"
type: log-entry
date: 2026-06-02
category: change
---

# Enclosure depth model → forward dolly (replaces the same-day frustum-widen)

**Trigger.** With the enclosure model from the entry above shipped, leaning IN to
the Grid Room / Gem made the grid squares *expand and stretch* (perceived depth
~doubled) and the floating gem *shrink* — the opposite of the wanted "move in =
zoom in." The ~15 cm rotational look also sheared/distorted the still-visible grid
instead of cleanly rotating once enveloped.

**Why the previous model did that (not a bug — geometry).** The earlier fix used
`cz = BASE_Z·e^(−ZOOM_K·hz)`, so leaning in shortened `cz` and WIDENED the off-axis
frustum. That is the geometrically-correct *fixed-window* result, but a foreground
object at `z = −10` has on-screen size ∝ `cz/(cz+10)`, so a smaller `cz` shrinks it
and stretches the receding grid. Window-correct, wrong feel.

**Fix — forward dolly (per-world mechanism, user-chosen).** For `enveloping = true`
worlds the engine now HOLDS `cz = BASE_Z` (FOV constant at 58° — no lens zoom) and
translates the whole scene toward the eye by `dolly = clamp(DOLLY_GAIN·hz,
[DOLLY_MIN, DOLLY_MAX])` world units along −z, baked into the modelview
(`mv = view_matrix(...) @ T(0,0,dolly)`). Leaning in dollies the camera INTO the
room: the gem grows with honest perspective (≈2.5× at full lean), the walls slide
past, and the front rim expands off-screen until it clears the near plane
(enveloped). Look-gate tightened to `om.proximity(hz, lo=ROT_GATE_LO=0.88,
hi=ROT_GATE_HI=1.0)`, tuned so the rim is already off-screen before any pan engages
— so the look can never shear a visible grid edge. Object worlds set `dolly ≡ 0`
and keep telephoto `cz` → byte-identical (`max |Δcz| = 0`). `DOLLY_GAIN = 13`,
`DOLLY_MAX = 14`, `DOLLY_MIN = 0` (a hard zoom-out floor — leaning back past the
neutral, bezel-locked framing does NOT pull the camera further out; you dolly in
from there and back out only to it). **camera_math.py untouched** (dolly is a
modelview translate; gate lo/hi are call args).

**Validation.** Rewrote `Scripts/validation/sim_envelop.py` to pin the dolly
invariants: constant FOV; monotone forward dolly; foreground gem GROWS on lean-in
(208→747 px, 2.53× neutral→enveloped); rim past the near plane when enveloped and
bezel-locked exactly at neutral; look zero through the approach with the rim already
off-screen the moment it engages; C¹ gate; object path untouched. **All 10 headless
sims pass** (`sim_viewing` / `sim_vertical` / `sim_offaxis` / `sim_orbit`
unchanged). Live GL "feel" tuning of `DOLLY_GAIN` / `ROT_GATE_LO` still needs a GUI
session (standing renderer constraint).

**Files.** `Launcher/app_engine.py` (DOLLY_* constants, per-world depth-response
block, modelview dolly, raised ROT_GATE_LO), `Worlds/world_runtime.py`
(`enveloping` docstring), `Scripts/validation/sim_envelop.py` (rewritten). World
JSONs unchanged. Records: [[known_issues]], [[current-focus]], [[constraints]],
[[off-axis-projection]], [[grid-room]], [[the-gem]].
