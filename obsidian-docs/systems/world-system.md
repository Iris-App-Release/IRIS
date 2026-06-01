---
title: World System
type: system
related: [rendering-engine, engine-loop-and-daemon, asset-pipeline, earth, the-watcher, worlds-index, design-decisions]
last_updated: 2026-05-31
sources: [Worlds/world_loader.py, Worlds/world_runtime.py, Worlds/earth/world.json, Worlds/the_watcher/world.json]
---

# World System

## Purpose

The world system separates **content from engine**. A "world" is a declarative
JSON file, not Python — it lists which mesh to show, what background to use,
which textures to load, and a handful of rendering flags. This is what lets IRIS
ship multiple experiences ([[earth]], [[the-watcher]], and more later) on top of
one frozen physics/rendering core, and lets the active world be **switched live**
with no restart.

It is content-only by design: this system touches **no** camera, physics, or
parallax code. It only chooses *what* [[rendering-engine]] composes.

## Two files

- `Worlds/world_loader.py` — the on-disk format. `WorldLoader(worlds_dir)` reads
  `Worlds/<name>/world.json` via `load_world(name)` and enumerates installed
  worlds via `list_available_worlds()` (any subdirectory containing a
  `world.json`). A `World` abstract base class defines the minimal interface.
- `Worlds/world_runtime.py` — the *active*-world selector. `WorldRuntime` decides
  which world the engine is currently drawing.

## Live switching

`WorldRuntime` reads the active world name from the `"world"` key of
`~/.iris/preferences.json`, defaulting to `earth`. It re-checks that file's
modification time **every frame** (mtime-cached), so changing the world — from
the demo UI, or by editing the prefs file by hand — takes effect immediately in
**both** the demo window and the detached wallpaper daemon, with no restart. This
mirrors the existing `~/.parallax_*` flag-file toggles the engine already polls
(see [[engine-loop-and-daemon]]).

`resolve_worlds_dir` tolerates either casing — the source tree uses `Worlds/`,
but PyInstaller bundles it as lowercase `worlds/` (see [[dmg-build-process]]).

Selection is defensive: if a named world fails to load, it keeps the current one
(or hard-falls-back to `earth` on first load), so a malformed `world.json` can
never leave the engine with nothing to draw.

## The `world.json` schema

Every field has an Earth-preserving default, so a minimal file still renders.

```json
{
  "name": "Earth",
  "description": "...",
  "version": "1.0",
  "environment": {
    "primary_mesh": "earth",            // which renderer class: earth | eye | gem
    "secondary_elements": ["clouds", "atmosphere"],
    "background": "stars",              // stars | sky (deployed: earth uses stars; the-watcher & gem use sky)
    "lighting": { "sun_direction": [1.0, 0.5, 1.0], "ambient_intensity": 0.3 }
  },
  "rendering": {
    "use_bloom": true,
    "use_parallax": true,
    "rotation_speed": 0.01,
    "show_icons": true,
    "clear_color": [0.0, 0.0, 0.012]
  },
  "assets": {
    "asset_dir": "the_watcher",         // optional; defaults to per-mesh dir
    "textures": { "day": "earth_day.jpg", ... },
    "background": { "stars": "milky_way_8k.jpg" }
  }
}
```

`WorldRuntime` exposes these as convenience properties with defaults:
`primary_mesh` (`"earth"`), `background` (`"stars"`), `show_icons` (`True`),
`clear_color` (`[0, 0, 0.012]`), plus the raw `env` and `rendering` dicts.

## Installed worlds

| World | Mesh | Icons | Background |
|---|---|---|---|
| [[earth]] | `earth` | on | stars |
| [[the-watcher]] | `eye` | off | void |

*(Bloom was removed engine-wide on 2026-06-01 — no world glows; the `use_bloom`
flag in each `world.json` is retained but ignored.)*

A side-by-side comparison lives in [[worlds-index]].

## Data flow

| Consumes | Produces | Destination | Purpose |
|----------|----------|-------------|---------|
| `~/.iris/preferences.json` ("world" key) | Active world name | [[engine-loop-and-daemon]] frame loop | decide what to render |
| `Worlds/<name>/world.json` | World metadata + flags | [[rendering-engine]] | mesh, background, bloom, icons, colors |
| (same) | `primary_mesh` ("earth", "eye", or "gem") | [[rendering-engine]] | choose Earth, Eye, or Gem class to draw |
| (same) | `background` ("stars" or "sky") | [[rendering-engine]] | draw Nebula+Stars or rendered sky (deployed worlds use stars for Earth, sky for The Watcher & The Gem) |
| (same) | `use_parallax`, `show_icons`, etc. | [[rendering-engine]] | toggle features per world (`use_bloom` is no longer read — bloom removed 2026-06-01) |
| (same) | Asset directory path | [[asset-pipeline]] | where to find textures for this world |

Worlds are **content only** — no camera, physics, or parallax logic. Each world
uses the *same* [[off-axis-projection]] math and [[head-tracking]] data; only the
rendered assets and visual flags change.

## Constraints

- The `primary_mesh` must map to a renderer class that exists (`earth` → `Earth`,
  `eye` → `Eye`). Adding a genuinely new mesh type needs renderer support, not
  just a JSON file.
- World metadata is re-read on switch (no caching beyond the mtime gate).

## Dependencies

- **Feeds:** [[rendering-engine]] (which primitives, textures, and flags to
  compose) and [[engine-loop-and-daemon]] (which owns the per-frame prefs poll).
- **Depends on:** [[asset-pipeline]] for the textures a world references.
- **Worlds:** [[earth]], [[the-watcher]], [[worlds-index]].
