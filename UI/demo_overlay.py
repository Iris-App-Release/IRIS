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
import subprocess
import sys
from pathlib import Path

import pygame

# OpenGL is imported lazily inside draw_gl() so this module can be imported (and
# its logic tested) in a headless process with no GL context.

# ── Paths (Iris config under ~/.iris; engine flags stay "parallax") ───────────
CONFIG_DIR        = Path.home() / ".iris"
PREFS_FILE        = CONFIG_DIR / "preferences.json"
DAEMON_PID_FILE   = CONFIG_DIR / "daemon.pid"          # written when we spawn it
TRACKING_OFF_FLAG = Path.home() / ".parallax_off"      # master switch the daemon polls
CAMERA_OFF_FLAG   = CONFIG_DIR / "camera_off"          # Settings camera-access switch

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
#  Palette — solid white pill buttons, black text, no glass effects.
# ══════════════════════════════════════════════════════════════════════════════

BTN_FILL_REST  = (255, 255, 255, 255)   # solid white at rest
BTN_FILL_HOVER = (214, 215, 222, 255)   # greys out slightly on hover

# Grey rounded container that sits BEHIND white pills (the "darkened grey
# background" of the tab bar). One grey, used everywhere — containers, the bottom
# action group, and the world-nav arrows — so the language stays consistent.
GREY_CONTAINER   = (40, 40, 45, 205)
GREY_TEXT        = (200, 200, 205)      # light label text drawn on the grey
GREY_TEXT_DIM    = (150, 150, 156)
ARROW_FILL       = (40, 40, 45, 205)    # nav arrows — same grey as the containers
ARROW_GLYPH      = (240, 240, 245)

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


def _glass_panel(surf, rect, radius, s=1.0) -> None:
    _aa_round_rect(surf, rect, (255, 255, 255, 255), radius)


def _glass_button(surf, rect, label, font, primary, hover_t, s=1.0) -> None:
    """Solid white pill; on hover it greys slightly and lifts with a soft shadow."""
    radius = int(_BTN_CORNER * s)
    # Soft drop shadow that grows in on hover (layered rects fake a blur).
    if hover_t > 0.01:
        for grow, a in ((8, 18), (4, 30), (1, 42)):
            g = int(grow * s)
            _aa_round_rect(surf, rect.inflate(g, g).move(0, int(2 * s)),
                           (0, 0, 0, int(a * hover_t)), radius + g // 2)
    # Fill interpolates white → grey by hover amount.
    fill = tuple(int(BTN_FILL_REST[i] + (BTN_FILL_HOVER[i] - BTN_FILL_REST[i]) * hover_t)
                 for i in range(4))
    _aa_round_rect(surf, rect, fill, radius)
    _text_shadow(surf, label, font, BTN_TEXT, rect.center, s)


def _text_shadow(surf, text, font, color, center, s=1.0) -> pygame.Rect:
    t = font.render(text, True, color)
    r = t.get_rect(center=center)
    surf.blit(t, r)
    return r


def _grey_container(surf, rect, s=1.0, radius=None) -> None:
    """Dark-grey rounded container drawn behind a white pill for depth."""
    r = int((_PANEL_CORNER if radius is None else radius) * s)
    _aa_round_rect(surf, rect, GREY_CONTAINER, r)


def _nav_arrow(surf, rect, direction, hover_t, s=1.0) -> None:
    """Grey rounded nav arrow (◀ / ▶). Instant, subtle drop shadow on hover."""
    radius = int(_BTN_CORNER * s)
    if hover_t > 0.01:
        for grow, a in ((6, 16), (3, 26), (1, 34)):
            g = int(grow * s)
            _aa_round_rect(surf, rect.inflate(g, g).move(0, int(2 * s)),
                           (0, 0, 0, int(a * hover_t)), radius + g // 2)
    _aa_round_rect(surf, rect, ARROW_FILL, radius)
    # Chevron glyph centred in the rect.
    cx, cy = rect.center
    aw = int(rect.w * 0.18)
    ah = int(rect.h * 0.24)
    if direction < 0:   # left ◀
        pts = [(cx + aw, cy - ah), (cx - aw, cy), (cx + aw, cy + ah)]
    else:               # right ▶
        pts = [(cx - aw, cy - ah), (cx + aw, cy), (cx - aw, cy + ah)]
    pygame.draw.polygon(surf, ARROW_GLYPH, pts)


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

        # World selection and active tab (Worlds / Community / Settings).
        self._active_tab = "worlds"
        self._world_keys, self._world_names = self._load_worlds()
        self.active_world = str(self._pref("world", "earth"))

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

        # Animation / interaction
        self._ctrl_alpha = 1.0
        self._last_input = self._now()
        self.hover: str | None = None
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

    def _load_worlds(self):
        """Return (keys, names): available world dir names + their display names,
        via the same WorldLoader the engine uses. Falls back to Earth-only."""
        try:
            from Worlds.world_loader import WorldLoader
            base = Path(__file__).resolve().parent.parent
            wdir = base / "Worlds"
            if not wdir.exists():
                wdir = base / "worlds"
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
          • before the camera is granted  → "Enable Camera"
          • while it is settling          → "Starting camera…" (no-op)
          • once granted                  → the Desktop Mode control
        Identical positioning/sizing/styling across the swap."""
        if not self._camera_ready():
            if self.live and not self.camera_denied:
                return ("Starting camera…", "none")     # in-flight, immediate feedback
            return (STRINGS["demo_ui"]["buttons"]["enable_camera"], "enable_camera")
        # Camera granted → Desktop Mode controls.
        if self.daemon_running and not self.desktop_paused:
            return ("Disable Desktop Mode", "disable_desktop")
        if self.daemon_running and self.desktop_paused:
            return (STRINGS["demo_ui"]["buttons"]["resume_desktop"], "resume_desktop")
        return (STRINGS["demo_ui"]["buttons"]["enable_desktop"], "enable_desktop")

    @property
    def preview_active(self) -> bool:
        """Engine reads this each frame: render the live 3-D world preview ONLY
        while the Worlds tab is showing. On Settings/Community the engine skips
        the (expensive) scene draw — the tab shows a solid card instead."""
        return self._active_tab == "worlds"

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
        pad = int(16 * S)
        btn_gap = int(8 * S)

        # ── Tab bar (always visible across all tabs) ──────────────────────────
        tab_specs = [("worlds", "Worlds"), ("community", "Community"),
                     ("settings", "Settings")]
        tab_w, tab_h = int(110 * S), int(36 * S)
        tab_gap = int(6 * S)
        tb_pad = int(6 * S)
        total_tab_w = len(tab_specs) * tab_w + (len(tab_specs) - 1) * tab_gap
        tabbar_w = total_tab_w + tb_pad * 2
        tabbar_h = tab_h + tb_pad * 2
        self._tabbar = pygame.Rect(w // 2 - tabbar_w // 2, int(20 * S),
                                   tabbar_w, tabbar_h)
        for i, (key, _) in enumerate(tab_specs):
            tx = self._tabbar.x + tb_pad + i * (tab_w + tab_gap)
            self._buttons[f"tab:{key}"] = pygame.Rect(
                tx, self._tabbar.y + tb_pad, tab_w, tab_h)

        # ── Worlds tab ────────────────────────────────────────────────────────
        if self._active_tab == "worlds":
            # World-name pill — centred just below the tab bar (width measured at
            # render time from the active world's display name).
            self._worldname_cy = self._tabbar.bottom + int(28 * S)

            # World navigation arrows — one at each screen edge, vertical centre.
            # They switch worlds instantly (no carousel/animation) and stay until
            # Desktop Mode is active (the whole HUD hides then).
            arrow = int(56 * S)
            ay = h // 2 - arrow // 2
            self._buttons["world_prev"] = pygame.Rect(int(40 * S), ay, arrow, arrow)
            self._buttons["world_next"] = pygame.Rect(
                w - int(40 * S) - arrow, ay, arrow, arrow)

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
            self._content_panel = None

        # ── Settings / Community tabs ──────────────────────────────────────────
        else:
            self._worldname_cy = None
            self._action_group = None
            self._status_rect  = None

            # Full-width content page below the tab bar
            page_top = self._tabbar.bottom + int(16 * S)
            page_h   = h - page_top - int(40 * S)
            page_w   = w - int(80 * S)
            self._content_panel = pygame.Rect(int(40 * S), page_top, page_w, page_h)

            if self._active_tab == "settings":
                cam_btn_w = min(int(300 * S), page_w - pad * 2)
                cam_btn_h = int(52 * S)
                self._buttons["camera_toggle"] = pygame.Rect(
                    w // 2 - cam_btn_w // 2,
                    page_top + int(80 * S),
                    cam_btn_w, cam_btn_h)

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
            self._click(self._hit(sp))
        elif ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_q):
            self.should_quit = True

    def _click(self, key: str | None) -> None:
        if key is None:
            return
        if key.startswith("tab:"):
            tab = key.split(":", 1)[1]
            if tab != self._active_tab:
                self._active_tab = tab
                self._compute_layout()
            return
        if key == "primary":
            _label, action = self._primary()
            if action == "enable_camera":
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
        elif key in ("world_prev", "world_next"):
            self._cycle_world(-1 if key == "world_prev" else +1)
        elif key == "camera_toggle":
            self._set_camera_enabled(not self.camera_enabled)

    def _cycle_world(self, step: int) -> None:
        """Instantly switch to the previous/next world. No animation — the engine
        polls the saved preference live and swaps the scene next frame."""
        keys = self._world_keys or ["earth"]
        if self.active_world in keys:
            i = keys.index(self.active_world)
        else:
            i = 0
        name = keys[(i + step) % len(keys)]
        self.active_world = name
        self._save_pref("world", name)
        self._toast_msg(f"World · {self._world_names.get(name, name)}", 1.8)

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
        on_worlds = self._active_tab == "worlds"
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

    def _signature(self):
        return (
            round(self._ctrl_alpha, 2),
            self._primary(), self.live, self.daemon_running, self.desktop_paused,
            self.tracking_active, self.camera_denied,
            self._active_tab, self.active_world, self.camera_enabled,
            self._toast[0] if self._toast else None,
            tuple(round(self._hover_anim.get(k, 0.0), 2) for k in self._buttons),
        )

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
        layer = pygame.Surface((self.w, self.h), pygame.SRCALPHA)

        # ── Tab bar (all tabs) — dark grey container, white active pill ───────
        _aa_round_rect(layer, self._tabbar, GREY_CONTAINER, int(_TABBAR_CORNER * S))
        for key, text in (("tab:worlds", "Worlds"),
                          ("tab:community", "Community"),
                          ("tab:settings", "Settings")):
            r = self._buttons[key]
            is_active = (key == f"tab:{self._active_tab}")
            if is_active:
                _aa_round_rect(layer, r, BTN_FILL_REST, int(_BTN_CORNER * S))
                _text_shadow(layer, text, self.fnt_small, BTN_TEXT, r.center, S)
            else:
                if self._hover_anim.get(key, 0.0) > 0.5:   # instant hover highlight
                    _aa_round_rect(layer, r, (255, 255, 255, 46), int(_BTN_CORNER * S))
                _text_shadow(layer, text, self.fnt_small, GREY_TEXT, r.center, S)

        # ── Worlds tab — nav arrows, world-name pill, bottom action group ─────
        if self._active_tab == "worlds":
            # World-name pill (white pill on a grey container), centred under tabs.
            wname = self._world_names.get(self.active_world, self.active_world)
            tw = self.fnt_btn.size(wname)[0]
            pill_w = tw + int(44 * S)
            pill_h = int(40 * S)
            name_pill = pygame.Rect(cx - pill_w // 2,
                                    self._worldname_cy - pill_h // 2,
                                    pill_w, pill_h)
            _grey_container(layer, name_pill.inflate(int(10 * S), int(10 * S)), s=S)
            _aa_round_rect(layer, name_pill, BTN_FILL_REST, int(_BTN_CORNER * S))
            _text_shadow(layer, wname, self.fnt_btn, BTN_TEXT, name_pill.center, S)

            # Navigation arrows (grey, instant hover shadow).
            _nav_arrow(layer, self._buttons["world_prev"], -1,
                       self._hover_anim.get("world_prev", 0.0), s=S)
            _nav_arrow(layer, self._buttons["world_next"], +1,
                       self._hover_anim.get("world_next", 0.0), s=S)

            # Bottom-centred action group: grey container + status + action pill.
            _grey_container(layer, self._action_group, s=S)
            _text_shadow(layer, self._status_text(), self.fnt_status,
                         GREY_TEXT, self._status_rect.center, S)
            label, _ = self._primary()
            _glass_button(layer, self._buttons["primary"], label, self.fnt_btn,
                          primary=True,
                          hover_t=self._hover_anim.get("primary", 0.0), s=S)

        # ── Settings tab — white card + camera-access toggle ──────────────────
        elif self._active_tab == "settings":
            if self._content_panel:
                _glass_panel(layer, self._content_panel,
                             radius=int(_PANEL_CORNER * S), s=S)
                _text_shadow(layer, "Settings", self.fnt_btn, BTN_TEXT,
                             (self._content_panel.centerx,
                              self._content_panel.y + int(38 * S)), S)
            if "camera_toggle" in self._buttons:
                r = self._buttons["camera_toggle"]
                # Grey container behind the pill so it reads on the white card.
                _grey_container(layer, r.inflate(int(12 * S), int(12 * S)), s=S)
                cam_label = ("Camera Access  ·  On" if self.camera_enabled
                             else "Camera Access  ·  Off")
                _glass_button(layer, r, cam_label, self.fnt_btn, primary=False,
                              hover_t=self._hover_anim.get("camera_toggle", 0.0), s=S)

        # ── Community tab — white card, coming soon ───────────────────────────
        elif self._active_tab == "community":
            if self._content_panel:
                _glass_panel(layer, self._content_panel,
                             radius=int(_PANEL_CORNER * S), s=S)
                _text_shadow(layer, "Community", self.fnt_btn, BTN_TEXT,
                             (self._content_panel.centerx,
                              self._content_panel.y + int(38 * S)), S)
                _text_shadow(layer, "Coming Soon", self.fnt_hint, GREY_TEXT_DIM,
                             self._content_panel.center, S)

        if ca < 0.999:
            layer.fill((255, 255, 255, int(255 * ca)), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(layer, (0, 0))

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

        self._cached = surf
        return surf

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
