---
title: Asset Pipeline
type: system
related: [rendering-engine, head-tracking, earth, the-watcher, dmg-build-process, ui-overlay, constraints]
last_updated: 2026-05-31
sources: [Scripts/tools/gen_eye_textures.py, Scripts/tools/gen_space_background.py, Scripts/tools/make_earth_icon.py, Scripts/tools/preview_overlay.py, Engine/shader_loader.py, assets/]
---

# Asset Pipeline

## Purpose

The asset pipeline covers everything from *where the textures come from* to *how
they get into the GPU and the shipped app*. IRIS keeps its bundle small by
**generating** most of its large textures procedurally from code (and one
permissively-licensed photo) rather than shipping huge pre-baked art, and by
auto-downloading the one model it can't generate.

## Generation tools (`Scripts/tools/`)

### `gen_eye_textures.py` — The Watcher's eye maps
Builds the equirectangular `eye_diffuse.png`, `eye_normal.png`, and
`eye_specular.png` (2048×1024) for [[the-watcher]]. It's a hybrid: the iris/pupil
come from a real macro photograph (CC BY-SA 4.0; see [[the-watcher]] for
attribution), **orthographically projected onto the front (+Z) cap** of the UV
sphere so the eye stares out of the screen; the surrounding bloodshot sclera,
veins, and limbal ring are synthesized procedurally (periodic in longitude so the
map wraps seamlessly). The normal map is embossed from luminance height; the
specular map is a wet-cornea gloss mask. Output → `assets/the_watcher/`.

### `gen_space_background.py` — deep-space backdrop
Generates `assets/stars/space_background.jpg` (4096×2048 equirectangular): soft
periodic-fBm nebula clouds, a broken Milky-Way band, and a dusting of faint
background stars. Pure numpy + Pillow, ~0.5 MB, seamless across the longitude
seam so it tiles cleanly on the inside-rendered `Nebula` sphere. The renderer
**prefers** this generated backdrop and falls back to `milky_way_8k.jpg` if it's
missing (see [[rendering-engine]]).

### `make_earth_icon.py` — app/shortcut icon
Draws a vectorised cartoon Earth (`assets/icon/earth_icon.png`, 1024²,
transparent, with an atmospheric glow ring) and applies it as the Finder icon of
the desktop shortcut via `NSWorkspace`. It is fully vectorised with numpy
specifically because an earlier per-pixel-loop version OOM-killed on an 8 GB Mac —
see [[constraints]].

### `preview_overlay.py` — HUD preview renderer
Renders the demo HUD ([[ui-overlay]]) over a synthetic space scene and saves
`Docs/preview/overlay_*.png`, using the same src-over alpha blend as the live
`draw_gl`, so the liquid-glass styling and text crispness can be reviewed without
launching the GL window. (The reference screenshots already in `Docs/preview/`
were produced this way.)

## How assets are loaded at runtime

- **Textures** go through `load_texture_2d` in [[rendering-engine]]'s shader
  loader: pygame decodes the PNG/JPG, mipmaps are generated, and a `flip_v` flag
  controls row order. Equirectangular maps are uploaded **un-flipped** so the
  north pole lands at the top UV row (otherwise the globe/eye is upside-down).
- **The face model** (`face_landmarker.task`, ~3.6 MB) is loaded by
  [[head-tracking]]; if absent it is downloaded on first run.
- **Path resolution** tolerates both the source-tree casing (`assets/`,
  `Worlds/`) and the lowercase layout PyInstaller bundles — see
  [[dmg-build-process]].

## Asset inventory

| Directory | Size | Contents | Origin |
|---|---|---|---|
| `assets/earth/` | ~22 MB | `earth_day/night/clouds/normal/specular.jpg` | Pre-supplied equirectangular maps |
| `assets/stars/` | ~2.1 MB | `milky_way_8k.jpg`, `space_background.jpg` | Panorama + **generated** backdrop |
| `assets/icon/` | ~1.3 MB | `Iris.icns`, `earth_icon.png` | App icon + **generated** cartoon Earth |
| `assets/the_watcher/` | ~2.4 MB | `eye_diffuse/normal/specular.png` + `source/` photo | **Generated** from a CC BY-SA photo |
| `assets/hdr/` | empty | — | Placeholder |
| `models/`, `Tracking/models/` | ~3.6 MB | `face_landmarker.task` | Auto-downloaded MediaPipe model |

## Constraints

- Generation tools target a memory-constrained Mac, so they are vectorised (no
  large per-pixel Python loops). See [[constraints]].
- The eye textures are a derivative work under CC BY-SA 4.0 — attribution must
  ship with the app ([[the-watcher]]).

## Dependencies

- **Feeds:** [[rendering-engine]] (all textures), [[earth]] / [[the-watcher]]
  (their world assets), [[head-tracking]] (the model).
- **Bundled by:** [[dmg-build-process]].
- **Preview tool serves:** [[ui-overlay]].
