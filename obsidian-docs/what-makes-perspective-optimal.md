---
name: what-makes-perspective-optimal
title: What Makes Perspective Optimal
type: architecture
related: [off-axis-projection, earth, grid-room, the-gem, head-tracking, constraints]
last_updated: 2026-06-02
---

# What Makes Perspective Optimal

> [!success] Implemented 2026-06-02 (final form) — enclosures use Earth's EXACT camera, with a capped look
> This page's central question — *how do enclosures get the sphere worlds' feel without
> shearing their anchored rim* — is resolved in the engine by **option 3** (the hybrid
> gate, §"Barriers" below). The path went through two intermediate designs (a
> frustum-widen, then a **forward dolly + merged engage·amp look**) that both made the
> grid worlds *diverge* from Earth; the user rejected them and asked for the grid worlds
> to behave **exactly** like the sphere worlds, anchored. Final shipped form:
> the enclosure worlds ([[grid-room]], [[the-gem]]) use the **identical telephoto zoom
> and the identical frozen proximity look-gate ([0.0, 0.8])** as [[earth]] — so they
> zoom the same, the look fades in over the same head-z distances, and a body at the
> Earth anchor subtends the same on-screen size Earth would. The **only** difference is
> a single constant, `LOOK_ENCLOSURE_AMP = 0.35`, that caps the look *amplitude* so the
> bezel-locked rim never shears ("just limit the distance I can look/pan in the grids").
> Mechanism in `Launcher/app_engine.py` (the `LOOK_ENCLOSURE_AMP` block); pinned by
> `Scripts/validation/sim_envelop.py`. (log: 2026-06-02 "revert+resimplify".)

## The Earth world is smooth because translation and rotation COEXIST

In [[earth]], the user experiences a **convergent band** where translation (parallax, eye distance) and rotation (view pan) are both active and blend smoothly together. This is the secret to the feel.

### How Earth achieves the blend

| Dimension | Earth (object world) | Enclosure (Grid Room / Gem) |
|---|---|---|
| **Eye distance model** | Telephoto: eye recedes as you lean in (`cz = BASE_Z·e^(+ZOOM_K·hz)`) | **Identical** — same telephoto `cz = BASE_Z·e^(+ZOOM_K·hz)`. *(Was a forward dolly; removed 2026-06-02 because it grew the gem ~3.6× and diverged from Earth's size.)* |
| **Rotation gate** | `om.proximity(hz, lo=0.0, hi=0.8)` — opens early, ramps smoothly | **Identical** — the same frozen `om.proximity(hz, [0.0, 0.8])` gate, so the look fades in over the same head-z distances. *(Was `engage·amp`; collapsed back to Earth's gate.)* |
| **At neutral (hz = 0)** | Eye at BASE_Z, far from the object; rotation gate ≈ 0 (minimal) | Rim bezel-locked; gate ≈ 0 → look ≈ 0 (anchor preserved exactly) |
| **Leaning in (hz → +1)** | Eye recedes (cz grows), object zooms; rotation gate smoothly ramps 0 → 1 → both active **across a wide band** | Same telephoto zoom + same gate ramp, so the look grows over the same band — but the look pan is multiplied by `LOOK_ENCLOSURE_AMP = 0.35` so it stays small enough that the bezel rim doesn't shear |
| **The only difference** | Full-amplitude pan (`prox · ROT_MAX`) | Capped pan (`prox · ROT_MAX · 0.35`) → bezel anchor holds while exploring |

The Earth user can:
1. **Lean in far away** (hz ≈ 0.3) and rotate gently — the translation (zoom) is still strong, rotation is light but present.
2. **Lean in closer** (hz ≈ 0.5) and rotate more — both are active, neither dominates.
3. **Lean in very close** (hz ≈ 0.8+) and rotate heavily — rotation now dominates, but translation hasn't stopped.

This **smooth coexistence** across hz ∈ [0.3, 0.8] is what makes Earth feel "optimal." It's a convergent fan of movement modes, not a sequential handoff.

### Why enclosures are different: the rim shear constraint

In enclosure worlds, rotation cannot engage until **the front rim (world z = 0) has cleared the near plane**. Why?

- When you rotate your head right in an enclosure, the window pans right, **revealing the scene's right side**.
- If the front rim is still on-screen (visible), panning **shears the rim** — it distorts as it rotates, reading as visual glitch, not intentional.
- Once the rim is off-screen (enveloped), rotation is clean: you're looking *around* inside the box, not distorting the visible boundary.

**Resolution (2026-06-02, final).** With the telephoto zoom restored (the dolly gone),
the rim never leaves the screen — it stays bezel-locked at z = 0 at *every* distance.
So the rim cannot be "cleared" before looking; instead the look **amplitude is capped**
(`LOOK_ENCLOSURE_AMP = 0.35`) so that any pan is small enough that the rim's on-screen
shift reads as a subtle parallax-like settle rather than a warp. Combined with the
(unchanged) proximity gate, the pan is ≈ 0 at rest — the rim is rock-solid anchored —
and grows to a small bounded max as you lean in.

**Result (now):** translation (zoom) and rotation (a gentle, capped look) **coexist
across the same wide band** (hz ∈ [0.0, 0.8]) and over the same distances as Earth,
while the resting rim stays exactly bezel-locked. The sequential hand-off — and the
gem-ballooning forward dolly — are both gone.

---

## The optimal enclosure would look like Earth — ✅ now achieved (2026-06-02)

The final design delivers exactly this list — by simply *being* Earth's camera, with a
capped look:

1. **The bezel-locked grid** — the resting framing at neutral (hz = 0) is pinned to the screen edges, aesthetically "sealed." The rim stays pinned at *every* distance now (telephoto keeps z = 0 on the screen edges; nothing carries it off).
2. **Same zoom, same size as Earth** — the gem subtends the on-screen size Earth would, initially and at full lean-in (shared telephoto `cz`).
3. **Same look timing** — rotation fades in over Earth's exact [0.0, 0.8] band, at the same distances, just as smoothly.
4. **No grid shear** — the look amplitude is capped (`LOOK_ENCLOSURE_AMP`) so the still-visible rim's on-screen shift stays a gentle settle, not a warp.

### Barriers and possible paths forward (the chosen path: option 3)

**The rim-shear barrier** — rotating while the rim is visible *will* distort it; that's
geometry, not a bug. Once the dolly was removed (so the rim is always on-screen at the
bezel), the only viable resolution that keeps the rim anchored is to bound the pan:

  1. **Accept small shear as aesthetic** — read the rim shift as "dynamic grid movement." Not chosen.
  2. **Redesign the front boundary** (fade/blur the z = 0 edge). Not needed.
  3. **Hybrid gate: open rotation early but only at low amplitude** — the pan is small so shear is imperceptible. ✅ **This is the shipped path** (a constant amplitude cap, since with the telephoto restored the rim is never "fully gone" to un-cap against — it's always at the bezel). This was the user's explicit pick: *"just limit the amount of distance I can look/pan in the grids."*
  4. **Lower the gate below a rim-clear point and accept slight shear.** Not chosen.

*(The earlier "dolly timing barrier" — balancing `DOLLY_GAIN` against the gate so the
rim cleared before looking — is moot: there is no dolly any more. The only live knob is
`LOOK_ENCLOSURE_AMP`.)*

---

## The core insight: smooth proximity gates are magic

Earth feels optimal because its **proximity gate is continuous, wide, and opens early:**
- `om.proximity(hz, lo=0.0, hi=0.8)` — rotation available across a **0.8-unit band**, starting from the far field.
- The smoothstep is C¹ — zero slope at the endpoints, max slope of 1.5/(0.8) ≈ 1.875 at the midpoint. **Imperceptible blend.**
- Rotation is *always on* to some degree; it just scales with proximity.

Enclosures went through two rejected gates — a late sequential one
(`om.proximity(hz, [0.75, 1.0])`) and then a merged `engage·amp` split — before
landing on the simplest answer.

**The shipped form (2026-06-02) gives enclosures Earth's gate by literally using it:**
`prox = om.proximity(hz)` — the same `[0.0, 0.8]` band, the same C¹ smoothstep, opening
early from the far field. The pan target is then multiplied by a single constant,
`LOOK_ENCLOSURE_AMP = 0.35`, before smoothing:

```
prox        = om.proximity(hz)              # identical to Earth
yaw_target  = yaw   * ROT_MAX_RAD       * prox
pitch_tgt   = pitch * ROT_MAX_PITCH_RAD * prox
if world.enveloping:                        # enclosure → cap the pan
    yaw_target *= LOOK_ENCLOSURE_AMP
    pitch_tgt  *= LOOK_ENCLOSURE_AMP
```

`prox · cap` is a smoothstep × constant → monotone, C¹, zero at the far field. So the
rim is rock-solid at rest and gains only a small, bounded pan as the viewer leans in.

---

## What shipped, and what still needs a live-feel pass

**Shipped (2026-06-02, final):** option 3 — the **hybrid gate (early rotation, capped
amplitude)** — but in its simplest possible form: the enclosure worlds reuse Earth's
exact telephoto zoom and Earth's exact `om.proximity(hz)` gate, and apply a single
constant pan cap `LOOK_ENCLOSURE_AMP = 0.35`. This was chosen over the earlier forward-
dolly + `engage·amp` merge because the user wanted the grid worlds to be *identical* to
the sphere worlds (same zoom, same look distances, gem the same size as Earth), anchored
— not a separate "enter the room" mechanism. All 10 headless sims pass; object worlds
byte-identical.

**Still needs a human in the room (live-feel calibration — one knob):**
- Tune `LOOK_ENCLOSURE_AMP` against real feel: raise toward 1.0 for a more Earth-like
  full pan (more rim shift near full lean-in); lower for a tighter anchor; `0.0` is a
  pure anchored window with no look. The sim bounds the geometry; the *threshold* of
  perception is the human's call.

---

## Why this matters

The user's instinct was correct: **the smoothness of exploration is determined by how much of the proximity band is active translation vs. rotation.** Earth's [0.0, 0.8] overlap is what makes it feel like you're *moving around the object.* The enclosures' old delayed gate [0.75, 1.0] made them feel like *first you move in, then you look around* — two phases, not one motion.

The final design takes the **third option — early rotation at capped amplitude so the shear is imperceptible** — but reaches it the simplest way: the enclosures just *are* the Earth camera (same zoom, same gate, same distances, gem the same size), with one constant capping the pan so the bezel anchor survives. The forward-dolly "enter the room" depth model was tried and rejected because it made the gem balloon and diverge from Earth's size. The remaining work is pure live-feel calibration of the single `LOOK_ENCLOSURE_AMP` knob — the geometry and invariants are settled and guarded by `sim_envelop.py`; the perception threshold needs a human in the room.
