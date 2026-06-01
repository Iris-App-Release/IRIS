---
name: new-world
description: Scaffold a new IRIS world. Worlds are declarative JSON content on top of the frozen physics/render core — this skill loads the schema, the two proven examples, and the constraints a new world must respect, then creates Worlds/<name>/world.json and flags whether new renderer/shader code is needed. Use when the user wants to add a world, scene, or new visual experience to the parallax wall.
---

# New World — IRIS / Parallax Wall

A "world" is **content, not code**: a declarative `Worlds/<name>/world.json`
that the frozen engine renders. [[earth]] and [[the-watcher]] both ride the
exact same off-axis parallax / zoom / rotation core — only the assets and flags
differ. The goal is the *smallest* change that produces a new experience.

## Step 1 — Load the design surface

Read these before scaffolding:

1. `obsidian-docs/systems/world-system.md` — The full `world.json` schema, the
   defaults, live-switching mechanism, and the data-flow table.
2. `Worlds/earth/world.json` and `Worlds/the_watcher/world.json` — The two
   working examples. Earth = full features (stars, bloom, icons, rotation);
   The Watcher = minimal mood piece (void, no bloom, no icons, no spin).
3. `obsidian-docs/architecture/constraints.md` — **Critical.** The "Content"
   section: `primary_mesh` must map to an existing renderer class. The "Viewing
   geometry" + "Graphics" sections: the scene anchor (`z = -10`), Earth/Eye
   radius (`R = 2.6`, same screen footprint), the anti-bloom alpha convention.
4. `obsidian-docs/worlds/worlds-index.md` — Side-by-side of existing worlds.
5. `obsidian-docs/architecture/design-decisions.md` — "The Watcher as a pure
   reskin" documents the reskin-first philosophy: prefer reusing an existing
   mesh + new texture over new geometry.

## Step 2 — Decide the implementation tier

Establish with the user (or infer) which tier the new world needs — **prefer
the lowest tier that achieves the look**:

| Tier | What it needs | Example |
|---|---|---|
| **A. Pure reskin** | New `world.json` + new textures only, reusing `earth` or `eye` mesh | A different planet (reuse `earth`); a different eye (reuse `eye`) |
| **B. New texture set** | Tier A + a generator script in `Scripts/tools/` (vectorised — 8GB RAM target) | A gas giant with generated bands |
| **C. New mesh/shader** | A new renderer class in `Engine/renderer.py` + a shader pair in `shaders/` + the `primary_mesh` → class mapping | A torus, a crystal world (note: `Gem` class exists but is unexposed) |

Tier A is almost always the right answer first. Only go to C if the silhouette
itself must change.

## Step 3 — Scaffold `world.json`

Create `Worlds/<name>/world.json`. Schema (every field has an Earth-preserving
default, so a minimal file still renders):

```json
{
  "name": "Display Name",
  "description": "One-line mood/concept.",
  "version": "1.0",
  "environment": {
    "primary_mesh": "earth | eye",          // MUST map to a renderer class
    "secondary_elements": ["clouds", "atmosphere"],  // [] for none
    "background": "stars | void",
    "lighting": { "sun_direction": [x, y, z], "ambient_intensity": 0.0-1.0 }
  },
  "rendering": {
    "use_bloom": true | false,
    "use_parallax": true,                    // keep true — it's the whole point
    "rotation_speed": 0.0,                   // radians/frame; 0 = no spin
    "show_icons": true | false,
    "clear_color": [r, g, b]                 // void worlds use [0,0,0]
  },
  "assets": {
    "asset_dir": "<name>",                   // optional; subdir under assets/
    "textures": { ... }                      // keys depend on the mesh
  }
}
```

Mirror the closest existing example (mood piece → copy The Watcher's flags;
rich planet → copy Earth's). Put any new textures under `assets/<asset_dir>/`.

## Step 4 — Wire renderer/shader ONLY if Tier C

If a genuinely new mesh is needed:
- Add the render class to `Engine/renderer.py` (follow the `Eye` class as the
  minimal template — geometry in `__init__`, `update(dt, ...)`, `draw(...)`).
- Add a `<name>.vert` / `<name>.frag` pair in `shaders/` (GLSL 120 only — see
  the Graphics constraints). Use `alpha = 0` if it must skip bloom.
- Map `primary_mesh` → the class in `Launcher/app_engine.py`'s render block
  (mirror the existing `if world.primary_mesh == "eye":` branch).
- Honor the frozen core: do not touch camera math, projection, or smoothing.

## Step 5 — Test

- `./preview.sh <name>` — launches straight into the new world from source
  (the script pre-selects the world via `~/.iris/preferences.json`). No rebuild.
- If you added/changed assets or shaders and want them in the signed app:
  `./hotswap.sh`. Python (new renderer class) needs a full `bash Build/build_dmg.sh`.
- If you touched anything geometry-adjacent, run the relevant sims in
  `Scripts/validation/` (they should be unaffected by a pure content world —
  if a sim breaks, you touched the frozen core).

## Step 6 — Document (mandatory)

- Create `obsidian-docs/worlds/<name>.md` (mirror `worlds/the-watcher.md`'s
  structure: what it is, world-definition table, how it renders, asset
  inventory/provenance, systems-used, data-flow table with `[[links]]`).
- Add the world to the comparison table in `obsidian-docs/worlds/worlds-index.md`
  and `obsidian-docs/systems/world-system.md` ("Installed worlds" table).
- If Tier C, update `obsidian-docs/systems/rendering-engine.md` (new class) and
  the `primary_mesh` mapping note in `obsidian-docs/architecture/constraints.md`.
- Add a dated entry to `obsidian-docs/log.md`.

The task is not done until the world renders AND the docs describe it.
