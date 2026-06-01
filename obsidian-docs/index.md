---
title: IRIS Wiki — Master Index
type: metadata
related: [system-interactions, design-decisions, worlds-index, docs-index, known_issues, current-focus, productification]
last_updated: 2026-05-31
sources: []
---

# IRIS Wiki — Master Index

This is the organized "brain" for **IRIS** — a head-tracked spatial desktop
("fish-tank VR") wallpaper for macOS. A webcam tracks your head; an off-axis
frustum re-renders a 3D world (Earth, or "The Watcher" eye) so the monitor reads
as a window into 3D space. IRIS runs as an interactive onboarding demo or a
click-through, always-on wallpaper. Three worlds ship: **Earth** (photo-real
globe), **The Watcher** (horror eyeball), and **The Gem** (rotating hot-pink
gemstone).

This wiki was compiled once by reading the whole `IRIS APP/` source tree. It is a
**read-only** reference — nothing here modifies the project. Pages cross-link with
Obsidian `[[wiki-links]]`; open this `obsidian-docs/` folder as (or inside) an
Obsidian vault to browse them as a graph.

## Start here

- New to the project? Read [Design Decisions](architecture/design-decisions.md)
  (the *why*) then [System Interactions](architecture/system-interactions.md)
  (how the pieces fit).
- Want the core illusion? [Off-Axis Projection](systems/off-axis-projection.md) +
  [Head Tracking](systems/head-tracking.md).
- Want the limits and gotchas? [Constraints](architecture/constraints.md).

## Systems

| Page | Summary | Type |
|---|---|---|
| [Off-Axis Projection](systems/off-axis-projection.md) | The Kooima "window" frustum + 3-component camera math that creates the illusion | system |
| [Head Tracking](systems/head-tracking.md) | Webcam → smoothed head 5-tuple (MediaPipe + Haar), threading, low-latency smoothing | system |
| [Rendering Engine](systems/rendering-engine.md) | Scene objects, GLSL 120 shaders, texture loading, and the bloom pipeline | system |
| [World System](systems/world-system.md) | JSON-defined, live-switchable worlds (content vs. engine) | system |
| [Engine Loop & Daemon](systems/engine-loop-and-daemon.md) | The frame-loop conductor (60 fps demo / 30 fps wallpaper): modes, the demo state machine, wallpaper/daemon, flag files | system |
| [UI Overlay](systems/ui-overlay.md) | The liquid-glass onboarding HUD over the live scene | system |
| [Orbital Icons](systems/orbital-icons.md) | In-scene GL icon ring + the standalone clickable Cocoa launcher | system |
| [Headless Simulation](systems/headless-simulation.md) | Six no-GPU validation sims that protect the frozen physics | system |
| [Asset Pipeline](systems/asset-pipeline.md) | Procedural texture generation, runtime loading, and the asset inventory | system |
| [Daemon Control](systems/daemon-control.md) | `parallaxctl` CLI driving the wallpaper via shared flag files | system |

## Worlds

| Page | Summary | Type |
|---|---|---|
| [Worlds Index](worlds/worlds-index.md) | Side-by-side comparison of all worlds + how to add one | world |
| [Earth](worlds/earth.md) | The flagship world: photo-real rotating Earth, stars, nebula, orbital icons | world |
| [The Watcher](worlds/the-watcher.md) | A giant unblinking eye in a black void (a reskin of the sphere pipeline) | world |
| [The Gem](worlds/gem.md) | A brilliant hot-pink rotating gemstone in pure white space (flat-shaded, two-light, fully procedural) | world |

## Releases

| Page | Summary | Type |
|---|---|---|
| [DMG Build Process](releases/dmg-build-process.md) | How `build_dmg.sh` + PyInstaller produce `Iris.app` / `Iris.dmg` | release |
| [Version History](releases/version-history.md) | The shipped DMGs (v0.0 → 1.3) and the productization arc (no git) | release |
| [Distribution Checklist](releases/distribution-checklist.md) | Steps to cut, verify, and ship a new build | release |

## Architecture

| Page | Summary | Type |
|---|---|---|
| [System Interactions](architecture/system-interactions.md) | Import chain, per-frame data flow, and the file-based message bus (diagrams) | architecture |
| [Constraints](architecture/constraints.md) | Viewing distance, latency, camera/permission, GL, platform, and memory limits | architecture |
| [Design Decisions](architecture/design-decisions.md) | The *why* behind every major architectural choice | architecture |

## Project status

| Page | Summary | Type |
|---|---|---|
| [Known Issues](known_issues.md) | Tracked bugs → root cause → fix (durable bug records) | reference |
| [Current Focus](development/current-focus.md) | What's actively being worked on right now | reference |
| [Productification Roadmap](productification.md) | Commercial progression path: milestones, business model, risks, immediate actions | strategy |

## Docs & metadata

| Page | Summary | Type |
|---|---|---|
| [Existing Docs Index](docs/docs-index.md) | Annotated map of the 12 hand-written source docs + preview screenshots | docs |
| [Ingestion Log](log.md) | Append-only record of how this wiki was built + maintained | metadata |
| [Handover](Handover.md) | Self-contained LLM context packet — system state, rules, decisions, next steps | metadata |

## How this wiki is organized

- **systems/** — the technical subsystems (one page each).
- **worlds/** — each playable world + a comparison index.
- **releases/** — building, versioning, and shipping.
- **architecture/** — the cross-cutting *how it fits* and *why*.
- **docs/** — a guide to the project's own pre-existing documentation.
- **development/** — active-work notes ([[current-focus]]); the root `known_issues.md` holds durable bug records.

Cross-references are bidirectional: if page A links to B, B links back to A. Every
page's frontmatter lists the `sources:` (the actual files read) so you can always
jump from the summary to the ground truth.
