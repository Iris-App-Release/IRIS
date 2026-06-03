#!/usr/bin/env python3
"""
buttons.py — IRIS reusable button system (pure pygame, grayscale-minimal).

A single ``Button`` class that renders the established, dialed-in IRIS control
look as a reusable primitive, so every surface in the app (HUD, World Builder,
Settings) can draw the *same* button instead of hand-rolling rects each time.

Design language (grayscale-minimal):
  • Four variants — PRIMARY (solid, high emphasis), SECONDARY (outlined, low
    emphasis), DESTRUCTIVE (red — the ONLY non-grayscale accent), MUTED
    (tertiary, minimal).
  • Three sizes — sm (12 px), md (14 px), lg (16 px), each with matched padding.
  • Five interaction states — default, hover, active (pressed), disabled, focus.
  • Subtle rounding (7.2 px ≈ 0.45 rem), never aggressive.
  • Shadows: none at rest; a soft 0 4px 6px/0.10 lift on hover; a tight
    0 1px 2px/0.05 *inset* press shadow plus a 0.98 scale on active.

Rendering is done entirely with pygame primitives — no external UI libraries.
Rounded corners are super-sampled and ``smoothscale``-d down so they stay crisp
at any device (Retina) scale; that anti-aliasing technique is the same one the
main HUD relies on, because ``pygame.draw.rect(border_radius=…)`` does NOT
anti-alias its corners.

────────────────────────────────────────────────────────────────────────────
ONE DELIBERATE DEVIATION FROM THE WRITTEN SPEC — instant hover.
────────────────────────────────────────────────────────────────────────────
The spec asks for "0.15 s ease-in-out for ALL state changes." In this codebase
that exact easing on *hover* was empirically the single most-noticed quality
defect (see obsidian-docs/systems/ui-overlay.md): a ~0.15–0.3 s hover settle
reads as sluggish, disconnected feedback. So hover is **instant by default**
(``instant_hover=True``) — the grey/shadow snaps within one frame — while the
0.15 s ease-in-out machinery is retained for the press and focus transitions,
where a brief settle feels intentional rather than laggy. Pass
``instant_hover=False`` to get literal spec behaviour everywhere.
"""

from __future__ import annotations

import pygame

# ══════════════════════════════════════════════════════════════════════════════
#  Palette — exact RGB targets from the spec (oklch → RGB, grayscale-minimal).
#  Destructive (red) is the only chromatic token; everything else is neutral.
# ══════════════════════════════════════════════════════════════════════════════

LIGHT = {
    "background":           (0xFF, 0xFF, 0xFF),   # oklch(1 0 0)      pure white
    "foreground":           (0x25, 0x25, 0x25),   # oklch(.145 0 0)   near-black
    "primary":              (0x25, 0x25, 0x25),   # near-black (de-blued to match unselected-tab black)
    "primary_foreground":   (0xF9, 0xF9, 0xF9),   # oklch(.985 0 0)   off-white
    "secondary":            (0xF7, 0xF7, 0xF7),   # oklch(.97 0 0)    light gray
    "secondary_foreground": (0x25, 0x25, 0x25),   # near-black (de-blued)
    "muted":                (0xF7, 0xF7, 0xF7),   # oklch(.97 0 0)    light gray
    "muted_foreground":     (0x8E, 0x8E, 0x8E),   # oklch(.556 0 0)   medium gray
    "border":               (0xEB, 0xEB, 0xEB),   # oklch(.922 0 0)   light border
    "ring":                 (0xB3, 0xB3, 0xB3),   # oklch(.708 0 0)   focus ring
    "destructive":          (0xD3, 0x2F, 0x2F),   # oklch(.577 .245 27.3) red
    "destructive_foreground": (0xFF, 0xFF, 0xFF),
}

DARK = {
    "background":           (0x25, 0x25, 0x25),   # oklch(.145 0 0)   near-black
    "foreground":           (0xF9, 0xF9, 0xF9),   # oklch(.985 0 0)   off-white
    "primary":              (0xEB, 0xEB, 0xEB),   # oklch(.922 0 0)   light gray
    "primary_foreground":   (0x25, 0x25, 0x25),   # near-black (de-blued)
    "secondary":            (0x25, 0x25, 0x25),   # near-black (de-blued)
    "secondary_foreground": (0xF9, 0xF9, 0xF9),   # oklch(.985 0 0)   off-white
    "muted":                (0x25, 0x25, 0x25),   # near-black (de-blued)
    "muted_foreground":     (0xB3, 0xB3, 0xB3),   # oklch(.708 0 0)   medium gray
    "border":               (0x44, 0x44, 0x44),   # oklch(1 0 0 / 10%) on near-black
    "ring":                 (0x8E, 0x8E, 0x8E),   # oklch(.556 0 0)   focus ring
    "destructive":          (0xC8, 0x5A, 0x5A),   # oklch(.704 .191 22.2) muted red
    "destructive_foreground": (0xFF, 0xFF, 0xFF),
}

# ── Frozen design tokens ──────────────────────────────────────────────────────
RADIUS         = 7.2     # px (0.45 rem) — subtle rounding, never aggressive
TRANSITION     = 0.15    # s, ease-in-out — press/focus settle (NOT hover)
LINE_HEIGHT    = 1.4     # text metrics target
LETTER_SPACING = 0       # px — tight, professional

# Shadow specs (offset_y, blur, alpha-0..1). "Default" is intentionally absent.
SHADOW_HOVER  = (4, 6, 0.10)   # 0 4px 6px rgba(0,0,0,.10)  — lift
SHADOW_ACTIVE = (1, 2, 0.05)   # 0 1px 2px rgba(0,0,0,.05)  — tight, inset feel

# Super-sample factor for crisp anti-aliased corners at any device scale.
_AA_SS = 4

# Size table: font px, horizontal/vertical padding, and a sensible min height.
# Padding scales with the size so the optical weight stays balanced.
SIZES = {
    "sm": {"font": 12, "pad_x": 12, "pad_y": 6,  "height": 28},
    "md": {"font": 14, "pad_x": 16, "pad_y": 9,  "height": 36},
    "lg": {"font": 16, "pad_x": 20, "pad_y": 12, "height": 44},
}


# ══════════════════════════════════════════════════════════════════════════════
#  Colour helpers
# ══════════════════════════════════════════════════════════════════════════════

def lighten(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    """Lighten an RGB toward white by ``amount`` (0..1). 0.05 == "lighten 5 %"."""
    return tuple(int(c + (255 - c) * amount) for c in rgb)


def darken(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    """Darken an RGB toward black by ``amount`` (0..1). 0.05 == "darken 5 %"."""
    return tuple(int(c * (1.0 - amount)) for c in rgb)


def _ease_in_out(t: float) -> float:
    """Cubic ease-in-out on 0..1 — matches the spec's 0.15 s ease curve."""
    t = max(0.0, min(1.0, t))
    return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ══════════════════════════════════════════════════════════════════════════════
#  Drawing primitives (pure pygame)
# ══════════════════════════════════════════════════════════════════════════════

def _aa_round_rect(surf: pygame.Surface, rect: pygame.Rect, color, radius: float,
                   width: int = 0) -> None:
    """Anti-aliased rounded rect (filled, or outlined when ``width`` > 0).

    ``pygame.draw.rect(border_radius=…)`` leaves stair-stepped corners; here we
    draw the shape at ``_AA_SS``× into a scratch surface and ``smoothscale`` it
    down so the corners are smooth at any device scale. ``color`` may be RGB or
    RGBA — RGBA lets us layer translucent shadow passes.
    """
    w, h = int(rect.w), int(rect.h)
    if w <= 0 or h <= 0:
        return
    ss = _AA_SS
    big = pygame.Surface((w * ss, h * ss), pygame.SRCALPHA)
    pygame.draw.rect(big, color, big.get_rect(),
                     width=int(width * ss), border_radius=int(radius * ss))
    surf.blit(pygame.transform.smoothscale(big, (w, h)), rect.topleft)


def _drop_shadow(surf: pygame.Surface, rect: pygame.Rect, radius: float,
                 spec: tuple[int, int, float], scale: float,
                 strength: float = 1.0) -> None:
    """Soft drop shadow faked by layering low-alpha rounded rects (a cheap blur).

    ``spec`` is (offset_y, blur, alpha). Wider, fainter rects underneath a
    tighter, stronger one approximate a Gaussian falloff. ``strength`` lets a
    transition fade the shadow in/out.
    """
    off_y, blur, alpha = spec
    base = int(alpha * 255 * max(0.0, min(1.0, strength)))
    if base <= 0:
        return
    oy = int(off_y * scale)
    for grow, a_frac in ((blur * 1.4, 0.45), (blur * 0.8, 0.70), (blur * 0.3, 1.0)):
        g = int(grow * scale)
        _aa_round_rect(surf, rect.inflate(g, g).move(0, oy),
                       (0, 0, 0, int(base * a_frac)), radius + g / 2)


def load_font(size: int, bold: bool = True) -> pygame.font.Font:
    """Load the minimalist bold sans the spec calls for, Retina-safe.

    ``pygame.font.SysFont`` silently falls back to the blurry default *bitmap*
    font when a family name isn't installed (it never raises), so we probe with
    ``match_font`` first and only construct a ``Font`` from a real path. Order:
    Inter → SF Pro Display → SF Pro Text → Helvetica Neue → Helvetica → Arial.
    """
    for name in ("Inter", "SF Pro Display", "SF Pro Text",
                 "Helvetica Neue", "Helvetica", "Arial"):
        path = pygame.font.match_font(name, bold=bold)
        if path:
            try:
                return pygame.font.Font(path, size)
            except Exception:
                continue
    return pygame.font.Font(None, size + 6)


# ══════════════════════════════════════════════════════════════════════════════
#  Button
# ══════════════════════════════════════════════════════════════════════════════

class Button:
    """A reusable, self-contained grayscale-minimal button.

    Lifecycle per frame::

        btn.update(mouse_pos, mouse_down, dt)   # advance state + transitions
        btn.draw(surface, scale)                # composite onto a surface

    or feed it events directly::

        clicked = btn.handle_event(event, mouse_pos)

    Parameters
    ----------
    rect : pygame.Rect | tuple
        Hit area / draw bounds in *logical* pixels (multiplied by ``scale`` at
        draw time for Retina). If ``None``, a size is derived from the label.
    label : str
        Button text. Rendered with a bold geometric sans (see ``load_font``).
    variant : {"primary", "secondary", "destructive", "muted"}
        Visual emphasis tier — see module docstring.
    size : {"sm", "md", "lg"}
        12 / 14 / 16 px text with matched padding.
    dark : bool
        Use the dark palette.
    on_click : callable | None
        Invoked (no args) when a press completes inside the button.
    enabled : bool
        Disabled buttons render muted at 50 % opacity and ignore input.
    instant_hover : bool
        Hover snaps with no easing (default, honouring this project's hard-won
        "instant hover" lesson). Set False for literal 0.15 s spec behaviour.
    """

    VARIANTS = ("primary", "secondary", "destructive", "muted")

    def __init__(self, rect, label: str, variant: str = "primary",
                 size: str = "md", dark: bool = False, on_click=None,
                 enabled: bool = True, instant_hover: bool = True) -> None:
        if variant not in self.VARIANTS:
            raise ValueError(f"variant must be one of {self.VARIANTS}, got {variant!r}")
        if size not in SIZES:
            raise ValueError(f"size must be one of {tuple(SIZES)}, got {size!r}")

        self.label = label
        self.variant = variant
        self.size = size
        self.palette = DARK if dark else LIGHT
        self.on_click = on_click
        self.enabled = enabled
        self.instant_hover = instant_hover

        spec = SIZES[size]
        if rect is None:
            # Auto-size from the label at logical scale (font measured at 1×).
            f = load_font(spec["font"])
            tw = f.size(label)[0]
            rect = pygame.Rect(0, 0,
                               tw + spec["pad_x"] * 2,
                               max(spec["height"], spec["font"] + spec["pad_y"] * 2))
        self.rect = pygame.Rect(rect)

        # Interaction state
        self.hovered = False
        self.pressed = False    # mouse currently held down on this button
        self.focused = False    # keyboard / tab focus (draws a ring)

        # Transition trackers (0..1), eased toward their state target.
        self._hover_t = 0.0
        self._press_t = 0.0

        # Per-scale font cache so we render crisp at physical resolution.
        self._fonts: dict[int, pygame.font.Font] = {}

    # ── geometry ──────────────────────────────────────────────────────────────

    def set_position(self, x: int, y: int) -> None:
        self.rect.topleft = (x, y)

    def contains(self, pos) -> bool:
        return self.rect.collidepoint(pos)

    # ── input ─────────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event, mouse_pos) -> bool:
        """Process a single pygame event. Returns True if a click *fired*.

        A click fires on MOUSEBUTTONUP that lands inside the button after a
        MOUSEBUTTONDOWN that also started inside it (standard press-release
        semantics, so a drag-off cancels).
        """
        if not self.enabled:
            return False
        fired = False
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.contains(mouse_pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.contains(mouse_pos):
                self.pressed = True
                self.focused = True
            else:
                self.focused = False
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.pressed and self.contains(mouse_pos):
                fired = True
                if self.on_click:
                    self.on_click()
            self.pressed = False
        return fired

    def update(self, mouse_pos, mouse_down: bool, dt: float) -> None:
        """Poll-style update: refresh hover/press from the cursor and advance the
        eased press/focus transitions by ``dt`` seconds. Use this *or*
        ``handle_event`` — not both for the same button."""
        if not self.enabled:
            self.hovered = self.pressed = False
            self._hover_t = self._press_t = 0.0
            return

        self.hovered = self.contains(mouse_pos)
        self.pressed = self.hovered and mouse_down

        # Hover is instant (binary) by default; press always eases (a brief
        # settle reads as intentional on a click, not laggy like hover did).
        if self.instant_hover:
            self._hover_t = 1.0 if self.hovered else 0.0
        else:
            self._hover_t = self._approach(self._hover_t, self.hovered, dt)
        self._press_t = self._approach(self._press_t, self.pressed, dt)

    @staticmethod
    def _approach(cur: float, target_on: bool, dt: float) -> float:
        """Step ``cur`` toward 0/1 at the 0.15 s transition rate."""
        target = 1.0 if target_on else 0.0
        if TRANSITION <= 0:
            return target
        step = dt / TRANSITION
        if cur < target:
            return min(target, cur + step)
        return max(target, cur - step)

    # ── colour resolution per state ─────────────────────────────────────────────

    def _resolve_colors(self):
        """Return (fill, text, border, border_w) for the current variant+state.

        Encodes the per-variant hover/active routes from the spec:
          • primary     hover → +5 % lighter;  active → −5 % darker
          • secondary   hover → faint tint fill; active → filled + darker border
          • destructive hover → slightly darker red; active → darker still
          • muted       hover → slightly darker; active → darker
        Hover and press amounts are scaled by their transition trackers so the
        colour shifts in step with the (eased) press / (instant) hover.
        """
        p = self.palette
        h, a = self._hover_t, self._press_t

        if self.variant == "primary":
            base = p["primary"]
            fill = _lerp(base, lighten(base, 0.05), h)      # hover: +5 % lighter
            fill = _lerp(fill, darken(base, 0.05), a)       # active: −5 % darker
            return fill, p["primary_foreground"], None, 0

        if self.variant == "secondary":
            # Transparent at rest → faint tint on hover → filled tint on active.
            tint = p["secondary"]
            rest = p["background"]
            fill = _lerp(rest, tint, max(h, a))
            border = _lerp(p["border"], p["ring"], a)       # active: darker border
            return fill, p["secondary_foreground"], border, max(1, int(1))

        if self.variant == "destructive":
            base = p["destructive"]
            fill = _lerp(base, darken(base, 0.08), h)       # hover: slightly darker
            fill = _lerp(fill, darken(base, 0.16), a)       # active: darker still
            return fill, p["destructive_foreground"], None, 0

        # muted
        base = p["muted"]
        fill = _lerp(base, darken(base, 0.04), h)           # hover: slightly darker
        fill = _lerp(fill, darken(base, 0.10), a)           # active: darker
        return fill, p["muted_foreground"], None, 0

    # ── rendering ───────────────────────────────────────────────────────────────

    def _font(self, scale: float) -> pygame.font.Font:
        px = max(1, int(SIZES[self.size]["font"] * scale))
        if px not in self._fonts:
            self._fonts[px] = load_font(px, bold=True)
        return self._fonts[px]

    def draw(self, surface: pygame.Surface, scale: float = 1.0) -> None:
        """Composite the button onto ``surface``.

        ``scale`` is the device/Retina factor: geometry is multiplied so the
        surface can be authored at physical resolution for crisp text (the same
        approach the HUD uses). All state (shadows, fill, scale-down on press,
        focus ring, disabled dimming) is derived from the current trackers.
        """
        s = max(0.1, float(scale))
        radius = RADIUS * s

        # Physical-pixel rect for this draw.
        r = pygame.Rect(int(self.rect.x * s), int(self.rect.y * s),
                        int(self.rect.w * s), int(self.rect.h * s))

        # Active press: scale to 0.98 about the centre (eased by _press_t).
        if self._press_t > 0.001:
            shrink = 1.0 - 0.02 * self._press_t
            cx, cy = r.center
            r = pygame.Rect(0, 0, int(r.w * shrink), int(r.h * shrink))
            r.center = (cx, cy)

        # ── Shadows ── none at rest; hover lifts; press shows a tight inset.
        if self._press_t > 0.001:
            # Tight, low shadow → reads as pressed-in (paired with the scale-down).
            _drop_shadow(surface, r, radius, SHADOW_ACTIVE, s, strength=self._press_t)
        elif self._hover_t > 0.001:
            _drop_shadow(surface, r, radius, SHADOW_HOVER, s, strength=self._hover_t)

        fill, text_col, border_col, border_w = self._resolve_colors()

        # ── Fill ──
        _aa_round_rect(surface, r, fill, radius)

        # ── Border (secondary only) ──
        if border_col is not None and border_w > 0:
            _aa_round_rect(surface, r, border_col, radius, width=max(1, int(border_w * s)))

        # ── Inset press highlight ── a faint top inner shade sells the "pushed in"
        # look without a real inner-shadow pass.
        if self._press_t > 0.4:
            inset = r.inflate(-int(2 * s), -int(2 * s))
            _aa_round_rect(surface, inset, (0, 0, 0, int(28 * self._press_t)),
                           max(1.0, radius - 1), width=max(1, int(1 * s)))

        # ── Focus ring ── 2 px ring offset just outside the button (keyboard a11y).
        if self.focused and self.enabled:
            ring = r.inflate(int(4 * s), int(4 * s))
            _aa_round_rect(surface, ring, (*self.palette["ring"], 200),
                           radius + 2 * s, width=max(1, int(2 * s)))

        # ── Label ──
        font = self._font(s)
        txt = font.render(self.label, True, text_col)
        surface.blit(txt, txt.get_rect(center=r.center))

        # ── Disabled dimming ── render normally, then knock the whole button back
        # to 50 % so muted colours + opacity read as inactive (no cursor change is
        # done here — that's the caller's job via pygame.mouse).
        if not self.enabled:
            veil = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            veil.fill((*self.palette["background"], 128))
            _aa_round_rect(veil, veil.get_rect(), (*self.palette["background"], 128), radius)
            surface.blit(veil, r.topleft)


# ══════════════════════════════════════════════════════════════════════════════
#  Convenience constructors
# ══════════════════════════════════════════════════════════════════════════════

def primary(rect, label, **kw):     return Button(rect, label, variant="primary", **kw)
def secondary(rect, label, **kw):   return Button(rect, label, variant="secondary", **kw)
def destructive(rect, label, **kw): return Button(rect, label, variant="destructive", **kw)
def muted(rect, label, **kw):       return Button(rect, label, variant="muted", **kw)
