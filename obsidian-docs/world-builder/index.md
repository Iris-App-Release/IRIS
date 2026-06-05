---
title: World Builder — Unification Sprint (index)
type: index
related: [WORLD_BUILDER_AUDIT, WORLD_SCHEMA, WORLD_BUILDER_LIVE_REVIEW, TEXT_TO_3D_RESEARCH, SCAN_IMPORT_ARCHITECTURE, IMPLEMENTATION_ROADMAP, grid-creator-tool-plan]
last_updated: 2026-06-05
sources: []
---

# World Builder — Unification Sprint

The 2026-06-05 sprint that closed the **grid ↔ parallax disconnect** and charted the path
to generated + scanned worlds. Build docs for the existing feature live in
[[grid-creator-tool-plan]]; these are the unification audit, the unified schema, and the
forward research/roadmap.

| Doc | Phase | What it is |
|---|---|---|
| [[WORLD_BUILDER_AUDIT]] | 1 | Live pipeline map; the 5 root causes of the disconnect; the fix + headless verification. |
| [[WORLD_SCHEMA]] | 2 | The single object schema + single coordinate convention both renderers consume. |
| [[WORLD_BUILDER_LIVE_REVIEW]] | 5 | Review of the generation path; concrete coordinate-confidence + determinism improvements. |
| [[TEXT_TO_3D_RESEARCH]] | 6 | Cloud text-to-3D landscape (2026); why local is impossible on Apple Silicon; Tripo = best fit. |
| [[SCAN_IMPORT_ARCHITECTURE]] | 7 | GLB/USDZ room + object scan import; the Apple RoomPlan hook; bezel-anchored portal worlds. |
| [[IMPLEMENTATION_ROADMAP]] | 8 | Phased plan (status, complexity, risk, deps) from the shipped sync fix to scans. |

## What shipped this sprint (code)

- `Worlds/placeable.py` — `grid_to_canvas_cell` (the shared transform; single source of truth).
- `UI/demo_overlay.py` — `_draw_builder_canvas` reads one source (grid_room `world.json`),
  uses the shared transform + `sanitize_objects`, depth flip + ruler corrected.
- `Scripts/validation/sim_grid_api.py` — §6 grid↔parallax sync guard. **12/12 sims green.**

## Still open

- Live GUI `/verify` of Phase 1 (camera/GL session) — see [[IMPLEMENTATION_ROADMAP]] §Verification.
- Phases 3 → 5 (generation hardening → mesh core → text-to-3D / scans).
