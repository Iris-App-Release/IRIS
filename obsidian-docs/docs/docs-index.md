---
title: Existing Docs Index
type: docs
related: [system-interactions, design-decisions, orbital-icons, engine-loop-and-daemon, dmg-build-process, ui-overlay]
last_updated: 2026-05-31
sources: [Docs/, PRODUCTIZATION_PHASE_SUMMARY.md, Docs/preview/]
---

# Existing Docs Index

The IRIS source tree already contains hand-written documentation in `Docs/` (plus
one summary at the project root). This page catalogs them and points each to the
wiki page that covers the same topic in its **current** form. The originals are
left untouched; where a source doc and the live code differ, the wiki pages
describe what the code does today.

## Overview & architecture

| Doc | What it covers | See also |
|---|---|---|
| `Docs/IRIS_OVERVIEW.txt` | The master "north star": product vision, the physics of head-coupled parallax, tracking, rendering, folder layout, the production/business plan, and a decision-history section. | [[design-decisions]], [[off-axis-projection]], [[head-tracking]], [[rendering-engine]] |
| `Docs/ARCHITECTURE_OVERVIEW.txt` | High-level folder structure and the five design principles (frozen physics, modular systems, PyInstaller-safe lowercase dirs, single entry point). | [[system-interactions]], [[constraints]] |
| `Docs/SYSTEM_FLOW.txt` | How the app starts, the main render loop, the demo state machine, and the wallpaper daemon behaviour. | [[engine-loop-and-daemon]], [[ui-overlay]] |
| `Docs/FILE_MAP.txt` | Quick one-liner reference for every major source file and the critical imports not to break. | [[system-interactions]] |

## Productization & packaging

| Doc | What it covers | See also |
|---|---|---|
| `PRODUCTIZATION_PHASE_SUMMARY.md` (root) | "Phase 2" summary: introducing the JSON world system and a launcher entry point as additive foundation layers. | [[world-system]], [[version-history]] |
| `Docs/FIRST_LAUNCH_AND_DMG_DESIGN.md` | The packaging + onboarding + product-UX design and roadmap: the DMG installer, the `.app` structure, the four-screen first-launch flow, the permission system, desktop-mode activation, settings, and the M0–M7 milestones. The richest source for *why* the demo/glass-UI and packaging are the way they are. | [[ui-overlay]], [[engine-loop-and-daemon]], [[dmg-build-process]], [[distribution-checklist]], [[design-decisions]] |

## Orbital-icon synchronization

These four document the orbital-icon ↔ Earth synchronization work and its
verification. They describe the icon system's coordinate/transform sharing; the
**current** implementation (in-scene GL billboards + the standalone clickable
Cocoa launcher) is described in [[orbital-icons]], and the rationale for its
evolution is in [[design-decisions]].

| Doc | What it covers | See also |
|---|---|---|
| `Docs/EARTH_ICON_SYNC.md` | The architecture for icons inheriting the Earth's transforms, including the exported camera-state file and the `/Applications/Orbital Apps/` folder integration. | [[orbital-icons]], [[system-interactions]] |
| `Docs/IMPLEMENTATION_SUMMARY.md` | Detailed change log for that synchronization work (functions added, data-flow diagram, performance budget). | [[orbital-icons]] |
| `Docs/IMPLEMENTATION_CHECKLIST.md` | Point-by-point verification checklist for the same work. | [[orbital-icons]] |
| `Docs/ICON_GL_MERGE_PLAN.md` | A design/scratch plan (marked "do not ship") for folding the icons into the GL scene as real depth-tested geometry — the rationale that produced today's `renderer.IconOrbit`. Also contains a historical note from a prior session flagging an anomalous file read. | [[orbital-icons]], [[design-decisions]] |

## Testing

| Doc | What it covers | See also |
|---|---|---|
| `Docs/LIVE_TEST_GUIDE.md` | Step-by-step live testing procedures and acceptance criteria for the icon-sync / parallax behaviour. | [[orbital-icons]], [[head-tracking]] |
| `Docs/TESTING_SHORTCUTS.md` | Reference for the double-clickable `.command` test shortcuts and CLI/monitoring commands. (The current CLI control surface is [[daemon-control]]; the legacy `.command` scripts live in `Archive/`.) | [[daemon-control]] |

## Visual references (`Docs/preview/`)

Rendered PNG snapshots used to review the UI without launching the GL window
(produced by `preview_overlay.py` — see [[asset-pipeline]] and [[ui-overlay]]):

- `overlay_1_floating.png`, `overlay_2_live.png`, `overlay_3_desktop.png` — the
  three demo HUD states.
- `overlay_1_alive.png`, `overlay_2_permission.png`, `overlay_3_active.png` — an
  earlier four-screen onboarding sequence.
- `world_picker_open.png` — the Browse Worlds picker.
- `the_watcher_front_preview.png` — a render of the [[the-watcher]] eye.

## Related

[[system-interactions]] · [[design-decisions]] · the [main index](../index.md)
