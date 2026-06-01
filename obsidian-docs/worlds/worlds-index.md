---
title: Worlds Index
type: world
related: [world-system, earth, the-watcher, gem, rendering-engine, asset-pipeline, productification]
last_updated: 2026-05-31
sources: [Worlds/earth/world.json, Worlds/the_watcher/world.json, Worlds/gem/world.json, Worlds/world_loader.py, Engine/renderer.py]
---

# Worlds Index

A "world" is a JSON definition under `Worlds/<name>/world.json` that tells the
engine what to draw. See [[world-system]] for the format and live-switching
mechanism. Three worlds currently ship.

## Comparison

| Property | [[earth]] | [[the-watcher]] | [[gem]] |
|---|---|---|---|
| Display name | Earth | The Watcher | The Gem |
| `primary_mesh` | `earth` | `eye` | `gem` |
| Renderer class(es) | `Earth` + `Stars` + `Nebula` + `IconOrbit` | `Eye` | `Gem` |
| Secondary elements | clouds, atmosphere | — | — |
| Background | `stars` (Milky Way) | `void` (pure black) | `void` (pure white) |
| Bloom | **on** | **off** | **off** |
| Orbital icons | **on** | **off** | **off** |
| Rotation | yes (~6°/s surface) | none (only ≤1.6° gaze drift) | 22°/s Y spin + ±25° sinusoidal X tilt |
| Parallax | yes | yes | yes |
| `clear_color` | `[0, 0, 0.012]` | `[0, 0, 0]` | `[1, 1, 1]` |
| Lighting (sun dir) | `[1.0, 0.5, 1.0]` | `[0.55, 0.42, 0.72]` | `[0.85, 0.52, 0.85]` |
| Fill light | — | — | `[-0.72, -0.30, 0.65]` |
| Ambient | 0.3 | 0.1 | 0.06 |
| Asset dir | `assets/earth/` + `assets/stars/` | `assets/the_watcher/` | *(none — fully procedural)* |
| Asset size | ~22 MB + ~2.1 MB | ~2.4 MB | 0 MB |
| Asset count | 5 textures + 2 backgrounds | 3 textures (+ 1 source photo) | 0 (geometry + shader only) |
| Shadow | none | none | soft oval disk below gem |
| Mood | bright, cinematic, inhabited | dark, minimal, uncanny | stark, brilliant, jewel-like |

## Systems every world uses

All worlds ride the same frozen core: [[off-axis-projection]] (the parallax),
[[head-tracking]] (the input), [[rendering-engine]] (the pixels), and
[[world-system]] (the selection). Earth additionally uses [[orbital-icons]]; Earth
and The Watcher draw textures produced or managed by [[asset-pipeline]]; The Gem
is fully procedural (no assets).

## Adding a world

1. Create `Worlds/<name>/world.json` with at least a `name` and an
   `environment.primary_mesh` that maps to an existing renderer class
   (`earth` or `eye`).
2. Drop any referenced textures under `assets/<asset_dir>/`.
3. Set `"world": "<name>"` in `~/.iris/preferences.json` — [[world-system]]
   picks it up live, in both the demo and the wallpaper daemon.

A genuinely new look (beyond `earth`/`eye`) also needs a new renderer class +
shader in [[rendering-engine]]; a JSON file alone only re-skins existing meshes.

## Related

[[world-system]] · [[rendering-engine]] · [[asset-pipeline]] · [[productification]]
