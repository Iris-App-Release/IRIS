---
title: Earth (World)
type: world
related: [world-system, rendering-engine, off-axis-projection, orbital-icons, asset-pipeline, the-watcher, worlds-index]
last_updated: 2026-05-31
sources: [Worlds/earth/world.json, Engine/renderer.py, assets/earth/, assets/stars/, assets/icon/]
---

# Earth (World)

## What it is

The default, flagship IRIS world: a photo-real, slowly rotating Earth suspended
in a star field, with a Milky-Way nebula backdrop and (optionally) a ring of
macOS app icons orbiting the planet. It is the world the engine falls back to and
the one all the physics was originally tuned against.

Defined by `Worlds/earth/world.json` and rendered by the `Earth`, `Stars`,
`Nebula`, and `IconOrbit` classes in [[rendering-engine]].

## World definition

| Field | Value |
|---|---|
| `name` | Earth |
| `primary_mesh` | `earth` |
| `secondary_elements` | `clouds`, `atmosphere` |
| `background` | `stars` |
| `lighting.sun_direction` | `[1.0, 0.5, 1.0]` |
| `lighting.ambient_intensity` | `0.3` |
| `use_bloom` | `true` |
| `use_parallax` | `true` |
| `rotation_speed` | `0.01` |
| `show_icons` | `true` |
| `clear_color` | `[0.0, 0.0, 0.012]` (near-black blue) |

## How it renders

The `Earth` class draws **three concentric spheres** (see [[rendering-engine]]):

1. **Surface** (`R = 2.6`) — day texture blended into a night-lights texture by
   the sun angle, with specular oceans and a normal map for relief. Real 23.5°
   axial tilt; rotates ~6°/s (~60 s per turn).
2. **Cloud shell** (`R = 2.625`) — a semi-transparent layer that drifts slightly
   faster than the surface (~7.5°/s) with an additional slow UV scroll.
3. **Atmosphere halo** (`R = 2.85`) — an additive scattering glow drawn from the
   sphere's back faces so it haloes the silhouette.

Behind the planet, `Stars` provides three parallax depth layers and `Nebula`
wraps the scene in the Milky Way. Because `show_icons` is true, [[orbital-icons]]
can place app icons on a tilted ring that passes in front of and behind the globe
with correct depth occlusion. Bloom ([[rendering-engine]]) is on, giving the
cinematic glow on the Earth's bright limb.

## Asset inventory

| Asset | Path | Notes |
|---|---|---|
| Day map | `assets/earth/earth_day.jpg` | Equirectangular |
| Night map | `assets/earth/earth_night.jpg` | City lights |
| Clouds | `assets/earth/earth_clouds.jpg` | Cloud shell |
| Normal map | `assets/earth/earth_normal.jpg` | Surface relief |
| Specular | `assets/earth/earth_specular.jpg` | Ocean shine |
| Background | `assets/stars/milky_way_8k.jpg` | 8K Milky-Way panorama |
| (Generated bg) | `assets/stars/space_background.jpg` | Preferred nebula backdrop if present |
| Earth icon | `assets/icon/earth_icon.png` | Branding / about |

`assets/earth/` is ~22 MB; `assets/stars/` ~2.1 MB. The icon and background
textures are produced by tools in [[asset-pipeline]].

## Systems used

[[off-axis-projection]] · [[head-tracking]] · [[rendering-engine]] ·
[[world-system]] · [[orbital-icons]] · [[asset-pipeline]]

## Related

[[the-watcher]] · [[worlds-index]]
