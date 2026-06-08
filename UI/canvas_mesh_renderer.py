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

# Oblique projection + face tables live in ONE place (Worlds.oblique) so the sprite
# renderer, the Canvas Cube stage, and the parity sim can never disagree about the
# map or about which face is the front. Robust import whether the repo root or UI/
# is the import root (mirrors world_builder_api / demo_overlay's fallback).
try:
    from Worlds.oblique import (
        project as _project, CA as _CA, SA as _SA, DR as _DR,
        CUBE_FACES as _CUBE_FACES,
    )
except ImportError:                                       # pragma: no cover
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    from Worlds.oblique import (
        project as _project, CA as _CA, SA as _SA, DR as _DR,
        CUBE_FACES as _CUBE_FACES,
    )

# ── Sprite cache — keyed by (model, r, g, b, hs×20 int, u int) ───────────────
_CACHE: dict = {}


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _P(x: float, y: float, z: float, u: float, ox: float, oy: float) -> tuple[int, int]:
    """Oblique projection — delegates to the shared Worlds.oblique.project so the
    sprite, the Canvas Cube, and the parity sim are the pixel-for-pixel same map."""
    sx, sy = _project(x, y, z, u, ox, oy)
    return (int(sx), int(sy))


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
    """Three visible faces, drawn back-to-front straight from Worlds.oblique.CUBE_FACES.

    The face set, their depth order, and their normals are defined ONCE in
    Worlds.oblique and pinned by sim_wb_preview_parity (front face = +Z, toward the
    glass — the same face the parallax camera sees). So the cube can never silently
    render inside-out again (the historical bug drew the −Z face as 'front')."""
    pad = 6
    # Size the sprite from all 8 projected corners; centre (0,0,0) inside it.
    pts8 = [_P(sx * hs, sy * hs, sz * hs, u, 0.0, 0.0)
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    xs = [p[0] for p in pts8]
    ys = [p[1] for p in pts8]
    w = (max(xs) - min(xs)) + pad * 2
    h = (max(ys) - min(ys)) + pad * 2
    ox, oy = pad - min(xs), pad - min(ys)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    edge = _shade(col, 0.28)
    for f in _CUBE_FACES:                              # listed back-to-front (front last)
        pts = [_P(cx * hs, cy * hs, cz * hs, u, ox, oy) for (cx, cy, cz) in f["corners"]]
        _poly(surf, pts, _shade(col, f["bright"]), edge)
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
    """Right body quad (+X) + front body quad (+Z, toward the viewer) + top ellipse cap.

    Same oblique map and the same Worlds.oblique.CYLINDER_FACES contract the parity
    sim checks: the front body is the +Z face (toward the glass), never −Z."""
    rw  = hs * 0.82   # "radius" in x — narrowed to hint at curvature
    pad = 6
    era = max(3, int(hs * u * 0.85))                   # top-cap ellipse semi-axes
    erb = max(2, int(era * 0.34))
    # Size the sprite from the body corners plus the cap's screen extent.
    pts8 = [_P(sx * rw, sy * hs, sz * hs, u, 0.0, 0.0)
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    capc = _P(0, +hs, 0, u, 0.0, 0.0)
    xs = [p[0] for p in pts8] + [capc[0] - era, capc[0] + era]
    ys = [p[1] for p in pts8] + [capc[1] - erb, capc[1] + erb]
    w = (max(xs) - min(xs)) + pad * 2
    h = (max(ys) - min(ys)) + pad * 2
    ox, oy = pad - min(xs), pad - min(ys)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    def P(x, y, z): return _P(x, y, z, u, ox, oy)

    edge = _shade(col, 0.28)
    # Right body face (+X, darker) — drawn first.
    _poly(surf,
          [P(+rw,-hs,+hs), P(+rw,-hs,-hs), P(+rw,+hs,-hs), P(+rw,+hs,+hs)],
          _shade(col, 0.50), edge)
    # Front body face (+Z, toward the viewer) — drawn after the side, never behind it.
    _poly(surf,
          [P(-rw,-hs,+hs), P(+rw,-hs,+hs), P(+rw,+hs,+hs), P(-rw,+hs,+hs)],
          _shade(col, 0.85), edge)

    # Top cap (+Y) — ellipse centred on P(0, +hs, 0)
    tx, ty = P(0, +hs, 0)
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
