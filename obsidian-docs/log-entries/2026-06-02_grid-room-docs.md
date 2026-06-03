---
title: "2026-06-02 — Docs: The Grid Room — world page + index integration"
type: log-entry
date: 2026-06-02
category: docs
---

# The Grid Room — world page + index integration

**Scope.** The Grid Room world (`Worlds/grid_room/world.json`, `GridRoom` renderer
class in `Engine/renderer.py`) existed in the source tree and was documented in
the architecture-layer [[grid-api-customization]] page but was **not documented as
a playable world**. Created a dedicated world page and updated all world-related
indexes to list it as the fourth available world.

## Created

- **New page:** `obsidian-docs/worlds/grid-room.md` — comprehensive world reference
  (92 KB) covering what the Grid Room is (spatial-reference scaffold), how it renders
  (wireframe cyan `GL_LINES` shadow-box in world space), dimensions (±11.33 × ±6.375
  × 18 deep, 8×8 grid cells), constraints (no shaders, alpha fade front→back, mesh
  cached), and integration with parallax. Related links tie it to [[gem]] (which shares
  grid dimensions), [[grid-api-customization]], and [[world-system]].

## Updated

- **`obsidian-docs/index.md`:** Intro text updated "Three worlds ship" → "Four worlds
  are available". Added Grid Room row to the worlds table (summary: "wireframe
  spatial-reference calibration tool").
- **`obsidian-docs/worlds/worlds-index.md`:** Expanded comparison table from 3 columns
  to 4. Now includes Grid Room properties: `primary_mesh: "room"`, `GridRoom` renderer,
  **no shaders** (fixed-function only), cyan color, 18.0 depth, 8 divisions (matching
  Gem), use case (reference/calibration vs. scenic). Updated intro to "Four worlds:
  three scenic, one utility/calibration". Updated "Systems every world uses" and
  "Adding a world" sections to list `room` as a valid `primary_mesh` type.
- **Related links:** Backlinks added to [[gem]] (which references grid dimensions),
  [[grid-api-customization]] (the design-decision that describes the grid API), and
  [[world-system]].

## Design notes

The Grid Room is **not a scenic experience** but a **spatial-reference utility and
API surface** for the [[grid-api-customization]] safe-customization framework. Its
receding wireframe grid teaches users/Claude the coordinate system directly on
screen; the converging lines provide the parallax illusion with a strong motion-
parallax cue; the rigid box helps the visual system distinguish head motion from
tracking jitter. No shaders (frozen GLSL is untouched); fully procedural geometry
(cached based on aperture dimensions, rebuilt only on resize). The cyan color was
chosen to complement both white-background worlds ([[gem]]) and blue starfields
([[earth]]).

**Wiki updated.** `[[grid-room]]` (new page), `[[worlds-index]]`, `[[index.md]]`,
and this log entry.
