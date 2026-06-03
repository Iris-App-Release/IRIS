---
title: Worlds Index
type: world
related: [world-system, earth, the-watcher, gem, grid-room, rendering-engine, asset-pipeline, productification]
last_updated: 2026-06-02
sources: [Worlds/earth/world.json, Worlds/the_watcher/world.json, Worlds/gem/world.json, Worlds/grid_room/world.json, Worlds/world_loader.py, Engine/renderer.py]
---

# Worlds Index

A "world" is a JSON definition under `Worlds/<name>/world.json` that tells the
engine what to draw. See [[world-system]] for the format and live-switching
mechanism. Four worlds are available: three scenic (Earth, The Watcher, The Gem)
and one utility/calibration (The Grid Room).

## Comparison

| Property | [[earth]] | [[the-watcher]] | [[gem]] | [[grid-room]] |
|---|---|---|---|---|
| Display name | Earth | The Watcher | The Gem | Grid Room |
| Use case | scenic destination | scenic destination | scenic + jewel focus | spatial reference / calibration |
| [[viewing-models\|Viewing model]] | object / open (telephoto) | object / open (telephoto) | enclosure / rim-anchored (telephoto) | enclosure / rim-anchored (telephoto) |
| `enveloping` (caps the look so the bezel rim doesn't shear; zoom + gate identical to Earth) | `false` | `false` | `true` | `true` |
| `primary_mesh` | `earth` | `eye` | `gem` | `room` |
| Renderer class | `Earth` + `Stars` + `Nebula` + `IconOrbit` | `Eye` | `Gem` | `GridRoom` |
| Shader used | yes (Earth/Star/Nebula) | yes (Eye) | yes (Gem) | **none** (fixed-function `GL_LINES`) |
| Background | `stars` (Milky Way) | `void` (pure black) | `void` (pure white clear) | `void` (near-black clear) |
| Environment | parallax stars + nebula | — | pink/white checkered box | cyan wireframe shadow-box |
| Orbital icons | **on** | **off** | **off** | **off** |
| Rotation | yes (~6°/s surface) | none (≤1.6° gaze drift) | 22°/s Y + ±25° sinusoidal X | none (static reference) |
| Parallax | yes | yes | yes | **yes** (especially front→back grid convergence) |
| `clear_color` | `[0, 0, 0.012]` | `[0, 0, 0]` | `[1, 1, 1]` | `[0.01, 0.012, 0.022]` |
| Lighting (sun) | `[1.0, 0.5, 1.0]` | `[0.55, 0.42, 0.72]` | `[0.85, 0.52, 0.85]` | N/A (unlit) |
| Fill light | — | — | `[-0.72, -0.30, 0.65]` | — |
| Ambient | 0.3 | 0.1 | 0.06 | N/A |
| Asset files | ~24 MB (Earth + stars) | ~2.4 MB | 0 (procedural) | 0 (procedural) |
| Asset count | 5 textures + 2 backgrounds | 3 textures | 0 | 0 |
| Shadow | none | none | soft oval on floor | none |
| Grid params | — | — | `grid_depth: 18`, `grid_divisions: 8` | `grid_depth: 18`, `grid_divisions: 8` (configurable) |
| Mood | bright, cinematic, inhabited | dark, minimal, uncanny | stark, brilliant, jewel-like | clinical, geometric, reference |

## Systems every world uses

All worlds ride the same frozen core: [[off-axis-projection]] (the parallax),
[[head-tracking]] (the input), [[rendering-engine]] (the pixels), and
[[world-system]] (the selection).

- **Earth:** additionally uses [[orbital-icons]] and [[asset-pipeline]] (5 textures)
- **The Watcher:** uses [[asset-pipeline]] (3 textures)
- **The Gem:** fully procedural (no assets; geometry + shader only)
- **The Grid Room:** fully procedural; no shaders; spatial-reference utility for [[grid-api-customization]]

## Adding a world

1. Create `Worlds/<name>/world.json` with at least a `name` and an
   `environment.primary_mesh` that maps to an existing renderer class:
   - `earth` → the Earth globe + background elements
   - `eye` → the eyeball (The Watcher's mesh)
   - `gem` → the brilliant-cut gemstone (The Gem)
   - `room` → the wireframe Grid Room (spatial reference)

2. Drop any referenced textures under `assets/<asset_dir>/` (if using existing
   meshes that have textures; `gem` and `room` are fully procedural).

3. Set `"world": "<name>"` in `~/.iris/preferences.json` — [[world-system]]
   picks it up live, in both the demo and the wallpaper daemon.

**For a genuinely new look** (beyond the four above), you also need a new renderer
class + shader in [[rendering-engine]]; a JSON file alone only re-skins existing
meshes. Examples: a new `Gem`-like procedural object with different geometry and
lighting; a completely new sky/background effect; integration with [[grid-api-customization]]
to place procedurally-generated assets in a Grid Room instance.

## Related

[[world-system]] · [[rendering-engine]] · [[asset-pipeline]] · [[productification]]
