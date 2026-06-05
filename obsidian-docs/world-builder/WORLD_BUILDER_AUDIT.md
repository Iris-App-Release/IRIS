---
title: World Builder — Pipeline Audit
type: audit
related: [grid-creator-tool-plan, grid-api-customization, world-system, constraints, WORLD_SCHEMA, WORLD_BUILDER_LIVE_REVIEW, IMPLEMENTATION_ROADMAP]
last_updated: 2026-06-05
sources:
  - UI/demo_overlay.py
  - UI/world_builder_api.py
  - UI/canvas_mesh_renderer.py
  - Worlds/placeable.py
  - Worlds/world_runtime.py
  - Engine/renderer.py
  - Launcher/app_engine.py
  - Scripts/world_builder_cli.py
  - Scripts/validation/sim_grid_api.py
---

# World Builder — Pipeline Audit (Phase 1)

> **Purpose.** Map the *live* World Builder pipeline as it actually exists in the
> recovered `recover-newer-work` tree (not as older docs describe it), find why the
> central 30° oblique grid and the parallax preview were two disconnected
> representations of the same world, and record the unification fix. Every claim
> below was traced against source on 2026-06-05.

---

## 0. TL;DR

The generation half was already unified and correct. The **display** half was not.

- One generator (`generate_world_objects` → `sanitize_objects`) produces objects in
  one canonical cell convention.
- The **3-D parallax renderer** consumed them correctly, fully data-driven, via
  `Worlds.placeable.grid_to_world`.
- The **2-D oblique HUD grid** (`_draw_builder_canvas`) re-derived positions with
  ad-hoc inline math that **(a) inverted depth, (b) hardcoded `D=8`, (c) read a
  different source than the parallax**. So the grid could show nothing, or show
  objects at the wrong depth, while the parallax updated correctly.

**Fix (this sprint):** both renderers now derive every object position from ONE
shared transform pair in `placeable.py` (`grid_to_world` for 3-D, `grid_to_canvas_cell`
for the oblique grid), and the grid reads the *same* `grid_room/world.json` the
parallax renders. A new headless sim section pins the agreement. See §5.

---

## 1. The live pipeline (verified)

```
PROMPT
  ├─ in-app:  DemoOverlay._wb_prompt  → _wb_send()        [UI/demo_overlay.py]
  └─ CLI/skill: world_builder_cli preview/save            [Scripts/world_builder_cli.py]
        ↓
generate_world_objects(prompt, world_def)                 [UI/world_builder_api.py]
   • _resolve_api_key()  (env → ~/.iris/anthropic_key → ~/.iris/config.json)
   • anthropic.messages.create(claude-sonnet-4-6, cached system prompt)
   • _parse_json_objects()
   • sanitize_objects(raw, D)         ← clamp + allowlist + count-cap (SAFETY GATE)
        ↓
OBJECTS — canonical centred cells:  gx,gy ∈ [-D/2..D/2], gz ∈ [0..D]  (gz=0 = GLASS)
        ↓
  ┌─────────────────────────────────────────┬──────────────────────────────────────┐
  │  WRITE: grid_room/world.json             │  HOLD (in-app only):                  │
  │  assets.placeable_objects   (_write_     │  DemoOverlay._wb_preview_objects      │
  │  scratch / CLI cmd_preview)              │  (+ bump _wb_preview_gen)             │
  └─────────────────────────────────────────┴──────────────────────────────────────┘
        ↓                                              ↓
PARALLAX (3-D, GL)                              OBLIQUE GRID (2-D, HUD)
world_runtime.poll() mtime hot-reload          DemoOverlay._draw_builder_canvas()
 → app_engine room branch (line ~961)           → P() 30° oblique projection
 → PlaceableObjects.draw(objs, hw, hh,          → canvas_mesh_renderer.render_object
     grid_depth, grid_divisions)                  (cached 2-D sprites)
 → grid_to_world(gx,gy,gz, hw,hh,depth,D)
 → GL fixed-function draw
```

### Three rendering consumers

| Consumer | File / entry | Coordinate source | Data-driven? |
|---|---|---|---|
| 3-D parallax | `Engine/renderer.py` `PlaceableObjects.draw` (≈1503) | `placeable.grid_to_world` | ✅ live `hw/hh`, JSON `D/depth` |
| 2-D oblique grid | `UI/demo_overlay.py` `_draw_builder_canvas` (≈1764) | **inline ad-hoc math** (was) | ❌ `D=8` hardcoded (was) |
| 2-D object sprites | `UI/canvas_mesh_renderer.py` `render_object` | matches grid `P()` | n/a (geometry only) |

---

## 2. The four audit questions

**Q1 — Where are object coordinates generated?**
In `UI/world_builder_api.generate_world_objects`: Claude emits a JSON array, parsed by
`_parse_json_objects`, then **everything** passes through `Worlds.placeable.sanitize_objects`
(clamp to box, allowlist `builtin:{cube,sphere,cylinder}`, cap at 64). The output is the
canonical centred-cell schema. The CLI uses the identical call; `--objects` injects
hand-authored JSON through the *same* `sanitize_objects`, so dev/test output is byte-identical
to the app's.

**Q2 — How does the parallax preview consume them?**
`_wb_send` / `cmd_preview` write them into `Worlds/grid_room/world.json`
`assets.placeable_objects` and set the active world to `grid_room`.
`WorldRuntime.poll()` notices the `world.json` mtime change and hot-reloads in place;
`app_engine`'s `room` branch reads `world.placeable_objects` and calls
`PlaceableObjects.draw(...)`, which re-`sanitize`s and maps each cell with
`grid_to_world` using the **live** aperture `hw/hh` and JSON `grid_depth/grid_divisions`.
This path was correct and is unchanged.

**Q3 — Why was the grid renderer disconnected?** Five concrete defects, all in
`_draw_builder_canvas` (see §3).

**Q4 — Do duplicate world representations exist?**
Yes — three, only loosely coupled:
1. `_wb_preview_objects` (in-memory, in-app Send only).
2. `grid_room/world.json` `placeable_objects` (on disk; what the parallax reads).
3. The committed `Worlds/<slug>/world.json` after Save.
The in-app Send wrote (1) **and** (2); the CLI wrote only (2). The grid read (1)-first,
the parallax read (2)-only. So which copy was "truth" depended on the entry path — the
structural seam behind the visible disconnect.

---

## 3. Root causes (the disconnect)

| # | Defect | Evidence (pre-fix) | Effect |
|---|---|---|---|
| **R1** | **Two independent transforms.** Parallax used `grid_to_world`; the grid used inline `gx+D/2, gy+D/2, gz` feeding `P()`. Shared `sanitize_objects` but **not** placement. | `_draw_builder_canvas` lines ≈1900-1909 | Nothing structurally forced the two views to agree; they drifted. |
| **R2** | **Depth inverted.** Canvas `P()` draws its bright undistorted face as the **back wall** (canvas z=0) and the glass at canvas z=D; engine `gz=0` is the **glass**. Canvas passed `cgz=gz` with a comment claiming "same convention." | `grid_to_world`: `wz=-(gz/D)*depth` (glass z=0) vs canvas face labels | An object the parallax puts **near the glass** was drawn on the grid **at the back wall**, and vice-versa. |
| **R3** | **`D=8` hardcoded** in the grid. | `_draw_builder_canvas` first line `D = 8` | Grid ignored `grid_divisions` — it wasn't reading the world definition at all (only worked because grid_room is 8). |
| **R4** | **Depth ruler reversed.** Floor depth labels `1..D` increased from back→glass; engine `gz` increases glass→back. | depth-label loop + its own (wrong) comment | Reading "depth 7" off the grid produced an object at a *different* depth than the square implied — breaks the trust contract. |
| **R5** | **Dual read source.** Grid read `_wb_preview_objects` first, scratch JSON as fallback; parallax read scratch only. | `objs = self._wb_preview_objects` then fallback | The **CLI/skill path** (writes scratch only) was shadowed by any stale in-memory preview ⇒ "**grid does not update, only parallax updates**" — the exact reported symptom. |

### Numeric proof of R2 (depth inversion)

```
PARALLAX  glass (gz=0)     → world z = -0.0   (NEAR viewer)
PARALLAX  back wall (gz=D) → world z = -18.0  (FAR from viewer)
CANVAS    passes cgz = gz directly ("no flip"):
          engine glass (gz=0)     drawn at canvas BACK wall (bright grid)
          engine back wall (gz=D) drawn at canvas FRONT opening (glass)
⇒ an object at the GLASS in parallax is drawn at the BACK WALL on the grid. INVERTED.
```

---

## 4. What was NOT broken (don't "fix" these)

- The generator + safety gate (`generate_world_objects` → `sanitize_objects`).
- The 3-D parallax path (`PlaceableObjects.draw` → `grid_to_world`): fully data-driven, correct.
- The HUD render cache: `_signature()` already includes `_wb_preview_gen` **and**
  `_scratch_mtime()`, so cache invalidation on change was already correct (the grid *did*
  re-render; it just re-rendered with inverted/shadowed data).
- The frozen core (`camera_math`, shaders, physics) — untouched and out of scope.

---

## 5. The unification fix (this sprint)

Three files changed; no frozen module touched.

1. **`Worlds/placeable.py`** — added `grid_to_canvas_cell(gx, gy, gz, divisions)`: the
   pure, tested second half of the single source of truth. Encapsulates the origin
   shift (`+D/2`) **and** the depth flip (`cgz = D - gz`) so the oblique grid and the
   3-D world agree by construction. Sits beside `grid_to_world`; both are GL-free and
   headless-testable.

2. **`UI/demo_overlay.py` `_draw_builder_canvas`** —
   - Reads `D` **and** the objects from the same `grid_room/world.json` the parallax
     renders (single source of truth; kills R3 + R5). Falls back to `_wb_preview_objects`
     only if the file is momentarily unreadable.
   - Maps every object through `grid_to_canvas_cell` and `sanitize_objects` — the exact
     clamp/allowlist the GL renderer applies — so both views render an identical set
     (kills R1 + R2).
   - Depth ruler relabelled to engine `gz` units (1 = nearest glass, D = back wall),
     and painter order corrected (back→front) (kills R4).

3. **`Scripts/validation/sim_grid_api.py`** — new **section 6** asserts grid↔parallax
   sync: anchor correspondence (glass↔front, back↔back), X/Y/depth direction agreement
   across 27 sampled cells, and monotonic depth (a deeper cell is deeper in *both*
   spaces — the exact invariant R2 violated).

### Verification (headless)

| Check | Result |
|---|---|
| All 12 `sim_*.py` (incl. new sync section) | ✅ 12/12 pass |
| `world_builder_cli.py selftest` (data-plane) | ✅ pass |
| `grid_to_canvas_cell` vs `grid_to_world` agreement, 27 cells | ✅ all axes agree |
| `grid_room/world.json` after run | ✅ clean (`placeable_objects: []`) |

### Still requires a live GUI session (`/verify`)

The camera/GL behaviours are only real in the running app. To close Phase 9 visually:
generate a scene with a clear front/back/left/right object, confirm it lands on the
**same** square on the oblique grid and in the live Preview, that the anchored rim and
30 fps wallpaper hold, and that hot-reload from the CLI updates the grid (R5 regression
guard). See [[IMPLEMENTATION_ROADMAP]] §"Verification".

---

## 6. Status

| Item | State |
|---|---|
| Pipeline mapped | ✅ |
| Root causes identified | ✅ (R1–R5) |
| Single source of truth (transform) | ✅ `grid_to_canvas_cell` + `grid_to_world` |
| Single source of truth (data) | ✅ grid reads `grid_room/world.json` |
| Depth + ruler corrected | ✅ |
| Headless sync guard | ✅ `sim_grid_api.py` §6 |
| Live GUI visual verify | ⏳ needs `/verify` session |

## Related
[[grid-creator-tool-plan]] · [[WORLD_SCHEMA]] · [[WORLD_BUILDER_LIVE_REVIEW]] ·
[[IMPLEMENTATION_ROADMAP]] · [[world-system]] · [[constraints]]
