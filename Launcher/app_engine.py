#!/usr/bin/env python3
"""
Parallax Wall — head-tracked 3-D window illusion (cinematic edition).

Renders a photoreal Earth with cloud shell, atmospheric scattering,
multi-layer parallax stars and a Milky-Way background nebula through a custom
GLSL pipeline. The scene draws straight to the screen (bloom post-processing was
removed). The camera offsets follow the viewer's head position in real time,
selling the illusion that the monitor is a window onto a fixed virtual scene.

Architecture:
    Tracking/face_tracker.py      head detection (MediaPipe FaceLandmarker / Haar fallback)
    Engine/shader_loader.py        GLSL compile + texture loading
    Engine/renderer.py             Earth, Gem, Stars, Nebula classes (shader-driven)
    Launcher/app_engine.py         This file — camera math + main loop + GL state
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

# Environment guards must be set BEFORE importing pygame
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEO_WINDOW_POS",       "0,0")
os.environ.setdefault("SDL_VIDEO_ALLOW_SCREENSAVER","1")

import pygame
from pygame.locals import (
    DOUBLEBUF, OPENGL, NOFRAME, FULLSCREEN, QUIT,
    KEYDOWN, K_ESCAPE, K_q,
)
from OpenGL.GL  import *
from OpenGL.GLU import gluPerspective, gluLookAt

from Tracking.face_tracker import FaceTracker, DENIED
from Engine.renderer import (
    Earth, Stars, Nebula, IconOrbit, Eye, Gem, GridRoom, PlaceableObjects,
    draw_window_frame,
)
from Engine import camera_math as om
from Engine import calibration as calib_mod

# Optional Cocoa hooks for desktop-level wallpaper mode
try:
    from AppKit import (NSApp,
                        NSApplication,
                        NSOpenGLContext,
                        NSWindowCollectionBehaviorCanJoinAllSpaces,
                        NSWindowCollectionBehaviorStationary,
                        NSApplicationActivationPolicyAccessory,
                        NSApplicationActivationPolicyProhibited)
    from Quartz import CGWindowLevelForKey, kCGDesktopWindowLevelKey
    _HAVE_COCOA = True
except ImportError:
    _HAVE_COCOA = False


SCRIPT_PATH       = Path(__file__).resolve()
TRACKING_OFF_FLAG = Path.home() / ".parallax_off"
WALLPAPER_OFF_FLAG = Path.home() / ".parallax_paused"   # whole engine paused
ICONS_OFF_FLAG    = Path.home() / ".parallax_icons_off"  # hide orbital icons only
EARTH_STATE_FILE  = Path.home() / ".parallax_earth_state.json"
# Camera-access switch the Settings toggle writes; polled live (like the flags
# above) so disabling the camera takes effect instantly in the demo AND daemon.
# When present: do NOT open the camera / track — render an idle scene instead.
CAMERA_OFF_FLAG   = Path.home() / ".iris" / "camera_off"

# World system — bundle-relative worlds dir + the shared preference file the demo
# UI writes the selected world into. Resolved for both source and frozen (_MEIPASS).
_BUNDLE_BASE      = Path(getattr(sys, "_MEIPASS", None) or SCRIPT_PATH.parent.parent)
PREFS_FILE        = Path.home() / ".iris" / "preferences.json"
# Opt-in per-user metric calibration (screen size + viewing distance). Polled
# live like the prefs/flag files; absent or disabled → the frozen framing is
# used unchanged. See Engine/calibration.py.
CALIBRATION_FILE  = Path.home() / ".iris" / "calibration.json"

# Display modes
#   wallpaper   – borderless desktop-level layer (DEFAULT, daemon-friendly)
#   fullscreen  – proper fullscreen window, ESC/Q quits
DISPLAY_MODE = os.environ.get("PARALLAX_MODE", "wallpaper").lower()
DAEMON_MODE  = os.environ.get("PARALLAX_DAEMON", "0") == "1"
ICON_DEBUG   = os.environ.get("PARALLAX_ICON_DEBUG", "0") == "1"

# ─── Frame-rate caps ──────────────────────────────────────────────────────────
# The head-tracking input updates at only ~30 Hz (MediaPipe VIDEO mode), so a
# 60 Hz RENDER loop redraws every parallax frame TWICE from identical head data —
# the second copy is pure wasted GPU + compositor work. As a desktop *wallpaper*
# this is the main reason opening other apps stutters: the window server has to
# recomposite a full-screen, native-Retina scene under every other window 60× a
# second. Capping the wallpaper/fullscreen render to 30 fps roughly halves GPU,
# WindowServer and PyOpenGL CPU load with no perceptible change to the parallax
# (it is still ≥ the input rate). The interactive onboarding demo keeps 60 fps so
# cursor/hover feedback stays crisp.
FPS_DEMO      = 60
FPS_WALLPAPER = 30

# ─── Camera / parallax constants (preserved from working version) ─────────────
MAX_SHIFT  = 4.5
BASE_Z     = 11.5     # neutral eye distance — MUST equal orbital_math.CAM_BASE_Z

# Camera smoothing. Historically a FIXED per-frame lerp factor (cam += 0.55·(target
# − cam)). A fixed per-frame factor makes the time-constant frame-rate dependent:
# the same 0.55 reaches the target ~2× slower in wall-clock time at the 30 fps
# wallpaper cap than at the 60 fps demo, which made Desktop Mode feel laggier than
# the onboarding preview (audit, log 2026-06-01). Fix: derive a true exponential
# time-constant (tau) from the original 0.55 AT THE 60 fps REFERENCE RATE, then
# each frame use a dt-aware factor  alpha = 1 − e^(−dt/tau). This reproduces the
# calibrated 0.55 feel byte-for-byte at 60 fps and keeps the SAME wall-clock
# responsiveness at 30 fps (and any other rate) instead of doubling the lag.
CAM_LAG          = 0.55            # legacy per-frame factor — the calibrated feel…
CAM_LAG_REF_FPS  = 60.0           # …as measured at this reference render rate
CAM_LAG_TAU      = -(1.0 / CAM_LAG_REF_FPS) / math.log(1.0 - CAM_LAG)  # ≈ 0.0209 s
CAM_LAG_DT_MAX   = 0.10           # clamp the smoothing dt so a long stall (resume
                                  # from pause, first frame) can't snap in one step

# Depth response to head-z — TELEPHOTO via eye-to-glass distance, applied
# IDENTICALLY to EVERY world. Exponential in head-z so the scale is perceptually
# uniform (constant multiplier per unit lean): cz = BASE_Z · e^(+ZOOM_K · hz):
#   • hz = 0  → cz = BASE_Z (neutral framing preserved exactly)
#   • lean IN  (hz→+1)  → larger cz → narrower frustum → world LARGER,  parallax weaker
#   • lean OUT (hz→-0.7)→ smaller cz → wider  frustum → world smaller, parallax stronger
# This is the calibrated telephoto feel that sim_viewing / sim_vertical pin for the
# OBJECT worlds (Earth / The Watcher) and that keeps the near-field vertical "push
# the planet off-screen" exploration.
#
# The ENCLOSURE worlds (Grid Room, Gem — world.enveloping = True) now use this SAME
# response, per the user's directive that the grid worlds' zoom operate EXACTLY like
# the sphere worlds. Because a gem sits at the Earth anchor (z = −10) and the camera
# math is shared, the gem subtends the SAME on-screen size the Earth would at any
# given head-z — initially and at full lean-in. (A 2026-06-02 experiment instead held
# cz constant and dollied the scene forward INTO enclosures to read as "entering a
# room"; it grew the gem ~3.6× and made its size diverge from Earth's, which the user
# rejected — so the forward dolly was removed. See log 2026-06-02.)
ZOOM_K     = 0.95     # head-z → log eye distance; hz∈[-0.7,1]→cz∈[≈5.9,≈29.7]
CAM_Z_MIN  = 5.0      # safety clamps — do not bind in the normal head-z range
CAM_Z_MAX  = 34.0

# Rotational-exploration gain (proximity-gated in the loop via om.proximity).
# Horizontal (yaw) uses ROT_MAX_DEG — the user reports lateral looking already
# feels excellent, so it is left untouched.
ROT_MAX_RAD = math.radians(om.ROT_MAX_DEG)

# ── Enclosure / grid worlds do NOT pan (rotational look held at zero) ─────────
# The ENCLOSURE worlds (Grid Room, Gem — world.enveloping = True) draw a front rim on
# the glass at world z = 0. Under the off-axis projection, geometry exactly on that
# z = 0 window plane maps to the screen edges for ANY eye position or zoom, so the rim
# is a HARD "bezel anchor" — the whole point of the grid: it communicates real cm² of
# digital space, a box behind the glass. A rotational look pans the view about the eye,
# which rotates that still-visible rim and SHEARS it — an anchored wall and a pan are a
# direct contradiction. Capping the pan (an earlier LOOK_ENCLOSURE_AMP) only made the
# shear smaller, never clean, so the enclosure look is simply ZERO (handled inline in
# the frame loop). Clean panning is exclusive to the SPHERE worlds, which have no
# anchored walls — that is for exploring the void; grids communicate the parallax box
# directly. Object / sphere worlds keep the full proximity-gated look, untouched.
# Pinned by Scripts/validation/sim_envelop.py.

# NEAR-FIELD VERTICAL EXPLORATION (Objective #2). Vertical looking gets its OWN,
# larger gain than yaw so that up close the viewer can peer UP / DOWN far enough
# to push the Earth off the top / bottom of the screen — like leaning to look
# up and down through a real nearby window. It is gated by the SAME proximity
# weight as yaw (om.proximity), so FAR-field vertical behaviour is unchanged
# (prox→0 ⇒ no vertical exploration); the effect grows smoothly as the viewer
# approaches. The final pan is clamped so the (geometrically expansive) upward
# side cannot over-rotate into discomfort.
#   • ROT_MAX_PITCH_DEG : vertical gain at full proximity + full head pitch.
#                         CALIBRATE if Earth leaves too easily/reluctantly.
#   • PITCH_PAN_MAX_DEG : hard clamp on the vertical pan magnitude (anti-nausea).
ROT_MAX_PITCH_DEG = 40.0
PITCH_PAN_MAX_DEG = 46.0
ROT_MAX_PITCH_RAD = math.radians(ROT_MAX_PITCH_DEG)
PITCH_PAN_MAX_RAD = math.radians(PITCH_PAN_MAX_DEG)

# Pitch re-zeroing onto the PLANET (the focal point). The webcam sits ABOVE the
# screen while the Earth is rendered near screen-centre, so the planet is a few
# inches BELOW the camera. A viewer resting their gaze on the planet is therefore
# tilting their head DOWN, and MediaPipe — which measures head pitch relative to
# the camera — reads that as "looking down" and pans the portal downward on its
# own. The effect grows as the viewer approaches (the planet drops further below
# the camera axis), which is exactly when rotation matters most.
#
# Fix: subtract a PROXIMITY-SCALED pitch bias so that looking AT the planet is the
# neutral (no-pan) pose and only deviations from it pan the view — rotation
# becomes relative to the planet, not the camera. The bias vanishes far away
# (prox→0, planet ≈ collinear with the camera) and reaches LOOK_PITCH_OFFSET up
# close (prox→1). Pitch ONLY — the planet sits directly below the camera, so yaw
# needs no offset. Lateral parallax, distance scaling and yaw are untouched.
#
# LOOK_PITCH_OFFSET is the resting downward-pitch READING (normalised −1..+1
# units) when the viewer is closest. It both (a) centres the resting gaze on the
# planet and (b) sets where the vertical-exploration range is balanced: because
# raw pitch saturates at +1, a LARGE offset eats the downward range and makes the
# upward side twitchy (head-level already pans far up). It is lowered from the
# earlier 0.6 to 0.25 so that near-field UP and DOWN exploration are roughly
# SYMMETRIC about the planet-resting gaze — the Earth clears the frame with a
# comparable deliberate tilt either way (Objective #2). This trades a little
# planet-anchor strength for usable downward exploration, which is the priority
# this round.
#   CALIBRATE LIVE: lean in, rest your eyes on the planet.
#     • raise it  → stronger planet centring, but downward exploration weakens
#                   and small upward glances throw the Earth off-screen sooner;
#     • lower it  → more symmetric up/down exploration, weaker centring anchor.
#   It may need the OPPOSITE sign if your tracker reports "looking down" as
#   +pitch (see tracker._PITCH_SIGN).
LOOK_PITCH_OFFSET = 0.25

# Objects: (base_x, base_y, base_z, parallax_factor)
# Under the off-axis "window" projection the scene is FIXED in world space and
# all parallax is produced by the eye moving relative to the stationary objects
# (the asymmetric frustum shears the view). The old symmetric gluLookAt rig
# needed an artificial per-object follow to fake parallax; that would now double
# the motion, so parallax_factor is 0 — the Earth simply sits at z = -10 and the
# geometry does the rest. (Field kept so the draw path and any future per-object
# artistic offset stay unchanged.)
OBJECTS = {
    "earth": ( 0.0,  0.0, -10.0, 0.0),
}


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _gl_drawable_size() -> tuple[int, int]:
    """Read the live GL viewport — handles Retina 2× backing automatically."""
    vp = (ctypes.c_int * 4)()
    glGetIntegerv(GL_VIEWPORT, vp)
    return int(vp[2]), int(vp[3])


def _enable_retina_surface() -> bool:
    """Make the SDL/OpenGL view render at the native Retina backing resolution.

    pygame 2.6's `ALLOW_HIGHDPI` window flag is a **no-op** on macOS (verified
    live: the GL drawable stays 1× with or without it). Without a high-res
    surface the entire window renders at 1× and macOS upscales it 2× — blurring
    BOTH the 3-D scene and the UI overlay. We fix it the way the flag was
    supposed to: set Cocoa's `wantsBestResolutionOpenGLSurface` directly on the
    SDL content view, then refresh the GL context so the drawable picks up the
    2× backing. Returns True if the high-res surface was enabled."""
    if not _HAVE_COCOA:
        return False
    try:
        import objc
        info = pygame.display.get_wm_info()
        capsule = info.get("window")
        if not capsule:
            return False
        # The SDL window handle arrives as a PyCapsule named "window".
        ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
        ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
        ptr = ctypes.pythonapi.PyCapsule_GetPointer(capsule, b"window")
        view = objc.objc_object(c_void_p=ptr).contentView()
        if not view.respondsToSelector_(b"setWantsBestResolutionOpenGLSurface:"):
            return False
        view.setWantsBestResolutionOpenGLSurface_(True)
        ctx = NSOpenGLContext.currentContext()
        if ctx is not None:
            ctx.update()           # refresh the drawable to the new 2× backing
        return True
    except Exception as e:
        print(f"[cocoa] best-resolution surface failed: {e}")
        return False


def _drop_to_desktop_level() -> None:
    """Pin the render window to the macOS desktop window level —
    below every app/widget, above the wallpaper proper. Click-through."""
    if not _HAVE_COCOA:
        return
    try:
        lvl = CGWindowLevelForKey(kCGDesktopWindowLevelKey)
        for w in NSApp.windows():
            w.setLevel_(lvl)
            w.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces |
                NSWindowCollectionBehaviorStationary
            )
            w.setIgnoresMouseEvents_(True)
    except Exception as e:
        print(f"[cocoa] setLevel failed: {e}")


def _hide_from_dock() -> None:
    """Demote NSApp activation policy so the wallpaper daemon doesn't
    appear in the Dock or Cmd-Tab switcher."""
    if not _HAVE_COCOA:
        return
    try:
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception as e:
        print(f"[cocoa] hide-from-dock failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    pygame.init()
    info = pygame.display.Info()
    SCREEN_W, SCREEN_H = info.current_w, info.current_h

    # `demo` (onboarding) runs in a centred, focusable window; wallpaper and
    # fullscreen keep their full-screen behaviour unchanged.
    if DISPLAY_MODE == "demo":
        W = min(1180, int(SCREEN_W * 0.70))
        H = min(760,  int(SCREEN_H * 0.72))
        os.environ.pop("SDL_VIDEO_WINDOW_POS", None)
        os.environ["SDL_VIDEO_CENTERED"] = "1"
    else:
        W, H = SCREEN_W, SCREEN_H

    # Request OpenGL 2.1 compatibility + MSAA. The interactive onboarding demo
    # uses 4× MSAA for the crispest first impression; the wallpaper/fullscreen
    # daemon drops to 2× — at desktop scale, recomposited under every window, 4×
    # MSAA is a real GPU/compositor cost for a barely-perceptible edge-quality
    # gain. (MSAA is fixed at context creation, so the demo→Desktop in-process
    # switch keeps whatever it launched with; the standalone wallpaper daemon
    # launches with PARALLAX_MODE=wallpaper and gets 2× from the start.)
    msaa_samples = 4 if DISPLAY_MODE == "demo" else 2
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 2)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 1)
    try:
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, msaa_samples)
    except pygame.error:
        pass

    if DISPLAY_MODE == "fullscreen":
        flags = DOUBLEBUF | OPENGL | FULLSCREEN
    elif DISPLAY_MODE == "demo":
        flags = DOUBLEBUF | OPENGL
    else:
        flags = DOUBLEBUF | OPENGL | NOFRAME
    pygame.display.set_mode((W, H), flags)
    pygame.display.set_caption("Iris" if DISPLAY_MODE == "demo" else "Parallax Wall")
    pygame.mouse.set_visible(DISPLAY_MODE != "fullscreen")

    if DISPLAY_MODE == "wallpaper":
        _drop_to_desktop_level()
        if DAEMON_MODE:
            _hide_from_dock()

    # Render at the true Retina backing resolution (the pygame HIGHDPI flag is a
    # no-op on macOS; this Cocoa call is what actually makes it 2×). Must run
    # before reading the GL drawable so the viewport reflects the 2× surface.
    _enable_retina_surface()

    # Retina-aware GL drawable
    W_gl, H_gl = _gl_drawable_size()
    if W_gl == 0 or H_gl == 0:
        W_gl, H_gl = W, H
    glViewport(0, 0, W_gl, H_gl)

    print(f"[main] window {W}×{H}  GL drawable {W_gl}×{H_gl}  mode={DISPLAY_MODE}")
    print(f"[main] GL_VERSION  = {glGetString(GL_VERSION).decode()}")
    print(f"[main] GL_RENDERER = {glGetString(GL_RENDERER).decode()}")
    print(f"[main] GLSL        = {glGetString(GL_SHADING_LANGUAGE_VERSION).decode()}")

    # Standing GL state
    glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LEQUAL)
    glHint(GL_PERSPECTIVE_CORRECTION_HINT, GL_NICEST)
    glClearColor(0.0, 0.0, 0.012, 1.0)
    try:
        glEnable(GL_MULTISAMPLE)
    except Exception:
        pass

    # Scene
    print("[main] Loading textures & compiling shaders…")
    nebula = Nebula()
    stars  = Stars()
    earth  = Earth()
    icons  = IconOrbit(debug=ICON_DEBUG)
    print("[main] Scene assembled.")

    # ── World system (JSON-defined, live-switchable: Earth, The Watcher, …) ────
    # The active world is read from ~/.iris/preferences.json and re-polled each
    # frame, so switching takes effect live in the demo AND the wallpaper daemon.
    # Camera/parallax are world-agnostic; only the drawn assets change.
    from Worlds.world_runtime import WorldRuntime, resolve_worlds_dir
    world = WorldRuntime(resolve_worlds_dir(_BUNDLE_BASE), PREFS_FILE)
    eye   = None   # The Watcher's eyeball — built lazily + guarded on first use,
                   # so an Earth-only session never touches the eye shader/texture.
    gem   = None   # The Gem — built lazily on first use, same guard pattern.
    room  = None   # The Grid Room — wireframe shadow-box, built lazily, same guard.
    placeables = None  # World Builder placeable-object draw helper, built lazily.

    # Live, mtime-cached metric calibration. Disabled by default, so half_h()→None
    # (camera_math uses the frozen WINDOW_HALF_H) and shift_scale→1.0: the camera
    # pipeline is byte-identical to before unless the user opts in.
    calib = calib_mod.CalibrationRuntime(CALIBRATION_FILE)
    print(f"[main] World system ready — active '{world.name}', available {world.available()}")

    # Bloom post-processing has been removed (user decision, 2026-06-01). The
    # scene now renders straight to the (multisampled) default framebuffer — no
    # off-screen FBO, no bright-extract/blur/composite. This drops the glow AND
    # the old composite grade (Reinhard tonemap, exposure ×1.22, vignette,
    # chromatic aberration); the trade was accepted. Everything the illusion
    # needs is generated upstream and is unaffected: off-axis parallax (camera
    # math), star twinkle (stars shader), and the gem's facet shimmer (gem
    # shader). A side benefit — the scene previously rendered into a
    # NON-multisampled bloom FBO, so MSAA never actually applied; drawing to the
    # default framebuffer now gives real anti-aliasing for the first time.

    # Projection is rebuilt every frame as an off-axis "window" frustum keyed to
    # the live eye position (orbital_math.off_axis_frustum). Here we only cache
    # the aspect ratio; gluPerspective is no longer used. At the neutral eye
    # (centred, z = BASE_Z) the off-axis frustum is identical to the old
    # gluPerspective(58°), so the resting framing is unchanged.
    aspect = W_gl / max(1, H_gl)
    glMatrixMode(GL_MODELVIEW)

    # Tracker. In demo mode the camera is NOT opened until the user grants it via
    # the onboarding overlay, so the macOS TCC prompt is preceded by our primer
    # card; in wallpaper/fullscreen it starts immediately as before.
    tracker = FaceTracker()
    overlay = None
    tracker_started = False
    desktop_active = False   # True once the demo window becomes the in-process wallpaper
    if DISPLAY_MODE == "demo":
        from UI.demo_overlay import DemoOverlay
        # Render the HUD at PHYSICAL resolution (scale = drawable/window) so text
        # is crisp on Retina instead of GL-upscaled. The overlay self-detects a
        # running wallpaper daemon (PID file) for correct reopen routing.
        overlay = DemoOverlay(W, H, scale=(W_gl / max(1, W)))
    else:
        # Wallpaper/fullscreen: start tracking immediately — UNLESS the user has
        # disabled camera access in Settings, in which case we never open the
        # camera (and never prompt). It is lazily started in the loop if the
        # camera is re-enabled later.
        if not CAMERA_OFF_FLAG.exists():
            tracker.start()
            tracker_started = True

    # Camera & animation state
    cam_x = cam_y = 0.0
    cam_z         = BASE_Z
    cam_yaw = cam_pitch = 0.0   # smoothed, proximity-gated view rotation (rad)

    # Sun in WORLD space — slight front-right + above
    sun_world  = np.array([0.55, 0.42, 0.72], dtype=np.float32)
    sun_world /= np.linalg.norm(sun_world)

    # Fill light (secondary, used by Gem): left-low-front, ~120° from key
    fill_world = np.array([-0.72, -0.30, 0.65], dtype=np.float32)
    fill_world /= np.linalg.norm(fill_world)

    clock = pygame.time.Clock()
    t0    = time.time()
    last  = t0
    last_state_write = 0.0  # throttles the icons-app state export (see below)
    window_visible = True   # Cocoa orderOut/orderFront mirrors this

    def _set_window_visible(visible: bool) -> None:
        """Show/hide the wallpaper window via Cocoa so the real macOS
        wallpaper shows through when the engine is toggled off."""
        if not (_HAVE_COCOA and DISPLAY_MODE == "wallpaper"):
            return
        try:
            for w in NSApp.windows():
                if visible:
                    w.orderFrontRegardless()
                else:
                    w.orderOut_(None)
        except Exception:
            pass

    # ── Orbital icons are decorative / non-interactive ────────────────────────
    # The icons are purely spatial wallpaper elements. We deliberately install
    # NO global mouse monitor and run NO per-frame hit-testing: click handling
    # added latency and instability for zero benefit on a click-through desktop
    # layer. Mouse events pass straight through to Finder / app windows beneath.

    while True:
        now  = time.time()
        dt   = now - last
        last = now
        t_s  = now - t0
        # Cap the render rate. The interactive demo runs at 60; once it becomes
        # the in-process wallpaper (desktop_active) — and in wallpaper/fullscreen
        # modes — drop to 30 to stop monopolising the GPU/compositor (see FPS_*).
        target_fps = FPS_DEMO if (DISPLAY_MODE == "demo" and not desktop_active) else FPS_WALLPAPER
        clock.tick(target_fps)

        # Input — keyboard quit only works in fullscreen mode (wallpaper
        # window has no focus). Daemon mode never quits on keys.
        mouse_pos = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == QUIT and not DAEMON_MODE:
                pygame.quit(); return
            if ev.type == KEYDOWN and ev.key in (K_ESCAPE, K_q) and DISPLAY_MODE in ("fullscreen", "demo"):
                pygame.quit(); return
            if overlay is not None:
                overlay.handle_event(ev, mouse_pos)

        # ── Demo (onboarding) per-frame control ───────────────────────────────
        # The overlay drives a small state machine; the engine only reacts to its
        # signals. Desktop Mode is performed IN-PROCESS (see below): no detached
        # daemon, so the camera grant is preserved, closing the app exits
        # everything, and relaunch is never blocked by a leftover process.
        if DISPLAY_MODE == "demo" and not desktop_active:
            overlay.update(dt)
            # Camera-access gate (Settings): if the user disabled the camera, stop
            # tracking immediately (camera released, head drifts to idle). The
            # overlay also drops out of live mode, so the scene falls back to the
            # scripted floating preview rather than freezing.
            cam_off = CAMERA_OFF_FLAG.exists()
            if cam_off and tracker_started:
                tracker.set_tracking(False)
            # Enable Camera → start tracking instantly (the TCC prompt is the OS's,
            # not a loading screen); the demo flips floating → live with no reload.
            # Suppressed while camera access is disabled in Settings.
            if overlay.tracking_requested and not cam_off:
                overlay.tracking_requested = False
                if not tracker_started:
                    # First enable: settle macOS authorization on the main thread,
                    # then spawn the worker. We ACT on the outcome rather than
                    # assuming success (the previous bug).
                    perm = tracker.start()
                    if perm == DENIED:
                        # No worker was spawned. Show the actionable status and leave
                        # tracker_started False so a later click can retry.
                        overlay.notify_camera_denied()
                    else:
                        tracker.set_tracking(True)
                        tracker_started = True
                else:
                    # Worker already running but was paused by the camera-off toggle.
                    # Resume tracking — the worker re-opens the camera on its next tick.
                    tracker.set_tracking(True)
            # Enable Desktop Mode → reconfigure THIS window into a click-through,
            # desktop-level wallpaper IN THE SAME PROCESS, keeping the already-
            # authorized camera/tracker running. SDL preserves the GL context and
            # textures across the resize, so only the viewport + aspect are
            # updated. The window stays in the Dock (not accessory) so the user can
            # always quit it (Cmd-Q / Dock → Quit), and quitting exits everything.
            if overlay.desktop_mode_requested:
                # Derive the new drawable from the backing scale measured at
                # startup (now correctly 2.0 on Retina thanks to the best-res
                # surface), then re-assert the high-res surface after the resize.
                scale = W_gl / max(1, W)       # drawable/window (Retina = 2.0, else 1.0)
                pygame.display.set_mode((SCREEN_W, SCREEN_H),
                                        DOUBLEBUF | OPENGL | NOFRAME)
                pygame.mouse.set_visible(False)
                _drop_to_desktop_level()       # desktop level + click-through (NOT dock-hidden)
                _enable_retina_surface()       # keep native Retina backing across the resize
                W, H = SCREEN_W, SCREEN_H
                W_gl, H_gl = int(round(W * scale)), int(round(H * scale))
                glViewport(0, 0, W_gl, H_gl)
                aspect = W_gl / max(1, H_gl)
                desktop_active = True
                overlay.desktop_mode_requested = False
                print("[main] Desktop Mode active (in-process wallpaper)")
            if overlay.should_quit:
                pygame.quit(); return
        else:
            # ── Toggle state (wallpaper / fullscreen only) ────────────────────
            # ~/.parallax_off is the master switch (camera + rendering both off)
            engine_off = TRACKING_OFF_FLAG.exists()
            # Camera-access gate (Settings): when disabled, keep rendering the
            # world but never open the camera — head input drifts to its idle
            # (centred) state, so Desktop Mode stays alive without face tracking.
            # Lazily start the tracker the first time the camera is re-enabled.
            cam_off = CAMERA_OFF_FLAG.exists()
            if not cam_off and not tracker_started:
                tracker.start()
                tracker_started = True
            if tracker_started:
                tracker.set_tracking(not engine_off and not cam_off)

            if engine_off:
                # Hide the window so the user sees their real macOS wallpaper.
                # Daemon stays alive — toggle ON brings it back instantly.
                if window_visible:
                    _set_window_visible(False)
                    window_visible = False
                    print("[main] Engine paused (wallpaper hidden, camera released)")
                time.sleep(0.25)
                continue
            else:
                if not window_visible:
                    _set_window_visible(True)
                    # Re-apply desktop level (Cocoa sometimes forgets after orderOut)
                    if DISPLAY_MODE == "wallpaper":
                        _drop_to_desktop_level()
                    window_visible = True
                    print("[main] Engine resumed")

        # ── Camera update — three INDEPENDENT, BLENDED viewing components ──────
        # Head input SOURCE differs by mode (the camera MATH below is identical):
        # before camera grant the demo feeds a scripted idle path into the very
        # same variables, so onboarding parallax uses the unchanged engine.
        if DISPLAY_MODE == "demo" and not desktop_active and not (overlay.live and tracker_started):
            # Floating preview: scripted idle motion (State A). In desktop mode the
            # window tracks live (desktop_active → fall through to tracker.head()).
            hx, hy, hz, yaw, pitch = overlay.scripted_head(t_s)
        else:
            hx, hy, hz, yaw, pitch = tracker.head()
            if overlay is not None and not overlay.tracking_active \
                    and (abs(hx) + abs(hy) + abs(hz)) > 1e-4:
                overlay.notify_tracking_active()

        # Frame-rate-independent smoothing factor for this frame. Derived from the
        # exponential time-constant CAM_LAG_TAU so the wall-clock responsiveness is
        # identical at 30 and 60 fps (it equals the legacy 0.55 at 60 fps). dt is
        # clamped so a long stall can't produce a one-frame snap.
        cam_alpha = 1.0 - math.exp(-min(dt, CAM_LAG_DT_MAX) / CAM_LAG_TAU)

        # Per-user metric calibration (opt-in; default = frozen framing). Polled
        # live so a Settings change / hand-edit takes effect without a restart.
        #   • win_half_h is None when disabled → off_axis_frustum uses the frozen
        #     WINDOW_HALF_H (byte-identical); a value matches the user's real
        #     screen subtense at the neutral eye distance.
        #   • shift is the lateral head-shift gain, scaled by parallax_gain (×1.0
        #     when disabled).
        calib.poll()
        win_half_h = calib.half_h()
        shift      = MAX_SHIFT * calib.shift_scale

        # 1. TRANSLATION (head position → eye position → off-axis frustum shear).
        # Horizontal axis is negated: the webcam image is mirrored left-right, so
        # raw hx tracks the wrong way. Flipping it gives the "looking through a
        # window" feel — head right reveals the scene's left side. Vertical (hy)
        # already reads correctly, so it is left unchanged.
        cam_x += cam_alpha * (-hx * shift        - cam_x)
        cam_y += cam_alpha * ( hy * shift * 0.55 - cam_y)

        # 2. DEPTH RESPONSE (head depth → on-screen scale) — TELEPHOTO, identical for
        # EVERY world. Leaning IN (hz → +1) pushes the eye AWAY from the glass so the
        # frustum narrows and the world grows; leaning OUT pulls the eye toward the
        # glass so the world recedes. cam_z also sets translational-parallax strength
        # (strong far / reduced close). The enclosure worlds (Grid Room, Gem) use this
        # SAME response — so the gem at the Earth anchor (z = −10) subtends the SAME
        # on-screen size the Earth would at any given head-z (the grid worlds zoom
        # EXACTLY like the sphere worlds, per the user's directive). The earlier
        # forward-dolly enclosure mechanism was removed. (off-axis-projection.md)
        cam_z_target = max(CAM_Z_MIN, min(CAM_Z_MAX, BASE_Z * math.exp(ZOOM_K * hz)))
        cam_z += cam_alpha * (cam_z_target - cam_z)

        # 3. ROTATION (head orientation → view pan), gated by PROXIMITY so it is
        # weak far away and dominant up close — a smooth blend, never a switch.
        # Turning the head right pans the portal right (revealing the scene's
        # RIGHT — the opposite sense to translation, as intended). The gate TIMING is
        # IDENTICAL for every world — om.proximity(hz), the frozen [0.0, 0.8] band — so
        # the enclosure look fades in over the SAME head-z distances as the Earth world.
        prox        = om.proximity(hz)
        yaw_target  =  yaw   * ROT_MAX_RAD * prox
        # Vertical uses its OWN larger gain (ROT_MAX_PITCH_RAD) so the viewer can
        # peer up/down far enough to push the Earth off-screen up close, then the
        # pan is clamped so the expansive upward side never over-rotates. Both are
        # still proximity-gated, so the far field is unchanged. (Yaw keeps the
        # untouched ROT_MAX_RAD — lateral looking already feels right.)
        pitch_in    = (pitch - LOOK_PITCH_OFFSET * prox) if tracker.has_rotation else pitch
        pitch_tgt   =  pitch_in * ROT_MAX_PITCH_RAD * prox
        # ENCLOSURE / GRID worlds (Grid Room, Gem — world.enveloping = True): NO pan.
        # The grid's whole purpose is to communicate real cm² of digital space — a box
        # anchored to the bezel, behind the glass. Rotating the view pans the view about
        # the eye, which rotates that still-visible z = 0 rim and SHEARS it: an anchored
        # wall and a rotational look cannot cleanly coexist. Clean panning works on the
        # SPHERE worlds precisely because they have no anchored walls — that is for
        # exploring the void; grids are for reading the parallax box directly. So the
        # enclosures keep the smooth telephoto zoom, the parallax window shift and the
        # bezel anchor, but the rotational look is held at ZERO. (Tried capping the pan;
        # any non-zero pan still shears the anchored rim — reverted 2026-06-02.) Object /
        # sphere worlds are untouched → byte-identical.
        if world.enveloping:
            yaw_target = 0.0
            pitch_tgt  = 0.0
        pitch_tgt   =  max(-PITCH_PAN_MAX_RAD, min(PITCH_PAN_MAX_RAD, pitch_tgt))
        cam_yaw    += cam_alpha * (yaw_target - cam_yaw)
        cam_pitch  += cam_alpha * (pitch_tgt  - cam_pitch)

        # ── Export state for the separate icons_overlay Cocoa app ─────────────
        # Since the orbital icons in the wallpaper mode's GL engine are purely
        # decorative/non-interactive, the clickable macOS desktop icons are
        # provided by a separate Cocoa process (orbital_icons.py). We export the
        # current smoothed camera state so that process can align its 2-D
        # projection with the 3-D Earth perfectly.
        # Throttled to ≤30 Hz: the head input itself updates at only ~30 Hz, so a
        # faster write just re-serialises identical values to disk in the render
        # thread (a synchronous filesystem write every frame was ~55 µs each and a
        # source of hitches). The separate icons app reads the latest snapshot, so
        # 30 Hz is ample for alignment.
        if now - last_state_write >= (1.0 / 30.0):
            last_state_write = now
            try:
                state_data = {
                    "hx": float(hx), "hy": float(hy), "hz": float(hz),
                    "cam_x": float(cam_x), "cam_y": float(cam_y), "cam_z": float(cam_z),
                    "cam_yaw": float(cam_yaw), "cam_pitch": float(cam_pitch),
                    "t_s": float(t_s),
                    # Effective window half-height (frozen value unless the user
                    # enabled metric calibration). Exported so the separate
                    # orbital_icons.py process can match the GL engine's framing;
                    # it currently assumes the frozen value, so under calibration
                    # the 2-D desktop icons may drift until they read this.
                    "win_half_h": float(win_half_h if win_half_h is not None else om.WINDOW_HALF_H),
                    "timestamp_ms": int(time.time() * 1000)
                }
                EARTH_STATE_FILE.write_text(json.dumps(state_data))
            except Exception:
                pass

        # Animate
        earth.update(dt)
        icons.update(dt)
        if eye is not None:
            eye.update(dt, hx, hy)
        if gem is not None:
            gem.update(dt)

        # Live world switch (cheap, mtime-cached; works in demo + daemon).
        world.poll()

        dpi_scale = max(1.0, W_gl / max(1, W))

        # ── World-preview suspend (demo only) ─────────────────────────────────
        # When the demo shows a non-Worlds tab (Settings / Community), the live
        # 3-D preview is fully hidden behind the solid card, so rendering it is
        # wasted GPU. Skip the ENTIRE scene draw: clear to a neutral dark, then
        # composite only the HUD card and flip. The preview restores the instant
        # the Worlds tab is reselected (overlay.preview_active flips True). Never
        # applies once Desktop Mode is active — the wallpaper must keep rendering.
        if (DISPLAY_MODE == "demo" and not desktop_active
                and overlay is not None and not overlay.preview_active):
            glClearColor(0.05, 0.05, 0.06, 1.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            overlay.draw_gl(W_gl, H_gl)
            pygame.display.flip()
            continue

        # Render straight to the default (multisampled) framebuffer — bloom
        # removed, so there is no off-screen FBO to bind. Viewport is already set
        # at startup and on the Desktop-Mode resize.

        # Per-world clear colour: Earth keeps its near-black blue; The Watcher is
        # a pure black void. (Identical value for Earth → no behavioural change.)
        cc = world.clear_color
        glClearColor(cc[0], cc[1], cc[2], 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # ── Off-axis "window" projection ──────────────────────────────────────
        # The monitor is a fixed rectangle at world z = 0; the eye is the tracked
        # head position. Rebuild the asymmetric frustum every frame so lateral eye
        # motion shears the view (true motion parallax) and the eye-to-glass
        # distance sets the subtended angle (the distance-scaling component). The
        # frustum itself carries no rotation — that lives in the modelview below.
        # Validated headlessly in sim_offaxis.py / sim_viewing.py.
        proj = om.off_axis_frustum(cam_x, cam_y, cam_z, aspect, half_h=win_half_h)
        glMatrixMode(GL_PROJECTION)
        glLoadMatrixf(np.ascontiguousarray(proj.T, dtype=np.float32))
        glMatrixMode(GL_MODELVIEW)

        # Modelview: proximity-gated view rotation about the eye, then eye→origin.
        # When far (prox→0) cam_yaw/pitch decay to 0 and this is a pure window;
        # up close it pans the portal so the viewer can "peek around" the world.
        mv = om.view_matrix(cam_x, cam_y, cam_z, cam_yaw, cam_pitch)
        glLoadMatrixf(np.ascontiguousarray(mv.T, dtype=np.float32))

        # Sun in EYE space (every shader does its math there). The view rotation
        # is the upper-left 3×3 of the modelview we just built on the CPU — use it
        # directly instead of reading GL_MODELVIEW_MATRIX back, which forced a
        # GPU→CPU pipeline stall every single frame for a value we already have.
        view_rot = mv[:3, :3]
        sun_eye  = (view_rot @ sun_world).tolist()
        fill_eye = (view_rot @ fill_world).tolist()

        # ── World-composed scene ──────────────────────────────────────────────
        # The active world's JSON declares its background, primary mesh and
        # whether orbital icons appear. Everything above (off-axis frustum,
        # modelview, sun) is world-AGNOSTIC and identical for every world — only
        # the drawn assets change, so the parallax/zoom/rotation feel is shared.

        # 1. Background — Earth's Milky Way + parallax stars, or an empty void.
        if world.background == "stars":
            # Milky Way (anchored to camera — feels infinitely distant)
            glPushMatrix()
            glTranslatef(cam_x, cam_y, cam_z)
            nebula.draw(t_s, brightness=0.85)
            glPopMatrix()
            # Multi-layer parallax stars
            stars.draw(t_s, dpi_scale=dpi_scale)
        # background == "void" → nothing drawn; the black clear colour IS the scene.

        # 2. Primary body. Most worlds anchor a single body at the (unchanged)
        #    Earth anchor (z = -10) so they share the exact off-axis parallax /
        #    zoom / rotation response. The Grid Room is the exception — an
        #    ENVIRONMENT drawn in world space whose front rim lands on the glass
        #    at z = 0 — so it is handled before the Earth-anchor translate.
        hw, hh = om.window_half_extents(aspect, win_half_h)   # live aperture extents

        if world.primary_mesh == "room":
            # Wireframe shadow-box room — built lazily like Eye/Gem; on failure
            # fall back to Earth rather than crash the engine.
            if room is None:
                try:
                    room = GridRoom()
                except Exception as e:
                    print(f"[main] Grid Room unavailable ({e}); falling back to Earth")
                    world.select("earth")
            if room is not None:
                room.draw(hw, hh, world.grid_depth, world.grid_divisions,
                          world.grid_color, t_s, dpi_scale)
                # World Builder: user-placed builtin primitives, drawn in world
                # space right after the grid (same frame of reference). Built
                # lazily + guarded; a failure here must never kill the wallpaper.
                objs = world.placeable_objects
                if objs:
                    if placeables is None:
                        try:
                            placeables = PlaceableObjects()
                        except Exception as e:
                            print(f"[main] PlaceableObjects unavailable ({e}); skipping")
                    if placeables is not None:
                        try:
                            placeables.draw(objs, hw, hh,
                                            world.grid_depth, world.grid_divisions)
                        except Exception as e:
                            print(f"[main] placeable draw failed ({e}); skipping")
            else:
                glPushMatrix(); glTranslatef(0.0, 0.0, OBJECTS["earth"][2])
                earth.draw(sun_eye, t_s); glPopMatrix()
        else:
            bx, by, bz, pf = OBJECTS["earth"]
            wx = bx + cam_x * pf
            wy = by + cam_y * pf

            # The Gem floats inside a checkered enclosure box that shares the Grid
            # Room's dimensions (aperture extents + grid_depth/grid_divisions). The
            # box is an ENVIRONMENT drawn in WORLD space (front rim on the glass at
            # z = 0), so it is built + drawn here, BEFORE the Earth-anchor translate.
            if world.primary_mesh == "gem":
                if gem is None:
                    try:
                        gem = Gem()
                    except Exception as e:
                        print(f"[main] The Gem unavailable ({e}); falling back to Earth")
                        world.select("earth")
                if gem is not None:
                    gem.draw_box(hw, hh, world.grid_depth, world.grid_divisions)

            glPushMatrix()
            glTranslatef(wx, wy, bz)
            if world.primary_mesh == "eye":
                # Build the eyeball lazily on first use; if its shader/textures fail
                # to load, log and fall back to Earth rather than crash the engine.
                if eye is None:
                    try:
                        eye = Eye()
                    except Exception as e:
                        print(f"[main] The Watcher unavailable ({e}); falling back to Earth")
                        world.select("earth")
                if eye is not None:
                    eye.draw(sun_eye, t_s)
                else:
                    earth.draw(sun_eye, t_s)
            elif world.primary_mesh == "gem":
                # The Gem — brilliant-cut rotating gemstone, floating inside the
                # checkered box drawn above. Built lazily there; if that failed the
                # world has already been switched to Earth, so gem is non-None here.
                if gem is not None:
                    gem.draw(sun_eye, fill_eye, t_s)
                else:
                    earth.draw(sun_eye, t_s)
            else:
                earth.draw(sun_eye, t_s)
                # Orbital icons live in EARTH-LOCAL space — drawn inside the very same
                # transform so they inherit Earth's parallax, camera, projection and
                # depth as one rigid body (real z-buffer occlusion, real perspective).
                # Worlds may opt out (The Watcher exists alone — no icons).
                if world.show_icons and not ICONS_OFF_FLAG.exists():
                    icons.draw(dpi_scale)
            glPopMatrix()

        # Opt-in window-frame anchor on the glass (world z = 0). Default OFF, so
        # the shipped Earth / Watcher / Gem worlds are unchanged; the Grid Room
        # draws its own rim, so it is excluded here.
        if world.show_window_frame and world.primary_mesh != "room":
            draw_window_frame(hw, hh, color=world.grid_color, dpi_scale=dpi_scale)

        # (Bloom Pass 2 removed — the scene is already on screen.)

        # ── Onboarding HUD (demo window only) — composited over the live scene.
        # Hidden once Desktop Mode is active: the window is then a click-through
        # fullscreen wallpaper and the HUD (sized for the small window) is not shown.
        if overlay is not None and not desktop_active:
            overlay.draw_gl(W_gl, H_gl)

        pygame.display.flip()


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        print("\nAPPLICATION CRASHED:")
        traceback.print_exc()
        try:
            input("\nPress ENTER to close…")
        except (EOFError, KeyboardInterrupt):
            pass
