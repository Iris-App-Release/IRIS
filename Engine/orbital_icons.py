#!/usr/bin/env python3
"""
icons_overlay.py — Orbital macOS application launcher for Parallax Wall.

Architecture:
  • Standalone PyObjC Cocoa app. No OpenGL, no SDL, no pygame.
  • Single transparent NSWindow that covers the main screen, pinned at
    kCGDesktopWindowLevel+1 (above the wallpaper, below Finder icons + apps).
  • Custom NSView draws real system NSImages of installed applications in
    elliptical orbits around the screen centre, animated at 60 Hz.
  • Window stays setIgnoresMouseEvents:YES so all clicks pass through to
    Finder / app windows below — preserving normal desktop behaviour.
  • An NSEvent global monitor catches mouse-down events anywhere on screen,
    hit-tests them against the current icon positions, and launches the
    matching app via NSWorkspace.openURL_ when there's a hit.
  • Toggle on/off via the flag file ~/.parallax_icons_off (polled at 1 Hz).

Configuration:
  Edit ~/.parallax_icons.json to choose which apps appear. Default list
  uses common system apps (Safari, Mail, Calendar, Notes, etc).
"""

from __future__ import annotations
import json, math, os, sys, time
from pathlib import Path

import objc
import numpy as np

# Add project root to path so we can import camera_math
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from Engine import camera_math as om

# ── Cocoa imports ─────────────────────────────────────────────────────────────
from Foundation import (
    NSObject, NSTimer, NSURL, NSMakeRect, NSMakePoint, NSMakeSize,
)
from AppKit import (
    NSApplication, NSApp,
    NSWindow, NSScreen, NSColor, NSView, NSImage,
    NSBackingStoreBuffered, NSWindowStyleMaskBorderless,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWorkspace, NSEvent,
    NSApplicationActivationPolicyAccessory,
    NSEventMaskLeftMouseDown,
    NSGraphicsContext, NSImageInterpolationHigh,
    NSShadow, NSCompositingOperationSourceOver,
)
from Quartz import CGWindowLevelForKey, kCGDesktopWindowLevelKey


HOME            = Path.home()
CONFIG_PATH     = HOME / ".parallax_icons.json"
FLAG_OFF        = HOME / ".parallax_icons_off"
EARTH_STATE_FILE = HOME / ".parallax_earth_state.json"
ORBITAL_APPS_DIR = Path("/Applications/Orbital Apps")

# Default app list — used if no config exists. Picks broad, commonly-installed
# items. Missing apps are silently skipped at load time.
_DEFAULT_APPS = [
    "/Applications/Safari.app",
    "/System/Applications/Mail.app",
    "/System/Applications/Calendar.app",
    "/System/Applications/Notes.app",
    "/System/Applications/Messages.app",
    "/System/Applications/Music.app",
    "/System/Applications/Photos.app",
    "/System/Applications/App Store.app",
    "/System/Applications/Maps.app",
    "/System/Applications/FaceTime.app",
]


def _ensure_config() -> None:
    """Write a default config on first run."""
    if CONFIG_PATH.exists():
        return
    CONFIG_PATH.write_text(json.dumps({
        "_doc": "Edit the 'apps' list to choose which icons orbit. Use full .app paths.",
        "apps": _DEFAULT_APPS,
        "orbit_radius_x": 520,
        "orbit_radius_y": 280,
        "icon_size":      80,
        "orbit_speed":    om.ORBIT_SPEED,
    }, indent=2))


def _load_config() -> dict:
    _ensure_config()
    try:
        data = json.loads(CONFIG_PATH.read_text())
        # Fill in defaults for any missing keys
        return {
            "apps":           data.get("apps", _DEFAULT_APPS),
            "orbit_radius_x": int(data.get("orbit_radius_x", 520)),
            "orbit_radius_y": int(data.get("orbit_radius_y", 280)),
            "icon_size":      int(data.get("icon_size", 80)),
            "orbit_speed":    float(data.get("orbit_speed", om.ORBIT_SPEED)),
        }
    except Exception as e:
        print(f"[icons] Config parse error ({e}) — using defaults")
        return {
            "apps": _DEFAULT_APPS,
            "orbit_radius_x": 520,
            "orbit_radius_y": 280,
            "icon_size":      80,
            "orbit_speed":    om.ORBIT_SPEED,
        }


def _desaturate_image(image, saturation: float = 0.48):
    """
    Return a copy of image with saturation reduced to `saturation` (0=grey, 1=full).
    Runs once at load time via CIColorControls — zero per-frame cost.
    Falls back to the original image if CoreImage is unavailable.
    """
    try:
        from Quartz import CIImage, CIFilter, CIContext
        tiff = image.TIFFRepresentation()
        ci   = CIImage.imageWithData_(tiff)
        f    = CIFilter.filterWithName_("CIColorControls")
        f.setDefaults()
        f.setValue_forKey_(ci,         "inputImage")
        f.setValue_forKey_(saturation, "inputSaturation")
        out  = f.outputImage()
        ctx  = CIContext.context()
        cg   = ctx.createCGImage_fromRect_(out, out.extent())
        size = image.size()
        result = NSImage.alloc().initWithCGImage_size_(cg, size)
        return result if result is not None else image
    except Exception as e:
        print(f"[icons] desaturate fallback ({e})")
        return image


def _load_apps(paths: list) -> list:
    """
    Resolve a list of .app paths into renderable icon descriptors.
    Returns a list of dicts: {path, name, url, image}.
    Silently skips paths that don't exist.
    """
    ws = NSWorkspace.sharedWorkspace()
    out = []
    for p in paths:
        if not Path(p).exists():
            continue
        url   = NSURL.fileURLWithPath_(p)
        image = ws.iconForFile_(p)
        if image is None:
            continue
        # Make the icon high-res so it scales cleanly when drawn larger
        image.setSize_(NSMakeSize(256, 256))
        # Tone down vivid icon colours so they don't glow on the dark desktop
        image = _desaturate_image(image)
        name = Path(p).stem
        out.append({"path": p, "name": name, "url": url, "image": image})
    return out


def _load_earth_state() -> dict:
    """
    Read the Earth transform state exported by app_engine.py.
    Returns dict with keys: hx, hy, hz, cam_x, cam_y, cam_z, cam_yaw, cam_pitch, t_s, timestamp_ms.
    Falls back to zero state if file is missing or stale.
    """
    try:
        if not EARTH_STATE_FILE.exists():
            return _zero_earth_state()
        data = json.loads(EARTH_STATE_FILE.read_text())
        # Freshness check — if file is older than 2s, we haven't heard
        # from the wallpaper daemon recently; use zero state for safety
        now_ms = int(time.time() * 1000)
        if now_ms - data.get("timestamp_ms", 0) > 2000:
            return _zero_earth_state()
        return data
    except Exception:
        return _zero_earth_state()


def _zero_earth_state() -> dict:
    """Return a neutral Earth state (no offset, no perspective shift)."""
    return {
        "hx": 0.0, "hy": 0.0, "hz": 0.0,
        "cam_x": 0.0, "cam_y": 0.0, "cam_z": 11.5,
        "cam_yaw": 0.0, "cam_pitch": 0.0,
        "t_s": 0.0,
        "timestamp_ms": 0,
    }


def _resolve_finder_alias(item: Path) -> str | None:
    """
    Resolve a macOS Finder alias file to its target POSIX path via NSURL.
    Returns the resolved path string, or None if resolution fails.
    """
    try:
        url = NSURL.fileURLWithPath_(str(item))
        resolved, _err = NSURL.URLByResolvingAliasFileAtURL_options_error_(url, 0, None)
        if resolved is not None:
            return resolved.path()
    except Exception:
        pass
    return None


def _resolve_to_app(item: Path) -> str | None:
    """
    Resolve an item in the Orbital Apps folder to a real .app bundle path.
    Handles: genuine .app dirs, symlinks pointing to .app dirs, and Finder
    aliases created by Option-dragging or cmd-alias in Finder.
    Returns the canonical absolute path, or None if not an .app bundle.
    """
    if item.name.startswith("."):
        return None
    # Real directory (follows symlinks via is_dir)
    if item.suffix == ".app" and item.is_dir():
        return str(item.resolve())
    # Finder alias — resolve via AppleScript
    target = _resolve_finder_alias(item)
    if target:
        tp = Path(target)
        if tp.suffix == ".app" and tp.is_dir():
            return str(tp.resolve())
    return None


def _scan_orbital_apps_folder() -> list:
    """
    Scan /Applications/Orbital Apps/ for .app bundles.
    Handles real .app directories, symlinks, and Finder aliases.
    Returns sorted list of canonical .app paths.
    """
    if not ORBITAL_APPS_DIR.exists():
        return []
    try:
        paths = []
        for item in ORBITAL_APPS_DIR.iterdir():
            real = _resolve_to_app(item)
            if real:
                paths.append(real)
        return sorted(paths)
    except Exception:
        return []


def _compute_earth_screen(cam_x: float, cam_y: float, cam_z: float,
                          cam_yaw: float, cam_pitch: float,
                          view_w: float, view_h: float) -> tuple:
    """
    Project Earth's world position to Cocoa logical pixels using the
    exact same off-axis projection and view rotation as the GL engine.
    """
    aspect = view_w / max(1.0, view_h)
    proj = om.off_axis_frustum(cam_x, cam_y, cam_z, aspect)
    view = om.view_matrix(cam_x, cam_y, cam_z, cam_yaw, cam_pitch)

    # Earth center is at (0, 0, -10) in world space
    res = om.project_point((0, 0, -10), view, proj, view_w, view_h)
    if res is None:
        return view_w * 0.5, view_h * 0.5
    sx, sy, _ndc_z, _eye_z = res
    # sx, sy are from bottom-left origin, which matches Cocoa's default view.
    return sx, sy


def _merge_app_lists(config_paths: list, orbital_paths: list) -> list:
    """
    Merge configured app paths with orbital folder apps.
    Orbital folder apps are appended (avoiding duplicates).
    Returns combined list with no duplicates.
    """
    # Use set to track what we've seen, preserve config order + orbital order
    seen = set()
    merged = []
    for path in config_paths + orbital_paths:
        if path not in seen:
            seen.add(path)
            merged.append(path)
    return merged


# ══════════════════════════════════════════════════════════════════════════════
#  OrbitView — draws icons in elliptical orbits around the screen centre
# ══════════════════════════════════════════════════════════════════════════════

class OrbitView(NSView):

    # Class-level placeholders (PyObjC views can't have __init__)
    icons       = objc.ivar()
    t0          = objc.ivar()
    last_pos    = objc.ivar()    # list of (cx, cy, r, app_dict) for hit testing
    rx          = objc.ivar()
    ry          = objc.ivar()
    icon_px     = objc.ivar()
    orbit_spd   = objc.ivar()
    earth_state = objc.ivar()    # dict: earth position, camera position, parallax state
    smooth_ps   = objc.ivar()    # smoothed perspective scale — prevents size flicker

    def initWithFrame_config_apps_(self, frame, cfg, apps):
        self = objc.super(OrbitView, self).initWithFrame_(frame)
        if self is None:
            return None

        self.rx        = cfg["orbit_radius_x"]
        self.ry        = cfg["orbit_radius_y"]
        self.icon_px   = cfg["icon_size"]
        self.orbit_spd = cfg["orbit_speed"]
        self.t0        = time.time()
        self.last_pos  = []
        self.earth_state = _zero_earth_state()
        self.smooth_ps   = 1.0

        # Build the icon descriptors with orbital parameters
        self.icons = []
        N = max(1, len(apps))
        for i, app in enumerate(apps):
            self.icons.append({
                "app":   app,
                "phase": 2.0 * math.pi * i / N,
                # Each icon also bobs slightly in radius for a "floating" feel
                "bob_amp":   18.0,
                "bob_phase": (i * 1.37) % (2.0 * math.pi),
                "bob_speed": 0.6 + 0.05 * (i % 5),
            })
        return self

    # NSView contract — say we're not opaque so the window background shows through
    def isOpaque(self):
        return False

    def isFlipped(self):
        # Cocoa default: origin at lower-left. Keep that — orbital math works
        # naturally in math-style coordinates.
        return False

    def drawRect_(self, dirty_rect):
        bounds = self.bounds()
        W      = bounds.size.width
        H      = bounds.size.height
        size   = self.icon_px

        # Load current Earth state exported by app_engine.py at 60 Hz
        self.earth_state = _load_earth_state()
        t = self.earth_state["t_s"]

        cam_x     = self.earth_state["cam_x"]
        cam_y     = self.earth_state["cam_y"]
        cam_z     = self.earth_state["cam_z"]
        cam_yaw   = self.earth_state["cam_yaw"]
        cam_pitch = self.earth_state["cam_pitch"]

        # Compute the Earth's screen position analytically using the exact same
        # camera math as app_engine.py.
        earth_screen_x, earth_screen_y = _compute_earth_screen(
            cam_x, cam_y, cam_z, cam_yaw, cam_pitch, W, H
        )

        z_depth = max(0.1, cam_z + 10.0)
        perspective_scale = 21.5 / z_depth

        if self.smooth_ps is None:
            self.smooth_ps = perspective_scale
        self.smooth_ps += 0.04 * (perspective_scale - self.smooth_ps)
        ps = self.smooth_ps

        # Hi-quality interpolation when NSImage scales
        ctx = NSGraphicsContext.currentContext()
        if ctx is not None:
            ctx.setImageInterpolation_(NSImageInterpolationHigh)

        # ── 3-D orbital ring tilt ─────────────────────────────────────────────
        # In the GL engine (renderer.py), the orbital plane is tilted by a
        # fixed ORBIT_TILT_DEG (63°) about the X axis.
        tilt  = math.radians(om.ORBIT_TILT_DEG)
        cos_t = math.cos(tilt)
        sin_t = math.sin(tilt)

        # Earth's visual radius in screen pixels — used for occlusion test
        earth_r_px = 2.6 * (H * 0.5) / (z_depth * math.tan(math.radians(29.0)))

        # ── Pass 1: compute position + depth for every icon ────────────────────
        items = []
        for ico in self.icons:
            angle = ico["phase"] + t * self.orbit_spd
            bob   = ico["bob_amp"] * math.sin(t * ico["bob_speed"] + ico["bob_phase"])

            R  = (self.rx + bob) * ps          # physical orbit radius (scaled)
            oc = math.cos(angle)
            os = math.sin(angle)

            x = earth_screen_x + R * oc
            y = earth_screen_y + R * os * cos_t

            # depth_z: +1 = far side (behind Earth), -1 = near side (in front)
            depth_z = os * sin_t

            # Size + base alpha from depth
            depth_norm      = (depth_z + 1.0) * 0.5   # 0 = near, 1 = far
            orbit_size_scale = 1.15 - 0.40 * depth_norm
            draw_size        = size * orbit_size_scale * ps

            # Occlusion: fade out far-side icons that overlap the Earth disk
            if depth_z > 0.0:
                dx   = x - earth_screen_x
                dy   = y - earth_screen_y
                dist = math.sqrt(dx * dx + dy * dy)
                # Smooth fade: fully gone at 0.5× earth radius, fully shown at 1.4×
                behind_fade = max(0.0, min(1.0,
                                  (dist - earth_r_px * 0.50) / (earth_r_px * 0.90)))
            else:
                behind_fade = 1.0

            alpha = (1.0 - 0.12 * depth_norm) * behind_fade
            items.append((depth_z, x, y, draw_size, alpha, ico["app"]))

        # ── Pass 2: draw far-to-near so near icons sit on top ─────────────────
        items.sort(key=lambda d: -d[0])

        new_positions = []
        for depth_z, x, y, draw_size, alpha, app in items:
            rect = NSMakeRect(x - draw_size * 0.5,
                              y - draw_size * 0.5,
                              draw_size, draw_size)
            app["image"].drawInRect_fromRect_operation_fraction_(
                rect, NSMakeRect(0, 0, 0, 0),
                NSCompositingOperationSourceOver,
                alpha,
            )
            new_positions.append((x, y, draw_size * 0.5, app))

        self.last_pos = new_positions

    # Called by NSTimer — just marks for redraw
    def tick_(self, timer):
        self.setNeedsDisplay_(True)

    # Hit-test for the global click monitor — point is in view coords.
    # @objc.python_method keeps this off the Cocoa selector table so PyObjC
    # doesn't reinterpret the Python argument list as an Objective-C signature.
    @objc.python_method
    def hit(self, view_point) -> "dict | None":
        for x, y, radius, app in self.last_pos:
            dx = view_point.x - x
            dy = view_point.y - y
            if dx*dx + dy*dy <= radius * radius:
                return app
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Toggle watcher — hide/show the window based on the flag file
# ══════════════════════════════════════════════════════════════════════════════

class ToggleWatcher(NSObject):

    window     = objc.ivar()
    last_state = objc.ivar()    # bool — last visible state

    def initWithWindow_(self, window):
        self = objc.super(ToggleWatcher, self).init()
        if self is None:
            return None
        self.window     = window
        self.last_state = True
        return self

    def tick_(self, timer):
        should_show = not FLAG_OFF.exists()
        if should_show == self.last_state:
            return
        if should_show:
            self.window.orderFrontRegardless()
            print("[icons] Overlay shown")
        else:
            self.window.orderOut_(None)
            print("[icons] Overlay hidden")
        self.last_state = should_show


# ══════════════════════════════════════════════════════════════════════════════
#  Orbital Apps folder watcher — monitor /Applications/Orbital Apps/ for changes
# ══════════════════════════════════════════════════════════════════════════════

class OrbitalAppsWatcher(NSObject):

    view             = objc.ivar()
    last_app_paths   = objc.ivar()    # cached list of .app paths

    def initWithView_(self, view):
        self = objc.super(OrbitalAppsWatcher, self).init()
        if self is None:
            return None
        self.view           = view
        self.last_app_paths = []
        return self

    def tick_(self, timer):
        """Poll /Applications/Orbital Apps/ every second for new/removed apps."""
        orbital_paths = _scan_orbital_apps_folder()

        # Only reload if the set of paths actually changed
        if set(orbital_paths) == set(self.last_app_paths):
            return

        self.last_app_paths = orbital_paths
        apps = _load_apps(orbital_paths)
        print(f"[icons] Orbital Apps folder changed — now tracking {len(apps)} apps")

        N = max(1, len(apps))
        view_icons = []
        for i, app in enumerate(apps):
            view_icons.append({
                "app":       app,
                "phase":     2.0 * math.pi * i / N,
                "bob_amp":   18.0,
                "bob_phase": (i * 1.37) % (2.0 * math.pi),
                "bob_speed": 0.6 + 0.05 * (i % 5),
            })
        self.view.icons = view_icons
        self.view.setNeedsDisplay_(True)


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        pass


def main() -> int:
    # ── Load all config & apps BEFORE touching Cocoa ─────────────────────────
    # NSApplication.sharedApplication() can invoke callbacks that disrupt Python
    # local-variable bindings across ObjC bridging — extract all values up front.
    _raw_cfg = _load_config()
    orbit_radius_x = _raw_cfg["orbit_radius_x"]
    orbit_radius_y = _raw_cfg["orbit_radius_y"]
    icon_size      = _raw_cfg["icon_size"]
    orbit_speed    = _raw_cfg["orbit_speed"]

    # Source apps exclusively from /Applications/Orbital Apps/
    orbital_paths = _scan_orbital_apps_folder()
    apps = _load_apps(orbital_paths)
    if not apps:
        print("[icons] No apps found in /Applications/Orbital Apps/")
        print(f"[icons] Add .app bundles to {ORBITAL_APPS_DIR} to populate the orbit.")
        print("[icons] Overlay will stay running and watch for apps added to that folder.")
    else:
        print(f"[icons] Loaded {len(apps)} apps from {ORBITAL_APPS_DIR}")

    # Re-pack into a plain dict — avoids bridging overhead at call site
    cfg = {
        "orbit_radius_x": orbit_radius_x,
        "orbit_radius_y": orbit_radius_y,
        "icon_size":      icon_size,
        "orbit_speed":    orbit_speed,
    }

    NSApplication.sharedApplication()
    NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # no Dock icon

    delegate = AppDelegate.alloc().init()
    NSApp.setDelegate_(delegate)

    # ── Build the overlay window ──────────────────────────────────────────────
    screen = NSScreen.mainScreen()
    sframe = screen.frame()

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        sframe,
        NSWindowStyleMaskBorderless,
        NSBackingStoreBuffered,
        False,
    )
    window.setOpaque_(False)
    window.setBackgroundColor_(NSColor.clearColor())
    window.setHasShadow_(False)

    # Sit just above the wallpaper but below Finder desktop icons + app windows.
    # This keeps icons visible without interfering with normal workflows.
    desktop = CGWindowLevelForKey(kCGDesktopWindowLevelKey)
    window.setLevel_(desktop + 1)

    # Float on every Space and stay put when Mission Control moves
    window.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces |
        NSWindowCollectionBehaviorStationary
    )

    # CRITICAL: click-through. Mouse events go to whatever's below us — Finder,
    # desktop, app windows. We catch clicks via a global monitor instead.
    window.setIgnoresMouseEvents_(True)

    # ── Build the orbit view ──────────────────────────────────────────────────
    view = OrbitView.alloc().initWithFrame_config_apps_(sframe, cfg, apps)
    window.setContentView_(view)
    window.orderFrontRegardless()

    # ── 60 Hz animation timer ────────────────────────────────────────────────
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0 / 60.0, view, "tick:", None, True
    )

    # ── 1 Hz toggle-flag watcher ─────────────────────────────────────────────
    watcher = ToggleWatcher.alloc().initWithWindow_(window)
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0, watcher, "tick:", None, True
    )

    # ── 1 Hz orbital apps folder watcher ──────────────────────────────────────
    apps_watcher = OrbitalAppsWatcher.alloc().initWithView_(view)
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0, apps_watcher, "tick:", None, True
    )

    # ── Global click monitor ─────────────────────────────────────────────────
    #
    # The overlay is click-through, so it never sees mouse-down events directly.
    # A global monitor observes left clicks across all apps; we hit-test them
    # against the current icon positions and launch the matching app.  We can't
    # consume events from a global monitor — the original click also reaches
    # whatever was beneath the cursor, but that's fine: clicks on the desktop
    # only deselect Finder icons, which is harmless.

    def handle_click(event):
        if FLAG_OFF.exists():
            return  # icons hidden — ignore
        screen_pt = NSEvent.mouseLocation()
        # Convert screen → window-local (window origin is sframe.origin)
        view_pt = NSMakePoint(
            screen_pt.x - sframe.origin.x,
            screen_pt.y - sframe.origin.y,
        )
        app = view.hit(view_pt)
        if app is None:
            return
        print(f"[icons] Launching {app['name']}")
        try:
            NSWorkspace.sharedWorkspace().openURL_(app["url"])
        except Exception as e:
            print(f"[icons] Launch failed: {e}")

    NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
        NSEventMaskLeftMouseDown, handle_click
    )

    print(f"[icons] Overlay running on {int(sframe.size.width)}×{int(sframe.size.height)}")
    print(f"[icons] Config file       : {CONFIG_PATH}")
    print(f"[icons] Toggle flag       : {FLAG_OFF}  (touch to hide, rm to show)")
    print("[icons] Press Ctrl-C to quit.")

    NSApp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
