---
name: world-builder
description: Author placeable objects (and capture wall/mesh intent) in the IRIS Grid Room from a natural-language description. This is the hands-on stand-in for the future World Builder API — the user runs /world-builder and describes their world ("a glowing red sphere back-left, a pink cube near the glass"); the skill turns that into clamped, allowlisted entries in Worlds/grid_room/world.json, which the running app hot-reloads. Use when the user wants to place/move/recolor objects in the grid, try out the builder, or describe a scene.
---

# World Builder — IRIS / Parallax Wall

This skill is the **manual stand-in for the World Builder API** (real API
integration is a later step). When the user runs `/world-builder` and describes
a scene, you translate that description into the **mutable creator surface** of
`Worlds/grid_room/world.json` — `assets.placeable_objects[]` — written **clamped
and allowlisted**, so the running app hot-reloads it into the live Grid Room.

You are the authoring backend. The user describes; you write valid JSON; the
engine draws it. Nothing here touches the frozen camera / shader / physics core.

## Step 0 — Ground yourself (read once per session)

1. `obsidian-docs/architecture/grid-creator-tool-plan.md` — the plan this implements.
2. `Worlds/placeable.py` — the **source of truth** for the allowlist, clamps, and
   the `grid_to_world` transform. Match it exactly; never invent ranges.
3. `Worlds/grid_room/world.json` — the file you edit (the `assets` block).

## Step 1 — The coordinate frame

There are **two views of the same box**; know both and convert between them.

**Builder-canvas view** (what the user sees in the World Builder tab): origin at
the **back-bottom-left** corner, three axes labeled `0..D`:
- **X → right** (`0` = left wall … `D` = right wall)
- **Y → up** (`0` = floor … `D` = ceiling)
- **Z → toward the viewer** (`0` = back wall … `D` = the glass / front)

**Engine-native view** (what actually goes in `grid_position`, per
`placeable.grid_to_world`): centered X/Y, front-origin Z, with `D = grid_divisions`
(default **8**):
- `gx ∈ [-D/2 .. +D/2]` left→right (0 = centre)
- `gy ∈ [-D/2 .. +D/2]` down→up (0 = centre)
- `gz ∈ [0 .. D]` glass→back (**0 = on the glass/front**, D = back wall)

**Conversion** (builder corner coords `cx,cy,cz` ∈ `0..D` → engine `grid_position`):
```
gx = cx - D/2
gy = cy - D/2
gz = D - cz        # canvas Z (0=back) is inverted vs engine gz (0=front/glass)
```
Write `grid_position` in the **engine-native** numbers. Sanity check: "back-left,
on the floor" = canvas `(0,0,0)` = engine `[-4, -4, 8]`; "centre of the room" =
engine `[0, 0, 4]`; "near the glass, dead centre" = engine `[0, 0, 0]`.

## Step 2 — The object schema (mutable surface only)

Each entry in `assets.placeable_objects[]`:
```json
{
  "id": "short_unique_name",
  "model": "builtin:cube | builtin:sphere | builtin:cylinder",
  "grid_position": [gx, gy, gz],
  "scale": 0.9,
  "color": [r, g, b],
  "emissive": true,
  "rotation": [pitch, yaw, roll]
}
```
Hard limits — **clamp before writing** (mirror `placeable.py`, don't guess):
- `model` ∈ the three `builtin:*` primitives. Map any described shape to the
  nearest one (ball/orb→sphere, box/block→cube, pillar/tube/can→cylinder).
- `grid_position`: `gx,gy ∈ [-4,4]`, `gz ∈ [0,8]` at the default `D=8`.
- `scale ∈ (0, 2.0]`.
- `color` each component `∈ [0,1]` (convert named colors / hex to 0–1 floats).
- `rotation` in degrees; yaw (`rotation[1]`) is the most useful.
- **≤ 64 objects total** (the engine caps it anyway; don't exceed it).

`emissive: true` reads as "glowing" in the void (flat color, lighting off) — the
right default for the neon grid aesthetic.

## Step 3 — The authoring loop

1. **Read** the current `Worlds/grid_room/world.json`.
2. **Parse** the user's description into objects. Infer cells from spatial words
   ("back-left", "near the glass", "floating high", "centre"). Keep ids stable so
   "move the red cube" edits the existing entry instead of adding a duplicate.
3. **Clamp** every field to Step 2. Skip anything you can't represent (and say so).
4. **Write** the updated `assets.placeable_objects[]` back to the JSON.
5. **Make it visible**: ensure the active world is the Grid Room —
   `~/.iris/preferences.json` `"world": "grid_room"`. If the app is running it
   **hot-reloads** within a frame (no restart). If not, tell the user to open it
   (or offer `/verify` / the run flow) — render confirmation is a GUI-only thing.
6. **Parity gate (run before confirming)** — verify the oblique Canvas Cube and
   the live 3-D preview agree on what you just wrote, instead of eyeballing it:
   ```
   .venv/bin/python Scripts/validation/sim_wb_preview_parity.py --scene Worlds/grid_room/world.json
   ```
   `RESULT: previews agree` (exit 0) = safe; relay its per-object placement table.
   A `parity check(s) FAILED` means the two previews disagree (renderer bug → use
   `/bug-fix`, not a re-author). A `⚠ … clamped` advisory means a coordinate was
   out of range and snapped to a wall — fix that `grid_position` and rewrite, don't
   report it as placed where the user asked.
7. **Confirm** back to the user in plain language: what you placed, where (in
   both "back-left near the floor" terms and the `grid_position`), and anything
   you clamped or couldn't yet do.

## Step 4 — Not yet renderable (capture intent, set expectations)

The user may describe things v1 can't draw yet. Be honest, don't silently drop:

- **Custom / described meshes** ("a low-poly fox", "a twisted torus"). v1 renders
  **primitives only** — map to the nearest builtin and tell the user it's an
  approximation. True describe-a-mesh is a later, curated track (see the plan
  §1.2); generating geometry/shaders next to the frozen core is out of scope here.
- **Wall textures** ("brick walls", "a starfield on the back wall"). The Grid Room
  walls are wireframe lines today — there is **no wall-texture renderer yet**. You
  may record the intent under a clearly-non-frozen `assets.wall_textures` note so
  the description isn't lost, but state plainly that it won't render until that
  renderer support lands. Do **not** fake it.

## Frozen boundaries — never cross (from CLAUDE.md + the plan §11)

- Edit **only** `assets.placeable_objects[]` (and the documented `assets.*` intent
  fields). **Never** change `grid_divisions`, `grid_depth`, `primary_mesh`,
  `enveloping`, anything under `camera`, or any `shaders/`.
- Never reintroduce grid panning. Never touch `Engine/camera_math.py` or physics.
- Reliability is the product: a malformed object must be skipped, never crash the
  scene. The engine's `sanitize_objects` is the backstop — but write valid JSON
  the first time.
