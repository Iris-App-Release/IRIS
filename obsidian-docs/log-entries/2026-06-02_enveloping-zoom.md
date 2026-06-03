---
title: "2026-06-02 — Fix: Per-world enveloping zoom + late look-gate for enclosure worlds"
type: log-entry
date: 2026-06-02
category: fix
---

# Per-world enveloping zoom + late look-gate for enclosure worlds

**Symptom (user, in the Grid Room).** Moving CLOSER made the grid *shrink* —
reading as "zooming out" — instead of enveloping the viewer, and the rotational
"look" was active at ordinary forearm distance, letting the viewer rotate the
z = 0 window plane and **peer past the bezel-locked front rim**. The desired
behaviour: all motion translational and rim-locked during approach, with
rotational look engaging only once *enveloped* (~10–15 cm from the camera).

**Root cause (two consuming-layer issues, NOT frozen camera_math).**
1. *Zoom direction.* `Launcher/app_engine.py` mapped `cz = BASE_Z·e^(+ZOOM_K·hz)`
   for every world, so leaning IN *increased* cz → narrower telephoto frustum.
   That is the calibrated, deliberate feel for a single FOREGROUND object (the
   Earth grows on approach — pinned by `sim_viewing`/`sim_vertical`), but it is
   backwards for an ENVIRONMENT you enter: a real shadow-box envelops you as the
   eye nears the glass (smaller cz → wider frustum). The window-correct sense is
   the one [[off-axis-projection]] already documents.
2. *Rotation gate.* `om.proximity(hz)` used the frozen default window `[0.0, 0.8]`,
   so rotation began the instant the viewer leaned past neutral — un-pinning the
   rim at forearm distance.

**Why per-world, not global.** A global zoom flip would (a) invert the Earth's
deliberately-calibrated telephoto zoom and (b) break `sim_viewing` checks 1–2 and
gut `sim_vertical`'s near-field "push the planet off-screen" exploration (a wide
close-range frustum can't pan a foreground object past half-FOV under the 46°
anti-nausea clamp). Both were explored and rejected with the user; the chosen
scope is **enclosure worlds only**.

**Fix.** A declarative `rendering.enveloping` flag (default **False** → object
worlds byte-identical). New `WorldRuntime.enveloping` property; set `true` in
`Worlds/grid_room/world.json` and `Worlds/gem/world.json`. In `app_engine.py`:
- `zoom_sign = -1.0 if world.enveloping else 1.0` → enclosure `cz = BASE_Z·e^(−ZOOM_K·hz)`
  (lean IN → cz 11.5→5.0, FOV 58°→104°, envelopment); object path unchanged.
- enclosure rotation uses `om.proximity(hz, lo=ROT_GATE_LO=0.7, hi=ROT_GATE_HI=1.0)`
  (zero look until enveloped, smooth ramp to full at hz=1.0); object path keeps the
  frozen default gate. **camera_math.py untouched** (lo/hi passed as args).

**Validation.** New guard `Scripts/validation/sim_envelop.py` (window-correct zoom
monotone, rim bezel-locked at every approaching eye, look gated to envelopment +
C¹, per-world sign genuinely flips). **All 10 headless sims pass**; `sim_viewing`
and `sim_vertical` are **byte-identical to before** (object path preserved), so the
Earth/Watcher feel + their guards are intact. Live GL confirmation in the Grid Room
still needs a GUI session (standing renderer constraint).

**Files.** `Launcher/app_engine.py`, `Worlds/world_runtime.py`,
`Worlds/grid_room/world.json`, `Worlds/gem/world.json`,
`Scripts/validation/sim_envelop.py` (new). Records: [[known_issues]],
[[current-focus]], [[constraints]], [[off-axis-projection]], [[grid-room]].
