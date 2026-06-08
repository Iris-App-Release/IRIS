"""
oblique.py — single source of truth for the World Builder's 30° oblique (cabinet)
projection and the placeable-primitive face geometry.

Pure / GL-free, exactly like Worlds.placeable. THREE consumers import from here and
must NOT re-derive any of it inline — the historical grid↔parallax disconnect came
from two copies of the same math drifting apart, and the inside-out cube came from
hand-rolled face corners with a flipped depth sign:

  • UI.demo_overlay._draw_builder_canvas — draws the Canvas Cube stage.
  • UI.canvas_mesh_renderer            — pre-renders the object sprites (table-driven).
  • Scripts/validation/sim_wb_preview_parity.py — proves the oblique preview and the
    live 3-D parallax preview agree (ordinal parity + the front-face invariant).

WHY "EQUAL" IS ORDINAL, NOT METRIC
----------------------------------
The Canvas Cube is a PARALLEL (cabinet) projection — a deliberately undistorted
technical drawing where squares stay square. The live preview is a PERSPECTIVE
off-axis frustum (Engine.camera_math). The two can NEVER be pixel-identical. "The
two previews are accurate and equal" therefore means they agree on every ORDINAL
spatial fact — left/right, up/down, near/far ordering — and on WHICH FACE of each
primitive points at the viewer. That ordinal contract is what this module and the
parity sim pin.

CONVENTION (matches Worlds.placeable canvas-cell space)
-------------------------------------------------------
  +x → right, +y → up, +z → TOWARD the viewer (the glass).
Under project(): +x → screen-right, +y → screen-up (smaller pixel-y, pygame is
y-down), +z → screen DOWN-LEFT (the receding depth axis). So the face an object
shows the viewer is its +z face — the same face the parallax camera (sitting on
+Z, looking toward −Z) sees frontally. The inside-out bug drew the −z face as
"front"; the front-face invariant below is the guard against it ever returning.
"""

from __future__ import annotations

import math

# ── Oblique constants (THE definition — every consumer imports these) ────────────
ANG = math.radians(30.0)      # oblique receding angle
CA  = math.cos(ANG)           # cos 30° ≈ 0.86603
SA  = math.sin(ANG)           # sin 30° = 0.5
DR  = 0.55                    # depth foreshortening (cabinet-ish)


def project(x: float, y: float, z: float, u: float,
            ox: float = 0.0, oy: float = 0.0) -> tuple[float, float]:
    """Oblique (cabinet) projection: object/cell space → screen pixels (floats).

    `u` is the cell size in pixels; (ox, oy) is where (0,0,0) lands. Screen y is
    DOWN-positive (pygame), so +y in the world maps to a SMALLER pixel-y. This is
    the ONE definition of P() — the canvas stage and the sprite renderer both call
    it, so they cannot disagree about where a cell or a vertex lands.
    """
    v = DR * u
    return (ox + x * u - z * v * CA,
            oy - y * u + z * v * SA)


def projector() -> tuple[float, float, float]:
    """The 3-D 'toward-viewer' direction of this oblique projection.

    The vector p such that a face with outward normal n is front-facing iff n·p > 0.
    Derived by solving project()'s 2×3 screen map for the depth direction that
    produces zero screen motion: p = (DR·cos30, DR·sin30, 1).
    """
    return (DR * CA, DR * SA, 1.0)


def toward_viewer_score(normal) -> float:
    """n·p — how strongly a face faces the viewer (>0 visible, larger = more frontal)."""
    px, py, pz = projector()
    return normal[0] * px + normal[1] * py + normal[2] * pz


def face_visible(normal, eps: float = 1e-9) -> bool:
    """True iff a face with this outward normal is front-facing in the oblique view."""
    return toward_viewer_score(normal) > eps


def view_depth(x: float, y: float, z: float) -> float:
    """Depth of a POINT along the oblique view direction (canvas-cell space).

    Larger = nearer the oblique viewer. The Canvas Cube MUST paint objects in
    ASCENDING view_depth (farthest first) so a nearer opaque sprite overdraws the
    ones hidden behind it — correct occlusion for the 30° view, whose viewpoint is
    front-RIGHT-ABOVE, not straight-on. Sorting by cgz alone is wrong: it ignores
    the +x/+y of the view direction, so a dot on the hidden (left/−x, or back) side
    of a sphere would wrongly paint on top of it. p is the same projector() the
    front-face logic uses — one consistent notion of 'toward the viewer'.
    """
    px, py, pz = projector()
    return x * px + y * py + z * pz


# ── Primitive face tables (the renderer draws ONLY from these) ───────────────────
# Each face: outward `normal`, paint `bright` (× base colour), and `corners` in
# half-extent units (±1). Tables are listed BACK-TO-FRONT — the last entry is the
# nearest face, painted last / brightest. The parity sim asserts, from these tables
# alone:
#   • every listed face is front-facing (face_visible) — no hidden face is drawn;
#   • the listed normals == the full set of front-facing axis faces (no missing/extra);
#   • the +Z face (toward the glass) is present, visible, and the strict max-score
#     face — i.e. the same face the parallax camera sees frontally. THIS is the
#     inside-out guard: the historical bug put the −Z face here and the box rendered
#     inside-out. Anyone reintroducing it has to break this table, which fails the sim.

# The principal viewer-facing normal (must be the +Z / toward-glass face).
FRONT_NORMAL = (0.0, 0.0, 1.0)

CUBE_FACES = [
    {"name": "top",   "normal": (0.0, 1.0, 0.0), "bright": 0.68,
     "corners": [(-1, 1, 1), (1, 1, 1), (1, 1, -1), (-1, 1, -1)]},
    {"name": "right", "normal": (1.0, 0.0, 0.0), "bright": 0.50,
     "corners": [(1, -1, 1), (1, 1, 1), (1, 1, -1), (1, -1, -1)]},
    {"name": "front", "normal": (0.0, 0.0, 1.0), "bright": 1.00,
     "corners": [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]},
]

# Cylinder is approximated by two body quads + a top elliptical cap (the renderer
# draws the cap specially). Only normals + paint brightness are pinned here; the
# parity sim runs the SAME visible-set + front-face invariant over these normals.
CYLINDER_FACES = [
    {"name": "right_body", "normal": (1.0, 0.0, 0.0), "bright": 0.50},
    {"name": "front_body", "normal": (0.0, 0.0, 1.0), "bright": 0.85},
    {"name": "top_cap",    "normal": (0.0, 1.0, 0.0), "bright": 0.76},
]

# The six axis-aligned face normals — the parity sim uses these to compute the full
# "should be visible" set and compare it against each table (no missing/extra faces).
AXIS_NORMALS = [
    (1.0, 0.0, 0.0), (-1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0), (0.0, -1.0, 0.0),
    (0.0, 0.0, 1.0), (0.0, 0.0, -1.0),
]


def visible_axis_normals() -> list[tuple]:
    """The axis faces that are front-facing under this oblique (the 'should draw' set)."""
    return [n for n in AXIS_NORMALS if face_visible(n)]
