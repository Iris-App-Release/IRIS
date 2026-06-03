---
title: "2026-05-31 — Polish: The Gem — size, tilt constraint, shadow"
type: log-entry
date: 2026-05-31
category: polish
---

# The Gem — size, tilt constraint, shadow

**Scope.** Three UX-driven changes to [[gem]] based on first impressions at
working distance. No camera math, world JSON, or shader code touched.

## Changes

**`Engine/renderer.py` — `make_gem` defaults:**
- `n`: 32 → 16 (64 flat-shaded triangles instead of 128). At n=32 the facets were
  too numerous to read individually; n=16 gives clear, distinct facet flashes.
- `r_girdle`: 1.45 → 2.2 (+52%). At working distance (BASE_Z=11.5, scene z=−10)
  the old gem subtended ~3.9° of view; the new size gives ~5.8° — comfortably
  visible without dominating. Crown / pavilion scaled proportionally:
  `h_crown` 0.52 → 0.79, `h_pav` 1.85 → 2.80.

**`Engine/renderer.py` — `Gem` class, rotation:**
- Removed: `_ROT_PITCH_DEG_S = 7.0` and the accumulating `_spin_x` (which could
  tilt the gem to 90° / sideways over time).
- Added: `_TILT_MAX_DEG = 25.0` and `_TILT_SPEED = 0.38 rad/s`. The X-axis tilt
  is now `25° × sin(tilt_phase)`, oscillating with period ≈ 16.5 s. The gem rocks
  gently ±25° from vertical and never approaches sideways.

**`Engine/renderer.py` — `Gem` class, shadow:**
- New `_build_shadow()`: 48-segment triangle-fan disk at `y = −3.30` (0.5 below the
  culet), `r = 3.50`, centre alpha 0.28 fading to 0 at the edge. Built once at
  `__init__` into numpy arrays.
- New `_draw_shadow()`: fixed-function pipeline, vertex colour array, depth writes
  off (`glDepthMask(GL_FALSE)`), blend on. Shadow is drawn first in `Gem.draw()`
  before the `glPushMatrix/glRotatef` for the gem spin, so it remains a flat
  horizontal disk on the "floor" regardless of gem tilt — always visually grounding.

## Validation

- All 6 headless sims still print "RESULT: all checks passed".
- Geometry check: 192 vertices / 64 flat triangles, Y ∈ [−2.80, 0.79], XZ r = 2.20.
- Python syntax check on `Engine/renderer.py`: OK.

**Wiki updated.** [[gem]] (How it renders, Constraints sections rewritten);
[[worlds-index]] (rotation row + new shadow row); [[rendering-engine]] (Gem entry);
and this log entry.
