---
title: "2026-06-01 — Decision: Bloom post-processing removed entirely"
type: log-entry
date: 2026-06-01
category: decision
---

# Bloom post-processing removed entirely (supersedes the per-world `use_bloom` gate)

**Trigger.** Follow-up to the entry above. Asked what bloom contributes
(answer: purely visual — soft glow on bright pixels, plus the composite's Reinhard
tonemap + exposure ×1.22 + vignette + chromatic aberration; zero functional role,
and it *costs* GPU). User then chose to **remove all glow and bloom on every world
including Earth**, with the only requirement that parallax, star twinkle and gem
shimmer keep working.

**Why it's safe for the three things that matter.** All three are generated
*upstream* of bloom and are untouched: parallax is `camera_math` (off-axis
frustum + view matrix), star twinkle is animated in `stars.frag` from `u_time`,
and the gem's facet shimmer is `gem.frag` specular/fresnel/emissive/iridescence.
Bloom only added a soft halo around the brightest pixels and the screen grade.

**Change.** `Launcher/app_engine.py`: removed the `BloomPipeline` import, its
construction, the Desktop-Mode FBO rebuild, and both render passes. The scene now
draws **straight to the default framebuffer** (the previous "FBO setup failed"
fallback path, now the only path). Reverted the two now-moot pieces from the entry
above: `WorldRuntime.use_bloom` (deleted) and the `BloomPipeline(downscale=…)`
parameter (`Engine/bloom_postfx.py` back to its original signature). The MSAA
4×→2× wallpaper trim from that entry is **kept** — and now actually matters:
because the scene previously rendered into a NON-multisampled bloom FBO, MSAA had
never applied; drawing to the multisampled default framebuffer means real
anti-aliasing for the first time. `bloom_postfx.py` is left in the tree (unused).

**Accepted visual change.** Every world loses the glow and the grade. Earth is
~22 % dimmer and flatter (lost the exposure multiplier + vignette + the gamma/
Reinhard tonemap); The Gem and The Watcher lose the glow halo and grade too. This
was explicitly chosen over the "keep the cheap grade, drop the glow" alternative.

**Validation.** `py_compile` clean (app_engine, renderer, bloom_postfx,
world_runtime). All seven headless sims pass (six existing + `sim_camlag`). The
GL/visual result needs a live GUI session to confirm (standing renderer
constraint), but the path is the proven no-FBO fallback.

**Wiki updated.** [[current-focus]] (top section rewritten — bloom removal
replaces the per-world gate), and this log entry.
