---
title: World Builder — Implementation Roadmap
type: roadmap
related: [WORLD_BUILDER_AUDIT, WORLD_SCHEMA, WORLD_BUILDER_LIVE_REVIEW, TEXT_TO_3D_RESEARCH, SCAN_IMPORT_ARCHITECTURE, grid-creator-tool-plan, productification, constraints]
last_updated: 2026-06-05
sources:
  - Worlds/placeable.py
  - UI/demo_overlay.py
  - Engine/renderer.py
  - Scripts/validation/sim_grid_api.py
---

# World Builder — Implementation Roadmap (Phase 8)

> A phased plan from "the grid and parallax finally agree" to "describe or scan any world".
> Each phase lists complexity, risk, and dependencies. The first two are **done this
> sprint**; the rest are sequenced so each de-risks the next.

```
[1] Grid synchronization        ✅ DONE  ── the trust foundation
[2] Unified world schema        ✅ DONE  ── one source of truth
        │
        ▼
[3] Improved object generation  ── determinism + structured output (cheap, high-value)
        │
        ▼
[4] Mesh-import core            ── GLB→VBO (the shared gate)
        │
        ├──▼ [4a] Text-to-3D integration (Tripo) ── "describe any object"
        │
        └──▼ [5] Scan importing (objects → rooms)  ── "scan your room"
```

---

## Phase 1 — Grid synchronization ✅ DONE

**Goal.** The oblique grid and the parallax preview show the same scene; a cell on the grid
is the cell in the world.

**Done:** `grid_to_canvas_cell` added to `placeable.py`; `_draw_builder_canvas` reads D +
objects from the same `grid_room/world.json` the parallax renders, maps through the shared
transform + `sanitize_objects`, depth flip + ruler corrected; `sim_grid_api.py` §6 pins the
sync invariant. **12/12 sims green.** See [[WORLD_BUILDER_AUDIT]].

- **Complexity:** M · **Risk:** Low (additive, frozen core untouched) · **Deps:** none.
- **Open:** live GUI `/verify` (camera/GL) — see Verification below.

## Phase 2 — Unified world schema ✅ DONE

**Goal.** One object schema + one coordinate convention consumed by both renderers.

**Done:** documented and enforced — `sanitize_objects` is the single safety gate;
`grid_to_world` (3-D) and `grid_to_canvas_cell` (grid) are the single transform pair. See
[[WORLD_SCHEMA]].

- **Complexity:** S (mostly codifying what the fix established) · **Risk:** Low · **Deps:** Phase 1.

## Phase 3 — Improved object generation

**Goal.** Make generation reproducible and the coordinates trustworthy.

**Scope** (from [[WORLD_BUILDER_LIVE_REVIEW]]): `temperature=0` (D1); few-shot spatial
anchors (C2); tool-use structured output matching the schema (C1); clamp-report so silent
"moved your object inside the box" corrections become visible (C5); deterministic ids +
stable ordering (D2/D3).

- **Complexity:** S–M · **Risk:** Low (authoring layer only; safety gate unchanged) ·
  **Deps:** Phase 2.
- **Gate:** the §9 reliability bake (10+ varied prompts, zero crashes / zero out-of-box
  escapes), all sims green.

## Phase 4 — Mesh-import core (the shared gate)

**Goal.** Load an external triangle mesh (GLB/GLTF/OBJ) and draw it in the frozen GL 2.1
renderer, cached and decimated.

**Scope** (from [[TEXT_TO_3D_RESEARCH]] §1 / [[SCAN_IMPORT_ARCHITECTURE]] §1): loader →
`Engine.renderer.Mesh(v,n,u,i)` (class exists) + texture upload (Earth path exists); extend
allowlist to `mesh:<asset_id>`; per-world `asset_dir` storage; content-hash cache;
vertex/triangle/texture caps; guard sim.

- **Complexity:** M · **Risk:** Med — PyInstaller bundling of the loader (`--collect-all`
  class of issue), perf caps on the 8 GB M2 target. · **Deps:** Phase 2.
- **Why first among the "big" features:** both Text-to-3D and Scan import ride on it.

## Phase 4a — Text-to-3D integration

**Goal.** "Describe any object" → a real generated mesh, behind Pro.

**Scope:** a `MeshProvider` abstraction; **Tripo AI** first (speed/cost/commercial);
cache by prompt+params; gate behind `Licensing/entitlement.py`; COGS channel (proxy / BYOK
/ hybrid — [[grid-creator-tool-plan]] §10.7). Free tier stays primitives (zero COGS).

- **Complexity:** M · **Risk:** Med (vendor API, COGS, latency UX) · **Deps:** Phase 4 + a
  payment/proxy decision.

## Phase 5 — Scan importing

**Goal.** Object scans → Grid Room / Void placeables; room scans → portal worlds (Apple
USDZ / RoomPlan hook).

**Scope** (from [[SCAN_IMPORT_ARCHITECTURE]]): S2 object scans (rides the placeable stack) →
S3 USDZ via Model I/O + RoomPlan plane shortcut → S4 room scans (RANSAC orient + bezel
anchor) → S5 gating/quota.

- **Complexity:** L · **Risk:** High for room alignment across messy scans (needs `/verify`);
  Low–Med for object scans. · **Deps:** Phase 4 (mesh core).

---

## Dependency graph

```
Phase 1 ─┬─ Phase 2 ─┬─ Phase 3  (parallel-able)
         │           └─ Phase 4 ─┬─ Phase 4a (Text-to-3D)
         │                       └─ Phase 5  (Scan import)
```

Phase 3 can proceed in parallel with Phase 4 (different layers). Phases 4a and 5 both
require Phase 4 and are independent of each other.

## Risk register (top items)

| Risk | Phase | Mitigation |
|---|---|---|
| Touching frozen core by accident | all | All work additive + fixed-function; `sim_*` frozen-invariance gate every commit. |
| Mesh perf blows the 30 fps wallpaper budget | 4 | Decimation + triangle/texture caps; reject too-heavy assets; `/verify` on M2. |
| PyInstaller misses a lazy-imported loader/native dep | 4,5 | `--collect-all` in `Iris.spec` (same pattern as pyobjc/anthropic). |
| COGS exceeds Pro price | 4a | Gate behind Pro; cache; finite `FREE_CUSTOMIZATION_LIMIT`. |
| Room-scan alignment is fragile | 5 | RoomPlan plane data shortcut; object scans first; robust fallbacks + `/verify`. |
| Generated content quality varies | 3,4a | Determinism (Phase 3); curated providers; reliability bake before charging. |

---

## Verification

**Headless (every commit):** all `Scripts/validation/sim_*.py` green, incl. `sim_grid_api.py`
§6 (sync) — currently **12/12**; plus `world_builder_cli.py selftest`.

**Live GUI (`/verify`, the one thing not yet done for Phase 1):** in the running app, build a
scene with distinct front/back/left/right/floor objects and confirm:
1. each object lands on the **same** square on the oblique grid and in the live Preview;
2. the depth ruler reads correctly (1 = glass, D = back wall);
3. a CLI `preview` hot-reloads the **grid** (not just the parallax) — the R5 regression guard;
4. anchored rim holds, no pan, 30 fps wallpaper budget intact;
5. spot-check `earth` / `the_watcher` (eye) / `gem` are visually unchanged (no `assets`
   block → empty placeable list → identical path; pinned headlessly by `sim_grid_api.py` §5).

## Related
[[WORLD_BUILDER_AUDIT]] · [[WORLD_SCHEMA]] · [[WORLD_BUILDER_LIVE_REVIEW]] ·
[[TEXT_TO_3D_RESEARCH]] · [[SCAN_IMPORT_ARCHITECTURE]] · [[grid-creator-tool-plan]] · [[productification]]
