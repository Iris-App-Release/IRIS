---
title: World Builder — Unified World Schema
type: reference
related: [WORLD_BUILDER_AUDIT, grid-creator-tool-plan, grid-api-customization, world-system, constraints, WORLD_BUILDER_LIVE_REVIEW]
last_updated: 2026-06-05
sources:
  - Worlds/placeable.py
  - Worlds/world_runtime.py
  - Worlds/grid_room/world.json
  - Engine/renderer.py
  - UI/world_builder_api.py
---

# World Builder — Unified World Schema (Phase 2)

> **Purpose.** Define the **single** object schema and the **single** coordinate
> convention that *both* renderers (the 3-D parallax world and the 2-D oblique grid)
> consume. No duplicate coordinate systems, no duplicate generation logic. This is the
> contract Claude authors to, `sanitize_objects` enforces, and both `grid_to_world`
> (3-D) and `grid_to_canvas_cell` (grid) read from.

---

## 1. The canonical placeable-object schema

Every generated object is exactly this shape after `sanitize_objects`:

```json
{
  "id": "neon_cube_1",
  "model": "builtin:cube",
  "grid_position": [3, 2, 5],
  "scale": 0.8,
  "color": [1.0, 0.2, 0.8],
  "emissive": true,
  "rotation": [0, 45, 0]
}
```

| Field | Type | Range / allowed | Meaning | Mutable by creator? |
|---|---|---|---|---|
| `id` | string | short snake_case | label for reference/editing | ✅ |
| `model` | string | `builtin:cube` \| `builtin:sphere` \| `builtin:cylinder` | primitive (allowlist) | ✅ (allowlist only) |
| `grid_position` | `[gx,gy,gz]` | gx,gy ∈ [−D/2, D/2]; gz ∈ [0, D] | **centred** integer cell (see §2) | ✅ |
| `scale` | float | (0, 2.0] | uniform size; 1.0 ≈ one cell | ✅ |
| `color` | `[r,g,b]` | each 0.0–1.0 | flat/emissive colour | ✅ |
| `emissive` | bool | — | glow as flat colour in the void (default true) | ✅ |
| `rotation` | `[rx,ry,rz]` | degrees | pitch, yaw, roll | ✅ |

**Immutable (rejected by the loader/clamp layer — never object fields):**
`grid_divisions`, `grid_depth`, `primary_mesh`, `enveloping`, `camera`, `lighting`,
shaders. A prompt that asks for these is ignored.

> The schema lives at `world.json` → `assets.placeable_objects[]`. Default `[]`, so
> every existing world is byte-identical and unaffected.

### Why `model`/`grid_position`, not `type`/`position`?

The Phase-2 brief sketched a friendlier `{type, position, scale, color}` shape. The
**implemented** names are deliberately stricter because they *are* the safety contract:

- `model` carries the `builtin:` namespace so the allowlist is explicit and forgeable
  inputs are obvious to reject.
- `grid_position` names the coordinate space (grid cells, not world units or pixels).
- `color` is `[r,g,b]` floats, not `"red"`, so it round-trips losslessly to GL
  `glColor4f` and to the canvas sprite shader with no name table to drift.

The **authoring layer** (Claude, via the system prompt in `world_builder_api.py`)
accepts friendly natural language ("a glowing red sphere") and *emits* the canonical
schema. So users never type the strict form; they describe, Claude conforms. See the
shorthand mapping below.

| Friendly intent | Canonical output |
|---|---|
| "sphere" / "ball" / "orb" | `"model": "builtin:sphere"` |
| "cube" / "box" / "block" | `"model": "builtin:cube"` |
| "cylinder" / "pillar" / "can" | `"model": "builtin:cylinder"` |
| "glowing red" | `"color": [1.0, 0.1, 0.1], "emissive": true` |
| "back-left" | `gx < 0`, `gz` near `D` |
| "near the glass / up front" | `gz` near `0` |
| "floating high" / "on the floor" | `gy` positive / `gy` near `−D/2` |

### Optional forward-compat: `metadata`

An additive, renderer-ignored `metadata` object is reserved for the friendlier authoring
surface and future tooling (provenance, source prompt, lock flags). Renderers and
`sanitize_objects` ignore unknown keys, so adding it is back-compatible:

```json
{ "id":"x","model":"builtin:sphere","grid_position":[0,0,4],
  "metadata": { "source_prompt": "a red orb in the middle", "locked": false } }
```

---

## 2. The coordinate convention (single source of truth)

**Centred integer grid cells.** `D = grid_divisions` (8 for the Grid Room).

```
gx ∈ [-D/2 .. +D/2]   left (−) → right (+)      0 = centre
gy ∈ [-D/2 .. +D/2]   down (−) → up (+)         0 = centre
gz ∈ [0 .. D]         GLASS (0, nearest) → BACK WALL (D, farthest)
```

This convention is stated to Claude (system prompt), enforced by `sanitize_objects`,
and is the input to **both** transforms below. There is exactly one depth convention:
**`gz = 0` is the glass (nearest the viewer).**

### Transform A — 3-D world (parallax): `grid_to_world`

```python
wx = (gx / (D/2)) * hw          # hw,hh = LIVE aperture half-extents
wy = (gy / (D/2)) * hh          #         (om.window_half_extents)
wz = -(gz / D) * depth          # glass at z=0, back wall at z=-depth
```

Consumed by `Engine/renderer.PlaceableObjects.draw` in world space, immediately after
`GridRoom`. Uses the live aperture so a cell at `±D/2` lands exactly on the rendered
side walls at any monitor aspect / calibration.

### Transform B — 2-D oblique grid (HUD): `grid_to_canvas_cell`

```python
cgx = gx + D/2                  # centred → corner origin (0..D)
cgy = gy + D/2
cgz = D - gz                    # DEPTH FLIP: glass(gz0)→front opening(cgz D),
                                #             back wall(gzD)→bright back grid(cgz0)
```

Consumed by `UI/demo_overlay._draw_builder_canvas`, fed into the canvas's 30° oblique
projection `P()`. The flip exists because the oblique canvas draws its bright
undistorted face as the **back wall**; without it, glass and back wall swap (the
historical bug — see [[WORLD_BUILDER_AUDIT]] R2).

### The invariant that ties them together

For any cell, both transforms agree on direction:

```
right in world (wx>0)        ⟺  right on grid (cgx > D/2)
up in world    (wy>0)        ⟺  up on grid    (cgy > D/2)
deeper in world (−wz larger) ⟺  deeper on grid (D − cgz larger)
```

Pinned by `Scripts/validation/sim_grid_api.py` §6 (27-cell sweep + monotonic-depth
check). **This is the guarantee behind the product promise:** *if an object appears at
a cell on the grid, it appears at that cell in the parallax world.*

---

## 3. Validation & clamping (the safety gate)

`Worlds.placeable.sanitize_objects(raw, divisions)` is pure, total, and crash-proof.
Both renderers call it, so neither can be handed something out of bounds:

- **Allowlist** `model` to the three primitives; unknown → skipped (never crash).
- **Clamp** `gx,gy ∈ [−D/2, D/2]`, `gz ∈ [0, D]`, `scale ∈ (0, 2.0]`, `color ∈ [0,1]³`.
- **Cap** the list at `MAX_OBJECTS = 64` (30 fps wallpaper budget on the 8 GB M2 target).
- **Skip** malformed entries individually — one bad object never takes down the scene.

Reliability is the product: a built-in primitive at an integer cell **always** renders
— no shader compile, no mesh import, no mid-demo failure mode.

---

## 4. Where each field is read (no duplication)

| Concern | Single owner |
|---|---|
| Object schema + clamp/allowlist/cap | `Worlds/placeable.py` `sanitize_objects` |
| Cell → 3-D world | `Worlds/placeable.py` `grid_to_world` |
| Cell → 2-D oblique grid | `Worlds/placeable.py` `grid_to_canvas_cell` |
| `placeable_objects` accessor (parallax) | `Worlds/world_runtime.py` `.placeable_objects` |
| Grid config (`grid_divisions`, `grid_depth`) | `world.json` `rendering` → both renderers read it live |

If a future field is added, it is added **once** in `placeable.py` and consumed by both
sides — never reintroduced as inline math in the HUD.

## Related
[[WORLD_BUILDER_AUDIT]] · [[grid-creator-tool-plan]] · [[grid-api-customization]] ·
[[world-system]] · [[WORLD_BUILDER_LIVE_REVIEW]] · [[constraints]]
