---
title: UI Overlay (Demo HUD)
type: system
related: [engine-loop-and-daemon, head-tracking, world-system, headless-simulation, asset-pipeline, distribution-checklist]
last_updated: 2026-06-01
fixed: [font-fallback-bitmap, retina-best-res-surface, aa-rounded-corners, idle-fade-respects-hover]
sources: [UI/demo_overlay.py, Launcher/app_engine.py, Config/Strings.json, Docs/preview/]
---

# UI Overlay (Demo HUD)

## Purpose

The UI overlay *is* the onboarding experience. IRIS never shows a landing page or
a loading screen — the live world is always rendering, and the overlay floats a
light, translucent "liquid-glass" HUD on top of it. The design rule is that **the
illusion is the product**: the controls are deliberately understated and fade
when idle so the world stays the star.

It runs only in `demo` window mode and is composited each frame by
[[engine-loop-and-daemon]]. The file is `UI/demo_overlay.py`.

## Retina / HiDPI rendering

Three things caused pixelated text and buttons on Retina displays. All fixed
(2026-05-31). Diagnosed empirically by rendering the overlay to PNG and
inspecting 3× pixel-magnified crops of the button corners, plus a live probe of
the GL drawable size.

**Cause 1 — Font fallback to bitmap** (`UI/demo_overlay.py:_load_font`):
`pygame.font.SysFont` silently returns the default pygame bitmap font when a
name isn't found rather than raising, so the original `try/except` loop returned
on the very first iteration ("SF Pro Display") with the wrong font every time —
`match_font('SF Pro Display')` returns `None` on macOS, so `SysFont` quietly
handed back the bitmap default. Fixed by checking `match_font` before calling
`Font`, which correctly falls through to Helvetica Neue (found at
`/System/Library/Fonts/HelveticaNeue.ttc`).

**Cause 2 — The real Retina bug: GL surface was 1×, not 2×**
(`Launcher/app_engine.py`). The window opened at 1× backing and macOS upscaled
the whole thing 2× bilinearly — blurring the 3-D scene AND the overlay.

> ⚠️ **`ALLOW_HIGHDPI` is a no-op in pygame 2.6 on macOS.** An earlier fix ORed
> `SDL_WINDOW_ALLOW_HIGHDPI` (`0x2000`) into the `set_mode` flags. A live probe
> proved it does **nothing** — the GL drawable stayed 1× (`scale=1.0`) with or
> without it, even though the display's `backingScaleFactor` is 2.0. pygame's
> `set_mode` does not pass that bit through to SDL2's window creation.

The working fix is `_enable_retina_surface()`: it reaches the SDL content view
through Cocoa (`pygame.display.get_wm_info()["window"]` → `PyCapsule_GetPointer`
→ `objc.objc_object`), sets `view.setWantsBestResolutionOpenGLSurface_(True)`,
then refreshes the GL context with `NSOpenGLContext.currentContext().update()`.
That flips the GL drawable from 1× to 2× (verified: 400×300 → 800×600). Called
right after `set_mode` (before reading `_gl_drawable_size()`) and again after the
desktop-mode resize. See [[rendering-engine]] — this benefits every mode, not
just the overlay.

**Cause 3 — Aliased rounded-rect corners** (`UI/demo_overlay.py`):
`pygame.draw.rect(border_radius=…)` does **not** anti-alias its corners — they
stair-step into "fine pixel art" jaggies (clearly visible in the magnified
crops, even at 2×). Fixed with `_aa_round_rect()`, which renders each pill/panel
at `_AA_SS`× (4×) and `smoothscale`s it down, giving smooth corners at any
device scale. Only runs on dirty frames (the surface is cached), so the cost is
negligible.

Causes 1 and 2 compounded: the bitmap font rendered at 1× then macOS-upscaled 2×
= maximum blur. Cause 3 was independent and survived even once the scale was
correct.

## Button styling

The buttons are deliberately **solid white pills with crisp black text** — no
liquid-glass translucency (that was tried and dropped). On hover a button
**greys slightly** (`BTN_FILL_REST` 255→`BTN_FILL_HOVER` ~214 interpolated by the
existing per-button `hover_t` animation) and lifts with a **soft drop shadow**
(layered low-alpha rounded rects faking a blur). Text colour is black
(`BTN_TEXT`); the floating first-run hint is the one exception — it sits directly
on the scene, so it stays white with a drop shadow for legibility.

## Two layers (so the logic is testable)

The overlay is split so it can be exercised without a GPU:

- **Pure logic** — the state model, the scripted idle motion, hit-testing, and
  the 2-D surface composition (pygame only). This is headless-safe and is
  exercised by `sim_overlay.py` (see [[headless-simulation]]).
- **GL bridge** — `draw_gl()` uploads the composed pygame `Surface` to a texture
  and draws it as a single blended, screen-filling quad in the engine's GL 2.1
  context. It re-uploads only when the UI actually changed (a cached signature
  marks the surface dirty), and saves/restores the GL state it touches.

The surface is composed at **physical Retina resolution** (the window size × the
backing scale) so text stays crisp instead of being GL-upscaled.

## State machine

The demo has three instantly-switched states (never reloaded):

1. **Floating preview** (default) — no camera. The overlay feeds
   `scripted_head(t)` — gentle sine-wave motion
   (`hx = 0.14·sin 0.55t`, `hy = 0.07·sin 0.40t`, `hz = 0.06·sin 0.22t`) — into the
   *same* camera variables the tracker would, so the parallax is real and the
   idle scene looks alive. Status: "Floating preview"; button: "Enable Camera".
2. **Live tracked** — after "Enable Camera". Real [[head-tracking]] drives the
   parallax. The status pill is now **honest about the transition** (it used to
   read "Live" the instant the button was clicked, even when the camera never
   opened — the "Live status on, no tracking" bug):
   - **"Starting camera…"** while the grant settles and the first frames arrive;
   - **"Live · head tracking on"** once real head data actually flows (the engine
     calls `notify_tracking_active()` when `|hx|+|hy|+|hz| > 0`);
   - **"Camera access needed — enable it in System Settings"** if access was denied
     (the engine calls `notify_camera_denied()`); the overlay drops back to the
     scripted floating preview so the scene stays alive rather than freezing.
   Button: "Enable Desktop Mode".
3. **Desktop mode** — once the wallpaper is active, the overlay reverts to a
   passive floating preview and the button becomes "Disable / Resume Desktop
   Mode". Desktop-mode presence is auto-detected via the daemon PID file (or a
   `pgrep launcher.py` fallback in source runs).

## Signals the engine reads

The overlay never touches physics; the engine polls these public fields each
frame:

| Field | Meaning |
|---|---|
| `tracking_requested` | User asked to enable the camera |
| `desktop_mode_requested` | User asked to enable Desktop Mode |
| `should_quit` | ESC/Q pressed |
| `live` | User intent: floating preview (False) vs. camera enabled (True) |
| `tracking_active` | The engine calls `notify_tracking_active()` once real head data arrives → status promotes to "Live · head tracking on" |
| `camera_denied` | The engine calls `notify_camera_denied()` when authorization was denied/unavailable → status shows the System-Settings hint and reverts to the scripted preview |

## Controls

- **Status pill** (top-centre) and a first-run hint.
- **Primary CTA** whose label/action follow the state machine (Enable Camera →
  Enable Desktop Mode → Disable/Resume Desktop Mode).
- **Secondary row:** Browse Worlds, Settings, Community.
  - *Browse Worlds* opens a picker built from [[world-system]]'s `WorldLoader`;
    selecting a world writes `"world"` to `~/.iris/preferences.json`, which the
    engine polls live (no restart).
  - *Settings* exposes a Camera Access toggle that creates/removes
    `~/.iris/camera_off` — the same flag the engine and [[head-tracking]] respect.
    Disabling drops the overlay back to floating-preview mode (`live = False`).
    Re-enabling + clicking "Enable Camera" correctly resumes the existing tracker
    worker thread via `set_tracking(True)` without a full re-authorization cycle
    (the worker is paused, not exited, so permissions are preserved). See
    [[known_issues]] for the prior bug where this re-enable was silently blocked.
  - *Community* is a "coming soon" placeholder.
- **Toasts**, smooth per-button hover animation, and an **idle fade** (the control
  cluster dims to ~34% after 4 s of no input). The idle timer treats an **active
  hover as engagement** — while the cursor rests on any control, `idle` is held at
  0 so the cluster stays fully lit (a stationary mouse emits no `MOUSEMOTION`, so
  without this a held hover used to dim the whole layer after 4 s, which read as
  "the buttons grey out, over an area bigger than the hitbox" — see
  [[known_issues]]).

## Cross-process state it owns

Writes `world`, `onboarded`, and `camera_enabled` to
`~/.iris/preferences.json`; toggles `~/.iris/camera_off` (camera access) and
`~/.parallax_off` (pause/resume desktop mode); reads `~/.iris/daemon.pid` to
detect a running wallpaper. These are the same files documented in
[[engine-loop-and-daemon]].

UI text is loaded from `Config/Strings.json`, with a complete built-in string
table as a fallback if that file isn't present.

## Constraints

- `demo` mode only; the wallpaper/fullscreen modes draw no HUD.
- Uses macOS system fonts (SF Pro Display/Text, falling back to Helvetica/Arial).
- The reference screenshots in `Docs/preview/` (`overlay_*`, `world_picker_open`)
  capture these states.

## Dependencies

- **Composited by:** [[engine-loop-and-daemon]].
- **Drives:** [[world-system]] (world selection), [[head-tracking]] (camera
  enable/disable).
- **Verified by:** [[headless-simulation]] (`sim_overlay` renders the HUD to PNG
  and checks the state machine without a GL context).
