---
title: "2026-06-01 — Polish: The Watcher — eyeball texture zoom and shader simplification"
type: log-entry
date: 2026-06-01
category: polish
---

# The Watcher — eyeball texture zoom and shader simplification

**Scope.** Modified texture mapping tool and simplified eyeball fragment shader.

## Changes

- **Texture Mapping:**
  - Shifted projection center in `map_photo_eye.py` from geometric image center `(110, 147)` to actual pupil center `(114, 165)`.
  - Reduced hemisphere mapping radius (`half`) from `110.0` to `65.0` pixels, zooming/enlarging the eye features by ~1.7×.
  - Adjusted `IRIS_HALF_ANG` from 38° to 25° to match the new scaled iris.
- **Shader:**
  - Simplified `shaders/eye.frag` to render only the raw B&W diffuse texture.
  - Removed wrap diffuse, normal mapping, cornea specular, iris emission, and rim glow. This allows the high-contrast B&W photo to pop cleanly without any coloring or shading.

## Validation

- Re-ran `map_photo_eye.py` to regenerate all textures.
- Ran all 6 headless simulation checks successfully.
