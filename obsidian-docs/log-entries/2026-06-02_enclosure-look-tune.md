---
title: "2026-06-02 — Tune: Enclosure rotational look — engage earlier + much smoother ramp"
type: log-entry
date: 2026-06-02
category: tune
---

# Enclosure rotational look — engage earlier + much smoother ramp

**Trigger.** User, in the enclosure worlds ([[grid-room]] / [[the-gem]]): enable the
rotational "look" ~5–10 cm further from the screen than it engages now (begin around
the 15–20 cm proximity band), and **vastly smooth** the transition.

**What the knobs are.** The look is gated by `om.proximity(hz, lo=ROT_GATE_LO,
hi=ROT_GATE_HI)` — a smoothstep on the tracker's head-z (`hz`, face-size based;
**no documented cm mapping**, so the cm targets translate to an hz threshold tuned
live). The forward dolly carries the front rim off-screen at `dolly > BASE_Z − NEAR
≈ 11.2` (`dolly = DOLLY_GAIN·hz`). The standing design rule (and `sim_envelop.py`)
requires the **rim gone BEFORE the look engages**, else a pan shears a still-visible
grid edge — the exact "grid distorts" regression the user reported on 2026-06-02 and
the reason the gate had been raised to 0.88.

**Decision (user-chosen: "earlier + keep it clean").** Lower the gate AND raise the
dolly gain together so the rim still clears first — earlier look with **no** shear,
at the cost of dollying into the room a little faster (explicitly accepted).

**Change (consuming layer only — `camera_math.py` untouched; lo/hi/gain are
args/constants in `app_engine.py`).**
- `ROT_GATE_LO` **0.88 → 0.75** — look begins further from the screen.
- `ROT_GATE_HI` 1.0 (unchanged) → window **[0.75, 1.0]** vs old [0.88, 1.0]: ~2×
  wider, so the smoothstep ramp is ~2× gentler (the "vastly smoother" fade).
- `DOLLY_GAIN` **13.0 → 15.5** — rim now clears at `hz ≈ 0.72` (= 11.2/15.5),
  *before* the 0.75 gate, preserving "rim gone first."
- `DOLLY_MAX` **14.0 → 16.0** — keeps `dolly` rising past the old clamp so the
  foreground body still grows **monotonically all the way to hz = 1.0** (gem now
  ≈3.6× at full lean vs the prior ≈2.5×; honest consequence of the faster dolly).
- `DOLLY_MIN` 0.0 (unchanged) — the bezel-locked zoom-out floor is intact.

**Validation.** `sim_envelop.py` updated in sync (constants + the check-5 zero-look
assertion list, which had pinned `prox(0.8)==0` — now `prox(0.7)==0`, since 0.8 sits
inside the new engagement window). The rim-clears-before-look invariant re-verified:
rim eye_z = **+0.12** at the new gate hz = 0.75 (> −NEAR, off-screen). **All 10
headless sims pass**; `py_compile` clean. Live GL "feel" confirmation of the exact
cm landing point still needs a GUI session (standing renderer constraint) — the hz
threshold is the live-calibration knob.

**Files.** `Launcher/app_engine.py` (DOLLY_*, ROT_GATE_LO + comments),
`Scripts/validation/sim_envelop.py` (synced constants + assertion). Records:
[[grid-room]], [[the-gem]], and this entry.
