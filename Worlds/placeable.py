"""
placeable.py — Pure (GL-free) coordinate transform + validation for World Builder
placeable objects in the Grid Room.

This module is the safety + math layer for user-customizable objects placed inside
the grid world (see obsidian-docs/architecture/grid-creator-tool-plan.md). It is
deliberately free of OpenGL and of the frozen camera/physics code, so:

  • the headless validation sim (Scripts/validation/sim_grid_api.py) can import and
    assert it with no GPU / no GL context, exactly like the other sims, and
  • a creator (or Claude) can never break the box or the engine: every object is
    allowlisted, clamped, and the whole set is count-capped before it ever reaches
    a draw call.

The renderer (Engine/renderer.PlaceableObjects) imports `grid_to_world` and
`sanitize_objects` from here and only does GL state + mesh draws on top.

Coordinate convention (integer grid cells; see §3 of the plan):
  gx ∈ [-D/2 .. +D/2]   left → right    (0 = centre, ±D/2 = side walls = ±hw)
  gy ∈ [-D/2 .. +D/2]   down → up       (0 = centre, ±D/2 = floor/ceiling = ±hh)
  gz ∈ [0 .. D]         glass → back     (0 = on the glass, D = back wall = -depth)
"""

from __future__ import annotations

# Public v1 allowlist — built-in primitives only. Unknown models are skipped (never
# crash), mirroring the lazy-load fallbacks in app_engine.py.
BUILTIN_PRIMITIVES = ("builtin:cube", "builtin:sphere", "builtin:cylinder")

# Caps that protect the 30 fps wallpaper budget on the 8 GB M2 target and keep any
# single object from escaping a few cells. Tuned conservatively; revisit in /verify.
MAX_OBJECTS = 64
SCALE_MIN   = 1e-3
SCALE_MAX   = 2.0


def _clampf(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def grid_to_world(gx: float, gy: float, gz: float,
                   hw: float, hh: float, depth: float, divisions: int):
    """Map an integer grid cell to live world coordinates.

    Uses the LIVE aperture half-extents `hw`/`hh` (om.window_half_extents) — never
    the old hardcoded [-4,4] bounds — so a cell at ±D/2 lands exactly on the
    rendered side walls regardless of monitor aspect / metric calibration.
    """
    D = max(1, int(divisions))
    half = D / 2.0
    wx = (gx / half) * hw
    wy = (gy / half) * hh
    wz = -(gz / D) * depth
    return (wx, wy, wz)


def grid_to_canvas_cell(gx: float, gy: float, gz: float, divisions: int):
    """Map a centred placeable cell to the World Builder oblique canvas's cell space.

    This is the SECOND half of the single source of truth (the first is
    `grid_to_world`, used by the 3-D parallax renderer). The 2-D oblique grid in the
    HUD must place an object on the same square the 3-D world places it, so both
    renderers derive every object position from THIS module — never from ad-hoc
    inline math that can silently drift (the historical grid↔parallax disconnect).

    Two convention shifts happen here, and ONLY here:

      • Origin: the engine/Claude convention is CENTRED (gx,gy ∈ [-D/2 .. +D/2],
        0 = centre); the oblique canvas addresses a CORNER-origin cube
        (0 .. D on each axis). So gx,gy are shifted by +D/2.

      • Depth: the engine runs gz=0 at the GLASS (nearest the viewer) → gz=D at the
        BACK wall (see `grid_to_world`: wz = -(gz/D)*depth, glass at z=0). The
        oblique canvas draws its bright, undistorted face as the BACK wall (canvas
        z=0) and opens toward the viewer to the glass (canvas z=D). To keep the two
        views consistent, depth is FLIPPED: cgz = D - gz. An object the parallax
        renders at the glass (gz=0) is drawn at the canvas front opening (cgz=D);
        one at the back wall (gz=D) lands on the bright back grid (cgz=0).

    Returns corner-origin canvas cell coords (cgx, cgy, cgz), each in [0, D], ready
    to feed the canvas's oblique projection P().
    """
    D = max(1, int(divisions))
    return (gx + D / 2.0,        # left/right : centred → corner origin
            gy + D / 2.0,        # down/up    : centred → corner origin
            D - gz)             # depth      : glass(gz 0)→front(cgz D), back(gz D)→back grid(cgz 0)


def sanitize_objects(raw, divisions: int) -> list[dict]:
    """Return a list of validated, clamped object dicts; skip malformed ones.

    Pure and total: any junk (wrong types, missing keys, out-of-range numbers,
    unknown model, overflow count) is handled by skipping or clamping — never by
    raising. Reliability is the product (plan §1.3), so a single bad object must
    not take down the scene.

    Each returned dict is normalized to:
        {id, model, grid_position:(gx,gy,gz), scale, color:(r,g,b),
         emissive:bool, rotation:(rx,ry,rz)}
    with grid_position clamped to the box and scale/color clamped to valid ranges.
    """
    out: list[dict] = []
    if not isinstance(raw, list):
        return out

    D = max(1, int(divisions))
    half = D / 2.0

    for obj in raw:
        if len(out) >= MAX_OBJECTS:
            break                                   # count cap — protect the frame budget
        if not isinstance(obj, dict):
            continue

        model = obj.get("model")
        if model not in BUILTIN_PRIMITIVES:
            continue                                # allowlist: unknown → skip

        pos = obj.get("grid_position", [0, 0, 0])
        try:
            gx, gy, gz = float(pos[0]), float(pos[1]), float(pos[2])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        gx = _clampf(gx, -half, half)
        gy = _clampf(gy, -half, half)
        gz = _clampf(gz, 0.0, float(D))

        try:
            scale = _clampf(float(obj.get("scale", 1.0)), SCALE_MIN, SCALE_MAX)
        except (TypeError, ValueError):
            scale = 1.0

        col = obj.get("color", [1.0, 1.0, 1.0])
        try:
            r = _clampf(float(col[0]), 0.0, 1.0)
            g = _clampf(float(col[1]), 0.0, 1.0)
            b = _clampf(float(col[2]), 0.0, 1.0)
        except (TypeError, ValueError, IndexError, KeyError):
            r = g = b = 1.0

        rot = obj.get("rotation", [0.0, 0.0, 0.0])
        try:
            rx, ry, rz = float(rot[0]), float(rot[1]), float(rot[2])
        except (TypeError, ValueError, IndexError, KeyError):
            rx = ry = rz = 0.0

        out.append({
            "id": obj.get("id"),
            "model": model,
            "grid_position": (gx, gy, gz),
            "scale": scale,
            "color": (r, g, b),
            "emissive": bool(obj.get("emissive", True)),
            "rotation": (rx, ry, rz),
        })

    return out
