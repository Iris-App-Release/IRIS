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
# group, the toast — so the language stays consistent.
GREY_CONTAINER   = (40, 40, 45, 205)
GREY_TEXT        = (200, 200, 205)      # light label text drawn on the grey
GREY_TEXT_DIM    = (150, 150, 156)
ARROW_GLYPH      = (240, 240, 245)      # nav-arrow triangle, drawn over the pill

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
        self._wb_prev_world = None        # world to restore when leaving the tab
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
        return (self._active_tab == "worlds"
                or (self._active_tab == "world_builder"
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
        # Detached tab-style mini-bars for the World Builder nav controls (set in
        # the world_builder branch below; None when not on that tab).
        self._wb_preview_bar = None
        self._wb_back_bar = None
        pad = int(16 * S)
        btn_gap = int(8 * S)

        # ── Tab bar (always visible across all tabs) ──────────────────────────
        tab_specs = [("worlds", "Worlds"), ("world_builder", "World Builder"),
                     ("community", "Community"), ("settings", "Settings")]
        tab_w, tab_h = int(124 * S), int(36 * S)
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

            # World navigation arrows — flanking the scene, pulled in from the
            # edges toward the centre. They switch worlds instantly (no carousel)
            # and stay until Desktop Mode is active (the whole HUD hides then).
            arrow = int(56 * S)
            edge_inset = int(120 * S)
            ay = h // 2 - arrow // 2
            self._buttons["world_prev"] = pygame.Rect(edge_inset, ay, arrow, arrow)
            self._buttons["world_next"] = pygame.Rect(
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
            self._worldname_cy = None
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

            elif self._active_tab == "world_builder":
                # Both WB nav controls live on the tab-bar ROW as detached grey
                # mini-bars holding a single tab-style pill — same top/height as
                # the main tab bar, but visually disconnected from it.
                mb_pad = tb_pad
                mb_h = tab_h
                if self._wb_view == "grid":
                    # Preview — parallel to the tab bar, detached to the RIGHT.
                    pill_w = int(120 * S)
                    bar_x = self._tabbar.right + int(12 * S)
                    self._wb_preview_bar = pygame.Rect(
                        bar_x, self._tabbar.y, pill_w + mb_pad * 2, mb_h + mb_pad * 2)
                    self._buttons["wb_preview"] = pygame.Rect(
                        bar_x + mb_pad, self._tabbar.y + mb_pad, pill_w, mb_h)
                else:
                    # Back to Canvas — top-LEFT, roughly where it was, aligned to
                    # the tab-bar row.
                    pill_w = int(150 * S)
                    bar_x = int(24 * S)
                    self._wb_back_bar = pygame.Rect(
                        bar_x, self._tabbar.y, pill_w + mb_pad * 2, mb_h + mb_pad * 2)
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
        elif ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_q):
            self.should_quit = True

    def _click(self, key: str | None) -> None:
        if key is None:
            return
        if key.startswith("tab:"):
            tab = key.split(":", 1)[1]
            if tab != self._active_tab:
                # World Builder edits ONE world (grid_room). Entering the tab
                # makes it the working world (remembering the prior selection);
                # leaving restores it, so the Worlds-tab choice is untouched.
                if tab == "world_builder":
                    self._wb_prev_world = self.active_world
                    self._wb_view = "grid"
                    self._set_world("grid_room")
                elif self._active_tab == "world_builder" and self._wb_prev_world:
                    self._set_world(self._wb_prev_world)
                self._active_tab = tab
                self._compute_layout()
            return
        if key == "wb_preview":
            # Enter the live Preview — the real off-axis render of the grid world.
            self._wb_view = "preview"
            self._set_world("grid_room")
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
        elif key in ("world_prev", "world_next"):
            self._cycle_world(-1 if key == "world_prev" else +1)
        elif key == "camera_toggle":
            self._set_camera_enabled(not self.camera_enabled)

    def _set_world(self, name: str) -> None:
        """Make `name` the active world (engine hot-swaps from the saved pref next
        frame). No-op if it is already active or not a known world."""
        if name == self.active_world or name not in (self._world_keys or []):
            return
        self.active_world = name
        self._save_pref("world", name)

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
            self._active_tab, self._wb_view, self.active_world, self.camera_enabled,
            self._toast[0] if self._toast else None,
            self._press_key,
            tuple(round(self._hover_anim.get(k, 0.0), 2) for k in self._buttons),
        )

    def _draw_btn(self, surf, rect, label, variant, size, dark, *, key=None):
        """Render one control with the shared Button primitive (UI/buttons.py).

        The overlay stores its rects in PHYSICAL px (already × self.s); Button
        works in logical px × scale, so we hand it the logical rect and draw at
        self.s. Hover/press come from the overlay's existing INSTANT-hover state
        keyed by `key`, so the new look stays in lock-step with the tested
        hit-testing — no easing is introduced on hover (the frozen rule). Returns
        the Button so callers can overlay a glyph (the nav arrows / WB chevrons).
        """
        S = self.s
        logical = pygame.Rect(round(rect.x / S), round(rect.y / S),
                              round(rect.w / S), round(rect.h / S))
        b = Button(logical, label, variant=variant, size=size, dark=dark)
        if key is not None:
            b._hover_t = self._hover_anim.get(key, 0.0)        # binary (instant)
            b._press_t = 1.0 if self._press_key == key else 0.0
        b.draw(surf, S)
        return b

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
        if self._active_tab == "worlds":
            # World-name chip — a static light pill (primary look in the dark
            # palette → light fill, dark text) so the active world stays legible
            # over any scene. Non-interactive (no hover key).
            wname = self._world_names.get(self.active_world, self.active_world)
            tw = self.fnt_btn.size(wname)[0]
            pill_w = tw + int(44 * S)
            pill_h = int(40 * S)
            name_pill = pygame.Rect(cx - pill_w // 2,
                                    self._worldname_cy - pill_h // 2,
                                    pill_w, pill_h)
            self._draw_btn(layer, name_pill, wname, "primary", "lg", dark=True)

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
            layer.fill(BTN_FILL_REST)                       # full-bleed blank white
            _text_shadow(layer, "Settings", self.fnt_btn, BTN_TEXT,
                         (cx, self._content_top), S)
            if "camera_toggle" in self._buttons:
                r = self._buttons["camera_toggle"]
                cam_label = ("Camera Access  ·  On" if self.camera_enabled
                             else "Camera Access  ·  Off")
                # Toggle state is conveyed by emphasis: On = filled primary,
                # Off = outlined secondary. Light palette — it sits on the white
                # Settings page, so the border/tint read without a grey backing.
                variant = "primary" if self.camera_enabled else "secondary"
                self._draw_btn(layer, r, cam_label, variant, "lg", dark=False,
                               key="camera_toggle")

        # ── World Builder tab — grid editor / live preview ────────────────────
        elif self._active_tab == "world_builder":
            if self._wb_view == "grid":
                # Grid editor: the world (the big labeled box) dominates a white
                # page; the Preview control sits on the tab-bar row (detached,
                # right) as a grey mini-bar holding a white tab-style pill.
                layer.fill(BTN_FILL_REST)                   # full-bleed blank white
                self._draw_builder_canvas(layer, S)
                if "wb_preview" in self._buttons:
                    _aa_round_rect(layer, self._wb_preview_bar, GREY_CONTAINER,
                                   int(_TABBAR_CORNER * S))
                    self._draw_btn(layer, self._buttons["wb_preview"], "Preview",
                                   "primary", "sm", dark=True, key="wb_preview")
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
            layer.fill(BTN_FILL_REST)                       # full-bleed blank white
            _text_shadow(layer, "Community", self.fnt_btn, BTN_TEXT,
                         (cx, self._content_top), S)
            _text_shadow(layer, "Coming Soon", self.fnt_hint, GREY_TEXT_DIM,
                         (cx, self.h // 2), S)

        if ca < 0.999:
            layer.fill((255, 255, 255, int(255 * ca)), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(layer, (0, 0))

        # ── Tab bar — drawn last, on `surf`, so it is NEVER idle-faded and its
        # hover feedback is instant/crisp (dark grey container, white active pill).
        _aa_round_rect(surf, self._tabbar, GREY_CONTAINER, int(_TABBAR_CORNER * S))
        for key, text in (("tab:worlds", "Worlds"),
                          ("tab:world_builder", "World Builder"),
                          ("tab:community", "Community"),
                          ("tab:settings", "Settings")):
            r = self._buttons[key]
            # Inverted scheme: the OCCUPIED tab is a BLACK pill (primary in the
            # LIGHT palette → near-black fill, off-white text); the rest are WHITE
            # pills (primary in the DARK palette → off-white fill, black text).
            # The grey tab-bar container behind them is unchanged.
            active = key == f"tab:{self._active_tab}"
            self._draw_btn(surf, r, text, "primary", "sm",
                           dark=not active, key=key)

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

        # Available builder area: below the tab bar, above the "Preview →" pill.
        pad = int(72 * S)
        top = (self._content_top or int(120 * S)) + int(14 * S)
        # Preview now lives on the tab-bar row (not the bottom edge), so the
        # canvas gets the full page height down to a bottom margin.
        bottom = self.h - int(60 * S)
        region_w, region_h = self.w - pad * 2, max(int(80 * S), bottom - top)
        rcx, rcy = self.w / 2, (top + bottom) / 2

        # Fit: figure spans D + D·dr·cos30 wide and D + D·dr·sin30 tall (in cell
        # units u). Solve u so the figure fills ~86 % of the area, then centre it.
        fig_w = D * (1 + dr * ca)
        fig_h = D * (1 + dr * sa)
        u = min(0.86 * region_w / fig_w, 0.86 * region_h / fig_h)
        v = dr * u                                  # depth-cell length on screen
        # Origin = back-bottom-left corner; centre the figure's bounding box.
        ox = rcx - (D * u - D * v * ca) / 2.0
        oy = rcy - (D * v * sa - D * u) / 2.0

        def P(gx, gy, gz):
            return (int(ox + gx * u - gz * v * ca),
                    int(oy - gy * u + gz * v * sa))

        GRID = (211, 213, 220)                      # faint interior grid lines
        EDGE = (120, 123, 132)                      # receding edges + front frame
        WALL = (20, 20, 26)                         # back-wall border (the focus)
        TICK = (38, 38, 46)                         # X / Y square numbers
        DEEP = GREY_TEXT_DIM                        # depth square numbers (subtle)

        def gline(a, b, color, width=1):
            pygame.draw.line(layer, color, a, b, width)

        def gaaline(a, b, color):
            pygame.draw.aaline(layer, color, a, b)

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

        # Four receding edges + the front opening frame ("the glass").
        for gx, gy in ((0, 0), (D, 0), (0, D), (D, D)):
            gline(P(gx, gy, 0), P(gx, gy, D), EDGE, 1)
        pygame.draw.lines(layer, EDGE, True,
                          [P(0, 0, D), P(D, 0, D), P(D, D, D), P(0, D, D)], 1)
        # Back-wall border — brightest line; this rectangle IS the world.
        pygame.draw.lines(layer, WALL, True,
                          [P(0, 0, 0), P(D, 0, 0), P(D, D, 0), P(0, D, 0)],
                          max(2, int(2 * S)))

        # ── Dimensions, centred INSIDE the squares (1..D), sharing square 1 ─────
        # X (width): centred in each bottom-row square. Square c spans points
        # [c-1,c], so its centre is at c-0.5; the bottom row centre-height is 0.5.
        for c in range(1, D + 1):
            _text_shadow(layer, str(c), self.fnt_small, TICK, P(c - 0.5, 0.5, 0), S)
        # Y (height): centred in each left-column square; skip 1 — the bottom-left
        # square already carries the shared "1".
        for r in range(2, D + 1):
            _text_shadow(layer, str(r), self.fnt_small, TICK, P(0.5, r - 0.5, 0), S)
        # Depth: centred in the floor's left-edge squares, running down-left.
        for d in range(1, D + 1):
            _text_shadow(layer, str(d), self.fnt_small, DEEP, P(0.5, 0, d - 0.5), S)

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
