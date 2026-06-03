---
title: "2026-06-02 — Merge: Grid + sphere merge — enclosures gain Earth's blended look"
type: log-entry
date: 2026-06-02
category: merge
---

# Grid + sphere merge — enclosures gain Earth's blended look while keeping their bezel anchor

**Trigger.** User decision: "take the good parts of the grid worlds and the good
parts of the sphere worlds and merge them." The [[earth]] (sphere/object) world has
the better **zooming + eye-looking** — rotation and translation coexist across a wide
proximity band, so it feels like *moving around* the scene. The enclosure worlds
([[grid-room]], [[the-gem]]) have the better **screen anchor** — the bezel-locked
front rim. The standing analysis page [[what-makes-perspective-optimal]] had already
diagnosed why and proposed the path; this entry **executes the proposed update**.

**What was wrong.** Enclosures deferred ALL rotational look until the viewer was
nearly enveloped (`om.proximity(hz, [0.75, 1.0])`), giving a SEQUENTIAL "first move
in, THEN look around" feel — the opposite of Earth's blended band [0.0, 0.8]. We
couldn't simply open the gate early, because rotating while the front rim is still on
screen shears the visible grid (the prior "grid distorts" regression).

**Fix — amplitude-gated early look (the option-4 path from the analysis page;
consuming layer only).** The single enclosure look weight is split into two
smoothstep factors, `prox = engage(hz)·amp(hz)`:
- `engage = om.proximity(hz, lo=LOOK_ENGAGE_LO=0.35, hi=LOOK_ENGAGE_HI=1.0)` — opens
  EARLY and WIDE, mirroring Earth's band, so the look blends with the forward dolly
  across the whole approach. `engage(0)=0`, so the resting rim stays bezel-locked.
- `amp = LOOK_PRELOOK_AMP + (1−LOOK_PRELOOK_AMP)·om.proximity(hz, [LOOK_AMP_LO,
  LOOK_AMP_HI])` — caps the look AMPLITUDE to `LOOK_PRELOOK_AMP = 0.22` while the
  front rim is still on screen, then ramps to full as the rim clears the near plane.
  `LOOK_AMP_LO = (BASE_Z − NEAR)/DOLLY_GAIN ≈ 0.72` is **derived** from `DOLLY_GAIN`,
  so cap-release always tracks the actual rim clear (they stay coupled if either is
  retuned); `LOOK_AMP_HI ≈ 0.92`.

**Why it's shear-free (verified numerically).** The bezel-locked rim leaves the
*screen* the instant the dolly starts — its corners are off-screen by hz ≈ 0.02, the
whole frame gone shortly after — i.e. long before the look engages at hz ≈ 0.35. So
during its on-screen exit the look is exactly zero and the rim never shears. After
that, the only still-visible geometry that could shear is the receding interior grid,
and the amplitude cap keeps that pan gentle until envelopment. Full-strength look
arrives only once enveloped (rim long gone). The product of two smoothsteps is
monotone and C¹ — no felt mode switch.

**Scope discipline.** `Engine/camera_math.py` is **untouched** — every `lo/hi` is a
`proximity()` call argument; the frozen smoothstep is unchanged. Object worlds keep
the frozen `om.proximity(hz)` gate ([0.0, 0.8]) and never amplitude-cap, so
Earth/The Watcher are byte-identical. The forward-dolly *depth* model and the
`DOLLY_MIN = 0` zoom-out floor are unchanged. The old `ROT_GATE_LO/HI` constants are
replaced by the `LOOK_*` block.

**Validation.** Rewrote `Scripts/validation/sim_envelop.py` check-5 to pin the merged
invariants: (a) zero look at neutral/lean-out (rim bezel-locked); (b) the MERGE — the
look engages EARLY (prox(0.5) > 0) where the old sequential gate was exactly 0; (c)
look amplitude capped ≤ 0.22 until the rim clears, and the capped early pan is a small
fraction of the enveloped pan; (d) full amplitude + significant reveal once enveloped;
(e) monotone reveal; (f) C¹ (max step 0.0026). Measured: prox(0.5)=0.030,
reveal grows 0→307 px, gem still grows 3.58× on lean-in (depth model intact). **All 10
headless sims pass**; `sim_viewing` / `sim_vertical` / `sim_offaxis` / `sim_orbit`
unchanged (object path preserved); `py_compile` clean. Live GL "feel" calibration of
`LOOK_ENGAGE_LO` / `LOOK_PRELOOK_AMP` still wants a GUI pass (standing renderer
constraint) — the geometry/invariants are settled; the perception threshold is the
human's call.

**Files.** `Launcher/app_engine.py` (replaced the `ROT_GATE_*` block with the merged
`LOOK_*` block + per-world `prox = engage·amp`; updated the DOLLY_GAIN comment),
`Worlds/world_runtime.py` (`enveloping` docstring), `Scripts/validation/sim_envelop.py`
(constants + helpers + check-5 + docstring rewritten).

**Wiki updated.** [[what-makes-perspective-optimal]] (the proposal page — now marked
implemented, with the shipped design + remaining live-feel pass), [[viewing-models]]
(Method B look), [[off-axis-projection]] (rotation component), [[constraints]]
(per-world depth response), [[grid-room]] + [[the-gem]] (enclosure look),
[[current-focus]] (new top entry), [[known_issues]] (update note on the dolly entry),
and this log entry.
