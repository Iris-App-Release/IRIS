---
title: UI Overlay (Demo HUD)
type: system
related: [engine-loop-and-daemon, head-tracking, world-system, headless-simulation, asset-pipeline, distribution-checklist]
last_updated: 2026-06-03
fixed: [font-fallback-bitmap, retina-best-res-surface, aa-rounded-corners, idle-fade-respects-hover, instant-hover-no-easing]
sources: [UI/demo_overlay.py, Launcher/app_engine.py, Config/Strings.json, Docs/preview/]
---

# UI Overlay (Demo HUD)

## Purpose

The UI overlay *is* the onboarding experience. IRIS never shows a landing page or
a loading screen — the live world is always rendering behind the HUD. The UI is
organised as a **four-tab app** (Worlds · World Builder · Community · Settings)
sitting over the scene. On the **Worlds** tab the design rule still holds — **the
illusion is the product**: the controls are understated pills and the HUD
idle-fades so the world stays the star. The **Community** and **Settings** tabs
are solid full-page cards; the **World Builder** tab is a full white page with a
2-D grid canvas (its *Preview* sub-view re-renders the live grid world). While a
full-page tab is showing the live 3-D preview is suspended unless it is the World
Builder *Preview* (see *World-preview suspend* below).

It runs only in `demo` window mode and is composited each frame by
[[engine-loop-and-daemon]]. The file is `UI/demo_overlay.py`.

The visual language (refit 2026-06-03 to **grayscale-minimal** — see *Button
styling*): controls render through the shared `Button` primitive in
`UI/buttons.py`, sitting on opaque mid-grey rounded containers, with an instant
drop shadow on hover. The lone chromatic accent is the World Builder canvas's
premium golden-yellow side panels. Corner radii (`_BTN_CORNER` / `_PANEL_CORNER`
/ `_TABBAR_CORNER`) are dialed-in; the Button primitive itself uses a 7.2 px
radius.

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

> 🔄 **Refit to a grayscale-minimal Button system (2026-06-03).** The buttons no
> longer hand-roll a "solid white pill" in `demo_overlay.py`; they all render
> through the shared **`Button` primitive in `UI/buttons.py`** — four variants
> (PRIMARY solid · SECONDARY outlined · DESTRUCTIVE red · MUTED), three sizes
> (sm/md/lg = 12/14/16 px), a subtle **7.2 px** radius, and shadows that are
> none-at-rest / soft-lift-on-hover / tight-inset-on-press. This was an explicit
> design request that overrode the previously-frozen white-pill language and
> iPhone radii.

The palette was **de-blued to neutral near-black `#252525`** (the bluish
`#363D52`/`#454F66` tones were dropped). Mapping of the HUD's controls (all via
`_draw_btn`, which feeds each Button the overlay's existing instant-hover state so
hit-testing and look stay in lock-step):

| Control | Variant · palette |
|---|---|
| **Occupied** tab | `primary` light → **black** fill, white text |
| **Inactive** tabs | `primary` dark → **white** fill, black text |
| Bottom action pill, "Preview", "Back to Canvas" | `primary` dark (white pill) |
| Nav arrows | `muted` dark (solid near-black) + hand-drawn glyph |
| Camera toggle — **On** / **Off** | `primary` (filled) / `secondary` (outlined) |

The tab scheme is **inverted**: the occupied tab is a black pill (white text) and
the others are white pills (black text), on a **lighter opaque mid-grey** bar
(`GREY_CONTAINER` = `(80,82,90)`). Those grey containers survive as **structural
backings** behind the tab bar / action group / toast / Preview button, keeping
labels legible over an arbitrary live scene; they are not buttons. There is no
world-name pill anymore — the active world is announced only by a toast.

> 🟡 **World Builder canvas accent.** The grid canvas adds two big premium
> **golden-yellow** side panels (`PREMIUM_GOLD` `#ECA31E`, the user's supplied
> swatch) with a border a few shades darker (`PREMIUM_GOLD_BORDER`) and bold navy
> titles. This is the *only* non-grayscale surface in the HUD.

> ⚡ **Hover is INSTANT — no easing.** `hover_t` is binary (0/1), set the moment
> the pointer enters/leaves the hit area (`update()`), so the grey-fill + shadow
> react within one frame. The previous `dt`-based interpolation (`dt*14`) took
> ~0.15–0.3 s to settle and read as sluggish, disconnected feedback; that was the
> single most-noticed quality defect, so responsiveness here is the priority.

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

The Worlds-tab **bottom action button** owns a single slot and runs through these
instantly-switched states (never reloaded):

1. **Floating preview** (default) — no camera. The overlay feeds
   `scripted_head(t)` — gentle sine-wave motion
   (`hx = 0.14·sin 0.55t`, `hy = 0.07·sin 0.40t`, `hz = 0.06·sin 0.22t`) — into the
   *same* camera variables the tracker would, so the parallax is real and the
   idle scene looks alive. Status: "Floating preview"; button:
   **"Enable Camera for Desktop Mode"** (the label spells out that the camera is
   the path to Desktop Mode). This same label shows on first open AND whenever
   camera access is disabled in Settings; in the latter case clicking it
   **re-enables camera access first** (`_set_camera_enabled(True)`), otherwise the
   engine would ignore the request while the `camera_off` flag exists.
2. **Live tracked** — after "Enable Camera for Desktop Mode". Real
   [[head-tracking]] drives the
   parallax. The status line is **honest about the transition** (it used to read
   "Live" the instant the button was clicked, even when the camera never opened —
   the "Live status on, no tracking" bug):
   - **"Starting camera…"** while the grant settles and the first frames arrive.
     During this window the button label itself reads "Starting camera…" and is a
     **no-op** (`action == "none"`) — the single slot is not yet offered as a
     Desktop Mode control.
   - **"Live · head tracking on"** once real head data actually flows (the engine
     calls `notify_tracking_active()` when `|hx|+|hy|+|hz| > 0`). **This is the
     "camera granted" trigger** — only now does the button swap to
     **"Enable Desktop Mode"**, in the exact same slot/size/style.
   - **"Camera access needed — enable it in System Settings"** if access was denied
     (the engine calls `notify_camera_denied()`); the overlay drops back to the
     scripted floating preview and the button returns to "Enable Camera for
     Desktop Mode" so the user can retry.
   The swap is gated by `_camera_ready()` = `tracking_active or daemon_running`.
   Disabling the camera again clears `tracking_active`, so the button correctly
   reverts to the enable-camera label (it used to wrongly stick on "Enable Desktop
   Mode" — a routing bug, now covered by `sim_overlay`).
3. **Desktop mode** — once the wallpaper is active, the overlay reverts to a
   passive floating preview and the button becomes "Disable / Enable Desktop
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
| `tracking_active` | The engine calls `notify_tracking_active()` once real head data arrives → status promotes to "Live · head tracking on" AND the bottom button swaps to Desktop Mode |
| `camera_denied` | The engine calls `notify_camera_denied()` when authorization was denied/unavailable → status shows the System-Settings hint and reverts to the scripted preview |
| `preview_active` *(property)* | `True` on the **Worlds** tab **and** in the World Builder **Preview** sub-view. The engine renders the live 3-D scene only when this is `True`; on Settings/Community and the WB grid editor it skips the whole scene draw (see *World-preview suspend*) |

## Controls

Everything is keyed to the **tab bar** (top-centre, always visible across all four
tabs): **Worlds · World Builder · Community · Settings**. It reads as a **row of
push-buttons** on a floating white container. **World Builder is ALWAYS the orange
accent pill** — a fixed CTA; the highlight never migrates to whichever tab is
selected. The other three are **dark-grey pills** (`GREY_CONTAINER`, light text
that brightens on hover). Whichever tab is **occupied** sinks into the **"click-in"
(pressed) state** — the orange Builder via `force_press` on the shared Button, the
grey tabs via `_draw_grey_tab` (a matching 0.98 shrink + darker fill + inset top
edge) — so the toggled tab reads as pressed-in regardless of colour. **Every** tab
(occupied or not) carries the *same* stationary soft drop shadow — the lift that
used to appear only on hover — drawn via `_soft_shadow`, so the unoccupied pills
visibly float. The previous **loud yellow `_outer_glow`** halo behind the active
tab was removed (it read as a constant loud shadow); the same de-loudening dropped
the Send pill's resting glow. `self._active_tab`
drives the whole layout; switching is instant (no reload). The tab bar is **drawn
last, directly on the output surface — not on the idle-faded layer** — so on the
Worlds tab it never dims and its hover feedback is always crisp (the idle-fade
easing previously read as hover lag here).

### Worlds tab

- **No world-name pill** — the active world is announced only by a transient
  toast on switch (the under-tab title pill was removed).
- **Navigation arrows** (`world_prev` / `world_next`) — near-black rounded ◀ / ▶ with
  slightly rounded triangle glyphs, vertically centred and **pulled in from the
  screen edges** (`edge_inset`) to flank the scene. Clicking switches worlds
  **instantly** (no carousel/animation): `_cycle_world()` advances the index and
  writes `"world"` to `~/.iris/preferences.json`, which the engine polls live (no
  restart). They replace the old vertical world-picker pill list. Available until
  Desktop Mode is active (the HUD hides entirely once it is). The cycle uses
  `self._world_keys`, which **excludes `grid_room`** (the World Builder's working
  world) — `grid_room` stays in `self._all_world_keys` for `_set_world` validity
  but is never a browsable world, and a saved `world == grid_room` pref is reset to
  `earth` on init.
- **Bottom action group** — a grey container centred at the bottom holding a
  **status line** (`_status_text()`) above the **single large action pill**
  (Enable Camera → Desktop Mode, per the state machine). This is the one home for
  the primary action; the old scattered "Desktop Mode" / "Live Head Tracking"
  corner pills were removed.

### Settings tab

A **full-bleed blank white page** (no inset card / dark frame — the white fills
the whole window, the tab bar floats on top) exposing a **Camera Access** toggle
that creates/removes `~/.iris/camera_off` — the same flag the engine and
[[head-tracking]] respect. The toggle sits on its own grey container so it reads
on the white. Disabling drops the overlay back to floating-preview mode
(`live = False`). Re-enabling + clicking "Enable Camera for Desktop Mode" resumes
the existing tracker worker thread via `set_tracking(True)` without a full
re-authorization cycle (the worker is paused, not exited, so permissions are
preserved). See [[known_issues]] for the prior bug where this re-enable was
silently blocked.

### World Builder tab

A **full white page** with two sub-views of the one `grid_room` world (`_wb_view`
= `"grid"` | `"preview"`); switching never edits the world, so state persists.

- **Grid editor** (`grid`) — a 2-D **30° oblique** drawing of the room: a true
  N×N back-wall grid with the depth axis receding down-left. Addressed by
  *square*, not point — **X** across the bottom row, **Y** up the left column
  (both share square 1), **Z** mapped to the **bottom row of the left wall**. The
  back-wall border plus the **left-wall and floor perimeters** are drawn in the
  same dark shade (`WALL`); the Z numbers match that shade. The cube fits **as
  tightly between the side panels as the tab bar** (same 16 px side gap, ~0.99
  fill).
- **Premium side panels** — two big **golden-yellow** cards flank the cube
  (`self._wb_left_panel` / `self._wb_right_panel`), tops aligned with the tab-bar
  row and a symmetric bottom inset. Left = the World-Builder explainer (to come),
  right = build settings. Bold navy titles. The **Preview** button (white pill on
  grey, key `wb_preview`) sits on the tab-bar row sized to the right panel, with
  the right panel directly under it.
- **Shadow layering (drawn in three passes).** `_premium_card` takes a `phase`
  arg so a foreground object can be sandwiched between a card's shadow and its
  fill. The grid view draws the panel **shadows first** (`phase="back"`), then the
  **cube**, then the panel **fills** (`phase="front"`) — so each panel's shadow
  falls **behind** the cube (the cube occludes its inner half) instead of across
  it. The right column's shadow is cast for a **taller `shadow_rect`** that
  stretches **up to the Preview button**, so the right side reads as one
  continuous shadow at the **same height as the left panel** (the Preview capsule
  itself is then fill-only). The cube's own **contact shadow** is spread across
  its **whole base footprint** (was a tight central blob) so it reads as grounded.
- **Preview** (`preview`) — transparent over the live off-axis render of
  `grid_room` (`preview_active` True). A detached grey **"Back to Canvas"** tab
  pill (`wb_back`) floats top-left so the user can iterate without losing work.

`grid_room` is kept **blank (no placeable meshes)** as a clean canvas preview.

### Community tab

A **full-bleed blank white page** — "Coming Soon" placeholder.

### Idle fade & toasts

**Toasts** float just above the bottom action group (Worlds) or near the bottom
edge (other tabs). The **idle fade** (the HUD dims to ~34% after 4 s of no input)
applies **only on the Worlds tab** — the full-page Settings/Community pages stay
at full opacity, since fading a solid white page would reveal the dark scene
through it.
The idle timer treats an **active hover as engagement** — while the cursor rests
on any control, `idle` is held at 0 so the HUD stays fully lit (a stationary mouse
emits no `MOUSEMOTION`, so without this a held hover used to dim the whole layer
after 4 s — see [[known_issues]]).

## World-preview suspend

The live 3-D scene is rendered **only while `preview_active` is True** — the
Worlds tab **and** the World Builder *Preview* sub-view. On the Settings/Community
tabs and the WB grid editor the scene is fully hidden behind the blank white page,
so rendering it is wasted GPU. Each frame [[engine-loop-and-daemon]] reads
`overlay.preview_active`; in `demo` mode (and not yet desktop-active) it skips the
entire scene draw — clears to a **fixed neutral dark** (`0.05, 0.05, 0.06`, *not*
`world.clear_color`, because the Gem world clears to white and would hide the
card), composites just the HUD, and continues. The preview restores the instant a
preview-active view is reselected. Never applies once Desktop Mode is active — the
wallpaper must keep rendering.

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
- Uses macOS system fonts (Inter/SF Pro Display, falling back to Helvetica/Arial).
- The control look now lives in `UI/buttons.py` (grayscale-minimal, 7.2 px radius)
  — restyle there, not by hand-rolling pills in the overlay.
- **Hover stays INSTANT** even though the spec's transition system supports
  easing: `instant_hover=True` is the Button default and `_draw_btn` sets the
  hover tracker as a binary 0/1. The 0.15 s ease applies only to press/focus.
  Re-introducing hover easing is the one defect this UI keeps relearning.

## Dependencies

- **Composited by:** [[engine-loop-and-daemon]].
- **Drives:** [[world-system]] (world selection), [[head-tracking]] (camera
  enable/disable).
- **Verified by:** [[headless-simulation]] (`sim_overlay` renders the HUD to PNG
  and checks the state machine without a GL context).
