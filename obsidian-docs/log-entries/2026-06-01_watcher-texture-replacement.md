---
title: "2026-06-01 — Texture-replacement: The Watcher — eye diffuse replaced with supplied photo"
type: log-entry
date: 2026-06-01
category: texture-replacement
---

# The Watcher — eye diffuse replaced with supplied photo

**Scope.** Texture-only replacement task. No shader, physics, animation, tracking,
or parallax systems were modified.

## Asset replaced

| Asset | Previous | New |
|---|---|---|
| `assets/the_watcher/eye_diffuse.png` | Procedural Eye-of-Cthulhu iris (gen_eye_textures.py) | Photo-based: `something-i-made-for-my-friends.gif` |
| `assets/the_watcher/eye_normal.png` | Derived from procedural diffuse | Re-derived from new diffuse luminance |
| `assets/the_watcher/eye_specular.png` | Procedural cornea mask | Regenerated; same angular definition (IRIS_HALF_ANG = 38°) |

Source image: `obsidian-docs/worlds/something-i-made-for-my-friends.gif` (220×294, grayscale, high-contrast B&W photo of a human eye).

## Files modified

- `assets/the_watcher/eye_diffuse.png` — replaced
- `assets/the_watcher/eye_normal.png` — regenerated
- `assets/the_watcher/eye_specular.png` — regenerated
- `Scripts/tools/map_photo_eye.py` — new script (companion to gen_eye_textures.py)
- `dist/Iris.app` — hot-swapped via hotswap.sh

## Mapping approach

Orthographic projection (parallel projection from +Z, the camera-facing direction).

The photo center (iris/pupil) maps to UV (0.25, 0.50) — the +Z pole on
`make_sphere()`'s equirectangular grid. The photo's shorter dimension (width = 220 px)
defines the hemisphere radius so the full horizontal extent of the photo fills the
sphere's visible face without stretching. Bilinear interpolation upsamples the
220×294 source to the 2048×1024 equirectangular target.

Back hemisphere (sz < 0) is filled pure black — it sits against the void and is
never normally visible.

The specular map retains the same 38° cornea cap angular definition as before so
the wet-glass specular highlight and iris emission (`eye.frag`) stay correctly
aligned with the iris region in the new photo.

The normal map is re-derived from the new diffuse's luminance gradient (same
NORMAL_STRENGTH = 4.5 as before) so surface relief follows the photo's actual
light/dark detail rather than the old procedural veins.

## Validation

- `eye_diffuse.png` at UV (0.25, 0.50): brightness = 0 (dark iris/pupil, correct).
- Specular peak at UV ≈ (0.241, 0.315), value 250/255 ≈ 0.98 (full cornea gloss, correct).
- No shader changes.
- No renderer changes.
- No physics, tracking, parallax, rotation, or animation changes.
- `hotswap.sh` completed with valid code signature.

**Wiki updated.** [[the-watcher]] (Asset inventory section); this log entry.
