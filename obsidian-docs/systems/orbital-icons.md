---
title: Orbital Icons
type: system
related: [off-axis-projection, rendering-engine, engine-loop-and-daemon, daemon-control, headless-simulation, earth, constraints]
last_updated: 2026-06-01
sources: [Engine/orbital_icons.py, Engine/renderer.py, Engine/camera_math.py, shaders/icon.vert, shaders/icon.frag]
---

# Orbital Icons

## Purpose

Orbital icons turn the wallpaper into a spatial app launcher: a ring of real
macOS application icons orbits the scene (around the Earth), tilted so it passes
in front of and behind the globe. The feature exists as **two complementary
implementations** — one for *looking* right and one for *clicking* right —
because doing both well at once is in tension on a click-through desktop layer.

Both source their apps from the **`/Applications/Orbital Apps/`** folder (real
`.app` bundles, symlinks, and Finder aliases are all resolved), and both derive
their geometry from the shared orbital constants in [[off-axis-projection]]
(`ORBIT_RADIUS = 4.2`, `ORBIT_TILT_DEG = 63°`, `ICON_WORLD_SIZE = 0.85`,
`ORBIT_SPEED = 0.22`).

## 1. In-scene GL icons (`renderer.IconOrbit`)

Part of [[rendering-engine]]. These are camera-facing billboards drawn in
**Earth-local space** — inside the very same modelview transform that positions
the Earth — so they inherit the Earth's parallax, projection, and depth as one
rigid body. The benefits are real-3D-correct:

- True **z-buffer occlusion** against the globe: the far arc of the ring passes
  behind the Earth and is hidden; the near arc passes in front.
- True perspective scaling, because the billboard keeps its real eye-space depth
  (the modelview's 3×3 is overwritten with a scaled identity, but the translation
  column — and thus depth — is preserved). As of 2026-06-01 the billboard is built
  **on the CPU**: the Earth-origin modelview is read **once** per frame and each
  icon's eye-space origin comes from a single mat·vec, replacing the former
  per-icon `glGetFloatv(GL_MODELVIEW_MATRIX)` (a GPU→CPU stall per icon). Result is
  pixel-identical; see the 2026-06-01 latency audit in [[log]] / [[constraints]].
- The icon shader **discards transparent texels** and writes `alpha = 0` — this
  was the anti-bloom mask that kept icons crisp instead of glowing. Bloom was
  removed engine-wide (2026-06-01), so the `alpha = 0` write is now **inert** but
  harmless; icons are crisp by default (see [[rendering-engine]]).

Crucially, the in-scene icons are **purely decorative and non-interactive**: the
engine installs no mouse monitor and runs no per-frame hit-testing on them,
because that added click latency and instability for zero benefit on a
click-through layer (mouse events pass straight through to Finder / apps). They
appear only on worlds with `show_icons` (i.e. [[earth]], not [[the-watcher]]) and
can be toggled off via `~/.parallax_icons_off`. Because the geometry comes from
[[off-axis-projection]], the live render is identical to the headless
verification in `sim_orbit.py` ([[headless-simulation]]).

## 2. Standalone Cocoa launcher (`Engine/orbital_icons.py`)

This is the *clickable* layer — a separate PyObjC Cocoa app (no OpenGL, no SDL,
no pygame). It runs as its own process and provides:

- A single transparent `NSWindow` covering the main screen, pinned at
  `kCGDesktopWindowLevel + 1` (above the wallpaper, below Finder icons and app
  windows) and **click-through** (`setIgnoresMouseEvents: YES`).
- A custom `NSView` that draws real system `NSImage`s (lightly desaturated so they
  don't glow on the dark desktop) in elliptical orbits at 60 Hz.
- **Click handling** via a global `NSEvent` monitor: it observes left-mouse-downs
  anywhere on screen, hit-tests them against the current icon positions, and
  launches the matching app with `NSWorkspace.openURL_`.

### Staying aligned with the 3-D scene

The standalone app has no GL context, yet its 2-D icon ring must line up exactly
with the GL Earth. It does this by reading **`~/.parallax_earth_state.json`** —
the live smoothed camera state that [[engine-loop-and-daemon]] exports every
frame — and projecting the Earth's world position to screen pixels with the
**exact same** `off_axis_frustum` / `view_matrix` / `project_point` math from
[[off-axis-projection]]. It applies the same 63° ring tilt, scales icon size and
alpha by depth, and fades far-side icons that overlap the Earth disk (occlusion).
A freshness check falls back to a neutral state if the export is older than 2 s
(i.e. the engine isn't running).

### Configuration & toggles

`~/.parallax_icons.json` sets the orbit radii, icon size, and speed (created with
defaults on first run). A 1 Hz watcher hides/shows the window from
`~/.parallax_icons_off`; another watches `/Applications/Orbital Apps/` for added
or removed apps.

## Why two implementations

The GL ring gives correct in-scene depth, parallax, and occlusion but is
deliberately non-interactive (clicking it would hurt latency). The Cocoa app adds
real, aligned clickability on top, sharing the same camera math so the two rings
coincide on screen. Together: visually integrated *and* actually launchable.

## Constraints

- macOS / PyObjC only; depends on the `/Applications/Orbital Apps/` folder being
  populated.
- The standalone app's alignment depends on a fresh camera-state export from a
  running engine (≤2 s old). See [[constraints]].

## Dependencies

- **Geometry:** [[off-axis-projection]] (shared orbital constants + projection).
- **In-scene variant:** lives in [[rendering-engine]]; verified by
  [[headless-simulation]] (`sim_orbit`).
- **Standalone variant:** consumes the camera state from
  [[engine-loop-and-daemon]]; toggled via the flags used by [[daemon-control]].
