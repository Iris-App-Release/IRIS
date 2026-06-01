# Parallax Wall — DMG + First-Launch Experience Design

**Date:** 2026-05-30
**Scope:** Packaging + onboarding + product UX ONLY. Physics / tracker / renderer / shaders are frozen.
**Status:** Design + roadmap. **M0–M2 now IMPLEMENTED** (see Build status).

---

## Build status — M0–M2 implemented (2026-05-30)

Name resolved to **Iris** (no rename needed). The dark 2-D launcher is replaced
by the live-demo-with-glass-overlay model the spec demands.

**New / changed files:**
- `overlay_ui.py` (NEW) — `DemoOverlay`: light/glass HUD + 3-screen state machine
  (alive → permission → active), scripted "alive" idle motion, hit-testing,
  pure-pygame surface composition, and a `draw_gl()` bridge that composites the
  HUD over the live GL scene (saves/restores depth/blend/cull/texture/matrix
  state). Plus `spawn_wallpaper_daemon()` for the camera handoff.
- `main.py` (EXTENDED, additive only) — new `PARALLAX_MODE=demo` window branch
  (centred, focusable, mouse-visible, no desktop-pinning); tracker start deferred
  until camera grant; head-input SOURCE swap (scripted ↔ tracker) feeding the
  **unchanged** camera math; per-frame overlay update/draw + Desktop-Mode handoff.
  Camera/parallax math (the off-axis frustum, view matrix, the 3-component blend)
  is byte-for-byte unchanged.
- `launcher.py` (REWRITTEN) — thin router: `PARALLAX_MODE=wallpaper|fullscreen`
  runs the engine directly (frozen-app daemon path); otherwise runs `demo`.
- `sim_overlay.py` (NEW) — headless validation of the overlay logic (state
  machine, idle bounds, hit-testing, render output, re-launch, scrim).

**Verification (done):** `sim_overlay` passes all checks; the 5 engine sims
(`sim_orbit/offaxis/viewing/latency/vertical`) still pass → physics unaffected;
all four modules `py_compile` and import cleanly in demo mode.

**Live verify (must run in the user's GUI session — camera/GL can't open from a
background shell):**
```bash
cd ~/Documents/ParallaxWall && .venv/bin/python launcher.py   # → demo window
```
Expect: centred window, live Earth breathing (scripted idle), an "Iris / Begin"
glass card over a soft dark scrim → Begin → camera primer → **Allow Camera**
fires the real macOS TCC prompt → scrim lifts to live tracking → "Enable Desktop
Mode" + Browse Worlds / Settings / Community. ESC/Q or close to quit. Calibrate
nothing — physics is the existing, validated build.

**Still TODO (M3–M7):** real TCC grant/deny/revoke wiring + persisted
`camera_onboarded` (M3), control-surface polish (M4), settings sheet + LaunchAgent
(M5), packaging — `brew install create-dmg`, PyInstaller, light DMG background,
ship `models/` (M6), Browse Worlds content (M7).

---

## 0. Current state vs. spec — what must be reconciled first

The engine is finished and correct. Productization, however, is half-built under a **different design than this spec calls for**. These conflicts must be resolved before/while building, because they cascade through every deliverable below.

### Decision A — Product name → **RESOLVED: "Iris"**
The product name is **Iris** (the spec's "Parallax Wall.app" wording was the old working title). All user-facing copy, the `.app` bundle, DMG volume, `.icns`, camera-usage string, and config dir `~/.iris/` stay as **Iris** — no rename needed. (`build_dmg.sh` already uses `APP_NAME="Iris"`.) The *repo dir* stays `~/Documents/ParallaxWall/` and internal engine identifiers ("parallax" flags like `~/.parallax_off`) are unchanged — only the **product surface** is Iris. The outstanding work is the **full reskin** of the launcher to the light/glass spec, not a rename.

### Decision B — Light mode + glass (spec) vs dark launcher (code)
`launcher.py` is a dark theme. The spec mandates **light mode only, frosted/liquid glass, soft shadows, Apple HIG**. The existing launcher palette and layout are discarded and replaced (see §3/§4). The *structure* of `launcher.py` (engine pid discovery, prefs persistence, detached spawn) is reusable; the *look* and *windowing model* are not.

### Decision C — "Demo behind UI" requires a GL launcher, not a 2D one  ⚠️ architectural
This is the heart of the spec ("the illusion is the product… demo remains visible at all times behind UI"). The current launcher is **2D pygame in its own window** that spawns `main.py` as a *separate* detached GL daemon. Two windows can't composite. The first-launch window must therefore **be a windowed instance of the engine itself**, with the UI drawn as a **2D HUD on top of the same GL context** (§4). This is the single largest piece of new work and it needs one new engine entry mode — see Decision D.

### Decision D — One new engine mode: `PARALLAX_MODE=demo`  (the only engine touch)
`main.py` today supports `wallpaper` (borderless, desktop-level, click-through, daemon) and `fullscreen` (ESC quits). Neither is right for onboarding. We add a **third mode, `demo`**: a normal centered/fullscreen *focusable* window, mouse visible, NOT pinned to desktop level, that runs the identical render path and exposes a hook for the HUD overlay. **This is additive and changes no physics, no camera math, no shaders** — it only adds a branch in window setup plus a per-frame overlay callback. It is the one sanctioned modification to engine code and stays within the "packaging/UX" mandate.

### Decision E — Single camera owner
macOS allows one AVFoundation consumer at a time, and `main.py`'s `tracker.start()` grabs it. The demo holds the camera during onboarding; activating Desktop Mode must **stop the demo's tracker, then launch the wallpaper daemon** which re-acquires it. Never run two trackers at once (§6).

---

## 1. DMG installer UI — design

**Goal:** Apple-native, one-screen, zero instructions beyond a single line.

```
┌───────────────────────────────────────────────────────────┐
│  Parallax Wall                                    (titlebar) │
│                                                              │
│      ┌─────────┐                       ┌─────────┐          │
│      │  🌍     │        ───────▶        │   📁    │          │
│      │ Parallax│                        │  Apps   │          │
│      │  Wall   │                        │         │          │
│      └─────────┘                       └─────────┘          │
│                                                              │
│           Drag Parallax Wall into Applications               │
│                                                              │
└───────────────────────────────────────────────────────────┘
       background: soft light gradient + faint Earth glow
```

**Spec → build mapping (`build_dmg.sh`):**
- Window 560×360, light background image (`assets/dmg/dmg_background.png` @2x = 1120×720), drawn with a faint centered Earth and the one-line caption baked into the PNG (so it can't be edited/missing).
- Left: `Parallax Wall.app` icon at ~(150,180), icon size 120.
- Right: Applications symlink at ~(410,180) via `--app-drop-link`.
- Hide the `.app` extension, hide the toolbar/status/path bars, no sidebar.
- `--no-internet-enable`; `.background/` hidden; `.DS_Store` provides the window chrome.
- **Use `create-dmg`** for the styled result (it positions icons + sets the background). `hdiutil` is the fallback but gives the bare list view — acceptable for dev, not for ship. `create-dmg` is **not currently installed** → `brew install create-dmg`.
- "Apple-like polish, not custom-game-installer": no animated background in v1 (the spec says optional + minimal). A static light gradient with one soft Earth glow reads more premium than motion here.

**Output:** `dist/Parallax Wall.dmg` containing only the app + the Applications alias.

---

## 2. macOS application architecture (.app structure)

Built with **PyInstaller `--windowed`** (already scaffolded in `build_dmg.sh`). The bundle is fully self-contained — no Python, no venv, no Terminal, no scripts visible to the user.

```
Parallax Wall.app/
└─ Contents/
   ├─ Info.plist            CFBundleName=Parallax Wall, NSCameraUsageDescription,
   │                        LSUIElement handling (see below), version
   ├─ MacOS/
   │  └─ Parallax Wall      ← PyInstaller bootloader → launcher.py (entry)
   ├─ Resources/
   │  ├─ ParallaxWall.icns  (from assets/icon/earth_icon.png via iconutil)
   │  ├─ assets/            earth/, stars/, icon/, dmg/
   │  ├─ worlds/            earth/ (+ future worlds)
   │  ├─ shaders/           all GLSL
   │  └─ models/            mediapipe face_landmarker task
   └─ Frameworks/           pygame, PyOpenGL, mediapipe, cv2, numpy (bundled)
```

**Entry point = `launcher.py`** (the onboarding/demo window), NOT `main.py`. `main.py` becomes an internal binary the launcher spawns for *Desktop Mode*.

**Key plist keys:**
- `NSCameraUsageDescription` — already written by `build_dmg.sh`; reword to "Parallax Wall uses your camera for head tracking. Processing happens locally; no video is stored or transmitted." (matches the spec's permission copy).
- The launcher window **must** appear in the Dock/⌘-Tab (it's a real app window), so do **not** set `LSUIElement=1` on the bundle. The *wallpaper daemon* hides itself at runtime via the existing `_hide_from_dock()` (`NSApplicationActivationPolicyAccessory`) — that's the right layer for it, leave it there.
- `CFBundleIconFile = ParallaxWall.icns`.

**Resource path resolution:** `launcher.py` already does `HERE = sys._MEIPASS or __file__.parent`. `main.py` uses `Path(__file__)`-relative asset loads → under PyInstaller those resolve inside the bundle automatically as long as `--add-data` ships `assets/ worlds/ shaders/ models/` (it does). **Verify the `models/` mediapipe `.task` file is collected** — it's the one asset most likely to be missed and it fails silently to the Haar fallback (degraded tracking) rather than crashing.

**Memory note (8 GB M2):** PyInstaller + mediapipe + opencv produces a large bundle (~400 MB–1 GB) and the build itself is RAM-hungry. Build with nothing else heavy running; expect ~2–3 min. This is a one-time build cost, not a runtime cost.

---

## 3. First-launch UI flow (the four screens)

One window. One GL context. A small **screen-state machine** drives a 2D HUD composited over the live Earth (§4). The Earth is rendered from frame 0 — there is never a moment where the product looks static.

```
        ┌─────────────────────────────────────────────┐
state:  │  ALIVE → PERMISSION → ACTIVATING → ACTIVE     │
        └─────────────────────────────────────────────┘
```

### Screen 1 — ALIVE (demo entry)
- Earth centered, rendered live. Tracker **not yet started** → no camera prompt yet. To keep it "inactive but alive," drive a gentle **scripted idle orbit** of the eye (a slow sinusoid fed into the same `cam_x/cam_y/cam_z` the tracker would set) so the parallax breathes without a camera.
- HUD: a single frosted-glass card, centered-low, light/translucent:
  > **Parallax Wall**
  > A window into a world that moves with you.
  > [ Begin ]   ← primary glass button
- Overall scene very slightly dimmed (a 12–18% white scrim) to read "asleep."

### Screen 2 — PERMISSION
Triggered by **[Begin]**. Apple-like glass dialog, minimal:
> **Parallax Wall uses your camera for head tracking.**
> Processing happens locally on your device.
> No video is stored or transmitted.
>
> [ Allow Camera ]   [ Not Now ]

- **Allow Camera** → starts the tracker, which triggers the **real macOS TCC prompt**. (Our card is the *pre-prompt* primer that explains *why* before the OS dialog appears — standard Apple-recommended pattern; raises grant rates and avoids a cold system prompt.)
- **Not Now** → stays on the scripted-idle demo with a persistent "Enable head tracking" affordance; product is still understandable, just not live-responsive.

### Screen 3 — ACTIVATING (the moment)
- On TCC grant, the scrim lifts (250–350 ms ease), idle-orbit hands off to live tracking. **No loading screen, no spinner** — the spec forbids it, and the engine is already running, so there is literally nothing to load. First tracked frame should land within the tracker's normal warmup (VIDEO-mode MediaPipe ~30 fps per memory).
- If grant is denied at the OS level, fall back to Screen 2's "Not Now" state with a one-line "Camera access is off — enable it in System Settings › Privacy" link.

### Screen 4 — ACTIVE (core overlay)
Earth fully responsive. Minimal glass UI floats over it, **never dominating**:
- Primary: **[ Enable Desktop Mode ]** (large glass pill, bottom-center)
- Secondary row (small, low-contrast glass): **Browse Worlds** · **Settings** · **Community**
- Auto-fade: the secondary controls fade to ~30% after ~4 s of no input and return on mouse move, so the illusion owns the screen. Primary CTA stays but dims.

**Transition rules:** all state changes cross-fade ≤350 ms; the Earth never stops rendering across any transition.

---

## 4. Live-demo integration architecture (Earth only)

This is the critical, novel piece. **The launcher window IS the engine in `demo` mode, with a 2D HUD layer on top.**

### 4.1 The new `demo` mode in `main.py` (only engine change)
Add a third branch to the existing mode logic:

```
DISPLAY_MODE == "demo":
    flags   = DOUBLEBUF | OPENGL          # no FULLSCREEN, no NOFRAME
    window  = centered, e.g. 1100×720 (or borderless-fullscreen if spec prefers)
    mouse   = visible
    skip _drop_to_desktop_level()         # it's a real focusable window
    skip _hide_from_dock()
    tracker = started ONLY when state≥PERMISSION-granted (see §5)
    overlay = HUD.draw(state) called each frame AFTER bloom composite, BEFORE flip
```

Everything between `glClear` and `pygame.display.flip()` — the off-axis frustum, view matrix, Earth/Stars/Nebula/Bloom — is **byte-for-byte identical** to wallpaper mode. We are not re-implementing the demo; we are re-hosting the exact engine in a window and adding one overlay call. Physics untouched.

### 4.2 The HUD overlay (2D over GL)
GL 2.1 + bloom owns the framebuffer, so the UI is drawn as a **textured 2D layer in the same context**, the standard technique:
1. Each frame (or only when UI changes — most frames it's static, so cache it), render the HUD to an off-screen **pygame `Surface` with per-pixel alpha** (frosted-glass cards, text, buttons, soft shadows — all 2D, easy to make light-mode/Apple-style).
2. Upload that surface to a GL texture; draw it as one screen-filling quad with `GL_BLEND` (`SRC_ALPHA, ONE_MINUS_SRC_ALPHA`), depth test off, ortho projection.
3. The "frosted glass" look = a translucent light-tinted rounded rect in the surface (optionally sampling a cheap blurred copy of the scene behind it for true liquid-glass; v1 can fake it with a 70–80% white rounded panel + 1px light border + soft drop shadow, which reads as glass over the dark space scene).

A new module **`overlay_ui.py`** owns: the screen-state machine, glass widgets (Card, GlassButton, PillButton), hit-testing against mouse, fade timers, and `draw(screen_state) -> Surface`. It imports nothing from the physics path. `main.py`'s demo branch just calls `overlay.handle_event(ev)` in the event loop and `overlay.blit_gl(W_gl,H_gl)` before flip.

### 4.3 Idle "alive" motion without a camera (Screen 1/2)
Before the tracker is granted, feed a scripted eye path into the same variables the tracker would:
`hx,hy = small slow Lissajous; hz = gentle breathing`. The existing smoothing (`CAM_LAG`) makes it cinematic. On grant, blend the scripted source out and the real `tracker.head()` in over ~0.5 s. Zero new physics — same inputs, different source.

### 4.4 Why not keep the two-process model?
Because you cannot composite a UI over another process's GL window, and an OS-level window screenshot/transparency hack is fragile and not "premium." Hosting the engine in-process is simpler, smoother, and gives pixel-perfect control of the overlay. The two-process model is retained **only** for the shipped wallpaper daemon (§6), where there is no overlay.

---

## 5. Permission system design

**Layered, Apple-recommended:**

1. **Pre-prompt primer (our glass card, Screen 2)** — explains *why* before the OS asks. Never substitutes for the OS prompt; it precedes it.
2. **OS TCC prompt** — fires automatically the first time `tracker.start()` opens the AVFoundation device. `NSCameraUsageDescription` (Info.plist) is the text macOS shows. **The TCC prompt only appears for a properly signed/bundled `.app`** launched from the GUI — not from a bare `python main.py` in a background shell (per project memory, that path fails with "not authorized / cannot spin main run loop"). So permission is only truly testable from the built `.app` in the user's GUI session.
3. **State tracking** — persist grant result in prefs (`camera_onboarded: true`) so Screen 2 is shown only on first run; thereafter the app goes straight to live demo (and macOS remembers the TCC grant itself).
4. **Denied / revoked path** — `tracker` already has a Haar fallback and a no-camera path; surface a calm one-liner + a `System Settings › Privacy & Security › Camera` deep link (`x-apple.systempreferences:com.apple.preference.security?Privacy_Camera`). Never nag, never modal-trap.

**Privacy posture to state in UI (true of the engine today):** tracking is local (MediaPipe on-device), only head *position/orientation* leaves the tracker (`hx,hy,hz,yaw,pitch` — not imagery), nothing is stored or transmitted.

---

## 6. Desktop-mode activation flow

The handoff from onboarding demo → live wallpaper. The one hard constraint is the single camera owner (Decision E).

```
[ Enable Desktop Mode ]  (Screen 4)
        │
        1. overlay shows a brief "Entering Desktop Mode…" glass toast (no spinner)
        2. demo stops its OWN tracker  → releases the camera          (critical)
        3. clear master switch:  rm ~/.parallax_off                    (engine visible)
        4. spawn wallpaper daemon detached:
              PARALLAX_MODE=wallpaper PARALLAX_DAEMON=1  <bundle>/main.py
              start_new_session=True, stdout/stderr → DEVNULL
           (reuses launcher.py._launch_engine, minus the dark UI)
        5. daemon: _drop_to_desktop_level() + _hide_from_dock(),
              tracker.start() re-acquires the now-free camera
        6. demo window fades out and quits (or minimizes to a menu-bar item)
        │
   Desktop is now the live head-tracked wallpaper, behind all app windows,
   click-through. No Terminal, no console, no second camera grab.
```

**Re-launch behavior:** after first run, opening `Parallax Wall.app` again should *not* force the full onboarding. Detect a running daemon (`pgrep -f main.py`, already in `launcher.py._find_engine_pid`) and present a compact **control surface** instead: Desktop Mode On/Off (writes `~/.parallax_off`), Browse Worlds, Settings, Quit. This subsumes the old `parallaxctl` / `.command` control center into the app — no Desktop `.command` files needed in the shipped product (keep them for dev only).

**Toggle semantics (already in engine):** `~/.parallax_off` hides the wallpaper window + releases the camera (instant on/off); `~/.parallax_icons_off` hides orbital icons. The Settings panel just touches/removes these flags.

---

## 7. Minimal settings system design

Light, glass, one panel — not a dashboard. Backed by a single JSON prefs file.

**Storage:** `~/.parallaxwall/preferences.json` (rename from `~/.iris/` per Decision A; migrate if `~/.iris/` exists). Keys:
```
{ "camera_onboarded": true, "last_world": "earth",
  "icons_visible": true, "desktop_mode_on_login": false,
  "tracking_sensitivity": 1.0 }
```

**Panel contents (glass sheet over the demo):**
- **Desktop Mode** — On/Off (the master `~/.parallax_off` toggle).
- **Orbital app icons** — Show/Hide (`~/.parallax_icons_off`).
- **Launch at login** — adds/removes a LaunchAgent plist (`~/Library/LaunchAgents/com.parallaxwall.daemon.plist`) so the wallpaper restores on reboot. Off by default.
- **Camera** — status pill + "Open Privacy Settings" deep link. No raw sliders for tracking gains — the spec wants calm; those calibration constants (`ROT_MAX_*`, `LOOK_PITCH_OFFSET`) stay developer-side, not user-facing. A single coarse "Responsiveness" slider mapping to `tracking_sensitivity` is the most I'd expose, and only if asked.
- **About** — version, "processing is local" privacy line, Community/Socials links.

Settings writes are immediate and reflected by the running daemon through the existing flag files (no IPC needed — the flags ARE the IPC, polled in `main.py`'s loop).

---

## 8. Implementation roadmap (high-level)

Sequenced so each step is independently verifiable, the engine is never broken, and the heaviest/riskiest piece (GL overlay) is de-risked early with the headless-safe parts first.

**M0 — Reconcile naming + theme (decisions A/B)** · ~0.5 day
Pick "Parallax Wall" vs "Iris" globally; strip the dark palette. Pure rename/constants; no behavior change. Gate everything else on this.

**M1 — `demo` engine mode (decision D)** · ~0.5 day
Add the `demo` branch to `main.py` window setup + a no-op `overlay` hook. Verify wallpaper/fullscreen modes are untouched; verify `demo` opens a focusable centered window showing the live Earth. (Live verify must run from the user's GUI session — agent shell can't open the camera/GL, per memory.)

**M2 — `overlay_ui.py`: glass HUD + screen-state machine** · ~2 days
Light-mode glass widgets, the 4-screen state machine, GL-texture compositing (§4.2), idle "alive" motion (§4.3). This is the bulk of the visible product. Build the Surface-rendering and hit-testing headlessly first (pure pygame, no GL) so most of it is testable without the live app.

**M3 — Permission flow (§5)** · ~0.5 day
Pre-prompt card → gated `tracker.start()` → grant/deny/revoke paths → persist `camera_onboarded`. Only end-to-end testable from the built `.app`.

**M4 — Activation + control surface (§6)** · ~0.5 day
Clean camera handoff to the wallpaper daemon; re-launch detection → compact control surface; subsume `parallaxctl` toggles.

**M5 — Settings (§7)** · ~0.5 day
Glass settings sheet wired to the flag files + LaunchAgent for login.

**M6 — Packaging (§§1–2)** · ~1 day
`brew install create-dmg`; install PyInstaller in venv; finish `build_dmg.sh` (rename, ship `models/`, light DMG background, verify camera plist); produce `Parallax Wall.app` + `.dmg`; smoke-test the full install → launch → onboard → activate loop on a clean user account. **Code signing / notarization** (so Gatekeeper doesn't block it on other Macs) is a separate follow-up requiring an Apple Developer ID — flag for the user; unsigned is fine for local/personal use.

**M7 — Browse Worlds (deferred, framework only)** · later
The spec wants this *minimal* — Earth active, others as locked placeholders. Note: `world_system.py` + `world.json` exist but are **not wired into `main.py`** (still hardcoded `Earth()`), and `world.json` asset paths don't resolve yet. Full world-switching is Phase-4 renderer work outside this UX scope; for now "Browse Worlds" shows Earth + greyed "Coming soon" tiles and changes nothing in the engine.

### Critical-path summary
`M0 → M1 → M2` delivers the spec's core ("install-less" dev preview of the live-demo-with-glass-UI). `M3–M6` make it a real shippable app. `M7` is intentionally a stub.

### Frozen (do not touch) — restating the mandate
`orbital_math.py`, `tracker.py`, `renderer.py` render math, `postfx.py`, all `shaders/`, and the camera/parallax math in `main.py`. The **only** sanctioned `main.py` edit is the additive `demo`-mode window branch + overlay hook (M1). Everything else is new files (`overlay_ui.py`) or packaging.
