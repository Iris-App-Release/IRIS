---
name: what-makes-perspective-optimal
title: What Makes Perspective Optimal
type: architecture
related: [off-axis-projection, earth, grid-room, the-gem, head-tracking, constraints]
last_updated: 2026-06-02
---

# What Makes Perspective Optimal

> [!success] Implemented 2026-06-02 — the grid + sphere merge shipped
> This page's central proposal is now **live in the engine**. The enclosure worlds
> ([[grid-room]], [[the-gem]]) adopt the Earth world's **early, wide, blended**
> rotational look (the "good part of the sphere worlds") while keeping their
> **bezel-locked screen anchor** (the "good part of the grid worlds"). The rim-shear
> barrier is resolved with the **amplitude-gated** path (option 4 / §"core insight"
> below): the look engages early but its *amplitude* is capped while the front rim is
> still on screen, ramping to full only once enveloped. Mechanism, exact constants,
> and the new invariants are in `Launcher/app_engine.py` (the `LOOK_*` block) and
> pinned by `Scripts/validation/sim_envelop.py`. See the bottom of this page for the
> shipped design and what still needs a live-feel pass. (log: 2026-06-02 "grid+sphere
> merge".)

## The Earth world is smooth because translation and rotation COEXIST

In [[earth]], the user experiences a **convergent band** where translation (parallax, eye distance) and rotation (view pan) are both active and blend smoothly together. This is the secret to the feel.

### How Earth achieves the blend

| Dimension | Earth (object world) | Enclosure (Grid Room / Gem) |
|---|---|---|
| **Eye distance model** | Telephoto: eye recedes as you lean in (`cz = BASE_Z·e^(+ZOOM_K·hz)`) | Forward dolly: camera moves into the room (`dolly = DOLLY_GAIN·hz`, `cz = constant`) |
| **Rotation gate** | `om.proximity(hz, lo=0.0, hi=0.8)` — opens early, ramps smoothly | **(merged 2026-06-02)** `engage(hz)·amp(hz)`: `engage = proximity(hz, [0.35, 1.0])` opens early + wide like Earth; `amp` caps amplitude to 0.22 while the rim is visible, ramping to 1.0 as it clears. *(Was `proximity(hz, [0.75, 1.0])` — held off until nearly enveloped.)* |
| **At neutral (hz = 0)** | Eye at BASE_Z, far from the object; rotation gate ≈ 0 (minimal) | Rim bezel-locked; `engage(0) = 0` → no rotation (anchor preserved) |
| **Leaning in (hz → +1)** | Eye recedes (cz grows), object zooms; rotation gate smoothly ramps 0 → 1 → both active **across a wide band** | Dolly increases; rotation engages early (from hz ≈ 0.35) blended with the dolly, but at *capped amplitude* until the rim clears (hz ≈ 0.72), then ramps to full — **active across a wide band, like Earth** |
| **The critical difference** | **Rotation becomes significant WHILE translation still dominates** → blended feel | **(now)** Same blended band, with the early portion amplitude-limited so the still-visible grid never shears → **blended feel + bezel anchor** |

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

This *used to* force the rotation gate to defer until dolly had carried the rim far past the near plane (the old `[0.75, 1.0]` gate — a hard separation, not a blend).

**Resolution (2026-06-02 merge).** Two facts let the gate open early without shear:
1. The bezel-locked rim leaves the *screen* the instant the dolly starts (it expands
   past the screen edges by hz ≈ 0.02 — verified numerically), long before the look
   engages at hz ≈ 0.35. So during its on-screen exit the look is still exactly zero;
   the rim never shears on its way out.
2. After that, the only still-visible geometry that *could* shear is the receding
   interior grid — and the **amplitude cap** (look limited to ~22 % until the rim
   clears the near plane at hz ≈ 0.72) keeps that pan gentle, so it reads as a slight
   parallax-like settle, not a warp. Full-strength look only arrives once enveloped.

**Result (now):** translation and rotation **coexist across a wide band** (hz ∈
[0.35, 1.0]) just like Earth — a smooth blend — while the resting rim stays exactly
bezel-locked. The sequential hand-off is gone.

---

## The optimal enclosure would look like Earth — ✅ now achieved (2026-06-02)

The merge delivers exactly this list. Opening rotation earlier *while keeping the rim
clean* now gives the user:

1. **The bezel-locked grid** — the resting framing at neutral (hz = 0) is pinned to the screen edges, aesthetically "sealed."
2. **Early rotation availability** — like Earth, rotation becomes significant while the user is still leaning in translationally.
3. **Smooth blended exploration** — translation and rotation coexist in a convergent band, neither a sharp hand-off.
4. **No grid shear** — the rim stays off-screen or is designed to read correctly while rotating.

### Barriers and possible paths forward

**The rim-shear barrier:**
- Rotating while the rim is visible *will* distort it — that's geometry, not a bug.
- Solutions:
  1. **Accept small shear as aesthetic:** The rim might read as "dynamic grid movement," not distortion, if it's fast and smooth enough. The user would live-test this.
  2. **Redesign the front boundary:** Instead of a hard edge at z = 0, fade or blur the rim so small distortions read as depth-of-field or parallax. Less "sealed," but avoids the shear read.
  3. **Hybrid gate:** Open rotation earlier but only at low amplitude — the pan is tiny until the rim is fully gone, so shear is imperceptible. This is closest to the current design's intent.
  4. **Lower the rotation gate threshold below the rim-clear point:** Accept that geometry will shear the rim slightly, live-test to see if it's tolerable, and recalibrate based on feel.

**The dolly timing barrier:**
- The faster you dolly in (higher `DOLLY_GAIN`), the sooner the rim clears — but also, the faster the foreground object grows. A slower dolly keeps the exploration phase longer but delays envelopment.
- Balancing `DOLLY_GAIN` against `ROT_GATE_LO` is the live-tuning knob. They move together: lower the gate (earlier rotation), raise the gain (rim clears sooner).

---

## The core insight: smooth proximity gates are magic

Earth feels optimal because its **proximity gate is continuous, wide, and opens early:**
- `om.proximity(hz, lo=0.0, hi=0.8)` — rotation available across a **0.8-unit band**, starting from the far field.
- The smoothstep is C¹ — zero slope at the endpoints, max slope of 1.5/(0.8) ≈ 1.875 at the midpoint. **Imperceptible blend.**
- Rotation is *always on* to some degree; it just scales with proximity.

Enclosures *used to* use a **shorter, later gate** (`om.proximity(hz, lo=0.75,
hi=1.0)` — rotation only across a 0.25-unit band, starting when nearly enveloped;
off for most of the approach, then on abruptly).

**The shipped merge (2026-06-02) gives enclosures Earth's gate** by splitting the
single weight into engagement × amplitude:
1. **Opens much earlier and wider** — `engage = proximity(hz, [0.35, 1.0])`, a
   0.65-unit band that mirrors Earth's [0.0, 0.8]. Rotation is available while the
   dolly (translation) still dominates → the blended feel.
2. **The rim constraint is satisfied by amplitude-gating, not deferral** — the early
   look runs at a capped ~22 % amplitude until the rim clears the near plane (hz ≈
   0.72), then ramps to full. The residual motion of the still-visible interior grid
   is therefore tiny → imperceptible shear (this is option 4 below, made concrete).
   `amp = 0.22 + 0.78·proximity(hz, [0.72, 0.92])`; the un-cap point is *derived* from
   `DOLLY_GAIN` so it always tracks the actual rim clear.

Both factors are smoothstep, so the product is monotone and C¹ — no felt mode switch.

---

## What shipped, and what still needs a live-feel pass

**Shipped (2026-06-02):** option 4 below — the **hybrid amplitude-gate** — was chosen
and implemented, because it gives the Earth-like early/wide blend *and* keeps the
bezel anchor with no rim redesign and no accepted shear. Constants landed at
`LOOK_ENGAGE_LO = 0.35`, `LOOK_PRELOOK_AMP = 0.22`, amplitude un-cap derived from
`DOLLY_GAIN` (≈ hz 0.72 → 0.92). All 10 headless sims pass; object worlds byte-identical.

The four options that were on the table (kept for the record):
1. ~~Open the gate at hz = 0.5/0.6 with a wider ramp and accept whatever shear results.~~
2. ~~Lower the gate + recalibrate `DOLLY_GAIN` so the rim still fully clears *first*.~~
   *(This was the prior model's invariant; the merge intentionally relaxes "rim
   fully clear before any look" in favour of amplitude-gating.)*
3. ~~Redesign the front rim (fade/blur/inner border) to hide shear.~~ — not needed.
4. **Hybrid amplitude-gate — only open rotation to ~20–30 % amplitude until the rim
   clears, then ramp to full.** ✅ **shipped.**

**Still needs a human in the room (live-feel calibration only — code knobs are ready):**
- Tune `LOOK_ENGAGE_LO` (how far out the look starts; lower = more Earth-like) and
  `LOOK_PRELOOK_AMP` (how much pre-envelopment look is allowed) against real feel.
- Confirm the capped early pan reads as a gentle parallax settle, not a warp, on the
  receding interior grid. If it's too lively, lower `LOOK_PRELOOK_AMP`; if too dead,
  raise it (or lower `LOOK_ENGAGE_LO`). The sim bounds the geometry; the *threshold*
  of perception is the human's call.

---

## Why this matters

The user's instinct was correct: **the smoothness of exploration is determined by how much of the proximity band is active translation vs. rotation.** Earth's [0.0, 0.8] overlap is what makes it feel like you're *moving around the object.* The enclosures' old delayed gate [0.75, 1.0] made them feel like *first you move in, then you look around* — two phases, not one motion.

The merge took the **third option — amplitude-gate early rotation so the shear is invisible** — so the enclosures now get the single integrated motion *and* keep their bezel anchor. The first two options (relax the rim constraint and accept shear; or keep the sequential hand-off) were rejected. The remaining work is pure live-feel calibration of the `LOOK_*` knobs — the geometry and invariants are settled and guarded by `sim_envelop.py`; the perception threshold needs a human in the room.
