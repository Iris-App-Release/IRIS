#!/usr/bin/env python3
"""
overlay_ui.py — Iris demo HUD (liquid-glass, state-driven).

A light, Apple-HIG glass overlay composited ON TOP of the live Earth engine
while it renders in `demo` window mode (see main.py). The illusion is the
product: the Earth is always live behind this UI; the overlay only floats
translucent controls over it and never stops the render or reloads.

The app always opens into ONE main interface (no landing page). The demo has
three state-driven, instantly-switched modes — never reloaded:

    FLOATING PREVIEW  (default)   idle scripted motion, no head tracking
        │  ▲
   Enable Camera   Enable Desktop Mode
        ▼  │
    LIVE TRACKED                  real head tracking, instant
        │
   Enable Desktop Mode  → demo reverts to FLOATING, the wallpaper daemon runs
                          independently in the background; this window stays
                          open as a passive preview.

Two layers, cleanly separated so the logic is testable without a GL context:
  • PURE LOGIC  — state model, scripted idle motion, hit-testing, 2-D surface
                  composition (pygame only). Headless-safe; exercised by
                  sim_overlay.py.
  • GL BRIDGE   — draw_gl(): uploads the composed Surface (rendered at physical
                  Retina resolution for crisp text) to a texture and draws one
                  blended quad in the engine's GL 2.1 context.

This module touches NO physics. The engine reads `tracking_requested`,
`desktop_mode_requested`, `should_quit`, and `live` each frame, and feeds
`scripted_head(t)` into the SAME camera variables the tracker would, so floating
parallax uses the unchanged camera math.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pygame

try:
    # Shared button primitive — the single grayscale-minimal control look.
    from UI.buttons import Button
except ImportError:  # source-run fallback when UI isn't the import root
    from buttons import Button

# OpenGL is imported lazily inside draw_gl() so this module can be imported (and
# its logic tested) in a headless process with no GL context.

# ── Paths (Iris config under ~/.iris; engine flags stay "parallax") ───────────
CONFIG_DIR        = Path.home() / ".iris"
PREFS_FILE        = CONFIG_DIR / "preferences.json"
DAEMON_PID_FILE   = CONFIG_DIR / "daemon.pid"          # written when we spawn it
TRACKING_OFF_FLAG = Path.home() / ".parallax_off"      # master switch the daemon polls
CAMERA_OFF_FLAG   = CONFIG_DIR / "camera_off"          # Settings camera-access switch

# Worlds that ship with the app + the World Builder scratch canvas. These are
# never offered in the Settings "Delete Portal" list and can never be removed — the
# delete flow only ever touches USER-created worlds inside Worlds/ (see _delete_portal).
BUILTIN_PORTALS = {"earth", "gem", "the_watcher", "grid_room"}

# Load localized strings from Config/Strings.json
_STRINGS_PATH = Path(__file__).parent.parent / "Config" / "Strings.json"
try:
    with open(_STRINGS_PATH) as f:
        STRINGS = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    # Fallback to hardcoded strings if JSON not available
    STRINGS = {
        "demo_ui": {
            "status": {
                "floating_preview": "Floating preview",
                "starting": "Starting camera…",
                "live_tracking": "Live · head tracking on",
                "camera_denied": "Camera access needed — enable it in System Settings",
                "desktop_active": "Desktop mode active",
                "desktop_paused": "Desktop mode paused"
            },
            "buttons": {
                "enable_camera": "Enable Camera",
                "enable_desktop": "Enable Desktop Mode",
                "resume_desktop": "Enable Desktop Mode"
            },
            "toasts": {
                "desktop_paused": "Desktop mode paused",
                "desktop_resumed": "Desktop mode resumed"
            }
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Palette — buttons now render via UI/buttons.py (grayscale-minimal variants).
#  What remains here is STRUCTURAL only: the dark-grey containers, the labels
#  drawn on them, the full-bleed page fill, and the nav-arrow glyph colour. These
#  are legibility backings over the live scene, not buttons, so they survive the
#  swap to the shared Button primitive.
# ══════════════════════════════════════════════════════════════════════════════

BTN_FILL_REST  = (255, 255, 255, 255)   # full-bleed white page fill + toast pill

# Grey rounded container that sits BEHIND controls for depth / legibility over
# the live scene. One grey, used everywhere — the tab bar, the bottom action
# group, the toast — so the language stays consistent. Fully OPAQUE so the white
# pills' drop shadows pop against a consistent backdrop instead of being lost in
# the live world showing through. A lighter mid-grey (the dark shade was dropped).
GREY_CONTAINER   = (80, 82, 90, 255)
GREY_TEXT        = (200, 200, 205)      # light label text drawn on the grey
GREY_TEXT_DIM    = (150, 150, 156)
ARROW_GLYPH      = (240, 240, 245)      # nav-arrow triangle, drawn over the pill

# Premium golden-yellow accent — used ONLY by the World Builder canvas side
# panels (everything else stays grayscale). The fill is the exact swatch the
# user supplied (Nippon "golden yellow", #ECA31E).
PREMIUM_GOLD        = (236, 163, 30)    # supplied golden yellow (#ECA31E) — panel fill
PREMIUM_GOLD_BORDER = (170, 117, 22)    # a few shades darker — panel border
PREMIUM_NAVY        = (23, 32, 58)      # deep navy — bold panel titles

# ── Premium warm-light theme (the World Builder visual upgrade) ───────────────
# Soft neumorphism: white cards floating on a warm off-white page, elevated by
# warm shadows + a faint gold outer glow, accented by a single highlight orange.
# These REPLACE the flat saturated-gold panels with elevated white surfaces.
PAGE_BG          = (245, 242, 238)   # warm off-white page background
PANEL_SURFACE    = (252, 250, 247)   # white card surface (panels, nav, capsules)
PANEL_SURFACE_2  = (248, 246, 242)   # secondary surface (inset input / cube faces)
GOLD_RIM         = (236, 200, 130)   # thin warm gold rim around the white cards
GOLD_RIM_SOFT    = (244, 224, 178)   # lighter rim, lower-contrast edges
ACCENT_ORANGE    = (236, 168, 28)    # highlight orange — active tab, CTA, icons
ACCENT_ORANGE_HI = (247, 192, 70)    # lighter orange — top of CTA gradient / glints
GLOW_YELLOW      = (255, 215, 80)    # warm glow colour (applied at low alpha)
INK              = (74, 66, 54)      # warm near-black — titles
INK_SOFT         = (138, 128, 114)   # muted warm gray — body / placeholder
GRID_LINE        = (216, 210, 201)   # very subtle cube grid lines (elegant, not technical)
CUBE_EDGE        = (196, 188, 176)   # soft warm cube outline (no hard black)
CUBE_EDGE_KEY    = (168, 158, 144)   # slightly stronger key edges (back-wall frame)

T_TITLE        = (255, 255, 255)
T_BODY         = (255, 255, 255)
T_DIM          = (255, 255, 255)
BTN_TEXT       = (0, 0, 0)

# Supersample factor for anti-aliased rounded corners (see _aa_round_rect).
_AA_SS = 4

# Corner radii (logical px) — iPhone-style, not full-pill.
_BTN_CORNER   = 10   # buttons, status pills, tab items
_PANEL_CORNER = 14   # floating panels and cards
_TABBAR_CORNER = 12  # tab bar container


# ══════════════════════════════════════════════════════════════════════════════
#  2-D drawing helpers (pure pygame). `s` = device scale → crisp Retina widths.
# ══════════════════════════════════════════════════════════════════════════════

def _load_font(size: int, bold: bool = False) -> pygame.font.Font:
    # SysFont silently returns the default bitmap font when a name isn't found
    # (no exception is raised), so we must use match_font to check existence first.
    for name in ("SF Pro Display", "SF Pro Text", "Helvetica Neue", "Helvetica", "Arial"):
        path = pygame.font.match_font(name, bold=bold)
        if path:
            try:
                return pygame.font.Font(path, size)
            except Exception:
                continue
    return pygame.font.Font(None, size + 6)


def _vgrad(size, top_rgba, bot_rgba) -> pygame.Surface:
    w, h = size
    g = pygame.Surface(size, pygame.SRCALPHA)
    denom = max(1, h - 1)
    for y in range(h):
        t = y / denom
        col = tuple(int(top_rgba[i] + (bot_rgba[i] - top_rgba[i]) * t) for i in range(4))
        pygame.draw.line(g, col, (0, y), (w, y))
    return g


def _aa_round_rect(surf, rect, color, radius) -> None:
    """Anti-aliased filled rounded rectangle.

    pygame.draw.rect(border_radius=…) does NOT anti-alias its corners — they
    stair-step into the "fine pixel art" jaggies. We render the shape at _AA_SS×
    and smoothscale it down, so the corners come out smooth and crisp at any
    device scale. Only called on dirty frames (the surface is cached), so the
    extra cost is negligible."""
    w, h = int(rect.w), int(rect.h)
    if w <= 0 or h <= 0:
        return
    ss = _AA_SS
    big = pygame.Surface((w * ss, h * ss), pygame.SRCALPHA)
    pygame.draw.rect(big, color, big.get_rect(), border_radius=int(radius * ss))
    surf.blit(pygame.transform.smoothscale(big, (w, h)), rect.topleft)


def _text_shadow(surf, text, font, color, center, s=1.0) -> pygame.Rect:
    t = font.render(text, True, color)
    r = t.get_rect(center=center)
    surf.blit(t, r)
    return r


def _grey_container(surf, rect, s=1.0, radius=None) -> None:
    """Dark-grey rounded container drawn behind a white pill for depth."""
    r = int((_PANEL_CORNER if radius is None else radius) * s)
    _aa_round_rect(surf, rect, GREY_CONTAINER, r)


def _filled_rounded_poly(surf, pts, color, r) -> None:
    """Filled polygon with rounded corners (Minkowski sum with a disc of radius
    r), supersampled + smoothscaled for clean anti-aliased edges. Used for the
    nav-arrow triangles so their corners are softened rather than razor-sharp."""
    ss = _AA_SS
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    pad = r + 2
    minx, miny = min(xs) - pad, min(ys) - pad
    w = int(max(xs) - min(xs) + pad * 2)
    h = int(max(ys) - min(ys) + pad * 2)
    if w <= 0 or h <= 0:
        return
    big = pygame.Surface((w * ss, h * ss), pygame.SRCALPHA)
    sp = [((p[0] - minx) * ss, (p[1] - miny) * ss) for p in pts]
    rr = max(1, int(r * ss))
    pygame.draw.polygon(big, color, sp)
    for a, b in zip(sp, sp[1:] + sp[:1]):
        pygame.draw.line(big, color, a, b, rr * 2)
    for p in sp:
        pygame.draw.circle(big, color, (int(p[0]), int(p[1])), rr)
    surf.blit(pygame.transform.smoothscale(big, (w, h)), (minx, miny))


# ══════════════════════════════════════════════════════════════════════════════
#  Soft-shadow / glow primitives (pure pygame, sprite-cached).
#
#  Premium neumorphism wants blurred drop shadows and a faint gold rim-glow under
#  every white card. Classic pygame has no gaussian_blur, so we fake a soft blur
#  by smooth-downscaling a rounded-rect sprite and scaling it back up (cheap, and
#  banding-free after two passes). Each sprite is keyed by its geometry and built
#  ONCE — the composed HUD surface is itself signature-cached, so on a dirty
#  re-render (hover, typing) these are pure blits, never rebuilt. No filter:blur,
#  no per-frame work: the cost is one-time, the runtime cost is a textured quad.
# ══════════════════════════════════════════════════════════════════════════════

_SPRITE_CACHE: dict = {}


def _blur_down_up(surf: pygame.Surface, factor: int) -> pygame.Surface:
    """Soft blur by smooth down-then-up scaling (two passes kill banding)."""
    w, h = surf.get_size()
    f = max(2, int(factor))
    sm = pygame.transform.smoothscale(surf, (max(1, w // f), max(1, h // f)))
    out = pygame.transform.smoothscale(sm, (w, h))
    sm2 = pygame.transform.smoothscale(out, (max(1, w // 2), max(1, h // 2)))
    return pygame.transform.smoothscale(sm2, (w, h))


def _blur_sprite(key, w, h, radius, color, alpha, blur):
    """Cached blurred, filled rounded-rect sprite. Returns (surface, pad)."""
    hit = _SPRITE_CACHE.get(key)
    if hit is not None:
        return hit
    if len(_SPRITE_CACHE) > 96:                 # bound growth across resizes
        _SPRITE_CACHE.clear()
    w, h = max(1, int(w)), max(1, int(h))
    pad = int(blur) + 2
    W, H = w + pad * 2, h + pad * 2
    base = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(base, (*color, int(alpha)), pygame.Rect(pad, pad, w, h),
                     border_radius=max(0, int(radius)))
    sprite = (_blur_down_up(base, blur), pad)
    _SPRITE_CACHE[key] = sprite
    return sprite


def _soft_shadow(surf, rect, radius, *, blur, dy, alpha, color=(0, 0, 0)) -> None:
    """Blurred drop shadow beneath ``rect`` (warm depth, prefers blit over blur)."""
    sprite, pad = _blur_sprite(("sh", int(rect.w), int(rect.h), int(radius),
                                int(blur), int(alpha), color),
                               rect.w, rect.h, radius, color, alpha, blur)
    surf.blit(sprite, (int(rect.x) - pad, int(rect.y) - pad + int(dy)))


def _outer_glow(surf, rect, radius, *, color, blur, spread, alpha) -> None:
    """Soft coloured glow radiating outward from ``rect`` (the gold rim-glow)."""
    gw, gh = int(rect.w) + spread * 2, int(rect.h) + spread * 2
    sprite, pad = _blur_sprite(("gl", gw, gh, int(radius + spread),
                                int(blur), int(alpha), color),
                               gw, gh, radius + spread, color, alpha, blur)
    surf.blit(sprite, (int(rect.x) - spread - pad, int(rect.y) - spread - pad))


def _front_lit_shadow(surf, rect, radius, passes) -> None:
    """Fully surrounding 'front-lit' shadow: concentric semi-transparent rings
    inflate outward in all directions with no directional offset, approximating
    a Gaussian halo on all four sides of the element.

    ``passes`` — sequence of (spread_px, alpha) pairs, outermost first.
    Each pass inflates the rect symmetrically and draws with the given alpha;
    the inner passes stack on top so visible alpha increases toward the card edge.
    """
    for sp, al in passes:
        sr = rect.inflate(int(sp) * 2, int(sp) * 2)
        _aa_round_rect(surf, sr, (0, 0, 0, al), int(radius) + int(sp))


def _radial_glow(surf, cx, cy, rw, rh, color, alpha) -> None:
    """Static warm radial light (the ground glow beneath the cube). Cached."""
    key = ("rad", int(rw), int(rh), color, int(alpha))
    sprite = _SPRITE_CACHE.get(key)
    if sprite is None:
        if len(_SPRITE_CACHE) > 96:
            _SPRITE_CACHE.clear()
        W, H = max(2, int(rw * 2)), max(2, int(rh * 2))
        base = pygame.Surface((W, H), pygame.SRCALPHA)
        steps = 26
        for i in range(steps, 0, -1):           # large→small: inner overwrites
            t = i / steps
            a = int(alpha * (1.0 - t) ** 2)      # soft quadratic falloff to edge
            ew, eh = int(W * t), int(H * t)
            pygame.draw.ellipse(base, (*color, a),
                                pygame.Rect((W - ew) // 2, (H - eh) // 2, ew, eh))
        sprite = _blur_down_up(base, 7)
        _SPRITE_CACHE[key] = sprite
    surf.blit(sprite, (int(cx - rw), int(cy - rh)))


def _premium_card(surf, rect, s, *, radius=None, fill=PANEL_SURFACE, rim=GOLD_RIM,
                  glow=GLOW_YELLOW, glow_alpha=46, shadow_alpha=28,
                  shadow_blur=22, shadow_dy=12, rim_w=1.5, phase="all",
                  shadow_rect=None) -> None:
    """The shared elevated-white-card style: faint gold outer glow + warm soft
    drop shadow + white fill + a thin gold rim. One function so every surface
    (side panels, nav bar, Preview capsule, input, upsell) elevates identically
    instead of hand-rolling depth per call.

    ``phase`` splits the draw so a foreground object can be sandwiched between a
    card's shadow and its fill: ``"back"`` paints only the glow + drop shadow,
    ``"front"`` only the rim + fill, ``"all"`` (default) both. ``shadow_rect``
    lets the shadow be cast for a TALLER/wider region than the card itself (e.g.
    the right panel's shadow stretched up behind the Preview button)."""
    r = int((_PANEL_CORNER if radius is None else radius) * s)
    if phase in ("all", "back"):
        srect = rect if shadow_rect is None else shadow_rect
        if glow is not None and glow_alpha > 0:
            _outer_glow(surf, srect, r, color=glow, blur=int(26 * s),
                        spread=int(11 * s), alpha=glow_alpha)
        _soft_shadow(surf, srect, r, blur=int(shadow_blur * s),
                     dy=int(shadow_dy * s), alpha=shadow_alpha)
    if phase in ("all", "front"):
        if rim is not None:
            rw = max(1, int(rim_w * s))
            _aa_round_rect(surf, rect, rim, r)                      # rim underlay
            _aa_round_rect(surf, rect.inflate(-2 * rw, -2 * rw), fill, max(1, r - rw))
        else:
            _aa_round_rect(surf, rect, fill, r)


def _aa_circle(surf, center, radius, color, width=0) -> None:
    """Anti-aliased filled (or outlined) circle — supersample + smoothscale, the
    same crisp-corners trick as _aa_round_rect (pygame.draw.circle is jaggy)."""
    radius = max(1, int(radius))
    d = radius * 2
    ss = _AA_SS
    big = pygame.Surface((d * ss, d * ss), pygame.SRCALPHA)
    pygame.draw.circle(big, color, (radius * ss, radius * ss), radius * ss,
                       width=int(width * ss))
    surf.blit(pygame.transform.smoothscale(big, (d, d)),
              (int(center[0]) - radius, int(center[1]) - radius))


# ══════════════════════════════════════════════════════════════════════════════
#  DemoOverlay
# ══════════════════════════════════════════════════════════════════════════════

class DemoOverlay:
    """State-driven main-interface HUD over the live demo."""

    def __init__(self, win_w: int, win_h: int, scale: float = 2.0,
                 daemon_running: bool | None = None,
                 desktop_paused: bool | None = None) -> None:
        pygame.font.init()
        # Render in PHYSICAL pixels so text is crisp on Retina (no GL upscale blur).
        self.s = max(1.0, float(scale))
        self.win_w, self.win_h = int(win_w), int(win_h)
        self.w = int(round(win_w * self.s))
        self.h = int(round(win_h * self.s))

        # Demo mode (instant, state-driven)
        self.live = False                 # False = floating preview, True = live tracked

        # Desktop-mode awareness. Auto-detect a running daemon unless told.
        det_run, det_paused = self._detect_daemon()
        self.daemon_running = det_run if daemon_running is None else bool(daemon_running)
        self.desktop_paused = det_paused if desktop_paused is None else bool(desktop_paused)

        # Session state
        self.onboarded = bool(self._pref("onboarded", False))

        # World selection and active tab (Worlds / World Builder / Community /
        # Settings).
        self._active_tab = "worlds"
        # World Builder has two sub-views of ONE world (grid_room): the 2-D grid
        # editor and the live "Preview" (the real off-axis render). Switching
        # between them never edits the world, so all state persists for free.
        self._wb_view = "grid"            # "grid" | "preview"
        self._wb_prev_portal = None        # world to restore when leaving the tab
        # World Builder authoring state. The right card holds the focusable prompt
        # input ("Describe your portal…") plus the Send + Save buttons; the left
        # card is a static explainer. All kept here so render stays allocation-free
        # (the surface is signature-cached) and the engine never sees this state.
        self._wb_prompt = ""              # current prompt text (<=150 chars)
        self._wb_focused = False          # prompt input has keyboard focus
        self._wb_prompt_rect = None
        # Transient preview: Send runs Claude and stores the sanitized objects here
        # (NOT saved). They're drawn on the Canvas Cube and mirrored to the grid_room
        # scratch portal.json so the live Preview shows them too. `_wb_preview_gen`
        # bumps on every Send/Save/clear so the signature-cached surface invalidates.
        self._wb_preview_objects: list[dict] = []
        self._wb_preview_gen = 0
        # Settings → Delete World flow: a toggleable list of user worlds, then a
        # Yes/No confirmation modal for the chosen one. `_delete_target` is the slug
        # awaiting confirmation (None = no modal); `_delete_card` is its modal rect.
        self._delete_list_open = False
        self._delete_target: str | None = None
        self._delete_card = None
        # grid_room is the World Builder's working world — keep it loadable but
        # OUT of the Portals-tab cycle (it's a blank canvas preview, not a world).
        self._all_portal_keys, self._portal_names = self._load_portals()
        self._portal_keys = [k for k in self._all_portal_keys
                            if k != "grid_room"] or ["earth"]
        self.active_portal = str(self._pref("portal", "earth"))
        if self.active_portal == "grid_room":
            self.active_portal = "earth"   # never persist the canvas world here

        # Camera-access control. Flag file is the live cross-process source of
        # truth the engine polls; persists across restarts.
        self.camera_enabled = not CAMERA_OFF_FLAG.exists()

        # Public signals the engine reads each frame
        self.tracking_requested     = False
        self.desktop_mode_requested = False
        self.should_quit            = False
        self.tracking_active        = False   # engine: real head data is flowing
        self.camera_denied          = False   # engine: camera access denied/unavailable

        # Fonts (sized in physical px)
        S = self.s
        self.fnt_btn    = _load_font(int(16 * S), bold=True)
        self.fnt_small  = _load_font(int(13 * S), bold=True)
        self.fnt_status = _load_font(int(13 * S), bold=True)
        self.fnt_hint   = _load_font(int(15 * S))
        # Dedicated tab font — unified size for ALL tab pills (active + inactive,
        # orange + grey) so text never grows/shrinks on tab switch.
        self.fnt_tab    = _load_font(int(14 * S), bold=True)

        # Animation / interaction
        self._ctrl_alpha = 1.0
        self._last_input = self._now()
        self.hover: str | None = None
        self._press_key: str | None = None    # control held down → active state
        self._hover_anim: dict[str, float] = {}
        self._toast: tuple[str, float] | None = None

        # Layout + GL texture + render cache
        self._buttons: dict[str, pygame.Rect] = {}
        self._tex = None
        self._sig = None
        self._cached: pygame.Surface | None = None
        self._dirty = True
        self._compute_layout()

    # ── time ──
    @staticmethod
    def _now() -> float:
        import time
        return time.monotonic()

    # ── Preferences ────────────────────────────────────────────────────────────

    def _pref(self, key, default):
        try:
            return json.loads(PREFS_FILE.read_text()).get(key, default)
        except Exception:
            return default

    def _save_pref(self, key, value) -> None:
        try:
            CONFIG_DIR.mkdir(exist_ok=True)
            data = {}
            if PREFS_FILE.exists():
                try:
                    data = json.loads(PREFS_FILE.read_text())
                except Exception:
                    data = {}
            data[key] = value
            PREFS_FILE.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    # ── World discovery (for the Browse Worlds picker) ──────────────────────────

    def _load_portals(self):
        """Return (keys, names): available world dir names + their display names,
        via the same WorldLoader the engine uses. Falls back to Earth-only."""
        try:
            from Portals.portal_loader import PortalLoader
            base = Path(__file__).resolve().parent.parent
            wdir = base / "Portals"
            if not wdir.exists():
                wdir = base / "portals"
            loader = WorldLoader(wdir)
            keys = loader.list_available_worlds() or ["earth"]
            names = {}
            for k in keys:
                try:
                    names[k] = loader.load_world(k).get("name", k)
                except Exception:
                    names[k] = k
            return keys, names
        except Exception:
            return ["earth"], {"earth": "Earth"}

    # ── Daemon detection (robust for the frozen app via a PID file) ─────────────

    @staticmethod
    def _detect_daemon() -> tuple[bool, bool]:
        running = False
        try:
            pid = int(DAEMON_PID_FILE.read_text().strip())
            os.kill(pid, 0)            # raises if not alive
            running = True
        except Exception:
            # Source-run fallback: a separate daemon `launcher.py` process. This
            # is THIS app's entry point (the old build used `main.py`; matching
            # that name false-positives on stale daemons from prior versions and
            # never finds the current daemon). The demo itself is launcher.py too,
            # but it's the current process, so excluding our own PID isolates the
            # daemon. Frozen builds skip this branch entirely (PID file above).
            try:
                r = subprocess.run(["pgrep", "-f", "launcher.py"],
                                   capture_output=True, text=True)
                running = any(int(p) != os.getpid()
                              for p in r.stdout.split() if p.strip().isdigit())
            except Exception:
                running = False
        paused = running and TRACKING_OFF_FLAG.exists()
        return running, paused

    # ── State helpers ────────────────────────────────────────────────────────────

    def _camera_ready(self) -> bool:
        """True once camera access is actually granted and working (real head
        data is flowing) or a wallpaper daemon is already running. This is the
        trigger that swaps the bottom action button: Enable Camera → Desktop
        Mode."""
        return bool(self.tracking_active or self.daemon_running)

    def _primary(self) -> tuple[str, str]:
        """The single bottom-centred action. Owns one slot:
          • before the camera is granted  → "Enable Camera for Desktop Mode"
          • while it is settling          → "Starting camera…" (no-op)
          • once granted                  → the Desktop Mode control
        Identical positioning/sizing/styling across the swap. The enable-camera
        label spells out that the camera is the path to Desktop Mode, and it is
        what shows on first open AND whenever camera access is disabled (the
        click re-enables access, see _click)."""
        if not self._camera_ready():
            if self.live and not self.camera_denied:
                return ("Starting camera…", "none")     # in-flight, immediate feedback
            return ("Enable Camera for Desktop Mode", "enable_camera")
        # Camera granted → Desktop Mode controls.
        if self.daemon_running and not self.desktop_paused:
            return ("Disable Desktop Mode", "disable_desktop")
        if self.daemon_running and self.desktop_paused:
            return (STRINGS["demo_ui"]["buttons"]["resume_desktop"], "resume_desktop")
        return (STRINGS["demo_ui"]["buttons"]["enable_desktop"], "enable_desktop")

    @property
    def preview_active(self) -> bool:
        """Engine reads this each frame: render the live 3-D world preview while
        the Worlds tab is showing, AND while World Builder is in its Preview view
        (the real off-axis conversion of the grid world the user is building). On
        Settings/Community and the World Builder grid editor the engine skips the
        (expensive) scene draw — those show a solid card instead."""
        return (self._active_tab == "portals"
                or (self._active_tab == "portal_builder"
                    and self._wb_view == "preview"))

    def _status_text(self) -> str:
        st = STRINGS["demo_ui"]["status"]
        if self.daemon_running and not self.desktop_paused:
            return st["desktop_active"]
        if self.daemon_running and self.desktop_paused:
            return st["desktop_paused"]
        # Honest live-state reporting (was: always "live" the instant the button
        # was clicked, even when the camera never opened — the "Live status on but
        # no tracking" bug). The engine drives these via notify_tracking_active()
        # / notify_camera_denied().
        if self.camera_denied:
            return st.get("camera_denied",
                          "Camera access needed — enable it in System Settings")
        if self.live and not self.tracking_active:
            return st.get("starting", "Starting camera…")
        if self.live:
            return st["live_tracking"]
        return st["floating_preview"]

    def _toast_msg(self, text, secs=2.4) -> None:
        self._toast = (text, self._now() + secs)

    def _set_paused(self, paused: bool) -> None:
        try:
            if paused:
                TRACKING_OFF_FLAG.touch()
            else:
                TRACKING_OFF_FLAG.unlink(missing_ok=True)
        except Exception:
            pass
        self.desktop_paused = paused

    def _set_camera_enabled(self, enabled: bool) -> None:
        """Enable/disable camera access. Writes the flag file the engine polls
        live (and mirrors the choice to preferences for persistence/display). On
        DISABLE we also drop out of live mode so the demo falls back to the
        scripted floating preview instead of a stalled tracker frame."""
        self.camera_enabled = bool(enabled)
        try:
            CONFIG_DIR.mkdir(exist_ok=True)
            if enabled:
                CAMERA_OFF_FLAG.unlink(missing_ok=True)
            else:
                CAMERA_OFF_FLAG.touch()
        except Exception:
            pass
        self._save_pref("camera_enabled", self.camera_enabled)
        if not enabled:
            self.live = False                  # back to floating preview (idle)
            # Camera is off → tracking is no longer active, so _camera_ready()
            # must drop back to False (unless a desktop daemon is running). Without
            # this the bottom action wrongly kept reading "Enable Desktop Mode"
            # after the camera was disabled again.
            self.tracking_active = False
            self.camera_denied   = False
        self._toast_msg("Camera access on" if enabled else "Camera access off", 2.2)

    def on_desktop_enabled(self) -> None:
        """Called by the engine once the wallpaper daemon is spawned: the demo
        reverts to a passive floating preview while the daemon runs independently."""
        self.daemon_running = True
        self.desktop_paused = False
        self.live = False

    def notify_tracking_active(self) -> None:
        """Engine: real head data has started flowing — promote to true 'Live'."""
        self.tracking_active = True
        self.camera_denied   = False

    def notify_camera_denied(self) -> None:
        """Engine: camera access was denied/unavailable, so the capture worker was
        not started. Surface an actionable status and fall back to the scripted
        floating preview so the scene stays alive (instead of a frozen 'Live')."""
        self.camera_denied   = True
        self.tracking_active = False
        self.live            = False

    # ── Scripted "floating preview" motion (no camera) ──────────────────────────

    def scripted_head(self, t: float):
        hx = 0.14 * math.sin(t * 0.55)
        hy = 0.07 * math.sin(t * 0.40 + 1.3)
        hz = 0.06 * math.sin(t * 0.22)
        return (hx, hy, hz, 0.0, 0.0)

    # ── Layout (physical px) ─────────────────────────────────────────────────────

    def _compute_layout(self) -> None:
        S = self.s
        w, h = self.w, self.h
        self._buttons = {}
        # World Builder canvas furniture (set in the world_builder branch below;
        # None when not on that tab). The grid view uses two premium side panels;
        # the preview view keeps the detached "Back to Canvas" mini-bar.
        self._wb_back_bar = None
        self._wb_left_panel = None
        self._wb_right_panel = None
        self._wb_prompt_rect = None
        self._delete_card = None
        pad = int(16 * S)
        btn_gap = int(8 * S)

        # ── Tab bar (always visible across all tabs) ──────────────────────────
        tab_specs = [("portals", "Portals"), ("portal_builder", "Portal Builder"),
                     ("community", "Community"), ("settings", "Settings")]
        tab_w, tab_h = int(124 * S), int(36 * S)
        tab_gap = int(6 * S)
        tb_pad = int(6 * S)
        total_tab_w = len(tab_specs) * tab_w + (len(tab_specs) - 1) * tab_gap
        tabbar_w = total_tab_w + tb_pad * 2
        tabbar_h = tab_h + tb_pad * 2
        self._tabbar = pygame.Rect(w // 2 - tabbar_w // 2, int(20 * S),
                                   tabbar_w, tabbar_h)
        # Bottom bar — identical geometry to the tab bar, same inset from the
        # bottom as the tab bar is from the top. Placeholder for subscribe/pricing.
        bb_y = h - int(20 * S) - tabbar_h
        self._bottombar = pygame.Rect(self._tabbar.x, bb_y, tabbar_w, tabbar_h)
        for i, (key, _) in enumerate(tab_specs):
            tx = self._tabbar.x + tb_pad + i * (tab_w + tab_gap)
            self._buttons[f"tab:{key}"] = pygame.Rect(
                tx, self._tabbar.y + tb_pad, tab_w, tab_h)

        # ── Worlds tab ────────────────────────────────────────────────────────
        if self._active_tab == "portals":
            # World navigation arrows — flanking the scene, pulled in from the
            # edges toward the centre. They switch worlds instantly (no carousel)
            # and stay until Desktop Mode is active (the whole HUD hides then).
            arrow = int(56 * S)
            edge_inset = int(120 * S)
            ay = h // 2 - arrow // 2
            self._buttons["portal_prev"] = pygame.Rect(edge_inset, ay, arrow, arrow)
            self._buttons["portal_next"] = pygame.Rect(
                w - edge_inset - arrow, ay, arrow, arrow)
            self._content_top = None

            # Bottom-centred action group: grey container holding a status line +
            # the single large action pill (Enable Camera → Desktop Mode).
            primary_w, primary_h = int(280 * S), int(56 * S)
            status_h  = int(26 * S)
            inner_gap = int(10 * S)
            gpad      = int(14 * S)
            group_w = primary_w + gpad * 2
            group_h = status_h + inner_gap + primary_h + gpad * 2
            group_x = w // 2 - group_w // 2
            group_y = h - group_h - int(28 * S)
            self._action_group = pygame.Rect(group_x, group_y, group_w, group_h)
            self._status_rect = pygame.Rect(group_x + gpad, group_y + gpad,
                                            primary_w, status_h)
            self._buttons["primary"] = pygame.Rect(
                group_x + gpad, group_y + gpad + status_h + inner_gap,
                primary_w, primary_h)

        # ── Settings / Community tabs ──────────────────────────────────────────
        else:
            self._action_group = None
            self._status_rect  = None

            # Full-bleed BLANK WHITE page — no inset card, no dark frame. The tab
            # bar floats on top; content is positioned below it (_content_top).
            self._content_top = self._tabbar.bottom + int(40 * S)

            if self._active_tab == "settings":
                cam_btn_w = int(320 * S)
                cam_btn_h = int(52 * S)
                self._buttons["camera_toggle"] = pygame.Rect(
                    w // 2 - cam_btn_w // 2,
                    self._content_top + int(60 * S),
                    cam_btn_w, cam_btn_h)

                # Delete World — toggles a list of the user's own worlds below it;
                # picking one opens the Yes/No confirmation modal (built-ins and the
                # grid_room scratch are never listed, so they can't be deleted).
                del_y = self._buttons["camera_toggle"].bottom + int(20 * S)
                self._buttons["delete_world"] = pygame.Rect(
                    w // 2 - cam_btn_w // 2, del_y, cam_btn_w, cam_btn_h)
                if self._delete_list_open:
                    ry = self._buttons["delete_world"].bottom + int(14 * S)
                    row_h, row_gap = int(46 * S), int(8 * S)
                    for k in self._deletable_portals():
                        self._buttons[f"del:{k}"] = pygame.Rect(
                            w // 2 - cam_btn_w // 2, ry, cam_btn_w, row_h)
                        ry += row_h + row_gap
                if self._delete_target is not None:
                    cw, chh = int(440 * S), int(232 * S)
                    card = pygame.Rect(w // 2 - cw // 2, h // 2 - chh // 2, cw, chh)
                    self._delete_card = card
                    bw, bh = int(180 * S), int(48 * S)
                    cgap = int(16 * S)
                    by = card.bottom - int(24 * S) - bh
                    self._buttons["del_confirm_no"] = pygame.Rect(
                        w // 2 - bw - cgap // 2, by, bw, bh)
                    self._buttons["del_confirm_yes"] = pygame.Rect(
                        w // 2 + cgap // 2, by, bw, bh)

            elif self._active_tab == "portal_builder":
                # Both WB nav controls live on the tab-bar ROW as detached grey
                # mini-bars holding a single tab-style pill — same top/height as
                # the main tab bar, but visually disconnected from it.
                mb_pad = tb_pad
                mb_h = tab_h
                if self._wb_view == "grid":
                    # Two big premium side panels flank the cube. Top aligned with
                    # the tab-bar row; bottom the same inset from the bottom as the
                    # tabs are from the top (symmetric).
                    # Panels are CENTRED in their side zones: the gap from the window
                    # edge to the panel equals the gap from the panel to the tab/cube
                    # edge — both are `gap`. Previously `edge` (40 px) ≠ `gap` (16 px).
                    top = self._tabbar.y
                    # Same vertical distance from bottom as tab bar is from top.
                    bottom = h - self._tabbar.y
                    gap = int(16 * S)
                    # Left panel — full height of the zone.
                    lx0, lx1 = gap, self._tabbar.left - gap
                    self._wb_left_panel = pygame.Rect(lx0, top, lx1 - lx0, bottom - top)
                    # Right panel — also full height (Preview button is now INSIDE
                    # the panel, between Send and Save — no button above the panel).
                    rx0, rx1 = self._tabbar.right + gap, w - gap
                    self._wb_right_panel = pygame.Rect(rx0, top, rx1 - rx0, bottom - top)

                    # Right panel content: prompt input + four stacked buttons
                    # (Restart → Send → Preview → Save World) pinned to the panel bottom.
                    rp = self._wb_right_panel
                    ipad = int(20 * S)
                    iptop = rp.y + int(64 * S)
                    save_h    = int(50 * S)
                    preview_h = int(46 * S)
                    send_h    = int(46 * S)
                    restart_h = int(36 * S)
                    bgap = int(12 * S)
                    save_y    = rp.bottom - int(20 * S) - save_h
                    preview_y = save_y - bgap - preview_h
                    send_y    = preview_y - bgap - send_h
                    restart_y = send_y - int(8 * S) - restart_h
                    self._buttons["wb_save"] = pygame.Rect(
                        rp.x + ipad, save_y, rp.w - ipad * 2, save_h)
                    self._buttons["wb_preview"] = pygame.Rect(
                        rp.x + ipad, preview_y, rp.w - ipad * 2, preview_h)
                    self._buttons["wb_send"] = pygame.Rect(
                        rp.x + ipad, send_y, rp.w - ipad * 2, send_h)
                    self._buttons["wb_restart"] = pygame.Rect(
                        rp.x + ipad, restart_y, rp.w - ipad * 2, restart_h)
                    self._wb_prompt_rect = pygame.Rect(
                        rp.x + ipad, iptop,
                        rp.w - ipad * 2, max(int(40 * S), restart_y - int(16 * S) - iptop))
                    self._buttons["wb_prompt"] = self._wb_prompt_rect
                    # Left panel ("How It Works") is a static explainer — no controls.
                else:
                    # Back to Canvas — centred in the gap between the window's left
                    # edge and the tab bar's left edge, on the tab-bar row.
                    pill_w = int(150 * S)
                    bar_w = pill_w + mb_pad * 2
                    bar_x = int(self._tabbar.left / 2 - bar_w / 2)
                    self._wb_back_bar = pygame.Rect(
                        bar_x, self._tabbar.y, bar_w, mb_h + mb_pad * 2)
                    self._buttons["wb_back"] = pygame.Rect(
                        bar_x + mb_pad, self._tabbar.y + mb_pad, pill_w, mb_h)

    def _hit(self, pos) -> str | None:
        for key, rect in self._buttons.items():
            if rect.collidepoint(pos):
                return key
        return None

    # ── Events ───────────────────────────────────────────────────────────────────

    def handle_event(self, ev, mouse_pos) -> None:
        # Incoming mouse is in WINDOW px; scale to physical for hit-testing.
        sp = (mouse_pos[0] * self.s, mouse_pos[1] * self.s)
        if ev.type == pygame.MOUSEMOTION:
            self._last_input = self._now()
            self.hover = self._hit(sp)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._last_input = self._now()
            key = self._hit(sp)
            self._press_key = key            # active-state visual while held
            self._click(key)
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            self._press_key = None
        elif ev.type == pygame.KEYDOWN:
            # While the World Builder prompt is focused, keystrokes edit the text
            # (so typing "q" doesn't quit the app); Esc just blurs the field.
            if self._wb_focused:
                self._wb_handle_key(ev)
            elif ev.key in (pygame.K_ESCAPE, pygame.K_q):
                self.should_quit = True

    def _click(self, key: str | None) -> None:
        # The delete confirmation is modal: while it's up only Yes/No are live.
        if self._delete_target is not None:
            if key == "del_confirm_yes":
                self._delete_portal(self._delete_target)
            elif key == "del_confirm_no":
                self._delete_target = None
                self._compute_layout()
            return
        # World Builder prompt focus: clicking the input focuses it; clicking
        # anywhere else (Send, Save, empty space, another tab) blurs it.
        if self._active_tab == "portal_builder" and self._wb_view == "grid":
            self._wb_focused = (key == "wb_prompt")
        if key is None:
            return
        if key == "wb_prompt":
            return                         # focus already set above; nothing else
        if key == "wb_restart":
            self._wb_restart()
            return
        if key == "wb_send":
            self._wb_send()
            return
        if key == "wb_save":
            self._wb_save()
            return
        if key.startswith("tab:"):
            tab = key.split(":", 1)[1]
            if tab != self._active_tab:
                # World Builder edits ONE world (grid_room). Entering the tab
                # makes it the working world (remembering the prior selection);
                # leaving restores it, so the Portals-tab choice is untouched.
                if tab == "portal_builder":
                    self._wb_prev_portal = self.active_portal
                    self._wb_view = "grid"
                    self._set_portal("grid_room")
                elif self._active_tab == "portal_builder" and self._wb_prev_portal:
                    self._set_portal(self._wb_prev_portal)
                self._active_tab = tab
                self._compute_layout()
            return
        if key == "wb_preview":
            # Enter the live Preview — the real off-axis render of the grid world.
            self._wb_view = "preview"
            self._set_portal("grid_room")
            self._compute_layout()
            return
        if key == "wb_back":
            self._wb_view = "grid"
            self._compute_layout()
            return
        if key == "primary":
            _label, action = self._primary()
            if action == "enable_camera":
                # If camera access was turned off in Settings, the engine ignores
                # tracking_requested while the camera_off flag exists — so clicking
                # "Enable Camera for Desktop Mode" here would be a dead button.
                # Re-enable access first so the click actually starts the camera.
                if not self.camera_enabled:
                    self._set_camera_enabled(True)
                self.tracking_requested = True
                self.live = True
                self.tracking_active = False
                self.camera_denied = False
                if not self.onboarded:
                    self.onboarded = True
                    self._save_pref("onboarded", True)
                self._toast_msg("Starting camera…", 2.0)
            elif action == "enable_desktop":
                self.desktop_mode_requested = True
                self.live = False
                self._toast_msg("Entering Desktop Mode…", 4.0)
            elif action == "disable_desktop":
                self._set_paused(True)
                self._toast_msg(STRINGS["demo_ui"]["toasts"]["desktop_paused"], 2.2)
            elif action == "resume_desktop":
                self._set_paused(False)
                self._toast_msg(STRINGS["demo_ui"]["toasts"]["desktop_resumed"], 2.2)
            # action == "none" (camera settling): no-op, the label already says so.
        elif key in ("portal_prev", "portal_next"):
            self._cycle_portal(-1 if key == "portal_prev" else +1)
        elif key == "camera_toggle":
            self._set_camera_enabled(not self.camera_enabled)
        elif key == "delete_world":
            self._delete_list_open = not self._delete_list_open
            self._compute_layout()
        elif key.startswith("del:"):
            self._delete_target = key.split(":", 1)[1]
            self._compute_layout()

    def _set_portal(self, name: str) -> None:
        """Make `name` the active world (engine hot-swaps from the saved pref next
        frame). No-op if it is already active or not a known world."""
        if name == self.active_portal or name not in (self._all_portal_keys or []):
            return
        self.active_portal = name
        self._save_pref("portal", name)

    def _cycle_portal(self, step: int) -> None:
        """Instantly switch to the previous/next world. No animation — the engine
        polls the saved preference live and swaps the scene next frame."""
        keys = self._portal_keys or ["earth"]
        if self.active_portal in keys:
            i = keys.index(self.active_portal)
        else:
            i = 0
        name = keys[(i + step) % len(keys)]
        self.active_portal = name
        self._save_pref("portal", name)
        self._toast_msg(f"World · {self._portal_names.get(name, name)}", 1.8)

    # ── World Builder authoring (prompt input + Claude save pipeline) ───────────

    def _wb_handle_key(self, ev) -> None:
        """Edit the prompt text from a KEYDOWN while the field is focused."""
        if ev.key == pygame.K_ESCAPE:
            self._wb_focused = False
            return
        if ev.key == pygame.K_BACKSPACE:
            self._wb_prompt = self._wb_prompt[:-1]
            return
        if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
            return                          # single-line-ish prompt; no newlines
        ch = ev.unicode
        if ch and ch.isprintable() and len(self._wb_prompt) < 150:
            self._wb_prompt += ch

    # ── Worlds-dir helpers (shared by Send / Save / Delete) ─────────────────────

    def _portals_dir(self) -> Path:
        """The Worlds/ directory (handles the lowercase fallback), matching the
        same base resolution `_load_portals` uses so rescans stay consistent."""
        base = Path(__file__).resolve().parent.parent
        wdir = base / "Portals"
        return wdir if wdir.exists() else base / "portals"

    def _grid_room_path(self) -> Path:
        return self._portals_dir() / "grid_room" / "portal.json"

    def _write_scratch(self, objects: list[dict]) -> None:
        """Mirror the previewed objects into the grid_room scratch portal.json so the
        engine's mtime hot-reload (`portal_runtime.poll`) shows them in live Preview.
        Best-effort: a write failure only means Preview lags, never a HUD crash."""
        try:
            path = self._grid_room_path()
            world_def = json.loads(path.read_text())
            world_def.setdefault("assets", {})["placeable_objects"] = objects
            path.write_text(json.dumps(world_def, indent=2))
        except Exception:
            pass

    # ── World Builder authoring (Send = preview, Save = commit a new world) ─────

    def _wb_restart(self) -> None:
        """Restart: clear the canvas, scratch, and prompt. Explicit user action only."""
        self._wb_preview_objects = []
        self._wb_preview_gen += 1
        self._wb_prompt = ""
        self._wb_focused = False
        self._write_scratch([])
        self._toast_msg("Canvas cleared")

    def _wb_send(self) -> None:
        """Send: prompt → Claude → validate → PREVIEW (no save).

        The sanitized objects are held in `_wb_preview_objects` (drawn on the Canvas
        Cube) and mirrored to the grid_room scratch world so the live Preview shows
        them too. Nothing is committed to the user's Worlds until Save. Every failure
        only toasts; it never crashes the HUD."""
        prompt = (self._wb_prompt or "").strip()
        if not prompt:
            self._toast_msg("Describe your portal first", 2.4)
            return
        try:
            from Portals.placeable import sanitize_objects
            try:
                from UI.world_builder_api import generate_world_objects
            except ImportError:
                from world_builder_api import generate_world_objects
        except Exception:
            self._toast_msg("Portal Builder unavailable", 2.6)
            return

        path = self._grid_room_path()
        try:
            world_def = json.loads(path.read_text())
        except Exception:
            self._toast_msg("Couldn't read the grid world", 2.6)
            return

        self._toast_msg("Building your world…", 6.0)
        raw = generate_world_objects(prompt, world_def)
        divisions = int(world_def.get("rendering", {}).get("grid_divisions", 8) or 8)
        objects = sanitize_objects(raw, divisions)        # validate BEFORE anything
        if not objects:
            self._toast_msg("No objects generated — try rephrasing "
                            "(check ANTHROPIC_API_KEY)", 3.4)
            return

        self._wb_preview_objects = objects
        self._wb_preview_gen += 1
        self._write_scratch(objects)       # drives the Canvas Cube + live Preview
        self._wb_focused = False
        n = len(objects)
        self._toast_msg(f"Preview ready — {n} object{'s' if n != 1 else ''}. "
                        "Save to keep it.", 3.2)

    def _derive_portal_name(self, prompt: str) -> str:
        """A friendly display name from the prompt (first few words, Title Cased)."""
        words = re.findall(r"[A-Za-z0-9]+", prompt or "")[:5]
        if not words:
            return "My World"
        return " ".join(w.capitalize() for w in words)[:40]

    def _unique_portal_slug(self, name: str) -> str:
        """A filesystem-safe, collision-free directory slug for a new world. Never
        a built-in or an existing world dir (numeric suffix added if needed)."""
        base = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_") or "portal"
        existing = set(self._all_portal_keys or []) | BUILTIN_PORTALS
        slug, i = base, 2
        while slug in existing or (self._portals_dir() / slug).exists():
            slug = f"{base}_{i}"
            i += 1
        return slug

    def _wb_save(self) -> None:
        """Save: commit the currently-previewed world to "my worlds".

        Creates a NEW `Portals/<slug>/portal.json` — a copy of the grid_room scratch
        (objects already baked in by Send) with a unique name — then rescans so it
        joins the Portals-tab cycle. grid_room itself stays the reusable blank scratch.
        Requires a preview (Send first); every failure only toasts."""
        if not self._wb_preview_objects:
            self._toast_msg("Press Send to preview a world first", 2.8)
            return
        try:
            world_def = json.loads(self._grid_room_path().read_text())
        except Exception:
            self._toast_msg("Couldn't read the grid world", 2.6)
            return

        name = self._derive_world_name(self._wb_prompt)
        slug = self._unique_world_slug(name)
        world_def["name"] = name
        world_def.setdefault("assets", {})["placeable_objects"] = self._wb_preview_objects
        try:
            wdir = self._portals_dir() / slug
            wdir.mkdir(parents=True, exist_ok=True)
            (wdir / "portal.json").write_text(json.dumps(world_def, indent=2))
        except Exception:
            self._toast_msg("Couldn't save the world", 2.6)
            return

        # Rescan so the new world appears in the Portals-tab cycle (grid_room stays out).
        self._all_portal_keys, self._portal_names = self._load_portals()
        self._portal_keys = [k for k in self._all_portal_keys
                            if k != "grid_room"] or ["earth"]
        # Reset the scratch for the next build.
        self._wb_preview_objects = []
        self._wb_preview_gen += 1
        self._wb_prompt = ""
        self._wb_focused = False
        self._write_scratch([])
        self._toast_msg(f"Saved “{name}” to your worlds", 3.0)

    # ── Settings → Delete World ─────────────────────────────────────────────────

    def _deletable_portals(self) -> list[str]:
        """User-created worlds only — built-ins + the grid_room scratch are excluded
        so they can never be offered for deletion."""
        return [k for k in self._portal_keys if k not in BUILTIN_PORTALS]

    def _delete_portal(self, slug: str) -> None:
        """Remove a user world after the Yes confirmation. Safety: refuse built-ins
        and anything that doesn't resolve to a direct child of Worlds/; rescan and
        fall back to a safe default if the active/prev world was the one removed."""
        wdir = self._portals_dir()
        target = (wdir / slug).resolve()
        if slug in BUILTIN_PORTALS or target.parent != wdir.resolve() or not target.is_dir():
            self._delete_target = None
            self._toast_msg("That portal can't be deleted", 2.6)
            self._compute_layout()
            return
        try:
            import shutil
            shutil.rmtree(target)
        except Exception:
            self._delete_target = None
            self._toast_msg("Couldn't delete that world", 2.6)
            self._compute_layout()
            return

        name = self._portal_names.get(slug, slug)
        self._all_portal_keys, self._portal_names = self._load_portals()
        self._portal_keys = [k for k in self._all_portal_keys
                            if k != "grid_room"] or ["earth"]
        if self.active_portal == slug:
            self.active_portal = "earth"
            self._save_pref("portal", "earth")
        if self._wb_prev_portal == slug:
            self._wb_prev_portal = "earth"
        self._delete_target = None
        if not self._deletable_portals():
            self._delete_list_open = False
        self._compute_layout()
        self._toast_msg(f"Deleted “{name}”", 2.6)

    # ── Per-frame update ───────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        # Idle-fade the control cluster so it never dominates the illusion.
        # Resting the cursor ON a control is an *engaged* state, not idle: the
        # mouse only emits MOUSEMOTION while it actually moves, so without this a
        # stationary hover let the whole cluster grey out after 4 s even though
        # the user was clearly pointing at a button (read as "the buttons grey a
        # couple seconds after I hover, over an area bigger than the hitbox" —
        # the whole control layer dims, not just the pill). Keep it lit while any
        # control is hovered.
        # Idle fade applies ONLY to the Worlds tab (a light HUD over the live
        # scene, where dimming keeps the world the star). The Settings/Community
        # pages are solid full cards — fading them would reveal the dark scene
        # through the card, so they stay at full opacity.
        on_worlds = self._active_tab == "portals"
        idle = (0.0 if (self.hover is not None or not on_worlds)
                else (self._now() - self._last_input))
        ca_target = 0.34 if idle > 4.0 else 1.0
        self._ctrl_alpha += (ca_target - self._ctrl_alpha) * min(1.0, dt * 5.0)

        # Hover is INSTANT — no easing. The previous dt-based interpolation took
        # ~0.15–0.3 s to settle, which read as sluggish, disconnected feedback.
        # Snapping hover_t to 0/1 the moment the pointer enters/leaves the hit
        # area makes the shadow + fill react immediately (highest-priority fix).
        for key in self._buttons:
            self._hover_anim[key] = 1.0 if self.hover == key else 0.0

        if self._toast and self._now() > self._toast[1]:
            self._toast = None

    # ── Surface composition (pure pygame, physical px) ────────────────────────────

    def _scratch_mtime(self) -> float:
        """mtime of the grid_room scratch portal.json, 0.0 on any error. Cheap stat,
        matched to the pattern used by WorldRuntime.poll()."""
        try:
            return self._grid_room_path().stat().st_mtime
        except Exception:
            return 0.0

    def _signature(self):
        return (
            round(self._ctrl_alpha, 2),
            self._primary(), self.live, self.daemon_running, self.desktop_paused,
            self.tracking_active, self.camera_denied,
            self._active_tab, self._wb_view, self.active_portal, self.camera_enabled,
            self._wb_prompt, self._wb_focused, self._wb_preview_gen,
            self._delete_list_open, self._delete_target, tuple(self._portal_keys),
            self._toast[0] if self._toast else None,
            self._press_key,
            tuple(round(self._hover_anim.get(k, 0.0), 2) for k in self._buttons),
            self._scratch_mtime(),
        )

    def _draw_btn(self, surf, rect, label, variant, size, dark, *, key=None,
                  force_press=False):
        """Render one control with the shared Button primitive (UI/buttons.py).

        The overlay stores its rects in PHYSICAL px (already × self.s); Button
        works in logical px × scale, so we hand it the logical rect and draw at
        self.s. Hover/press come from the overlay's existing INSTANT-hover state
        keyed by `key`, so the new look stays in lock-step with the tested
        hit-testing — no easing is introduced on hover (the frozen rule). Returns
        the Button so callers can overlay a glyph (the nav arrows / WB chevrons).

        ``force_press`` pins the button in its pressed "click-in" state regardless
        of the cursor — used by the selected tab, which reads as permanently
        toggled-in.
        """
        S = self.s
        logical = pygame.Rect(round(rect.x / S), round(rect.y / S),
                              round(rect.w / S), round(rect.h / S))
        b = Button(logical, label, variant=variant, size=size, dark=dark)
        b._hover_t = 0.0                                        # no hover animation
        b._press_t = 1.0 if (force_press or (key is not None
                                             and self._press_key == key)) else 0.0
        b.draw(surf, S)
        return b

    def _draw_grey_tab(self, surf, r, text, key, active, rad, S) -> None:
        """A raised dark-grey tab pill. Occupied tab shows the click-in look:
        0.98 shrink + thick border ring a few shades darker than the fill.
        No hover animation, no inset strip."""
        pr = pygame.Rect(r)
        fill = GREY_CONTAINER
        if active:
            cx, cy = pr.center
            pr = pygame.Rect(0, 0, int(pr.w * 0.98), int(pr.h * 0.98))
            pr.center = (cx, cy)
            fill = tuple(int(c * 0.86) for c in GREY_CONTAINER[:3])
            # Thick border ring: draw border colour across the full rect, then fill
            # inset so a darker ring is visible around the edge.
            bw = int(3 * S)
            brd = tuple(max(0, int(c * 0.62)) for c in GREY_CONTAINER[:3])
            _aa_round_rect(surf, pr, brd, rad)
            _aa_round_rect(surf, pr.inflate(-bw * 2, -bw * 2), fill,
                           max(1, rad - bw))
        else:
            _aa_round_rect(surf, pr, fill, rad)
        _text_shadow(surf, text, self.fnt_tab, (255, 255, 255), pr.center, S)

    def render_surface(self) -> pygame.Surface:
        sig = self._signature()
        if self._cached is not None and sig == self._sig:
            self._dirty = False
            return self._cached
        self._sig = sig
        self._dirty = True

        S = self.s
        surf = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))

        ca = max(0.0, min(1.0, self._ctrl_alpha))
        cx = self.w // 2
        # Tab-content draws on `layer` (idle-faded on Worlds). The tab bar is
        # drawn LATER, directly on `surf`, so it is never idle-faded and its hover
        # feedback stays instant/crisp (the prior lag was the fade easing in).
        layer = pygame.Surface((self.w, self.h), pygame.SRCALPHA)

        # ── Worlds tab — nav arrows, world-name pill, bottom action group ─────
        if self._active_tab == "portals":
            # (No world-name title pill — the active world is announced only by
            # the quick toast above the bottom action group on switch.)

            # Navigation arrows — muted solid pills (legible over the scene) with
            # the triangle glyph drawn on top.
            for key, direction in (("world_prev", -1), ("world_next", +1)):
                r = self._buttons[key]
                self._draw_btn(layer, r, "", "muted", "md", dark=True, key=key)
                acx, acy = r.center
                aw, ah = int(r.w * 0.18), int(r.h * 0.24)
                if direction < 0:   # left ◀
                    pts = [(acx + aw, acy - ah), (acx - aw, acy), (acx + aw, acy + ah)]
                else:               # right ▶
                    pts = [(acx - aw, acy - ah), (acx + aw, acy), (acx - aw, acy + ah)]
                _filled_rounded_poly(layer, pts, ARROW_GLYPH, r=max(2, int(3 * S)))

            # Bottom-centred action group: grey container (legibility) + status
            # label + the single primary action button.
            _grey_container(layer, self._action_group, s=S)
            _text_shadow(layer, self._status_text(), self.fnt_status,
                         GREY_TEXT, self._status_rect.center, S)
            label, _ = self._primary()
            self._draw_btn(layer, self._buttons["primary"], label,
                           "primary", "lg", dark=True, key="primary")

        # ── Settings tab — blank white page + camera-access toggle ────────────
        elif self._active_tab == "settings":
            layer.fill(PAGE_BG)                             # warm off-white page
            _text_shadow(layer, "Settings", self.fnt_btn, INK,
                         (cx, self._content_top), S)
            if "camera_toggle" in self._buttons:
                r = self._buttons["camera_toggle"]
                cam_label = ("Camera Access  ·  On" if self.camera_enabled
                             else "Camera Access  ·  Off")
                # Toggle state is conveyed by emphasis: On = orange accent (the
                # premium "enabled" colour), Off = outlined secondary. Sits on the
                # warm Settings page, so the tint reads without a grey backing.
                variant = "accent" if self.camera_enabled else "secondary"
                self._draw_btn(layer, r, cam_label, variant, "lg", dark=False,
                               key="camera_toggle")
            # Delete World — outlined until opened (destructive is reserved for the
            # final Yes), then the user's own worlds list below it.
            if "delete_world" in self._buttons:
                r = self._buttons["delete_world"]
                self._draw_btn(layer, r, "Delete Portal", "secondary", "lg",
                               dark=False, key="delete_world")
            if self._delete_list_open:
                rows = self._deletable_portals()
                if not rows:
                    _text_shadow(layer, "No custom worlds yet — build one in "
                                 "World Builder.", self.fnt_hint, INK_SOFT,
                                 (cx, self._buttons["delete_world"].bottom + int(40 * S)), S)
                else:
                    for k in rows:
                        bk = f"del:{k}"
                        if bk not in self._buttons:
                            continue
                        rr = self._buttons[bk]
                        _premium_card(layer, rr, S, radius=_BTN_CORNER, glow_alpha=0,
                                      shadow_alpha=18, shadow_blur=12, shadow_dy=5)
                        nm = self.fnt_hint.render(self._portal_names.get(k, k), True, INK)
                        layer.blit(nm, nm.get_rect(
                            midleft=(rr.left + int(18 * S), rr.centery)))
                        dl = self.fnt_small.render("Delete", True, (211, 47, 47))
                        layer.blit(dl, dl.get_rect(
                            midright=(rr.right - int(18 * S), rr.centery)))

        # ── World Builder tab — grid editor / live preview ────────────────────
        elif self._active_tab == "portal_builder":
            if self._wb_view == "grid":
                # Grid editor: warm off-white page with the cube floating at the
                # centre between two elevated WHITE cards (soft neumorphism).
                layer.fill(PAGE_BG)                         # warm off-white page

                # Side-panel shadows are laid down FIRST so the cube draws ON TOP
                # of them — each panel's shadow falls BEHIND the cube, not across
                # it. The right column's shadow is stretched UP to include the
                # Preview button so it reads as one continuous shadow that matches
                # the left panel's full height.
                # Side-panel + Preview shadows — fully surrounding front-lit style
                # (no directional offset; four concentric rings expand on every side).
                # Drawn BEFORE the cube so the cube sits ON TOP of the halo.
                pan_rad  = int(_PANEL_CORNER  * S)
                pv_rad   = int(_TABBAR_CORNER * S)
                # Large-element passes (panels): wide outer ring → tight inner ring.
                _PAN_PASSES = (
                    (int(10 * S), 14),
                    (int(6  * S), 22),
                    (int(3  * S), 32),
                    (int(1  * S), 40),
                )
                if self._wb_left_panel:
                    _front_lit_shadow(layer, self._wb_left_panel, pan_rad, _PAN_PASSES)
                if self._wb_right_panel:
                    _front_lit_shadow(layer, self._wb_right_panel, pan_rad, _PAN_PASSES)
                # Preview is now inside the right panel — no separate floating shadow.

                # The cube, drawn over the inner halo of each panel shadow.
                self._draw_builder_canvas(layer, S)

                # Gold rim glow — drawn before fills so it halos outward around the
                # gold edge; the opaque white fill covers the glow centre, leaving
                # only the exterior shimmer visible. Same blur/spread as the old
                # _premium_card glow pass, revived without touching the shadow layer.
                _glow_blur   = max(3, int(5 * S))
                _glow_spread = max(2, int(4 * S))
                for panel in (self._wb_left_panel, self._wb_right_panel):
                    if panel:
                        _outer_glow(layer, panel, pan_rad,
                                    color=GLOW_YELLOW, blur=_glow_blur,
                                    spread=_glow_spread, alpha=62)

                # Elevated white side panels — fills (rim + white surface) ON TOP
                # of cube overflow and glow. The brand lockup tops the left card.
                for panel in (self._wb_left_panel, self._wb_right_panel):
                    if panel:
                        _premium_card(layer, panel, S, radius=_PANEL_CORNER,
                                      phase="front")
                self._draw_wb_logo(layer, S)
                self._panel_header(layer, self._wb_left_panel,
                                   "How It Works", S, top_off=78)
                self._panel_header(layer, self._wb_right_panel,
                                   "Portal Builder", S, top_off=34)

                # Right panel — the "Describe your portal…" prompt input + the
                # Send (preview) and Save (commit) buttons stacked beneath it.
                self._draw_wb_prompt(layer, S)
                self._draw_wb_actions(layer, S)
                # Left panel — a static explainer of what World Builder is + advice.
                self._draw_wb_left(layer, S)
                # Preview is drawn inside _draw_wb_actions (between Send and Save).
            else:
                # Live preview: transparent over the real off-axis 3-D render
                # (preview_active drives the engine). "Back to Canvas" sits on the
                # tab-bar row, top-left, as a detached grey mini-bar + white tab
                # pill — it reads as a tab, disconnected from the real tab bar.
                if "wb_back" in self._buttons:
                    _aa_round_rect(layer, self._wb_back_bar, GREY_CONTAINER,
                                   int(_TABBAR_CORNER * S))
                    self._draw_btn(layer, self._buttons["wb_back"], "Back to Canvas",
                                   "primary", "sm", dark=True, key="wb_back")

        # ── Community tab — blank white page, coming soon ─────────────────────
        elif self._active_tab == "community":
            layer.fill(PAGE_BG)                             # warm off-white page
            _text_shadow(layer, "Community", self.fnt_btn, INK,
                         (cx, self._content_top), S)
            _text_shadow(layer, "Coming Soon", self.fnt_hint, GREY_TEXT_DIM,
                         (cx, self.h // 2), S)

        if ca < 0.999:
            layer.fill((255, 255, 255, int(255 * ca)), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(layer, (0, 0))

        # ── Tab bar — drawn last, on `surf`, so it is NEVER idle-faded and its
        # hover feedback is instant/crisp. A floating WHITE container holds a row
        # of push-button tabs.
        # Container shadow: same direct-offset approach as the individual tabs —
        # a dark semi-transparent copy of the bar shape shifted down.
        tb_rad = int(_TABBAR_CORNER * S)
        # Tab bar container shadow — front-lit (all sides), hidden on Worlds tab
        # (the bar floats over the live scene there; any shadow reads oddly).
        if self._active_tab != "worlds":
            _front_lit_shadow(surf, self._tabbar, tb_rad, (
                (int(6 * S), 16),
                (int(3 * S), 28),
                (int(1 * S), 44),
            ))
        _aa_round_rect(surf, self._tabbar, PANEL_SURFACE, tb_rad)
        tab_rad = int(_BTN_CORNER * S)
        for key, text in (("tab:worlds", "Worlds"),
                          ("tab:portal_builder", "Portal Builder"),
                          ("tab:community", "Community"),
                          ("tab:settings", "Settings")):
            r = self._buttons[key]
            active = key == f"tab:{self._active_tab}"
            builder = key == "tab:world_builder"
            # Drop shadow only on unoccupied, unpressed tabs — the occupied tab
            # reads as sunk-in so it gets no shadow for its entire tenure.
            if not active and self._press_key != key:
                _aa_round_rect(surf, r.move(0, int(4 * S)), (0, 0, 0, 72), tab_rad)
            if builder:
                # World Builder is always the orange accent pill — both states drawn
                # manually so fnt_tab is used consistently (no Button-internal sizing).
                if active:
                    # Occupied: thick border ring + fill + white text.
                    bw = int(3 * S)
                    brd = tuple(max(0, int(c * 0.68)) for c in ACCENT_ORANGE)
                    _aa_round_rect(surf, r, brd, tab_rad)
                    _aa_round_rect(surf, r.inflate(-bw * 2, -bw * 2),
                                   ACCENT_ORANGE, max(1, tab_rad - bw))
                else:
                    # Unoccupied: plain orange pill.
                    _aa_round_rect(surf, r, ACCENT_ORANGE, tab_rad)
                _text_shadow(surf, text, self.fnt_tab, (255, 255, 255), r.center, S)
            else:
                # Dark-grey pill; the occupied one shows the click-in look + border.
                self._draw_grey_tab(surf, r, text, key, active, tab_rad, S)

        # Toast (does not fade with idle). On the Worlds tab it floats just above
        # the bottom action group; elsewhere it sits near the bottom edge — never
        # over the tab bar or the world-name pill.
        if self._toast:
            text = self._toast[0]
            rw = self.fnt_hint.size(text)[0] + int(44 * S)
            rh = int(44 * S)
            if self._action_group is not None:
                ty = self._action_group.top - rh - int(14 * S)
            else:
                ty = self.h - rh - int(28 * S)
            rect = pygame.Rect(cx - rw // 2, ty, rw, rh)
            _grey_container(surf, rect.inflate(int(10 * S), int(10 * S)), s=S)
            _aa_round_rect(surf, rect, BTN_FILL_REST, int(_BTN_CORNER * S))
            _text_shadow(surf, text, self.fnt_hint, BTN_TEXT, rect.center, S)

        # ── Bottom bar — placeholder for subscribe / pricing content ─────────────
        # Identical geometry to the tab bar (same width, same height, same inset
        # from the bottom as the tab bar is from the top). Solid accent-orange fill
        # with the same front-lit shadow as the top bar.
        if (hasattr(self, "_bottombar") and self._bottombar
                and self._active_tab == "portal_builder"
                and self._wb_view == "grid"):
            _front_lit_shadow(surf, self._bottombar, tb_rad, (
                (int(6 * S), 16),
                (int(3 * S), 28),
                (int(1 * S), 44),
            ))
            _aa_round_rect(surf, self._bottombar, ACCENT_ORANGE, tb_rad)

        # ── Delete-World confirmation modal — on top of everything, modal.
        if self._delete_target is not None and self._delete_card:
            veil = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            veil.fill((28, 24, 18, 120))                    # warm dim, lighter scrim
            surf.blit(veil, (0, 0))
            card = self._delete_card
            _premium_card(surf, card, S, radius=_PANEL_CORNER, glow_alpha=40,
                          shadow_alpha=48, shadow_blur=30, shadow_dy=18)
            name = self._portal_names.get(self._delete_target, self._delete_target)
            _text_shadow(surf, "Delete this world?", self.fnt_btn, INK,
                         (card.centerx, card.top + int(54 * S)), S)
            _text_shadow(surf, f"“{name}” will be permanently removed.",
                         self.fnt_hint, INK_SOFT,
                         (card.centerx, card.top + int(96 * S)), S)
            _text_shadow(surf, "Are you sure you want to delete this?",
                         self.fnt_hint, INK_SOFT,
                         (card.centerx, card.top + int(120 * S)), S)
            self._draw_btn(surf, self._buttons["del_confirm_no"], "No",
                           "secondary", "md", dark=False, key="del_confirm_no")
            self._draw_btn(surf, self._buttons["del_confirm_yes"], "Yes, delete",
                           "destructive", "md", dark=False, key="del_confirm_yes")

        self._cached = surf
        return surf

    # ── World Builder panel content (prompt input + build settings) ─────────────

    @staticmethod
    def _wrap_lines(text, max_w, font):
        """Greedy word-wrap to ``max_w`` px; long single words break by chars."""
        lines, cur = [], ""
        for word in text.split(" "):
            # A word wider than the box on its own gets char-broken first.
            while font.size(word)[0] > max_w and len(word) > 1:
                piece = ""
                for ch in word:
                    if not piece or font.size(piece + ch)[0] <= max_w:
                        piece += ch
                    else:
                        break
                if cur:
                    lines.append(cur); cur = ""
                lines.append(piece)
                word = word[len(piece):]
            trial = word if not cur else cur + " " + word
            if not cur or font.size(trial)[0] <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def _draw_wrapped(self, surf, text, rect, color, font, S) -> None:
        """Left-aligned, word-wrapped text inside ``rect`` (clipped to height)."""
        pad = int(12 * S)
        max_w = rect.w - pad * 2
        if max_w <= 0:
            return
        line_h = font.get_linesize()
        y = rect.y + pad
        for ln in self._wrap_lines(text, max_w, font):
            if y + line_h > rect.bottom - pad:
                break
            surf.blit(font.render(ln, True, color), (rect.x + pad, y))
            y += line_h

    def _draw_wrapped_para(self, surf, text, rect, color, font, S) -> None:
        """Like ``_draw_wrapped`` but honours explicit ``\\n`` paragraph breaks
        (blank lines get a half-line of air). Clipped to the rect height."""
        pad = int(12 * S)
        max_w = rect.w - pad * 2
        if max_w <= 0:
            return
        line_h = font.get_linesize()
        y = rect.y + pad
        for para in text.split("\n"):
            if not para:
                y += line_h // 2
                continue
            for ln in self._wrap_lines(para, max_w, font):
                if y + line_h > rect.bottom - pad:
                    return
                surf.blit(font.render(ln, True, color), (rect.x + pad, y))
                y += line_h

    # ── Premium World Builder chrome (logo, headers, glyphs) ────────────────────

    def _gold_icon_chip(self, layer, cx, cy, size_log, S) -> None:
        """Small gold app-icon chip (rounded square, lighter core) for a header."""
        sz = int(size_log * S)
        rad = int(6 * S)
        rect = pygame.Rect(0, 0, sz, sz)
        rect.center = (int(cx), int(cy))
        _soft_shadow(layer, rect, rad, blur=int(7 * S), dy=int(2 * S), alpha=40)
        _aa_round_rect(layer, rect, ACCENT_ORANGE, rad)
        inner = rect.inflate(-int(sz * 0.44), -int(sz * 0.44))
        _aa_round_rect(layer, inner, ACCENT_ORANGE_HI, max(1, rad - int(2 * S)))

    def _panel_header(self, layer, panel, title, S, top_off=34) -> None:
        """Left-aligned card title with a gold icon chip (premium, not centred)."""
        if not panel:
            return
        cy = panel.top + int(top_off * S)
        pad = int(22 * S)
        chip = 18
        cx = panel.left + pad + int(chip * S / 2)
        self._gold_icon_chip(layer, cx, cy, chip, S)
        tx = panel.left + pad + int(chip * S) + int(12 * S)
        t = self.fnt_btn.render(title, True, INK)
        layer.blit(t, t.get_rect(midleft=(tx, cy)))

    def _draw_wb_logo(self, layer, S) -> None:
        """IRIS brand lockup at the top of the left card — a gold iris glyph plus
        a letter-spaced wordmark. Placeholder for the final logo; just presented
        with premium spacing/alignment (keep, don't redesign)."""
        lp = self._wb_left_panel
        if not lp:
            return
        cy = lp.top + int(34 * S)
        pad = int(22 * S)
        r = int(11 * S)
        gx = lp.left + pad + r
        _aa_circle(layer, (gx, cy), r, ACCENT_ORANGE)               # iris ring
        _aa_circle(layer, (gx, cy), int(r * 0.46), PANEL_SURFACE)   # cream pupil
        _aa_circle(layer, (gx, cy), int(r * 0.22), ACCENT_ORANGE_HI)
        # Letter-spaced wordmark.
        x = gx + r + int(12 * S)
        for ch in "IRIS":
            g = self.fnt_btn.render(ch, True, INK)
            layer.blit(g, g.get_rect(midleft=(x, cy)))
            x += g.get_width() + int(2 * S)

    def _draw_eye_glyph(self, layer, rect, S) -> None:
        """Gold 'eye' icon + centred 'Preview' lockup inside the capsule."""
        tw = self.fnt_small.size("Preview")[0]
        eye_w = int(24 * S)
        total = eye_w + int(10 * S) + tw
        x0 = rect.centerx - total // 2
        ex, ey = x0 + eye_w // 2, rect.centery
        eye = pygame.Rect(0, 0, eye_w, int(14 * S))
        eye.center = (ex, ey)
        pygame.draw.ellipse(layer, ACCENT_ORANGE, eye, width=max(1, int(2 * S)))
        _aa_circle(layer, (ex, ey), int(3.4 * S), ACCENT_ORANGE)

    def _draw_wb_prompt(self, layer, S) -> None:
        """Right card: the focusable "Describe your portal…" floating input card."""
        fld = self._wb_prompt_rect
        if not fld:
            return
        # Floating inset card: secondary surface, soft inner shadow at the top
        # edge, thin soft border. Reads as recessed writing space, not a flat box.
        rad = int(_BTN_CORNER * S)
        _aa_round_rect(layer, fld, GOLD_RIM_SOFT, rad)              # soft border
        bw = max(1, int(1 * S))
        _aa_round_rect(layer, fld.inflate(-2 * bw, -2 * bw), PANEL_SURFACE_2,
                       max(1, rad - bw))
        # Faint top inner shadow → recessed feel.
        ish = pygame.Surface((fld.w - 4 * bw, int(7 * S)), pygame.SRCALPHA)
        ish.fill((0, 0, 0, 14))
        ish = _blur_down_up(ish, max(2, int(4 * S)))
        layer.blit(ish, (fld.x + 2 * bw, fld.y + bw))
        if self._wb_focused:                # orange focus ring while taking keys
            pygame.draw.rect(layer, ACCENT_ORANGE, fld, width=max(1, int(2 * S)),
                             border_radius=rad)
        if self._wb_prompt:
            shown, color = self._wb_prompt + ("|" if self._wb_focused else ""), INK
        elif self._wb_focused:
            shown, color = "|", ACCENT_ORANGE
        else:
            shown, color = "Describe your portal…", INK_SOFT
        self._draw_wrapped(layer, shown, fld, color, self.fnt_hint, S)

    def _draw_wb_left(self, layer, S) -> None:
        """Left card: a static explainer — what World Builder is + how to write a
        good prompt. No controls (Send + Save live on the right card)."""
        lp = self._wb_left_panel
        if not lp:
            return
        body = (
            "Portal Builder turns a sentence into objects inside your grid room.\n\n"
            "Describe a scene with positions and colours, then press Send to "
            "preview it on the grid. Press Save to keep it as its own world.\n\n"
            "Try: “a glowing red sphere back-left, a tall pink cylinder near the "
            "glass, a blue cube floating high in the centre.”\n\n"
            "Words it understands: back / front (near the glass), left / right, "
            "high / low, centre — and colours like red, gold or blue."
        )
        top = lp.top + int(112 * S)
        rect = pygame.Rect(lp.x + int(22 * S), top,
                           lp.w - int(44 * S), lp.bottom - int(24 * S) - top)
        self._draw_wrapped_para(layer, body, rect, INK_SOFT, self.fnt_hint, S)

    def _draw_wb_actions(self, layer, S) -> None:
        """Right card: Restart → Send → Preview → Save World stacked at the panel bottom."""
        btn_rad = int(_BTN_CORNER * S)
        if "wb_restart" in self._buttons:
            r = self._buttons["wb_restart"]
            self._draw_btn(layer, r, "Restart", "secondary", "sm", dark=False, key="wb_restart")
        if "wb_send" in self._buttons:
            r = self._buttons["wb_send"]
            _aa_round_rect(layer, r.move(0, int(4 * S)), (0, 0, 0, 72), btn_rad)
            self._draw_btn(layer, r, "Send", "accent", "lg", dark=False, key="wb_send")
        if "wb_preview" in self._buttons:
            # Preview: white card with gold rim + eye glyph (same visual style as
            # before, now positioned inside the panel between Send and Save).
            r = self._buttons["wb_preview"]
            _aa_round_rect(layer, r.move(0, int(4 * S)), (0, 0, 0, 72), btn_rad)
            _premium_card(layer, r, S, radius=_BTN_CORNER, glow_alpha=0, phase="front",
                          shadow_alpha=0, shadow_blur=0, shadow_dy=0)
            self._draw_eye_glyph(layer, r, S)
            _text_shadow(layer, "Preview", self.fnt_small, INK,
                         (r.centerx + int(14 * S), r.centery), S)
        if "wb_save" in self._buttons:
            r = self._buttons["wb_save"]
            _aa_round_rect(layer, r.move(0, int(4 * S)), (0, 0, 0, 72), btn_rad)
            self._draw_btn(layer, r, "Save World", "primary", "lg", dark=False,
                           key="wb_save")

    # ── World Builder stage ────────────────────────────────────────────────────────

    def _draw_builder_canvas(self, layer, S) -> None:
        """The World Builder stage: the world the user is building, drawn LARGE.

        A STRICT 30° oblique (parallel) projection — the back wall is a true,
        undistorted N×N grid of squares and the depth axis recedes down-left at
        exactly 30°, so squares stay square and the figure reads like a clean
        technical drawing rather than a foreshortened perspective. The box is fit
        to ~86 % of the available area.

        We address locations by SQUARE, not by point: the back wall has D×D
        squares numbered 1..D. The dimension numbers are centred INSIDE the
        squares — X (width) across the bottom row, Y (height) up the left column —
        and both axes share square 1 in the bottom-left corner. Depth squares run
        down-left along the floor's left edge. Static (no per-frame state).
        """
        D = 8                                       # squares per axis (grid_room default)
        ANG = math.radians(30.0)
        ca, sa = math.cos(ANG), math.sin(ANG)       # exact 30° oblique direction
        dr = 0.55                                   # depth foreshortening (cabinet-ish)

        # Available builder area: the gap BETWEEN the two premium side panels,
        # below the tab bar. The cube is centred in this central column and fits
        # as tightly to the panels as the tab bar does (same 16px side gap).
        inner = int(16 * S)
        lp, rp = self._wb_left_panel, self._wb_right_panel
        region_left  = (lp.right if lp else int(72 * S)) + inner
        region_right = (rp.left if rp else self.w - int(72 * S)) - inner
        top = self._tabbar.bottom + int(14 * S)
        # Bottom boundary: above the bottom bar (when present), otherwise symmetric.
        bb = getattr(self, "_bottombar", None)
        bottom = (bb.top - int(12 * S)) if bb else (self.h - self._tabbar.y - int(12 * S))
        region_w = max(int(120 * S), region_right - region_left)
        region_h = max(int(80 * S), bottom - top)
        rcx, rcy = (region_left + region_right) / 2, (top + bottom) / 2

        # Fit: figure spans D + D·dr·cos30 wide and D + D·dr·sin30 tall (in cell
        # units u). Solve u so the figure fills ~86 % of the area, then centre it.
        fig_w = D * (1 + dr * ca)
        fig_h = D * (1 + dr * sa)
        u = min(0.99 * region_w / fig_w, 0.99 * region_h / fig_h)
        v = dr * u                                  # depth-cell length on screen
        # Origin = back-bottom-left corner; centre the figure's bounding box.
        ox = rcx - (D * u - D * v * ca) / 2.0
        oy = rcy - (D * v * sa - D * u) / 2.0

        def P(gx, gy, gz):
            return (int(ox + gx * u - gz * v * ca),
                    int(oy - gy * u + gz * v * sa))

        GRID = GRID_LINE                            # very subtle interior grid lines
        EDGE = CUBE_EDGE                            # soft receding edges + front frame
        WALL = CUBE_EDGE_KEY                        # soft key edges (back / perimeters)
        NUM  = INK_SOFT                             # muted square numbers (elegant)

        def gline(a, b, color, width=1):
            pygame.draw.line(layer, color, a, b, width)

        def gaaline(a, b, color):
            pygame.draw.aaline(layer, color, a, b)

        # ── Floating depth: a warm radial ground light + a soft contact shadow
        # BENEATH the cube, so it reads as elevated above the warm page (static).
        foot_w = D * (u + v * ca)                   # screen footprint width
        fcx = (P(0, 0, 0)[0] + P(D, 0, 0)[0] + P(D, 0, D)[0] + P(0, 0, D)[0]) / 4
        fcy = (P(0, 0, 0)[1] + P(D, 0, 0)[1] + P(D, 0, D)[1] + P(0, 0, D)[1]) / 4
        _radial_glow(layer, fcx, fcy + foot_w * 0.10, foot_w * 0.82, foot_w * 0.34,
                     (255, 224, 150), 70)           # warm ground light
        # Soft contact shadow spread across the cube's WHOLE base footprint (was a
        # tight central blob) so the cube reads as grounded along its full bottom.
        _radial_glow(layer, fcx, fcy + foot_w * 0.13, foot_w * 0.70, foot_w * 0.22,
                     (74, 62, 48), 90)              # soft contact shadow

        # ── Solid white-ish faces so the cube is a bright object, not a wireframe.
        def face(pts, color):
            pygame.draw.polygon(layer, color, [P(*p) for p in pts])
        face([(0, 0, 0), (D, 0, 0), (D, D, 0), (0, D, 0)], PANEL_SURFACE)     # back (brightest)
        face([(0, 0, 0), (0, D, 0), (0, D, D), (0, 0, D)], (243, 240, 234))   # left (in shade)
        face([(0, 0, 0), (D, 0, 0), (D, 0, D), (0, 0, D)], (250, 247, 241))   # floor (warm-lit)

        # Floor grid (depth cue) — receding down-left at 30°.
        for i in range(D + 1):
            gaaline(P(0, 0, i), P(D, 0, i), GRID)            # depth rings
            gaaline(P(i, 0, 0), P(i, 0, D), GRID)            # receding floor lines
        # Left wall grid.
        for i in range(D + 1):
            gaaline(P(0, i, 0), P(0, i, D), GRID)
            gaaline(P(0, 0, i), P(0, D, i), GRID)
        # Back wall full grid (the square stage — width × height).
        for i in range(D + 1):
            gaaline(P(i, 0, 0), P(i, D, 0), GRID)            # vertical
            gaaline(P(0, i, 0), P(D, i, 0), GRID)            # horizontal

        # Four receding edges + the front opening frame ("the glass") — soft.
        for gx, gy in ((0, 0), (D, 0), (0, D), (D, D)):
            gline(P(gx, gy, 0), P(gx, gy, D), EDGE, 1)
        pygame.draw.lines(layer, EDGE, True,
                          [P(0, 0, D), P(D, 0, D), P(D, D, D), P(0, D, D)], 1)
        # Perimeters — a soft warm key edge (NOT thick black); the back wall is
        # the defining rectangle, the left wall + floor share the same soft tone.
        wlw = max(1, int(1.5 * S))
        pygame.draw.lines(layer, WALL, True,
                          [P(0, 0, 0), P(D, 0, 0), P(D, D, 0), P(0, D, 0)], wlw)
        pygame.draw.lines(layer, WALL, True,
                          [P(0, 0, 0), P(0, D, 0), P(0, D, D), P(0, 0, D)], wlw)
        pygame.draw.lines(layer, WALL, True,
                          [P(0, 0, 0), P(D, 0, 0), P(D, 0, D), P(0, 0, D)], wlw)

        # ── Dimensions, centred INSIDE the squares (1..D), sharing square 1 ─────
        # Muted so the grid feels elegant, not technical.
        for c in range(1, D + 1):
            _text_shadow(layer, str(c), self.fnt_small, NUM, P(c - 0.5, 0.5, 0), S)
        for r in range(2, D + 1):
            _text_shadow(layer, str(r), self.fnt_small, NUM, P(0.5, r - 0.5, 0), S)
        # Depth labels: 1=near glass, D=back wall — all three axes share cube 1 at
        # the front-bottom-left corner of the canvas box.
        for d in range(1, D + 1):
            _text_shadow(layer, str(d), self.fnt_small, NUM, P(0, 0.5, d - 0.5), S)

        # ── Previewed objects from the last Send (transient; not yet saved) ─────
        # The placeable coord system is CENTRED (gx,gy ∈ [-D/2..D/2], gz ∈ [0..D]
        # with 0 = glass), while this oblique canvas addresses a CORNER-origin cube
        # (0..D on every axis, gz = 0 at the back wall). Convert, then paint back
        # (far) → front (near) so nearer objects overlap farther ones correctly.
        # Fall back to the scratch portal.json when no in-app Send has been run yet
        # (e.g. objects placed via the CLI or /world-builder-live skill).
        objs = self._wb_preview_objects
        if not objs:
            try:
                scratch = json.loads(self._grid_room_path().read_text())
                objs = scratch.get("assets", {}).get("placeable_objects", []) or []
            except Exception:
                objs = []
        if objs:
            items = []
            for o in objs:
                try:
                    gx, gy, gz = o["grid_position"]
                except (KeyError, TypeError, ValueError):
                    continue
                # gx/gy: centred [-D/2..D/2] → corner-origin [0..D] for P().
                # gz: engine and canvas share the same convention (0=glass, D=back wall),
                # so no flip — just pass gz directly. Sort descending so back wall draws first.
                items.append((gz, gx + D / 2.0, gy + D / 2.0, o))
            items.sort(key=lambda t: t[0], reverse=True)   # back wall (gz≈D) drawn first
            for gz_val, cgx, cgy, o in items:
                self._draw_canvas_object(layer, P, u, cgx, cgy, gz_val, o, S)

    def _draw_canvas_object(self, layer, P, u, cgx, cgy, cgz, obj, S) -> None:
        """Blit a pre-rendered oblique mesh sprite onto the canvas.

        Geometry is rendered once by UI.canvas_mesh_renderer (same 30° oblique
        constants as P()) then cached — this method is just glow + blit, no
        per-frame polygon work.  P(0,0,0) sits at the sprite's midpoint, so
        ``get_rect(center=P(cgx,cgy,cgz))`` aligns it correctly."""
        r, g, b = obj.get("color", (1.0, 1.0, 1.0))
        col = (int(max(0.0, min(1.0, r)) * 255),
               int(max(0.0, min(1.0, g)) * 255),
               int(max(0.0, min(1.0, b)) * 255))
        try:
            scale = float(obj.get("scale", 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        hs    = max(0.05, min(scale, 4.0)) * 0.5
        model = obj.get("model", "builtin:sphere")
        px, py = P(cgx, cgy, cgz)

        # Emissive glow halo — drawn first so the mesh sits on top of it.
        if bool(obj.get("emissive", True)):
            gl_r = max(4, int(hs * u * 1.8))
            gl   = pygame.Surface((gl_r * 4, gl_r * 4), pygame.SRCALPHA)
            pygame.draw.circle(gl, (*col, 88), (gl_r * 2, gl_r * 2), gl_r * 2)
            layer.blit(_blur_down_up(gl, max(2, int(4 * S))),
                       (int(px - gl_r * 2), int(py - gl_r * 2)))

        # Blit cached pre-rendered sprite.
        try:
            from UI.canvas_mesh_renderer import render_object
        except ImportError:
            from canvas_mesh_renderer import render_object
        sprite = render_object(model, col, hs, u)
        layer.blit(sprite, sprite.get_rect(center=(int(px), int(py))))

    # ── GL bridge ─────────────────────────────────────────────────────────────────

    def draw_gl(self, drawable_w: int, drawable_h: int) -> None:
        """Upload the composed Surface and draw it as one blended, screen-filling
        quad in the live GL 2.1 context. Re-uploads only when the UI changed.
        Saves/restores the engine state it touches."""
        from OpenGL.GL import (
            GL_TEXTURE_2D, GL_RGBA, GL_UNSIGNED_BYTE, GL_LINEAR,
            GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
            GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE,
            GL_DEPTH_TEST, GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
            GL_CULL_FACE, GL_PROJECTION, GL_MODELVIEW, GL_QUADS,
            GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE, GL_TEXTURE0,
            glGenTextures, glBindTexture, glTexParameteri, glTexImage2D,
            glTexSubImage2D, glUseProgram, glDisable, glEnable, glIsEnabled,
            glDepthMask, glBlendFunc, glActiveTexture, glColor4f, glTexEnvi,
            glMatrixMode, glPushMatrix, glPopMatrix, glLoadIdentity,
            glBegin, glEnd, glTexCoord2f, glVertex2f,
        )

        surf = self.render_surface()
        first = self._tex is None
        if first:
            self._tex = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self._tex)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        if first or self._dirty:
            data = pygame.image.tostring(surf, "RGBA", False)   # row 0 = top
            glBindTexture(GL_TEXTURE_2D, self._tex)
            if first:
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.w, self.h, 0,
                             GL_RGBA, GL_UNSIGNED_BYTE, data)
            else:
                glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, self.w, self.h,
                                GL_RGBA, GL_UNSIGNED_BYTE, data)
            self._dirty = False

        was_cull = glIsEnabled(GL_CULL_FACE)
        glUseProgram(0)
        glActiveTexture(GL_TEXTURE0)
        glDisable(GL_DEPTH_TEST); glDepthMask(False)
        glDisable(GL_CULL_FACE)
        glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self._tex)
        glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE)
        glColor4f(1.0, 1.0, 1.0, 1.0)

        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
        glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
        glBegin(GL_QUADS)
        glTexCoord2f(0.0, 0.0); glVertex2f(-1.0,  1.0)
        glTexCoord2f(1.0, 0.0); glVertex2f( 1.0,  1.0)
        glTexCoord2f(1.0, 1.0); glVertex2f( 1.0, -1.0)
        glTexCoord2f(0.0, 1.0); glVertex2f(-1.0, -1.0)
        glEnd()
        glMatrixMode(GL_PROJECTION); glPopMatrix()
        glMatrixMode(GL_MODELVIEW);  glPopMatrix()

        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        if was_cull:
            glEnable(GL_CULL_FACE)
        glDepthMask(True); glEnable(GL_DEPTH_TEST)


# ══════════════════════════════════════════════════════════════════════════════
#  Desktop-mode handoff
# ══════════════════════════════════════════════════════════════════════════════

def spawn_wallpaper_daemon(here: Path) -> None:
    """Launch the live wallpaper as a detached, dock-hidden daemon and record its
    PID so the launcher can detect it on reopen (robust for the frozen app, where
    the daemon process is the bundle binary, not `main.py`). The demo MUST have
    stopped its own tracker first (single camera owner)."""
    try:
        TRACKING_OFF_FLAG.unlink(missing_ok=True)
    except Exception:
        pass

    env = {**os.environ, "PARALLAX_MODE": "wallpaper", "PARALLAX_DAEMON": "1"}
    env.pop("SDL_VIDEO_CENTERED", None)
    env.pop("SDL_VIDEO_WINDOW_POS", None)

    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        # Source-run path: re-invoke the project's root entry (launcher.py) in
        # wallpaper mode. `here` is the engine's dir (Launcher/); the root entry
        # lives one level up, so resolve it from this module's own location.
        root = Path(__file__).resolve().parent.parent
        venv_py = root / ".venv" / "bin" / "python3"
        python = str(venv_py) if venv_py.exists() else sys.executable
        cmd = [python, str(root / "launcher.py")]

    proc = subprocess.Popen(cmd, env=env, start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        CONFIG_DIR.mkdir(exist_ok=True)
        DAEMON_PID_FILE.write_text(str(proc.pid))
    except Exception:
        pass
