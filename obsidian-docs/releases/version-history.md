---
title: Version History
type: release
related: [dmg-build-process, distribution-checklist, design-decisions, world-system, the-watcher, known_issues, productification]
last_updated: 2026-05-31
sources: [dist/, Build/build_dmg.sh, PRODUCTIZATION_PHASE_SUMMARY.md, Docs/FIRST_LAUNCH_AND_DMG_DESIGN.md]
---

# Version History

## Source of truth

The project is **not under git**, so there is no commit log to mine. This history
is reconstructed from the build artifacts in `dist/`, the `VERSION` in
[[dmg-build-process]], and the dated design/summary docs. Treat the per-version
detail as best-effort, not an authoritative changelog.

## Shipped DMGs (in `dist/`)

| Version | Artifact | Size | Notes |
|---|---|---|---|
| v0.0 | `Iris-v0.0.dmg` | ~262 MB | First end-to-end bundle |
| 1.1 | `Iris-1.1.dmg` | ~134 MB | Bundle roughly halved vs v0.0 |
| 1.2 | `Iris-1.2.dmg` | ~134 MB | — |
| 1.3 | `Iris-1.3.dmg` | ~134 MB | — |
| 1.4 | `Iris-1.4.dmg` | ~134 MB | **Camera-permission fix** — "Enable Camera" now surfaces the TCC dialog and head tracking starts (also fixes tracking-less Desktop Mode). Built 2026-05-31. See [[known_issues]]. |
| 1.5 | `Iris-1.5.dmg` | 128 MB | **Settings camera toggle re-enable fix** — disabling then re-enabling the camera from Settings and clicking "Enable Camera" now correctly resumes head tracking. Built 2026-05-31. See [[known_issues]]. |

v0.0–1.3 were built on 2026-05-30, **1.4** and **1.5** on 2026-05-31; the current
`Build/build_dmg.sh` produces **1.5**. The ~128 MB size drop after v0.0 is visible in the artifacts (likely the
move to a leaner bundle — e.g. `opencv-python-headless` and a single-arch build);
the intermediate `Iris/` onedir folder in `dist/` is the unpacked PyInstaller
output, not a release.

## The arc (from the design/summary docs)

The dated docs describe the trajectory the builds followed:

- **Engine core (pre-productization).** The head-tracked parallax engine — the
  off-axis frustum, three-component blend, MediaPipe tracking, Earth rendering,
  bloom — was built and calibrated first, then "frozen." See
  [[off-axis-projection]], [[head-tracking]], [[rendering-engine]].
- **Productization Phase 2.** Introduced the JSON [[world-system]] (separating
  content from engine) and a launcher entry point, as recorded in
  `PRODUCTIZATION_PHASE_SUMMARY.md`.
- **First-launch / DMG productization (2026-05-30, M0–M2).** Replaced the old
  dark 2-D launcher with the in-process "demo behind glass UI" model
  ([[ui-overlay]]), added the `demo` engine mode, and stood up the PyInstaller +
  DMG packaging. See [[design-decisions]] and `Docs/FIRST_LAUNCH_AND_DMG_DESIGN.md`.
- **Second world.** [[the-watcher]] was added on top of the world system,
  exercising it as a true content layer beyond Earth.

## Naming

The product surface is **Iris**; the engine's internal identifiers and flag files
still use the original "parallax" working title (e.g. `~/.parallax_off`), and the
window caption in non-demo modes reads "Parallax Wall." This split is intentional
(see [[design-decisions]]).

## Dependencies

Produced by [[dmg-build-process]]; shipping steps in [[distribution-checklist]]. Commercial progression and milestone planning in [[productification]].
