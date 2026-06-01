---
title: Engine Loop & Daemon
type: system
related: [head-tracking, off-axis-projection, rendering-engine, world-system, ui-overlay, orbital-icons, daemon-control, system-interactions, constraints]
last_updated: 2026-06-01
sources: [Launcher/app_engine.py, Launcher/app_entry.py, launcher.py]
---

# Engine Loop & Daemon

## Purpose

This is the conductor. Everything else in IRIS is a component; the engine loop is
what wires them together each frame: read [[head-tracking]] → compute the
[[off-axis-projection]] matrices → tell [[rendering-engine]] what the
[[world-system]] selected → present to screen, then composite the
[[ui-overlay]] on top. It also owns the app's three runtime *personalities*
(onboarding demo, in-process wallpaper, detached daemon) and the live flag-file
toggles that switch between them.

The core file is `Launcher/app_engine.py`.

## Entry chain

The bundled `.app` executable runs a thin router, not the engine directly:

```
Iris.app  →  launcher.py (root)         # ensures project root / _MEIPASS on sys.path
          →  Launcher/app_entry.py      # picks the mode, defaults to "demo"
          →  Launcher/app_engine.main() # the frame loop (60 fps demo / 30 fps wallpaper)
```

A single bundled binary serves every mode; `app_engine.py` reads the
`PARALLAX_MODE` environment variable **at import time**, so the router must set it
before importing the engine.

## Display modes (`PARALLAX_MODE`)

| Mode | Window | Use |
|---|---|---|
| `demo` | Centred, focusable ~1180×760 window with the onboarding overlay | First-launch experience (the default) |
| `wallpaper` | Borderless (`NOFRAME`), pinned to the macOS desktop window level, click-through | The always-on background |
| `fullscreen` | True fullscreen; ESC/Q quits | Testing / kiosk |

`PARALLAX_DAEMON=1` additionally hides the process from the Dock and Cmd-Tab
(accessory activation policy). `PARALLAX_ICON_DEBUG=1` draws the orbital ring
guide.

## Startup sequence

1. `pygame.init()`, request an **OpenGL 2.1 compatibility** context with 4× MSAA.
2. Size the window per mode; read the **Retina drawable** size from the live GL
   viewport (handles 2× backing).
3. Set standing GL state (depth test `LEQUAL`, perspective-correction hint,
   clear colour, multisample).
4. Build the scene objects (`Nebula`, `Stars`, `Earth`, `IconOrbit`; the `Eye` is
   built lazily on first use of The Watcher), the `WorldRuntime`
   ([[world-system]]), the `BloomPipeline` (with graceful fallback), the
   `FaceTracker` ([[head-tracking]]), and — in demo mode — the `DemoOverlay`
   ([[ui-overlay]]).

## Frame rate

The loop is capped per mode via `clock.tick(target_fps)`: **`FPS_DEMO = 60`** for
the interactive onboarding demo, **`FPS_WALLPAPER = 30`** for wallpaper,
fullscreen, and the in-process desktop wallpaper (`desktop_active`). The 30 Hz
wallpaper cap matches the ~30 Hz [[head-tracking]] input — a 60 Hz render simply
redrew every parallax frame twice from identical head data, doubling GPU and
macOS WindowServer compositing cost for no visible benefit (it was the main cause
of desktop stutter while other apps were open). See [[constraints]] and the
2026-06-01 perf pass in [[log]].

## The frame loop

Each frame runs four stages:

1. **Input** — pump pygame events (quit, ESC/Q in demo/fullscreen only), forward
   mouse/keyboard to the overlay.
2. **Mode control** — either the demo state machine (Enable Camera / Enable
   Desktop Mode / quit) *or* the wallpaper/fullscreen flag toggles (below).
3. **Camera update** — blend the three viewing components into smoothed
   `cam_x/y/z`, `cam_yaw/pitch`, then export the camera state to a file for the
   separate icons app.
4. **Render** — clear with the per-world colour, build the off-axis projection +
   view modelview, rotate the sun into eye space, draw background + primary mesh
   (+ icons), run bloom to screen, composite the HUD, and `flip()`.

### Applying the camera math

[[off-axis-projection]] supplies the matrix forms; the loop supplies the *feel*
via these constants and rules:

- **Translation** — `cam_x/y` follow head position (`MAX_SHIFT = 4.5`, vertical
  scaled ×0.55), smoothed by `CAM_LAG = 0.55`. The horizontal axis is negated to
  correct for the mirrored webcam image.
- **Distance scaling** — `cam_z = BASE_Z · e^(ZOOM_K · hz)` (`BASE_Z = 11.5`,
  `ZOOM_K = 0.95`, clamped to `[5.0, 34.0]`). Exponential so leaning is
  perceptually uniform; the *same* `cam_z` also couples parallax strength to
  distance, exactly as window optics do.
- **Rotation** — proximity-gated via `om.proximity(hz)`. Yaw uses `ROT_MAX_DEG`
  (20°); **vertical gets its own larger gain** (`ROT_MAX_PITCH_DEG = 40°`,
  hard-clamped to `46°`) so the viewer can peer up/down enough to push the Earth
  off-screen up close. A proximity-scaled **pitch re-zeroing** (`LOOK_PITCH_OFFSET
  = 0.25`) makes "resting your gaze on the planet" the neutral pose — compensating
  for the webcam sitting above the screen while the planet renders near centre.

### World compositing

The frustum, modelview, and sun are **world-agnostic** — only the drawn assets
change, so every world shares the identical parallax/zoom/rotation feel:

- Background `stars` → draw the `Nebula` (anchored to the camera so it feels
  infinitely distant) plus the parallax `Stars`. Background `void` → draw
  nothing; the black clear colour *is* the scene.
- Primary body at the fixed Earth anchor (`z = -10`): `eye` → the lazily-built
  `Eye` (falling back to Earth if its shader/textures fail); otherwise the
  `Earth`, with [[orbital-icons]] drawn inside the same transform when
  `show_icons` is set and the icons aren't toggled off.

`world.poll()` re-reads the active-world preference each frame (cheap,
mtime-cached) so switches take effect live.

## Three ways to become the wallpaper

- **In-process Desktop Mode (current path).** The demo's "Enable Desktop Mode"
  button reconfigures **this same window** into a fullscreen, borderless,
  desktop-level, click-through wallpaper — *in the same process*. The already-
  authorized camera keeps running; SDL preserves the GL context and textures, so
  only the size-dependent bloom FBO is rebuilt. The window stays in the Dock so
  the user can always quit it (and quitting exits everything cleanly).
- **Detached daemon.** [[daemon-control]] (`parallaxctl start`) launches a
  separate `PARALLAX_MODE=wallpaper PARALLAX_DAEMON=1` process, tracked by
  `~/.iris/daemon.pid`, logging to `~/.iris/daemon.log`.
- **Direct.** Running with `PARALLAX_MODE=wallpaper` (or `fullscreen`) starts the
  engine straight into that mode.

## Live flag files

The loop polls these every frame, so external changes take effect instantly in
both the demo and any wallpaper process:

| File | Effect |
|---|---|
| `~/.parallax_off` | Master pause — hide the window (real macOS wallpaper shows through) and release the camera |
| `~/.parallax_icons_off` | Hide the orbital icons only |
| `~/.iris/camera_off` | Camera-access switch (Settings): keep rendering but never open the camera; head drifts to idle |
| `~/.iris/preferences.json` | User prefs, including the active `world` |
| `~/.parallax_earth_state.json` | *Written by* the engine (throttled to ≤30 Hz) — the live smoothed camera state, so the standalone [[orbital-icons]] Cocoa app can align its 2-D projection. Writing faster than the ~30 Hz head input just re-serialised identical values to disk in the render thread |

## Frame loop data flow

The frame loop (60 fps demo / 30 fps wallpaper) wires together all the major systems:

| Step | Consumes | Produces | Feeds |
|---|---|---|---|
| 1. Camera read | [[head-tracking]].head() → (hx, hy, hz, yaw, pitch) | Smoothed head state | internal blend |
| 2. Parallax math | Head 5-tuple | `cam_x`, `cam_y`, `cam_z`, `cam_yaw`, `cam_pitch` | [[rendering-engine]] |
| 3. Projection | `cam_*` vars | Projection matrix from [[off-axis-projection]] | [[rendering-engine]] + bloom |
| 4. Modelview | `cam_*` vars | Modelview matrix from [[off-axis-projection]] | [[rendering-engine]] |
| 5. World pick | `~/.iris/preferences.json` | Active world description | [[world-system]] |
| 6. Eye tracking | Head `(hx, hy)` | → Eye.update(dt, hx, hy) | [[the-watcher]] Eye class |
| 7. Render scene | All above + time | Framebuffer + depth | Bloom FBO |
| 8. Bloom | Scene FBO | Bright-pass + blur + composite | Onscreen |
| 9. HUD overlay | User interaction | Final frame | Screen flip |
| 10. Export state | Smoothed camera `cam_x`, `cam_y`, `cam_z` | `~/.parallax_earth_state.json` | [[orbital-icons]] Cocoa app |

## Constraints

- Keyboard quit works only in `demo`/`fullscreen`; the `wallpaper` window has no
  focus, and daemon mode never quits on keys.
- Desktop-level pinning and Dock-hiding are Cocoa-only (macOS). See
  [[constraints]].
- Single-camera ownership: the camera must be released by one consumer before
  another can open it — see [[head-tracking]].

## Dependencies

Orchestrates [[head-tracking]], [[off-axis-projection]], [[rendering-engine]],
[[world-system]], [[ui-overlay]], and (via the exported state file)
[[orbital-icons]]. Controlled out-of-band by [[daemon-control]]. Packaged by
[[dmg-build-process]].
