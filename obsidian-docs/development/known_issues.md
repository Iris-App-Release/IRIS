---
title: Known Issues
type: reference
related: [head-tracking, constraints, engine-loop-and-daemon, dmg-build-process, ui-overlay, current-focus]
last_updated: 2026-05-31
sources: [Tracking/face_tracker.py, Launcher/app_engine.py, UI/demo_overlay.py, launcher.py, Build/build_dmg.sh]
---

# Known Issues

Tracked bugs with their root cause and resolution — newest first. Each entry is
meant to be the *durable* record: once something is understood here, it should
never have to be re-derived from chat history or source again.

---

## [RESOLVED 2026-05-31] Pixelated text and buttons in demo HUD

**Symptom.** Text labels, button corners, and status pill text in the demo
overlay appeared blurry / like "fine pixel art" on a Retina display.

**How it was diagnosed.** Empirically, not by guessing: rendered the overlay
surface to PNG over a dark background and inspected 3× pixel-magnified crops of
the button corners; separately ran a live probe creating a real GL window and
reading `GL_VIEWPORT` to measure the actual drawable scale. This is what exposed
that the HIGHDPI flag (below) was inert.

**Root cause — three independent issues:**

1. **Font fallback to pygame bitmap** (`UI/demo_overlay.py:_load_font`).
   `pygame.font.SysFont('SF Pro Display', ...)` silently returns the default
   pygame bitmap font when the font isn't found — it never raises, so the
   `try/except` loop exited on the first iteration with garbage. Confirmed:
   `match_font('SF Pro Display')` → `None`; SysFont'd render size matches
   `Font(None, 24)` exactly. Helvetica Neue IS available at
   `/System/Library/Fonts/HelveticaNeue.ttc` but the loop never reached it.

2. **GL surface was 1×, not 2× on Retina** (`Launcher/app_engine.py`). The
   window rendered at 1× backing and macOS bilinearly upscaled the whole thing
   2×, blurring both the 3-D scene and the overlay.

   > ⚠️ **A prior fix added `ALLOW_HIGHDPI` (`0x2000`) to the `set_mode` flags.
   > That flag is a NO-OP in pygame 2.6 on macOS.** Live probe: GL drawable was
   > 400×300 (scale 1.0) with AND without the flag, while the screen's
   > `backingScaleFactor` is 2.0. pygame's `set_mode` does not forward that bit
   > to SDL2. Do not re-add it thinking it does anything.

   **The working fix is Cocoa, not a flag.** `_enable_retina_surface()` gets the
   SDL content view (`get_wm_info()["window"]` PyCapsule → `PyCapsule_GetPointer`
   → `objc.objc_object`), calls
   `view.setWantsBestResolutionOpenGLSurface_(True)`, then
   `NSOpenGLContext.currentContext().update()`. Verified live: GL drawable jumps
   400×300 → 800×600. Runs after every `set_mode` (startup + desktop-mode
   resize). Benefits every mode, not just demo.

3. **Aliased rounded-rect corners** (`UI/demo_overlay.py`).
   `pygame.draw.rect(border_radius=…)` does not anti-alias its corners — they
   stair-step (visible in the magnified crops even once the scale was 2×). Fixed
   with `_aa_round_rect()`: render the pill/panel at 4× and `smoothscale` down.
   Only runs on dirty (cached) frames.

Issues 1+2 compounded (bitmap font at 1× then macOS-doubled = worst case);
issue 3 was independent and survived the scale fix.

**Validation.** `sim_overlay.py` all 26 checks pass; both files parse;
`objc` + `NSOpenGLContext` import in the venv; magnified PNG crops show smooth
corners and a working hover grey + lift shadow.

See [[ui-overlay]] (full writeup + button styling), [[rendering-engine]]
(Retina-surface constraint).

---

## [RESOLVED 2026-05-31] Settings camera toggle: re-enable does not reactivate tracking

**Symptom.** Camera enable → Settings → disable → Settings → re-enable → click
"Enable Camera": camera never restarts. The disable path worked correctly; the
failure was silently stuck only during re-activation.

**Root cause.** `Launcher/app_engine.py`, demo-mode control block. The
`tracking_requested` handler was guarded by `not tracker_started`:

```python
if overlay.tracking_requested and not tracker_started and not cam_off:
```

`tracker_started` is set to `True` on the first enable and **never cleared** on
a Settings disable — because the disable path only calls
`tracker.set_tracking(False)` (which pauses the worker without exiting it), it
does not reset the flag. After the first enable cycle `not tracker_started` is
always `False`, so the entire re-enable block is **permanently skipped**: the
live worker thread sits paused with `set_tracking(False)` and nothing ever calls
`set_tracking(True)` to resume it.

**Exact failure location.** `Launcher/app_engine.py`, line 413 (original), the
outer `if` condition of the `tracking_requested` handler.

**Fix.** Removed `not tracker_started` from the outer guard and split into two
branches inside:

- `not tracker_started` (first-ever enable): existing path — call `tracker.start()`,
  settle macOS authorization, spawn the worker.
- `else` (worker already running, was paused by camera-off toggle): just call
  `tracker.set_tracking(True)` to resume the worker. The worker re-opens the
  camera on its next tick. No re-authorization, no new thread.

The overlay's existing `_click("enable_camera")` handler already resets
`tracking_active = False` before setting `tracking_requested = True`, so the
status pill correctly returns to "Starting camera…" until real frames arrive.

**Files modified.** `Launcher/app_engine.py` — the `tracking_requested` block
in the demo per-frame control path (~5 lines changed).

**Validation.**

- Disable → re-enable cycle: clicking Settings → Camera Access · Off → Camera
  Access · On → "Enable Camera" now resumes head tracking (status advances from
  "Starting camera…" to "Live · head tracking on" once frames flow).
- `sim_overlay.py` and `sim_latency.py` unaffected (pure logic / physics tests).
- First-time enable flow unchanged: the `not tracker_started` branch is
  identical to the original.

**Remaining risks / notes.**

- `tracker_started` remains True after this path; a subsequent Settings disable
  will again pause via `set_tracking(False)`, and the next "Enable Camera" click
  will correctly hit the new `else` branch. Multiple disable→re-enable cycles
  are handled correctly.
- The worker thread is reused across disable/re-enable cycles. A `tracker.stop()`
  + `tracker.start()` full restart is only needed if the thread itself has exited
  (e.g. an unhandled exception in `_run`). That edge case is pre-existing and
  unchanged.

See [[ui-overlay]] (camera toggle UI), [[head-tracking]] (worker lifecycle).

---

## [RESOLVED 2026-05-31] "Live Status On" but no head tracking — invalid code signature → TCC silently denies (verified live)

**This is the real, end-to-end fix.** The two entries below were each *necessary
but not sufficient*; this one is what made head tracking actually work in the
shipped `.app` (confirmed live: TCC dialog appears → grant → "Live · head tracking
on" → the world tracks the head).

**Symptom.** Entering Live mode flipped the status pill to "Live" **without any
camera-permission prompt**, but no head tracking happened — in *both* a source
run ("Preview") *and* the bundled app ("Desktop"). The scene either froze at
centre or kept playing the scripted idle motion.

**Root cause (primary — the bundle).** `Build/build_dmg.sh` patches `Info.plist`
(version + `NSCameraUsageDescription`) with `PlistBuddy` in **step 7, AFTER**
PyInstaller has already ad-hoc-signed the bundle in step 5 — and then never
re-signs. Editing a sealed resource invalidates the signature:
`codesign --verify dist/Iris.app` → *"invalid Info.plist (plist or signature have
been modified)."* **macOS TCC silently denies camera (and mic) access to an app
whose code signature is invalid** — no dialog is ever shown and the request is
auto-denied. Proven on the running app: with the camera reset to *NotDetermined*,
`AVCaptureDevice.requestAccessForMediaType_completionHandler_` invoked its
handler with **denied in ~52 ms** (no dialog) and the TCC status jumped straight
to *Denied (2)*. This is also why the previous pyobjc fix couldn't help: the
import worked, but the request was auto-denied before any prompt.

**Root cause (secondary — the worker thread, affects source too).** Even with a
valid signature, the capture worker opening `cv2.VideoCapture(0)` on a background
thread triggered OpenCV's *own* AVFoundation authorization request, which logs
*"can not spin main run loop from other thread"* and fails forever. The previous
design also **ignored** the result of its main-thread permission request — it
spawned the worker regardless — and the overlay set `live = True` the instant the
button was clicked, so the UI claimed "Live" while every camera open failed
silently. Net effect: a permanent "Live, but nothing tracks" with no feedback and
no usable logs (the `--windowed` bundle discards stdout, so every `print()` in the
camera path was invisible).

**Fix (robust redesign of the camera permission + init path).**

1. **Re-sign after the Info.plist edits** (`Build/build_dmg.sh`, new step 7b):
   `codesign --force --deep --sign - "$APP_PATH"` then `codesign --verify --deep
   --strict` — and **fail the build** if it's still invalid, so this can never
   silently regress. A *valid* ad-hoc signature is all TCC needs to present the
   prompt. **This is the change that fixes the shipped app.**
2. **App owns authorization; OpenCV stands down.** `OPENCV_AVFOUNDATION_SKIP_AUTH=1`
   is set before any `cv2` import (in `launcher.py` and `Tracking/face_tracker.py`)
   so OpenCV never makes its broken off-thread request; we settle the grant
   ourselves on the main thread.
3. **`request_camera_access()` (rewrite of `_request_camera_permission`)** returns
   a tri-state — `authorized` / `denied` / `unavailable` — presenting the TCC
   dialog and pumping the run loop only for a *NotDetermined* status.
4. **`start()` consumes the result** (it no longer ignores it): on `denied` it does
   **not** spawn a worker that would spin forever; it records `tracker.permission`
   and returns it. The engine then calls `overlay.notify_camera_denied()`.
5. **Honest UI** (`UI/demo_overlay.py`): the status pill is driven by real state —
   "Starting camera…" until frames arrive, "Live · head tracking on" once head
   data actually flows (`notify_tracking_active`), or "Camera access needed —
   enable it in System Settings" on denial (and it falls back to the live scripted
   preview so the scene never freezes).
6. **File logging** to `~/.iris/iris.log` (stdout is lost in the windowed bundle) —
   the camera/permission flow is now always inspectable in the field.

**Files involved.** `Build/build_dmg.sh` (re-sign + verify — the decisive fix),
`Tracking/face_tracker.py` (SKIP_AUTH, `request_camera_access`, result-consuming
`start()`, file logger), `Launcher/app_engine.py` (acts on `tracker.permission`),
`UI/demo_overlay.py` (honest status + `notify_camera_denied`), `launcher.py`
(early SKIP_AUTH + persistent `MPLCONFIGDIR`).

**Validation (live, not just headless).** Rebuilt with the re-sign step →
`codesign --verify` passes. `tccutil reset Camera com.iris.parallaxwall`, launched
`dist/Iris.app`, clicked **Enable Camera**: the macOS dialog **appeared** (vs the
52 ms auto-deny before), granting it flipped the pill to **"Live · head tracking
on"**, the menu-bar camera light lit, the Earth tracked the head, and
`~/.iris/iris.log` recorded `authorization answered: authorized → camera opened —
head tracking live` (MediaPipe engine). `sim_overlay` + `sim_latency` still pass.

**Remaining risks / notes.**
- Ad-hoc signatures change cdhash each rebuild, so macOS may re-prompt (or require
  a `tccutil reset Camera com.iris.parallaxwall`) after a fresh build; a real
  Developer ID signature would make grants stable (see [[distribution-checklist]]).
- **Source runs still can't self-authorize** (a bare interpreter has no bundle
  identity, so `request_camera_access()` returns `denied`); the overlay now says so
  honestly. The bundled `.app` is the supported path. See [[constraints]].
- The duplicate `cv2`/`pygame` SDL2 dylib warning at startup is pre-existing and
  harmless.

See [[head-tracking]] (mechanism), [[dmg-build-process]] (the re-sign step), and
[[ui-overlay]] (honest status states).

---

## [RESOLVED 2026-05-31] "Enable Camera" never prompts — pyobjc not bundled (necessary, not sufficient)

**Superseded by the entry above** (invalid code signature was the ultimate cause).
This pyobjc fix was a *real and necessary* prerequisite — without it AVFoundation
can't even be imported in the frozen app — but it was **not sufficient on its
own**: with pyobjc bundled, the request still imported fine yet was auto-denied by
TCC because the bundle's signature was invalid. The earlier "wired in
`_request_camera_permission()`" fix (bottom section) was correct in source, passed
the headless control-flow test, yet the **bundled `.app` still never prompted**. Live unbuffered logs showed OpenCV's worker thread retrying
`cv2.VideoCapture(0)` with authorization status stuck at `0` (NotDetermined)
within seconds — impossible if the main-thread `_request_camera_permission()`
had actually run and pumped the run loop. The "fix" was **inert at runtime**.

**Root cause (packaging).** `_request_camera_permission()` does
`from AVFoundation import AVCaptureDevice` / `from Foundation import NSRunLoop`
**lazily, inside a `try/except ImportError`**. PyInstaller's static analysis
never sees those imports, so its bundled pyobjc hooks never run. The pyobjc
packages got pulled into the bundle only *transitively as binary deps* — so
`Iris.app` shipped **only the compiled `.so` cores** (`_objc…so`,
`_AVFoundation…so`, `_Foundation…so`) with **none of the pure-Python modules and
no `__init__.py`**. In pyobjc the public API (`AVCaptureDevice`, `NSRunLoop`, …)
lives in those `__init__.py` files, so inside the frozen app
`from AVFoundation import AVCaptureDevice` raised `ImportError`,
`_request_camera_permission()` hit its `except` and returned `False`
**instantly**, no dialog was presented, authorization stayed NotDetermined, and
every worker `cv2.VideoCapture(0)` failed forever. Identical end-user symptom to
the entry below, different layer — the call-site code was already correct; the
*frameworks it needed were absent from the package*.

**Confirmation.** Source `.venv` (`python3.11`) has full pyobjc — `objc` (32
`.py`), `Foundation` (7), `AVFoundation` (2), all with `__init__.py`; live import
succeeds. The shipped `dist/Iris.app` had **0 `.py`** in each of those dirs —
only the `.so`s.

**Fix.** Collect the full pyobjc packages into the bundle. The canonical build
path is `Build/build_dmg.sh`, which invokes PyInstaller via **explicit CLI
flags** against `launcher.py` (NOT `Iris.spec`; `--specpath` regenerates a throw-
away spec each build). Added there:

- `--hidden-import objc --hidden-import Foundation --hidden-import AVFoundation`
- `--collect-all objc --collect-all Foundation --collect-all AVFoundation`

The standalone `Iris.spec` got the matching `collect_all('objc' / 'Foundation' /
'AVFoundation')` + hidden-imports so the two build paths stay consistent.

**Validation.**

- `collect_all()` in the venv resolves all three packages (objc: 33 datas/34
  hidden; Foundation: 8/9; AVFoundation: 3/4) — i.e. their pure-Python modules
  are now collected.
- Rebuilt `dist/Iris.app` via `bash Build/build_dmg.sh` (exit 0): the bundle now
  ships **objc 64 `.py`, Foundation 14 `.py`, AVFoundation 4 `.py`, each with
  `__init__.py`** (previously zero). `from AVFoundation import AVCaptureDevice`
  can now succeed in the frozen app.
- **Remaining live check (needs a GUI session + camera grant, per
  [[constraints]]):** launch the rebuilt `dist/Iris.app`, click **Enable
  Camera** → the macOS TCC dialog should now appear; grant → status flips to
  "Live · head tracking on" and the world tracks the head; confirm **Desktop
  Mode** keeps tracking. If the camera was previously **denied** for
  `com.iris.parallaxwall`, macOS won't re-prompt — reset with
  `tccutil reset Camera com.iris.parallaxwall`.

**Files involved.**

- `Build/build_dmg.sh` — added the three pyobjc `--hidden-import` /
  `--collect-all` flags + a "do not remove" note. **This is the file that
  actually affects the build.**
- `Iris.spec` — mirrored the collection for the standalone-spec path.
- `Tracking/face_tracker.py` — unchanged here; its `start()` /
  `_request_camera_permission()` were already correct from the entry below.

**Lesson.** A lazy `try/except` import is invisible to PyInstaller; any optional
native dependency reached that way must be force-collected in the build, or it
silently degrades to its `except` branch in the frozen app while working
perfectly from source. Mechanism documented in [[head-tracking]] and
[[dmg-build-process]].

---

## [SUPERSEDED 2026-05-31] "Enable Camera" never prompts; head tracking never starts - earlier than 3:44 AM

> **Partial fix only — see the RESOLVED entry above.** Wiring in
> `_request_camera_permission()` was the correct *source* change, but the bundled
> app still failed because pyobjc itself was not packaged. Kept for the call-site
> reasoning, which remains accurate.

**Symptom.** Clicking **Enable Camera** in the demo HUD did nothing visible: the
macOS camera-permission (TCC) dialog never appeared and head tracking never
started. The [[earth]] / [[the-watcher]] worlds kept playing the scripted
floating-preview motion, and **Desktop Mode** rendered but never responded to the
head.

**Root cause.** `FaceTracker.start()` tried to surface the TCC prompt with a bare
`cv2.VideoCapture(0)` "primer" on the main thread. OpenCV's AVFoundation backend
does **not** issue `AVCaptureDevice.requestAccessForMediaType:` for a
`notDetermined` status and does **not** pump the main run loop, so:

- the permission dialog was never presented (nor awaited), and
- authorization stayed `notDetermined`, so every `cv2.VideoCapture(0)` open — the
  main-thread prime *and* every worker-thread retry (3 s backoff) — failed.
  `active` stayed `False` and `head()` returned the idle 5-tuple forever.

The project already contained the correct mechanism — `_request_camera_permission()`
(it checks `authorizationStatusForMediaType_`, calls
`requestAccessForMediaType_completionHandler_`, and pumps `NSRunLoop.runUntilDate_`
until the user answers) — but it was **dead code**: nothing called it. The stable
bundle id (`com.iris.parallaxwall`) and `NSCameraUsageDescription` were both
correctly present in the built app (verified in the shipped `Info.plist`), so the
*prerequisites* for a prompt existed; the **request that fires it was simply never
made**. The `start()` docstring had rationalized dropping the AVFoundation request
by claiming it "did not reliably surface the dialog inside the bundled app" — but
that failure mode only occurs when `requestAccess` is called *off* the main
thread; `start()` runs on the main thread, so the request is correct there.

**Why it was hard to spot.** Every "obvious" cause was clean: the click→signal
wiring ([[ui-overlay]]), the main-thread call site ([[engine-loop-and-daemon]]),
the demo mode router, the absence of a stale `~/.iris/camera_off` flag, and the
bundle id + camera-usage string in the build ([[dmg-build-process]]) were all
correct. The defect was the *missing* authorization request, not a broken one.

**Files involved.**

- `Tracking/face_tracker.py` — `start()` (the fix) and `_request_camera_permission()`
  (the previously-dead helper, now wired in).
- Call sites were already correct and unchanged — both invoke `start()` on the
  main thread: the demo path in `Launcher/app_engine.py` (`tracking_requested` →
  `start()`) and the wallpaper/fullscreen path.

**Fix.** `start()` now calls `_request_camera_permission()` on the main thread to
present the dialog and settle the grant *before* spawning the worker; the
misleading cv2 probe was removed. No camera math, parallax physics, or unrelated
system was touched. Mechanism documented in [[head-tracking]].

**Validation.**

- Headless control-flow test: confirms `start()` requests permission on the
  **main** thread, then spawns the worker on a separate thread, in that order.
- `Scripts/validation/sim_latency.py` and `sim_overlay.py` both pass — the frozen
  smoothing physics ([[headless-simulation]]) and the demo state machine are
  unaffected.
- Live validation (requires a real GUI session with the rebuilt `.app`, per
  [[constraints]]): rebuild via `bash Build/build_dmg.sh`, launch `dist/Iris.app`,
  click **Enable Camera** → the TCC dialog should appear; grant → status flips to
  "Live · head tracking on" and the world tracks the head; then enable **Desktop
  Mode** and confirm tracking continues.

**Remaining risks / notes.**

- If the camera was previously **denied** for `com.iris.parallaxwall`, macOS will
  not re-prompt — re-enable it in System Settings → Privacy & Security → Camera
  (or `tccutil reset Camera com.iris.parallaxwall`).
- `dist/Iris.app` predates this fix and must be **rebuilt** to carry it.
- A bare `python launcher.py` source run may attribute the prompt to the host
  process (Terminal / Python) rather than Iris; the bundled `.app` is the reliable
  path.
- On non-macOS, `_request_camera_permission()` returns `False` (no pyobjc) and the
  worker opens the camera directly via OpenCV, exactly as before — unchanged.

## Related

[[head-tracking]] · [[constraints]] · [[engine-loop-and-daemon]] · [[current-focus]]
