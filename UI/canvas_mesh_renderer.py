"""
UI/canvas_mesh_renderer.py

Pre-renders placeable-object meshes from a 30° oblique perspective that
exactly matches the World Builder canvas projection, caches the result as a
transparent pygame.Surface, and exposes a single entry point:

    sprite = render_object(model, col, hs, u)
    layer.blit(sprite, sprite.get_rect(center=P(cgx, cgy, cgz)))

First call for a given (model, colour, half-size, cell-px-size) renders once;
every subsequent call returns the cached Surface — zero per-frame polygon work.

Only this module renders. Nothing outside it is touched.
"""

import math
import pygame

try:
    import pygame.gfxdraw as _gfx
    _HAS_GFX = True
except ImportError:
    _HAS_GFX = False

# ── Oblique constants — must stay in sync with _draw_builder_canvas ──────────
_ANG = math.radians(30.0)
_CA  = math.cos(_ANG)   # cos 30°  ≈ 0.866
_SA  = math.sin(_ANG)   # sin 30°  = 0.500
_DR  = 0.55             # depth foreshortening (cabinet projection)

# ── Sprite cache — keyed by (model, r, g, b, hs×20 int, u int) ───────────────
_CACHE: dict = {}


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _P(x: float, y: float, z: float, u: float, ox: float, oy: float) -> tuple[int, int]:
    """30° oblique projection matching the canvas P() exactly."""
    v = _DR * u
    return (int(ox + x * u - z * v * _CA),
            int(oy - y * u + z * v * _SA))


def _shade(col: tuple, frac: float) -> tuple[int, int, int, int]:
    return (min(255, int(col[0] * frac)),
            min(255, int(col[1] * frac)),
            min(255, int(col[2] * frac)), 255)


def _poly(surf: pygame.Surface, pts, fill: tuple, edge: tuple) -> None:
    """Fill a polygon then draw an antialiased outline on top."""
    if _HAS_GFX:
        _gfx.filled_polygon(surf, pts, fill)
        _gfx.aapolygon(surf, pts, edge)
    else:
        pygame.draw.polygon(surf, fill[:3], pts)
        pygame.draw.aalines(surf, edge[:3], True, pts)


# ── Per-primitive renderers ───────────────────────────────────────────────────

def _render_cube(col: tuple, hs: float, u: float) -> pygame.Surface:
    """Three visible faces — top (68%), right side (50%), front (100%)."""
    v   = _DR * u
    pad = 6
    w   = int(math.ceil(2 * hs * (u + v * _CA))) + pad * 2
    h   = int(math.ceil(2 * hs * (u + v * _SA))) + pad * 2
    # P(0,0,0) → sprite centre (ox, oy).  The oblique spread is symmetric
    # around the cube's logical centre, so no extra offset needed.
    ox, oy = w / 2.0, h / 2.0
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    def P(x, y, z): return _P(x, y, z, u, ox, oy)

    edge = _shade(col, 0.28)
    # Painter's order: top → right → front (nearest viewer, drawn last).
    _poly(surf,
          [P(-hs,+hs,+hs), P(+hs,+hs,+hs), P(+hs,+hs,-hs), P(-hs,+hs,-hs)],
          _shade(col, 0.68), edge)
    _poly(surf,
          [P(+hs,-hs,+hs), P(+hs,+hs,+hs), P(+hs,+hs,-hs), P(+hs,-hs,-hs)],
          _shade(col, 0.50), edge)
    _poly(surf,
          [P(-hs,-hs,-hs), P(+hs,-hs,-hs), P(+hs,+hs,-hs), P(-hs,+hs,-hs)],
          _shade(col, 1.00), edge)
    return surf


def _render_sphere(col: tuple, hs: float, u: float) -> pygame.Surface:
    """Filled circle + specular highlight + rim darkening."""
    rad = max(4, int(hs * u * 1.15))
    pad = max(4, int(rad * 0.45))
    sz  = rad * 2 + pad * 2
    cx, cy = sz // 2, sz // 2
    surf = pygame.Surface((sz, sz), pygame.SRCALPHA)

    # Base fill
    if _HAS_GFX:
        _gfx.filled_circle(surf, cx, cy, rad, (*col, 255))
        _gfx.aacircle(surf, cx, cy, rad, (*col, 255))
    else:
        pygame.draw.circle(surf, col, (cx, cy), rad)

    # Specular highlight — top-left bright spot
    hi  = tuple(min(255, int(c + (255 - c) * 0.60)) for c in col)
    hx  = int(cx - rad * 0.27)
    hy  = int(cy - rad * 0.29)
    hr  = max(2, int(rad * 0.30))
    if _HAS_GFX:
        _gfx.filled_circle(surf, hx, hy, hr, (*hi, 255))
        _gfx.aacircle(surf, hx, hy, hr, (*hi, 255))
    else:
        pygame.draw.circle(surf, hi, (hx, hy), hr)

    # Rim darkening (depth cue)
    rim = tuple(max(0, int(c * 0.42)) for c in col)
    pygame.draw.circle(surf, rim, (cx, cy), rad, max(1, int(rad * 0.10)))

    return surf


def _render_cylinder(col: tuple, hs: float, u: float) -> pygame.Surface:
    """Front body quad + right body quad + top ellipse cap."""
    v   = _DR * u
    rw  = hs * 0.82   # "radius" in x — narrowed to hint at curvature
    pad = 6
    w   = int(math.ceil(2 * rw * u + hs * v * _CA)) + pad * 2
    h   = int(math.ceil(2 * hs * u + hs * v * _SA)) + pad * 2
    ox, oy = w / 2.0, h / 2.0
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    def P(x, y, z): return _P(x, y, z, u, ox, oy)

    edge = _shade(col, 0.28)
    # Right body face (darker, drawn first)
    _poly(surf,
          [P(+rw,-hs,-hs), P(+rw,-hs,+hs), P(+rw,+hs,+hs), P(+rw,+hs,-hs)],
          _shade(col, 0.50), edge)
    # Front body face
    _poly(surf,
          [P(-rw,-hs,-hs), P(+rw,-hs,-hs), P(+rw,+hs,-hs), P(-rw,+hs,-hs)],
          _shade(col, 0.85), edge)

    # Top cap — ellipse centred on P(0, +hs, 0)
    tx, ty = P(0, +hs, 0)
    era = max(3, int(hs * u * 0.85))
    erb = max(2, int(era * 0.34))
    cap = _shade(col, 0.76)
    if _HAS_GFX:
        _gfx.filled_ellipse(surf, int(tx), int(ty), era, erb, cap)
        _gfx.aaellipse(surf, int(tx), int(ty), era, erb, _shade(col, 0.28))
    else:
        cap_r = pygame.Rect(tx - era, ty - erb, era * 2, erb * 2)
        pygame.draw.ellipse(surf, cap[:3], cap_r)

    return surf


# ── Public entry point ────────────────────────────────────────────────────────

def render_object(model: str, col: tuple, hs: float, u: float) -> pygame.Surface:
    """Return a cached pre-rendered sprite for `model`.

    Parameters
    ----------
    model : 'builtin:cube' | 'builtin:sphere' | 'builtin:cylinder'
    col   : (r, g, b) int tuple 0-255
    hs    : half-size in grid cells
    u     : cell size in pixels (from the canvas layout)

    The sprite's logical centre (pixel where P(0,0,0) lands) sits at the
    sprite's midpoint, so ``layer.blit(sprite, sprite.get_rect(center=P(cx,cy,cz)))``
    places it correctly in the oblique canvas.
    """
    key = (model, col[0], col[1], col[2], round(hs * 20), round(u))
    if key in _CACHE:
        return _CACHE[key]
    if model == "builtin:cube":
        surf = _render_cube(col, hs, u)
    elif model == "builtin:cylinder":
        surf = _render_cylinder(col, hs, u)
    else:
        surf = _render_sphere(col, hs, u)
    _CACHE[key] = surf
    return surf


def clear_cache() -> None:
    """Evict all cached sprites — call on window resize."""
    _CACHE.clear()
