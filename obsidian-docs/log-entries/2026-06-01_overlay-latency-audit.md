---
title: "2026-06-01 — Fix + Audit: Overlay idle-fade-on-hover; render-path latency audit"
type: log-entry
date: 2026-06-01
category: fix
---

# Overlay idle-fade-on-hover; render-path latency audit

**Two user reports.** (1) Demo buttons "grey out a couple seconds after I hover,
over an area bigger than the hitbox." (2) "Latency is slightly high for the
illusion to be believable" — suspected the [[the-gem]] checkered floor and/or
"all 3 worlds loaded at once."

## 1. Overlay greying — root cause found (not the hitbox)

**Reproduced headlessly.** With the cursor resting on the primary button
(`hover == "primary"`, `hover_t == 1.0`), the whole control cluster still faded to
`_ctrl_alpha = 0.34` after the 4 s idle timeout.

**Root cause.** `DemoOverlay.update()` computed `idle = now - _last_input`, and
`_last_input` only refreshes on `MOUSEMOTION` / `MOUSEBUTTONDOWN`. A mouse emits
no events while held still, so a *stationary hover* — an actively-engaged state —
was treated as idle and the entire control layer (status pill + every button +
scrim) dimmed. That whole-layer dim is the "area bigger than the hitbox" the user
saw; the hitbox itself is fine (`_hit` uses the same rect that draws the grey
fill — `sim_overlay` check 7 confirms exact hit-testing). The user's hitbox
hypothesis was a red herring.

**Fix.** `UI/demo_overlay.py:update()` — treat an active hover as engagement:
`idle = 0.0 if self.hover is not None else (now - _last_input)`. Controls stay lit
while the cursor rests on any control; idle-fade resumes when it moves away.

## 2. Latency audit — the two suspected causes do NOT hold

- **Checkered floor:** already fixed in the 2026-06-01 perf pass (60×60 = 21,600 →
  **6 verts**, mipmapped `GL_REPEAT` texture). It is now a 2-triangle plane + one
  texture lookup — not a measurable per-frame cost.
- **"All 3 worlds loaded at once":** false. `WorldRuntime` holds exactly **one**
  world definition (`self._def`); `Eye`/`Gem` renderers are built lazily on first
  selection and cached, and only the *active* world's mesh is drawn (the draw path
  branches on `world.primary_mesh`). Switching is instant because the heavy
  `Earth`/`Stars`/`Nebula` objects are pre-built at startup and Gem/Eye persist —
  intentional caching, **not** concurrent rendering. ([[world-system]])

## 2b. Real render-path costs — two GPU→CPU stalls removed

Both were flagged "recommended next" in the 2026-06-01 entry; now done.

- `Launcher/app_engine.py`: removed `_view_rot_3x3()` and its per-frame
  `glGetFloatv(GL_MODELVIEW_MATRIX)`. The view rotation is now sliced from the
  `mv` matrix already built on the CPU (`view_rot = mv[:3, :3]`). Pixel-identical;
  one pipeline stall gone **every frame, every world**.
- `Engine/renderer.py` (`IconOrbit.draw`): replaced the **per-icon** `glGetFloatv`
  with a single Earth-origin modelview read + a CPU billboard (`diag(ICON_SIZE)`
  3×3, eye-space origin via one mat·vec). **N stalls/frame → 1** in the Earth
  world. Verified numerically identical to the old read-back (max abs matrix diff
  1.9e-6 = float32 noise).

## 2c. Findings flagged, NOT changed (frozen / risk)

- **Headline head→photon latency is dominated by the FROZEN pipeline, not render
  cost.** MediaPipe VIDEO ~34 ms mean / 68 ms p95, then **two** smoothing layers:
  the tracker's velocity-adaptive lerp (frozen; `sim_latency`) **plus** a second
  `CAM_LAG = 0.55` per-frame exponential in `app_engine`. Because `CAM_LAG` is
  applied **per frame, not dt-normalised**, its time-constant is frame-rate
  dependent: ~57 ms to 90 % at the 60 fps demo vs **~113 ms at the 30 fps
  wallpaper/desktop cap** — so the illusion genuinely feels laggier once Desktop
  Mode drops to 30 fps. This is the most likely source of the "slightly high"
  perception. Making `CAM_LAG` dt-aware would fix it but touches frozen smoothing
  — **needs explicit approval + a new sim**; not done. ([[constraints]])
- **Bloom runs in the Gem world even though `gem/world.json` sets
  `"use_bloom": false`** — the engine's `bloom_enabled` is global and never reads
  the per-world flag. Wasted full-screen post-process in a world that asked for it
  off. Recommend honouring per-world `use_bloom`; not changed (behaviour/risk).
- Client-side vertex arrays still re-streamed every frame (Earth = 3 spheres,
  96×96). VBO migration still recommended.

**Validation.** `sim_overlay` (26 checks), `sim_latency`, `sim_orbit` all pass;
`py_compile` clean on all three edited files; billboard equivalence checked
numerically (1.9e-6).

**Wiki updated.** [[known_issues]] (overlay fix), [[current-focus]] (audit +
stalls done), [[constraints]] (glGet stalls removed; CAM_LAG frame-rate note),
[[ui-overlay]] (idle-fade respects hover), and this log entry.
