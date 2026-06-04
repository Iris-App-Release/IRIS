---
title: Vital Source-Code Resurrection — 2026-06-04
type: incident-record
status: recovered
related: [version-control, current-focus, grid-creator-tool-plan, Claude-Interrupted]
last_updated: 2026-06-04
---

# Vital Source-Code Resurrection (world→portal incident)

> **One line.** A "rename world → portal" branding pass corrupted the launcher;
> the revert that followed buried a full day of *uncommitted* work (performance
> upgrade + redesigned World Builder UI). All of it was recovered from git
> objects and un-branded. Nothing was lost.

## What happened (timeline, 2026-06-03 → 06-04)

1. **03:03** — last clean commit `48f17f1` (World Builder canvas, premium gold panels).
2. **03:03 → 23:12 (≈20 h)** — large body of work done but **never committed**:
   - **Performance upgrade** — lazy asset loading (~870 MB saved for non-Earth
     worlds), occlusion-aware render pause (P2.1), per-call `glGetError` disabled
     in release (P1.4), icons-consumer pgrep guard (P1.3); `perf_reports/` + `Scripts/perf/`.
   - **Redesigned World Builder UI** — `demo_overlay.py` **+1174 lines**, the
     How It Works / Community / Send / Preview / Save World flow,
     `canvas_mesh_renderer.py`, `world_builder_api.py` (Claude authoring).
3. **23:12–23:15** — a case-insensitive `world → portal` rename was run across the
   tree and committed (`f50c88e` … `6c2c723`). **The first portal commit swept the
   entire uncommitted working tree into git** — so the new work was captured, just
   with "portal" text on top. The rename was **incomplete/inconsistent** (e.g.
   `Iris.spec` still named `Worlds.world_runtime` while the files were now
   `Portals/portal_runtime.py`) → **imports failed → launcher broken**.
4. **23:17** — the "fix" reverted the 4 portal commits back to `48f17f1`. This
   **also deleted all the uncommitted work** that had been swept into them. The app
   on disk fell back to a 2-day-old binary.

## Where the work actually was

- `48f17f1` = clean base (pushed to `origin/main`).
- **`6c2c723`** (last portal commit) = **the complete newer working tree**, just
  branded. `UI/demo_overlay.py` there is 106 KB (vs 59 KB at base) — the screenshot UI.
- Diff `48f17f1…6c2c723` = **72 files, 5 980 insertions** = everything thought lost.

## Recovery (branch `recover-newer-work`, commit `dfb2ace`)

Took `6c2c723`'s full tree and reversed **only** the branding:

- Case-preserving `portal → world` across code + content (16 files).
- Renamed back: `Portals/ → Worlds/`, `portal.json → world.json` (×4),
  `portal_builder_api → world_builder_api`, `portal_builder_cli → world_builder_cli`,
  skills `portal-builder* → world-builder*`.
- `Engine/camera_math.py` restored **byte-identical** from `48f17f1` (frozen).
- Preserved the legitimate **"panning a portal"** window metaphor in
  `camera_math.py`, `app_engine.py`, `sim_viewing.py`, `off-axis-projection.md`,
  `productification.md` (these predate the branding and are NOT renamed).

## Verification

- All modules compile + import; `Worlds.world_runtime` / `world_loader` /
  `world_builder_api` resolve.
- **All 12 validation sims green** (incl. `sim_world_builder.py`, `sim_offaxis.py`).
- `bash Build/build_dmg.sh` succeeds, signature valid (TCC camera grant intact).
- Runtime: `World system ready — available ['earth','gem','grid_room','the_watcher']`;
  lazy-load perf path active (`Scene ready (Earth/Nebula/Stars load on demand)`).

## Lessons / guardrails

- **Commit before any sweeping rename.** The damage was only possible because a
  day of work sat uncommitted; the rename + revert is otherwise harmless.
- A blanket find/replace of a core domain word ("world") across 300 K lines is
  never a "branding" task — it renames modules, files, dirs, JSON keys, and skill
  names, and *will* desync `Iris.spec` hiddenimports from the bundle.
- Safety tags kept during recovery: `safety-2026-06-03-prerecover`,
  `portal-work-snapshot` (= `6c2c723`).
