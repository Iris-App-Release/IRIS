"""
renderer.py — Shader-based scene renderer for Parallax Wall.

Classes:
  Earth     – textured day/night sphere + cloud shell + atmospheric scattering
  Gem       – brilliant-cut faceted crystal with fresnel + emissive core
  Stars     – multi-layer parallax point-sprite starfield
  Nebula    – inside-rendered milky-way background sphere

Each class owns its mesh, textures, and shader program. The host code
calls .draw(...) with sun/fill light directions (in eye space) and per-object
animation state — the renderer manages all GL state changes internally.
"""

import ctypes
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from OpenGL.GL import *

# Byte-offset sentinel for attribute pointers when a VBO is bound (the pointer
# argument is then interpreted as an offset into the bound buffer, not a client
# address). All our static buffers are tightly packed from offset 0.
_VBO_OFFSET0 = ctypes.c_void_p(0)

from Engine import camera_math as om
from Engine.shader_loader import (
    load_program, load_texture_2d, bind_texture_unit, Uniforms,
)
from Worlds.placeable import grid_to_world, sanitize_objects

HERE        = Path(__file__).parent.parent  # project root
ASSETS      = HERE / "assets"
SHADERS_DIR = HERE / "shaders"


# ══════════════════════════════════════════════════════════════════════════════
#  Geometry primitives
# ══════════════════════════════════════════════════════════════════════════════

def make_sphere(radius: float = 1.0, slices: int = 96, stacks: int = 96):
    """
    UV-sphere mesh.  Returns (vertices, normals, uvs, indices) as float32/uint32
    arrays.  UVs run 0–1 longitude (wraps) × 0–1 latitude (pole-clamped).
    """
    verts, norms, uvs = [], [], []
    for i in range(stacks + 1):
        phi = math.pi * i / stacks
        v   = i / stacks
        for j in range(slices + 1):
            theta = 2.0 * math.pi * j / slices
            u = j / slices
            x = math.sin(phi) * math.cos(theta)
            y = math.cos(phi)
            z = math.sin(phi) * math.sin(theta)
            verts.append((x * radius, y * radius, z * radius))
            norms.append((x, y, z))
            uvs.append((u, v))

    idx = []
    row = slices + 1
    for i in range(stacks):
        for j in range(slices):
            a = i * row + j
            b = a + row
            idx += [a, b, a + 1, b, b + 1, a + 1]

    return (
        np.array(verts, dtype=np.float32),
        np.array(norms, dtype=np.float32),
        np.array(uvs,   dtype=np.float32),
        np.array(idx,   dtype=np.uint32),
    )


def _face_normal(a, b, c):
    ab = np.array(b, dtype=np.float64) - np.array(a, dtype=np.float64)
    ac = np.array(c, dtype=np.float64) - np.array(a, dtype=np.float64)
    n  = np.cross(ab, ac)
    ln = np.linalg.norm(n)
    return (n / ln) if ln > 1e-9 else np.array([0.0, 1.0, 0.0])


def make_gem(n=16, r_girdle=2.2, table_ratio=0.48, h_crown=0.79, h_pav=2.80):
    """
    Brilliant-cut faceted gem geometry as a flat-shaded triangle soup.
    Returns (vertices, normals) — no indexing, each triangle has its own
    flat normal so adjacent facets get distinct specular highlights.
    """
    r_table = r_girdle * table_ratio
    ang     = [2.0 * math.pi * i / n for i in range(n)]
    girdle  = [(r_girdle * math.cos(a), 0.0,     r_girdle * math.sin(a)) for a in ang]
    table   = [(r_table  * math.cos(a), h_crown, r_table  * math.sin(a)) for a in ang]
    culet   = (0.0, -h_pav, 0.0)
    tc      = (0.0,  h_crown, 0.0)

    verts, norms = [], []
    def push(v_list, n_vec):
        for v in v_list:
            verts.append(v)
            norms.append(tuple(n_vec))

    for i in range(n):
        j = (i + 1) % n
        # Table
        nrm = _face_normal(tc, table[j], table[i])
        push([tc, table[j], table[i]], nrm)
        # Crown trapezoid (two triangles, shared normal)
        nrm = _face_normal(table[i], table[j], girdle[j])
        push([table[i], table[j], girdle[j]], nrm)
        push([table[i], girdle[j], girdle[i]], nrm)
        # Pavilion
        nrm = _face_normal(girdle[i], girdle[j], culet)
        push([girdle[i], girdle[j], culet], nrm)

    return (
        np.array(verts, dtype=np.float32),
        np.array(norms, dtype=np.float32),
    )


def make_cube(half: float = 0.5):
    """Axis-aligned unit cube centred at origin (edge length 2*half).

    24 vertices (4 per face) so each face carries its own flat normal — used by
    the World Builder `builtin:cube` primitive. Returns (vertices, normals, indices)
    as float32/float32/uint32; no UVs (objects are flat-coloured, not textured)."""
    faces = [
        ((0, 0, 1),  [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),   # +Z
        ((0, 0, -1), [(1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)]),  # -Z
        ((1, 0, 0),  [(1, -1, 1), (1, -1, -1), (1, 1, -1), (1, 1, 1)]),   # +X
        ((-1, 0, 0), [(-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)]),  # -X
        ((0, 1, 0),  [(-1, 1, 1), (1, 1, 1), (1, 1, -1), (-1, 1, -1)]),   # +Y
        ((0, -1, 0), [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)]),  # -Y
    ]
    verts, norms, idx = [], [], []
    for nrm, corners in faces:
        base = len(verts)
        for c in corners:
            verts.append((c[0] * half, c[1] * half, c[2] * half))
            norms.append(nrm)
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return (
        np.array(verts, dtype=np.float32),
        np.array(norms, dtype=np.float32),
        np.array(idx,   dtype=np.uint32),
    )


def make_cylinder(radius: float = 0.5, height: float = 1.0, segments: int = 24):
    """Capped cylinder, axis = Y, centred at origin (spans y ∈ [-h/2, +h/2]).

    Side quads carry radial normals; caps carry axial normals — used by the World
    Builder `builtin:cylinder` primitive. Returns (vertices, normals, indices)."""
    hy = height / 2.0
    verts, norms, idx = [], [], []

    # Side wall.
    for i in range(segments):
        a0 = 2.0 * math.pi * i / segments
        a1 = 2.0 * math.pi * (i + 1) / segments
        x0, z0 = math.cos(a0), math.sin(a0)
        x1, z1 = math.cos(a1), math.sin(a1)
        base = len(verts)
        verts += [(x0 * radius, -hy, z0 * radius), (x1 * radius, -hy, z1 * radius),
                  (x1 * radius,  hy, z1 * radius), (x0 * radius,  hy, z0 * radius)]
        norms += [(x0, 0.0, z0), (x1, 0.0, z1), (x1, 0.0, z1), (x0, 0.0, z0)]
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]

    # Top (+Y) and bottom (-Y) caps as triangle fans.
    for cy, ny, flip in ((hy, 1.0, False), (-hy, -1.0, True)):
        center = len(verts)
        verts.append((0.0, cy, 0.0)); norms.append((0.0, ny, 0.0))
        ring = len(verts)
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            verts.append((math.cos(a) * radius, cy, math.sin(a) * radius))
            norms.append((0.0, ny, 0.0))
        for i in range(segments):
            nxt = (i + 1) % segments
            idx += ([center, ring + nxt, ring + i] if flip
                    else [center, ring + i, ring + nxt])

    return (
        np.array(verts, dtype=np.float32),
        np.array(norms, dtype=np.float32),
        np.array(idx,   dtype=np.uint32),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Indexed mesh wrapper (uses client-side arrays — fine for our vertex counts)
# ══════════════════════════════════════════════════════════════════════════════

class Mesh:
    """Lightweight wrapper around per-attribute numpy arrays + element index.

    The geometry is STATIC (spheres, gem facets — built once, never animated on
    the CPU; all motion is via the modelview), so it is uploaded to GL buffer
    objects (VBOs/EBO) ONCE at construction and the GPU reuses it every frame.
    The previous client-side-array path re-copied every vertex from CPU to the
    driver on each draw — for the Earth's three 96×96 spheres + the 64×64 Nebula
    that was ~190 k vertices streamed per frame. If buffer creation is
    unavailable for any reason the class transparently falls back to the original
    client-array path (no behavioural change, just the old cost)."""

    def __init__(self, verts, norms, uvs=None, indices=None):
        self.verts = np.ascontiguousarray(verts, dtype=np.float32)
        self.norms = np.ascontiguousarray(norms, dtype=np.float32)
        self.uvs   = np.ascontiguousarray(uvs,   dtype=np.float32) if uvs is not None else None
        self.idx   = np.ascontiguousarray(indices, dtype=np.uint32) if indices is not None else None
        self.n_indices = len(self.idx) if self.idx is not None else len(self.verts)

        # Upload to GPU buffers once. _vbo_v is the "VBOs available" sentinel;
        # if it is None the draw path uses client arrays exactly as before.
        self._vbo_v = self._vbo_n = self._vbo_t = self._ebo = None
        try:
            self._vbo_v = int(glGenBuffers(1))
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_v)
            glBufferData(GL_ARRAY_BUFFER, self.verts.nbytes, self.verts, GL_STATIC_DRAW)
            self._vbo_n = int(glGenBuffers(1))
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_n)
            glBufferData(GL_ARRAY_BUFFER, self.norms.nbytes, self.norms, GL_STATIC_DRAW)
            if self.uvs is not None:
                self._vbo_t = int(glGenBuffers(1))
                glBindBuffer(GL_ARRAY_BUFFER, self._vbo_t)
                glBufferData(GL_ARRAY_BUFFER, self.uvs.nbytes, self.uvs, GL_STATIC_DRAW)
            if self.idx is not None:
                self._ebo = int(glGenBuffers(1))
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._ebo)
                glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.idx.nbytes, self.idx, GL_STATIC_DRAW)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
        except Exception as e:
            print(f"[renderer] VBO upload failed ({e}); using client arrays")
            self._vbo_v = self._vbo_n = self._vbo_t = self._ebo = None
            glBindBuffer(GL_ARRAY_BUFFER, 0)

    def draw(self):
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)

        if self._vbo_v is not None:
            # VBO path — bind each buffer and pass a byte offset (0). The index
            # buffer is bound for glDrawElements; everything is unbound again at
            # the end so the floor/shadow/icon/bloom client-array draws (which
            # share this GL state) keep working.
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_v)
            glVertexPointer(3, GL_FLOAT, 0, _VBO_OFFSET0)
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_n)
            glNormalPointer(   GL_FLOAT, 0, _VBO_OFFSET0)
            if self.uvs is not None:
                glClientActiveTexture(GL_TEXTURE0)
                glEnableClientState(GL_TEXTURE_COORD_ARRAY)
                glBindBuffer(GL_ARRAY_BUFFER, self._vbo_t)
                glTexCoordPointer(2, GL_FLOAT, 0, _VBO_OFFSET0)
            if self.idx is not None:
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._ebo)
                glDrawElements(GL_TRIANGLES, self.n_indices, GL_UNSIGNED_INT, _VBO_OFFSET0)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
            else:
                glDrawArrays(GL_TRIANGLES, 0, self.n_indices)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
        else:
            # Client-array fallback (original path).
            glVertexPointer(3, GL_FLOAT, 0, self.verts)
            glNormalPointer(   GL_FLOAT, 0, self.norms)
            if self.uvs is not None:
                glClientActiveTexture(GL_TEXTURE0)
                glEnableClientState(GL_TEXTURE_COORD_ARRAY)
                glTexCoordPointer(2, GL_FLOAT, 0, self.uvs)
            if self.idx is not None:
                glDrawElements(GL_TRIANGLES, self.n_indices, GL_UNSIGNED_INT, self.idx)
            else:
                glDrawArrays(GL_TRIANGLES, 0, self.n_indices)

        if self.uvs is not None:
            glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)
        glDisableClientState(GL_NORMAL_ARRAY)


# ══════════════════════════════════════════════════════════════════════════════
#  Earth (surface + clouds + atmosphere)
# ══════════════════════════════════════════════════════════════════════════════

class Earth:
    """
    Photo-real Earth: textured surface, independently rotating cloud shell,
    and atmospheric-scattering halo. All three drawn as concentric spheres.
    """

    R_SURFACE     = 2.6      # base radius
    R_CLOUDS      = 2.625    # slightly above surface — avoids z-fighting
    R_ATMOSPHERE  = 2.85     # extends out for the glow

    AXIAL_TILT_DEG = 23.5     # real Earth axial tilt

    def __init__(self):
        # Three concentric spheres
        v, n, u, i = make_sphere(self.R_SURFACE,    96, 96)
        self.surface = Mesh(v, n, u, i)
        v, n, u, i = make_sphere(self.R_CLOUDS,     96, 96)
        self.clouds = Mesh(v, n, u, i)
        v, n, u, i = make_sphere(self.R_ATMOSPHERE, 64, 64)
        self.atmo = Mesh(v, n, u, i)

        # Textures — flip_v=False because equirectangular maps store north-pole
        # at the top row; the sphere UV has v=0 at y=+1 (north), so the image
        # must NOT be flipped before upload or the globe is upside-down.
        self.tex_day      = load_texture_2d(ASSETS / "earth" / "earth_day.jpg",      flip_v=False)
        self.tex_night    = load_texture_2d(ASSETS / "earth" / "earth_night.jpg",    flip_v=False)
        self.tex_clouds   = load_texture_2d(ASSETS / "earth" / "earth_clouds.jpg",   flip_v=False)
        self.tex_specular = load_texture_2d(ASSETS / "earth" / "earth_specular.jpg", flip_v=False)

        # Shader programs
        self.prog_earth  = load_program("earth",      SHADERS_DIR)
        self.prog_clouds = load_program("clouds",     SHADERS_DIR)
        self.prog_atmo   = load_program("atmosphere", SHADERS_DIR)
        self.u_earth     = Uniforms(self.prog_earth)
        self.u_clouds    = Uniforms(self.prog_clouds)
        self.u_atmo      = Uniforms(self.prog_atmo)

        # Animation state
        self.surface_spin = 0.0     # degrees
        self.cloud_spin   = 0.0
        self.cloud_uv_off = 0.0

    def update(self, dt: float):
        # Earth rotates ~6°/sec (≈60 sec per full turn) — slow & cinematic
        self.surface_spin = (self.surface_spin + 6.0 * dt) % 360.0
        # Cloud sphere drifts a bit faster than the surface
        self.cloud_spin   = (self.cloud_spin   + 7.5 * dt) % 360.0
        # Slow UV scroll on the cloud texture itself for layered drift
        self.cloud_uv_off = (self.cloud_uv_off + 0.004 * dt) % 1.0

    def draw(self, sun_eye, time_s: float):
        # ── 1. Earth surface ──────────────────────────────────────────────────
        glPushMatrix()
        # Apply axial tilt then daily rotation
        glRotatef(self.AXIAL_TILT_DEG, 0.0, 0.0, 1.0)
        glRotatef(self.surface_spin,   0.0, 1.0, 0.0)

        glUseProgram(self.prog_earth)
        bind_texture_unit(0, self.tex_day)
        bind_texture_unit(1, self.tex_night)
        bind_texture_unit(2, self.tex_specular)
        self.u_earth.i("u_day",      0)
        self.u_earth.i("u_night",    1)
        self.u_earth.i("u_specular", 2)
        self.u_earth.v3("u_sun_eye", *sun_eye)

        glEnable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        self.surface.draw()
        glPopMatrix()

        # ── 2. Cloud shell ────────────────────────────────────────────────────
        glPushMatrix()
        glRotatef(self.AXIAL_TILT_DEG, 0.0, 0.0, 1.0)
        glRotatef(self.cloud_spin,     0.0, 1.0, 0.0)

        glUseProgram(self.prog_clouds)
        bind_texture_unit(0, self.tex_clouds)
        self.u_clouds.i("u_clouds",     0)
        self.u_clouds.v3("u_sun_eye",   *sun_eye)
        self.u_clouds.f("u_uv_offset",  self.cloud_uv_off)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        self.clouds.draw()
        glDepthMask(GL_TRUE)
        glPopMatrix()

        # ── 3. Atmospheric scattering halo ────────────────────────────────────
        glUseProgram(self.prog_atmo)
        self.u_atmo.v3("u_sun_eye",  *sun_eye)
        self.u_atmo.f("u_intensity", 1.0)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDepthMask(GL_FALSE)
        glEnable(GL_CULL_FACE)
        glCullFace(GL_FRONT)
        self.atmo.draw()
        glDisable(GL_CULL_FACE)
        glDepthMask(GL_TRUE)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_BLEND)
        glUseProgram(0)


# ══════════════════════════════════════════════════════════════════════════════
#  Crystal gem
# ══════════════════════════════════════════════════════════════════════════════

class Gem:
    """Brilliant-cut crystal driven by the gem shader."""

    _ROT_YAW_DEG_S = 22.0   # primary spin around Y-axis (degrees/s)
    _TILT_MAX_DEG  = 25.0   # peak tilt from vertical — oscillates ±this
    _TILT_SPEED    = 0.38   # oscillation rate (rad/s); period ≈ 16.5 s

    # Grounding shadow disk — drawn on the box floor, directly beneath the gem.
    _SHADOW_R     =  3.50
    _SHADOW_ALPHA =  0.28

    # Checkered enclosure box. The gem floats inside a 5-face room (floor, ceiling,
    # back wall, left/right walls) that shares the Grid Room's dimensions — the live
    # aperture half-extents plus grid_depth / grid_divisions. Each face is mapped so
    # that exactly ONE checker square lands on ONE grid cell (the checker IS the
    # grid): the 8×8 checker texture is laid down with UV span = divisions /
    # _BOX_TEX_CHECKS, giving `divisions` checks across the `divisions` cells of
    # every face regardless of its aspect. Drawn in WORLD space (front rim on the
    # glass at z = 0) like GridRoom, so the gem at the z = -10 anchor floats inside.
    _BOX_TEX_CHECKS = 8
    _GEM_ANCHOR_Z   = -10.0   # world z of the gem (matches OBJECTS["earth"])

    def __init__(self):
        v, n = make_gem()
        uvs = np.zeros((len(v), 2), dtype=np.float32)
        self.mesh = Mesh(v, n, uvs)
        self.prog = load_program("gem", SHADERS_DIR)
        self.u    = Uniforms(self.prog)
        self._spin_y     = 0.0
        self._tilt_phase = 0.0
        self._shadow_v, self._shadow_c = self._build_shadow()
        self._checker_tex = self._build_checker_texture(checks=self._BOX_TEX_CHECKS)
        # Enclosure box mesh — (re)built and cached when the aperture/grid changes.
        self._box_key = None
        self._box_v   = None
        self._box_uv  = None

    # ── Checkered enclosure box ─────────────────────────────────────────────────

    def _build_checker_texture(self, size: int = 512, checks: int = 8) -> int:
        """
        Procedurally generate a pink/white checkerboard GL texture.
        `checks` squares per axis; GL_REPEAT tiles it seamlessly across each
        box face.  Returns the texture ID.
        """
        px    = size // checks
        white = np.array([255, 255, 255], dtype=np.uint8)
        pink  = np.array([255, 182, 193], dtype=np.uint8)
        img   = np.zeros((size, size, 3), dtype=np.uint8)
        for row in range(checks):
            for col in range(checks):
                c = white if (row + col) % 2 == 0 else pink
                img[row*px:(row+1)*px, col*px:(col+1)*px] = c

        tid = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, tid)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, size, size, 0,
                     GL_RGB, GL_UNSIGNED_BYTE, img)
        glGenerateMipmap(GL_TEXTURE_2D)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glBindTexture(GL_TEXTURE_2D, 0)
        return tid

    def _build_box_mesh(self, half_w, half_h, depth, divisions):
        """
        Five interior faces (floor, ceiling, back wall, left/right walls) of the
        enclosure box, as textured quads in WORLD space — front rim on the glass
        at z = 0, back wall at z = -depth, floor/ceiling at y = ∓half_h, side walls
        at x = ±half_w.  Every face spans `divisions` grid cells per edge, so each
        face's UVs run 0..(divisions / _BOX_TEX_CHECKS): the 8×8 checker lays down
        exactly `divisions` checks across `divisions` cells → one check per grid
        cell, with checks stretched to match each face's (possibly non-square) cell.
        """
        s  = max(1, int(divisions)) / float(self._BOX_TEX_CHECKS)   # UV span per edge
        hw, hh, d = float(half_w), float(half_h), float(depth)
        verts, uvs = [], []

        def quad(p0, p1, p2, p3):
            # Two triangles; p0=uv(0,0), p1=uv(s,0), p2=uv(s,s), p3=uv(0,s).
            verts.extend([p0, p1, p2, p0, p2, p3])
            uvs.extend([(0.0, 0.0), (s, 0.0), (s, s),
                        (0.0, 0.0), (s, s), (0.0, s)])

        # Floor (y = -hh):  x ∈ [-hw, hw], z ∈ [0, -d]
        quad((-hw, -hh, 0.0), ( hw, -hh, 0.0), ( hw, -hh, -d), (-hw, -hh, -d))
        # Ceiling (y = +hh)
        quad((-hw,  hh, 0.0), ( hw,  hh, 0.0), ( hw,  hh, -d), (-hw,  hh, -d))
        # Back wall (z = -d):  x ∈ [-hw, hw], y ∈ [-hh, hh]
        quad((-hw, -hh, -d), ( hw, -hh, -d), ( hw,  hh, -d), (-hw,  hh, -d))
        # Left wall (x = -hw):  z ∈ [0, -d], y ∈ [-hh, hh]
        quad((-hw, -hh, 0.0), (-hw, -hh, -d), (-hw,  hh, -d), (-hw,  hh, 0.0))
        # Right wall (x = +hw)
        quad(( hw, -hh, 0.0), ( hw, -hh, -d), ( hw,  hh, -d), ( hw,  hh, 0.0))

        return (np.array(verts, dtype=np.float32),
                np.array(uvs,   dtype=np.float32))

    def draw_box(self, half_w, half_h, depth, divisions) -> None:
        """Draw the checkered enclosure box + grounding shadow in WORLD space.

        Called BEFORE the Earth-anchor translate (the box is an environment, like
        GridRoom), so the gem drawn afterwards floats inside it."""
        key = (round(half_w, 3), round(half_h, 3),
               round(depth, 3), int(divisions))
        if key != self._box_key:
            self._box_v, self._box_uv = self._build_box_mesh(
                half_w, half_h, depth, divisions)
            self._box_key = key

        # Faces: flat, unlit, textured checker (fixed-function). Cull off so the
        # interior faces are visible regardless of winding.
        glUseProgram(0)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        glDisable(GL_CULL_FACE)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self._checker_tex)
        glColor3f(1.0, 1.0, 1.0)   # no colour tint

        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_TEXTURE_COORD_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, self._box_v)
        glTexCoordPointer(2, GL_FLOAT, 0, self._box_uv)
        glDrawArrays(GL_TRIANGLES, 0, len(self._box_v))
        glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

        glDisable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, 0)

        # Soft grounding shadow on the checker floor, beneath the gem anchor.
        glPushMatrix()
        glTranslatef(0.0, -float(half_h) + 0.02, self._GEM_ANCHOR_Z)
        self._draw_shadow()
        glPopMatrix()

    # ── Shadow disk ───────────────────────────────────────────────────────────

    def _build_shadow(self, n_pts: int = 48):
        """Flat triangle-fan disk in the y = 0 plane with centre-to-edge alpha
        fade. Positioned onto the box floor by draw_box's translate."""
        verts  = [(0.0, 0.0, 0.0)]
        colors = [(0.0, 0.0, 0.0, self._SHADOW_ALPHA)]
        for i in range(n_pts + 1):
            a = 2.0 * math.pi * i / n_pts
            verts.append((self._SHADOW_R * math.cos(a),
                          0.0,
                          self._SHADOW_R * math.sin(a)))
            colors.append((0.0, 0.0, 0.0, 0.0))
        return (np.array(verts, dtype=np.float32),
                np.array(colors, dtype=np.float32))

    def _draw_shadow(self) -> None:
        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glUseProgram(0)

        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, self._shadow_v)
        glColorPointer(4, GL_FLOAT, 0, self._shadow_c)
        glDrawArrays(GL_TRIANGLE_FAN, 0, len(self._shadow_v))
        glDisableClientState(GL_COLOR_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

        glDepthMask(GL_TRUE)
        glEnable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)

    # ── Animation / draw ──────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        self._spin_y     = (self._spin_y + self._ROT_YAW_DEG_S * dt) % 360.0
        self._tilt_phase += self._TILT_SPEED * dt

    def draw(self, sun_eye, fill_eye, time_s: float):
        # Gem mesh only — the checkered enclosure box and the grounding shadow are
        # drawn by draw_box() in WORLD space, before the anchor translate.
        tilt = self._TILT_MAX_DEG * math.sin(self._tilt_phase)
        glPushMatrix()
        glRotatef(self._spin_y, 0.0, 1.0, 0.0)
        glRotatef(tilt,         1.0, 0.0, 0.0)

        glUseProgram(self.prog)
        self.u.v3("u_sun_eye",   *sun_eye)
        self.u.v3("u_fill_eye",  *fill_eye)
        self.u.f ("u_time",      time_s)

        glEnable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        self.mesh.draw()
        glUseProgram(0)
        glPopMatrix()


# ══════════════════════════════════════════════════════════════════════════════
#  Multi-layer parallax starfield (point sprites)
# ══════════════════════════════════════════════════════════════════════════════

class Stars:
    """
    Multi-layer parallax starfield using point sprites.  Stars are
    distributed across three depth shells; the rendering layer iterates
    them at decreasing distance so near stars overlap far stars.
    """

    def __init__(self, n_near=900, n_mid=1500, n_far=2200):
        random.seed(7)
        # Stellar-temperature tint table (visual only — positions are unchanged).
        # White still dominates, with subtle hot blue-white and cool warm classes
        # so the field reads as varied astrophysical temperatures.
        tints = {
            "w":  (1.00, 1.00, 1.00),   # white (Sun-like)
            "bw": (0.80, 0.88, 1.00),   # blue-white (hot)
            "b":  (0.62, 0.78, 1.00),   # cold blue
            "y":  (1.00, 0.92, 0.70),   # warm yellow-white
            "o":  (1.00, 0.80, 0.55),   # soft orange
            "r":  (1.00, 0.72, 0.62),   # warm red
        }
        layers = [
            ("near", n_near, 16.0, 26.0, 2.2, 7.5),
            ("mid",  n_mid,  32.0, 56.0, 1.1, 4.5),
            ("far",  n_far,  62.0, 90.0, 0.5, 1.7),
        ]
        all_v   = []
        all_c   = []
        all_s   = []
        all_t   = []
        for name, n, r_lo, r_hi, sz_lo, sz_hi in layers:
            for _ in range(n):
                theta = random.uniform(0.0, 2.0 * math.pi)
                phi   = math.acos(random.uniform(-1.0, 1.0))
                r     = random.uniform(r_lo, r_hi)
                x = r * math.sin(phi) * math.cos(theta)
                y = r * math.sin(phi) * math.sin(theta)
                z = r * math.cos(phi)
                all_v.append((x, y, z))
                # Wider brightness range for depth variation; ~8% are notably
                # brighter "feature" stars that earn visible diffraction spikes.
                b = random.uniform(0.60, 1.0)
                if random.random() < 0.08:
                    b = b + 0.40
                tint = random.choice(["w","w","w","w","bw","bw","b","y","o","r"])
                tr, tg, tb = tints[tint]
                # Colour channels may exceed 1.0 for feature stars — the additive
                # blend saturates them to brilliant white cores. Alpha keeps the
                # true brightness (b) for the fragment shader's spike scaling.
                all_c.append((tr * b, tg * b, tb * b, b))
                all_s.append(random.uniform(sz_lo, sz_hi))
                all_t.append(random.random())

        self.verts   = np.array(all_v, dtype=np.float32)
        self.colors  = np.array(all_c, dtype=np.float32)
        self.sizes   = np.array(all_s, dtype=np.float32)
        self.twink   = np.array(all_t, dtype=np.float32)

        self.prog    = load_program("stars", SHADERS_DIR)
        self.u       = Uniforms(self.prog)
        self.a_size  = glGetAttribLocation(self.prog, "a_size")
        self.a_twink = glGetAttribLocation(self.prog, "a_twinkle_seed")

        # Static star field → upload all four attribute arrays to VBOs once
        # (positions/colours never change; only the shader animates them per
        # frame from u_time). Avoids re-streaming ~4.6 k points every frame.
        # _vbo_v doubles as the "VBOs available" sentinel; None → client arrays.
        self._vbo_v = self._vbo_c = self._vbo_s = self._vbo_t = None
        try:
            self._vbo_v = int(glGenBuffers(1))
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_v)
            glBufferData(GL_ARRAY_BUFFER, self.verts.nbytes, self.verts, GL_STATIC_DRAW)
            self._vbo_c = int(glGenBuffers(1))
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_c)
            glBufferData(GL_ARRAY_BUFFER, self.colors.nbytes, self.colors, GL_STATIC_DRAW)
            self._vbo_s = int(glGenBuffers(1))
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_s)
            glBufferData(GL_ARRAY_BUFFER, self.sizes.nbytes, self.sizes, GL_STATIC_DRAW)
            self._vbo_t = int(glGenBuffers(1))
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_t)
            glBufferData(GL_ARRAY_BUFFER, self.twink.nbytes, self.twink, GL_STATIC_DRAW)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
        except Exception as e:
            print(f"[renderer] Stars VBO upload failed ({e}); using client arrays")
            self._vbo_v = self._vbo_c = self._vbo_s = self._vbo_t = None
            glBindBuffer(GL_ARRAY_BUFFER, 0)

    def draw(self, time_s: float, dpi_scale: float = 1.0):
        glUseProgram(self.prog)
        self.u.f("u_time",       time_s)
        self.u.f("u_size_scale", dpi_scale)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDepthMask(GL_FALSE)
        try:
            glEnable(GL_PROGRAM_POINT_SIZE)
        except Exception:
            pass
        try:
            glEnable(GL_POINT_SPRITE)
        except Exception:
            pass

        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)

        use_vbo = self._vbo_v is not None
        if use_vbo:
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_v)
            glVertexPointer(3, GL_FLOAT, 0, _VBO_OFFSET0)
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_c)
            glColorPointer(4, GL_FLOAT, 0, _VBO_OFFSET0)
            if self.a_size >= 0:
                glEnableVertexAttribArray(self.a_size)
                glBindBuffer(GL_ARRAY_BUFFER, self._vbo_s)
                glVertexAttribPointer(self.a_size, 1, GL_FLOAT, GL_FALSE, 0, _VBO_OFFSET0)
            if self.a_twink >= 0:
                glEnableVertexAttribArray(self.a_twink)
                glBindBuffer(GL_ARRAY_BUFFER, self._vbo_t)
                glVertexAttribPointer(self.a_twink, 1, GL_FLOAT, GL_FALSE, 0, _VBO_OFFSET0)
            glDrawArrays(GL_POINTS, 0, len(self.verts))
            glBindBuffer(GL_ARRAY_BUFFER, 0)
        else:
            glVertexPointer(3, GL_FLOAT, 0, self.verts)
            glColorPointer(4, GL_FLOAT, 0, self.colors)
            if self.a_size >= 0:
                glEnableVertexAttribArray(self.a_size)
                glVertexAttribPointer(self.a_size, 1, GL_FLOAT, GL_FALSE, 0, self.sizes)
            if self.a_twink >= 0:
                glEnableVertexAttribArray(self.a_twink)
                glVertexAttribPointer(self.a_twink, 1, GL_FLOAT, GL_FALSE, 0, self.twink)
            glDrawArrays(GL_POINTS, 0, len(self.verts))

        if self.a_size  >= 0: glDisableVertexAttribArray(self.a_size)
        if self.a_twink >= 0: glDisableVertexAttribArray(self.a_twink)
        glDisableClientState(GL_VERTEX_ARRAY)
        glDisableClientState(GL_COLOR_ARRAY)
        try:
            glDisable(GL_POINT_SPRITE)
        except Exception:
            pass
        glDepthMask(GL_TRUE)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_BLEND)
        glUseProgram(0)


# ══════════════════════════════════════════════════════════════════════════════
#  Milky-Way nebula background
# ══════════════════════════════════════════════════════════════════════════════

class Nebula:
    """
    Background sphere of the Milky Way, rendered from the inside.
    Drawn with depth writes disabled so it sits behind everything else.
    """

    R = 95.0   # large enough to enclose the entire scene

    def __init__(self):
        v, n, u, i = make_sphere(self.R, 64, 64)
        # Flip normals inward (we view from inside)
        n = -n
        self.mesh = Mesh(v, n, u, i)
        # Prefer the generated deep-space backdrop (nebula + Milky-Way band +
        # faint stars). Fall back to the legacy near-black astrophoto if the
        # generated asset is missing (run scripts/gen_space_background.py).
        space_bg = ASSETS / "stars" / "space_background.jpg"
        bg = space_bg if space_bg.exists() else ASSETS / "stars" / "milky_way_8k.jpg"
        self.tex  = load_texture_2d(bg)
        self.prog = load_program("nebula", SHADERS_DIR)
        self.u    = Uniforms(self.prog)

    def draw(self, time_s: float, brightness: float = 0.55):
        glUseProgram(self.prog)
        bind_texture_unit(0, self.tex)
        self.u.i("u_nebula",     0)
        self.u.f("u_brightness", brightness)
        self.u.f("u_time",       time_s)

        glDepthMask(GL_FALSE)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glCullFace(GL_FRONT)            # see inside of sphere
        self.mesh.draw()
        glDisable(GL_CULL_FACE)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glUseProgram(0)


# ══════════════════════════════════════════════════════════════════════════════
#  Orbital application icons  (real depth-tested billboards in Earth-LOCAL space)
# ══════════════════════════════════════════════════════════════════════════════
#
# Geometry is owned entirely by orbital_math.py (the same module sim_orbit.py
# verifies headlessly) so the render path cannot drift from the math.
#
#   • IconOrbit.draw() is called by the host INSIDE the same
#         glPushMatrix(); glTranslatef(earth_world); … ; glPopMatrix()
#     block that positions the Earth. The modelview origin is therefore the
#     Earth's center, so every icon placed at orbital_math.orbital_local_pos()
#     inherits the Earth's parallax, camera, projection and depth — one rigid
#     body, no second coordinate system, no 2-D offset hacks.
#   • Each icon is a camera-facing billboard: translate to its Earth-local
#     position, then overwrite the modelview's 3×3 rotation with a scaled
#     identity (size = ICON_WORLD_SIZE). Preserving the translation column
#     keeps the true eye-space depth, so perspective scaling AND z-buffer
#     occlusion against the Earth come for free.
#   • Transparent texels are DISCARDed in icon.frag, so an icon never writes
#     depth where it is invisible — clean two-way occlusion, no sorting.

ORBITAL_APPS_DIR = Path("/Applications/Orbital Apps")


def _resolve_finder_alias(item: Path):
    """Resolve a macOS Finder alias file to its target POSIX path (or None)."""
    try:
        from Foundation import NSURL
        url = NSURL.fileURLWithPath_(str(item))
        resolved, _err = NSURL.URLByResolvingAliasFileAtURL_options_error_(url, 0, None)
        if resolved is not None:
            return resolved.path()
    except Exception:
        pass
    return None


def _resolve_to_app(item: Path):
    """Resolve a folder entry to a real .app bundle path (handles aliases)."""
    if item.name.startswith("."):
        return None
    if item.suffix == ".app" and item.is_dir():
        return str(item.resolve())
    target = _resolve_finder_alias(item)
    if target:
        tp = Path(target)
        if tp.suffix == ".app" and tp.is_dir():
            return str(tp.resolve())
    return None


def _scan_orbital_apps_folder():
    """Sorted list of canonical .app paths in /Applications/Orbital Apps/."""
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


def _nsimage_to_texture(img, size: int = 256) -> int:
    """
    Rasterise an NSImage into an RGBA8 OpenGL texture; return its id.
    NSBitmapImageRep draws top-down, so the rows are flipped to GL's
    bottom-left origin before upload.
    """
    from AppKit import (NSBitmapImageRep, NSGraphicsContext,
                        NSDeviceRGBColorSpace, NSCompositingOperationCopy)
    from Foundation import NSMakeRect, NSZeroRect

    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, NSDeviceRGBColorSpace, size * 4, 32)
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    img.drawInRect_fromRect_operation_fraction_(
        NSMakeRect(0, 0, size, size), NSZeroRect, NSCompositingOperationCopy, 1.0)
    NSGraphicsContext.restoreGraphicsState()

    raw = bytes(rep.bitmapData())                       # top-down RGBA8
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(size, size, 4)
    arr = np.ascontiguousarray(arr[::-1])               # flip to GL origin

    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, arr)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    try:
        glGenerateMipmap(GL_TEXTURE_2D)
    except Exception:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glBindTexture(GL_TEXTURE_2D, 0)
    return tex


class IconOrbit:
    """
    A ring of macOS app icons orbiting the Earth in Earth-LOCAL space.

    The host draws this inside the Earth's modelview block (origin = Earth
    center). All positions come from orbital_math, so the live render is
    identical to the headless verification in sim_orbit.py.
    """

    RESCAN_INTERVAL = 1.0        # seconds between Orbital-Apps folder polls
    ALPHA_CUT       = 0.5        # fragment discard threshold (clean occlusion)
    ICON_TEX_SIZE   = 256

    def __init__(self, debug: bool = False):
        self.debug       = debug
        self.t           = 0.0
        self._rescan_acc = 0.0
        self._app_paths  = []
        self.icons       = []        # dicts: path,name,url,tex,phase,bob_phase
        self._fade       = 0.0       # global fade-in 0→1

        # Unit quad (centered, XY plane) + UVs — drawn per icon as a billboard.
        self._quad_v  = np.array([[-0.5, -0.5, 0.0], [0.5, -0.5, 0.0],
                                  [0.5, 0.5, 0.0], [-0.5, 0.5, 0.0]], dtype=np.float32)
        self._quad_uv = np.array([[0.0, 0.0], [1.0, 0.0],
                                  [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)

        self.prog = load_program("icon", SHADERS_DIR)
        self.u    = Uniforms(self.prog)

        self._load_apps(_scan_orbital_apps_folder())
        print(f"[icons] IconOrbit ready — {len(self.icons)} app(s) in orbit")

    # ── App / texture management ──────────────────────────────────────────────
    def _load_apps(self, paths) -> None:
        """(Re)build the icon list + GL textures from a list of .app paths."""
        from AppKit import NSWorkspace
        from Foundation import NSURL, NSMakeSize
        ws = NSWorkspace.sharedWorkspace()

        for ico in self.icons:                       # free previous textures
            try:
                glDeleteTextures([ico["tex"]])
            except Exception:
                pass

        self.icons = []
        N = max(1, len(paths))
        for i, p in enumerate(paths):
            if not Path(p).exists():
                continue
            img = ws.iconForFile_(p)
            if img is None:
                continue
            img.setSize_(NSMakeSize(self.ICON_TEX_SIZE, self.ICON_TEX_SIZE))
            try:
                tex = _nsimage_to_texture(img, self.ICON_TEX_SIZE)
            except Exception as e:
                print(f"[icons] texture build failed for {p}: {e}")
                continue
            self.icons.append({
                "path":      p,
                "name":      Path(p).stem,
                "url":       NSURL.fileURLWithPath_(p),
                "tex":       tex,
                "phase":     2.0 * math.pi * i / N,
                "bob_phase": (i * 1.37) % (2.0 * math.pi),
            })
        self._app_paths = list(paths)

    def rescan(self) -> None:
        paths = _scan_orbital_apps_folder()
        if set(paths) != set(self._app_paths):
            print(f"[icons] Orbital Apps changed — {len(paths)} app(s)")
            self._load_apps(paths)

    # ── Per-frame update ──────────────────────────────────────────────────────
    def update(self, dt: float) -> None:
        self.t     += dt
        self._fade  = min(1.0, self._fade + dt * 1.5)    # ~0.7 s fade-in
        self._rescan_acc += dt
        if self._rescan_acc >= self.RESCAN_INTERVAL:
            self._rescan_acc = 0.0
            self.rescan()

    # ── Draw (called inside the Earth modelview block) ─────────────────────────
    def draw(self, dpi_scale: float = 1.0) -> None:
        if not self.icons:
            return

        glUseProgram(self.prog)
        self.u.i("u_tex", 0)
        self.u.f("u_fade", self._fade)
        self.u.f("u_alpha_cut", self.ALPHA_CUT)

        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glEnable(GL_BLEND)
        # Colour uses normal source-over compositing, but the ALPHA channel is
        # forced to 0 wherever an icon body draws. The bloom bright-pass reads
        # that alpha as an anti-bloom mask (see post_bright.frag) so icons stay
        # opaque and crisp instead of glowing — without disturbing the Earth or
        # star bloom, both of which keep alpha >= 1.
        glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ZERO, GL_ZERO)
        glActiveTexture(GL_TEXTURE0)

        glEnableClientState(GL_VERTEX_ARRAY)
        glClientActiveTexture(GL_TEXTURE0)
        glEnableClientState(GL_TEXTURE_COORD_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, self._quad_v)
        glTexCoordPointer(2, GL_FLOAT, 0, self._quad_uv)

        # Icons are purely decorative spatial elements — no projection / hit-test
        # work is done here (that added per-frame gluProject stalls and click
        # latency for zero benefit on a click-through desktop layer).
        #
        # Billboard maths is done on the CPU. Previously each icon read the
        # modelview back with glGetFloatv(GL_MODELVIEW_MATRIX) — a GPU→CPU
        # pipeline stall PER ICON, every frame. Instead we read the Earth-origin
        # modelview ONCE and derive each icon's billboard from it: the billboard
        # linear block is always diag(ICON_WORLD_SIZE), and only the translation
        # column (the icon origin in eye space) changes — a single CPU mat·vec.
        # Pixel-identical to the old per-icon read-back; N stalls → 1 per frame.
        s = om.ICON_WORLD_SIZE
        # glGetFloatv returns column-major [col][row]; .T gives the math-order
        # modelview A (A[row][col]) at the Earth origin.
        A = np.array(glGetFloatv(GL_MODELVIEW_MATRIX), dtype=np.float32).T
        glPushMatrix()
        for ico in self.icons:
            angle  = om.icon_angle(ico["phase"], self.t)
            radius = om.icon_radius(self.t, ico["bob_phase"])
            lx, ly, lz = om.orbital_local_pos(angle, radius)

            # Icon origin in eye space (keeps true depth → perspective scaling
            # AND z-buffer occlusion against the Earth, exactly as before).
            p = A @ np.array([lx, ly, lz, 1.0], dtype=np.float32)
            # Billboard modelview in GL column-major layout: scaled-identity 3×3
            # (faces the camera) with the eye-space origin as the translation col.
            m = np.array([[s, 0.0, 0.0, 0.0],
                          [0.0, s, 0.0, 0.0],
                          [0.0, 0.0, s, 0.0],
                          [float(p[0]), float(p[1]), float(p[2]), 1.0]],
                         dtype=np.float32)
            glLoadMatrixf(m)

            glBindTexture(GL_TEXTURE_2D, ico["tex"])
            glDrawArrays(GL_TRIANGLE_FAN, 0, 4)
        glPopMatrix()

        glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)
        glBindTexture(GL_TEXTURE_2D, 0)
        # Restore the standard blend func so nothing downstream inherits the
        # zero-alpha write mask.
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_BLEND)
        glDepthMask(GL_TRUE)
        glUseProgram(0)

        if self.debug:
            self._draw_debug_ring()

    # ── Debug visualisation (orbital ring + Earth-center crosshair) ────────────
    def _draw_debug_ring(self) -> None:
        glUseProgram(0)
        glDisable(GL_TEXTURE_2D)
        glDepthMask(GL_FALSE)
        glDisable(GL_DEPTH_TEST)
        glColor4f(0.2, 0.9, 1.0, 0.6)                   # tilted orbital ring
        glBegin(GL_LINE_LOOP)
        for k in range(72):
            a = 2.0 * math.pi * k / 72
            lx, ly, lz = om.orbital_local_pos(a, om.ORBIT_RADIUS)
            glVertex3f(float(lx), float(ly), float(lz))
        glEnd()
        glColor4f(1.0, 0.3, 0.3, 0.9)                   # Earth-center crosshair
        glBegin(GL_LINES)
        glVertex3f(-0.4, 0.0, 0.0); glVertex3f(0.4, 0.0, 0.0)
        glVertex3f(0.0, -0.4, 0.0); glVertex3f(0.0, 0.4, 0.0)
        glVertex3f(0.0, 0.0, -0.4); glVertex3f(0.0, 0.0, 0.4)
        glEnd()
        glColor4f(1.0, 1.0, 1.0, 1.0)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)


# ══════════════════════════════════════════════════════════════════════════════
#  The Watcher — eyeball (single textured sphere; reuses the sphere pipeline)
# ══════════════════════════════════════════════════════════════════════════════

class Eye:
    """
    A gigantic, uncanny eyeball for the "The Watcher" world.

    Deliberately minimal: ONE textured sphere the same radius as the Earth
    surface (so it occupies the same screen footprint), drawn through the exact
    same make_sphere / Mesh / shader / texture pipeline as everything else. The
    iris is baked facing the camera (eye_diffuse at UV 0.25, 0.50). It does NOT
    spin like the Earth — instead:
      • A near-imperceptible gaze "drift" gives a faint base sense of life.
      • Dynamic eye tracking: the sphere rotates toward the viewer's head
        position (hx/hy from face_tracker) so the iris actively follows the
        user. Gaze is smoothed with a lerp so movement feels intentional.
        Rotation is clamped to realistic eye-movement limits.
    eye.frag outputs alpha = 0 so the bloom bright-pass skips it (biological,
    not magical). No new rendering/camera/physics systems are introduced.
    """

    R         = Earth.R_SURFACE   # 2.6 — match Earth so it fills the same space
    DRIFT_DEG = 1.6               # peak gaze-drift angle (nearly imperceptible)

    # Eye-tracking limits. Pushed well beyond "realistic" anatomy so the eye
    # feels locked on rather than politely glancing — this is a horror prop,
    # not a biology lesson. The sphere can comfortably rotate this far before
    # the iris starts to clip off-screen.
    GAZE_MAX_YAW_DEG   = 32.0
    GAZE_MAX_PITCH_DEG = 26.0
    # Snappy lerp: ~7 frames (0.12 s at 60 fps) to reach 92 % of target.
    # The eye doesn't drift — it snaps onto the viewer and holds.
    GAZE_LERP = 0.30

    def __init__(self):
        v, n, u, i = make_sphere(self.R, 96, 96)
        self.mesh = Mesh(v, n, u, i)

        wdir = ASSETS / "the_watcher"
        # flip_v=False — same equirectangular convention as the Earth maps
        # (north pole at the top row); see Scripts/tools/gen_eye_textures.py.
        self.tex_diffuse  = load_texture_2d(wdir / "eye_diffuse.png",  flip_v=False)
        self.tex_normal   = load_texture_2d(wdir / "eye_normal.png",   flip_v=False)
        self.tex_specular = load_texture_2d(wdir / "eye_specular.png", flip_v=False)

        self.prog = load_program("eye", SHADERS_DIR)
        self.u    = Uniforms(self.prog)
        self.t    = 0.0
        # Smoothed gaze angles driven by head-tracking data (degrees).
        self._gaze_yaw   = 0.0
        self._gaze_pitch = 0.0

    def update(self, dt: float, hx: float = 0.0, hy: float = 0.0) -> None:
        self.t += dt
        # hx convention: +1 = viewer to the LEFT (mirrored camera frame).
        # To track the viewer, the iris (at +Z pole) must rotate toward them:
        #   viewer LEFT  → iris rotates LEFT  → negative yaw around Y
        #   viewer UP    → iris rotates UP    → negative pitch around X
        # Clamped to realistic eye-movement limits before smoothing.
        target_yaw   = max(-self.GAZE_MAX_YAW_DEG,
                           min( self.GAZE_MAX_YAW_DEG,   -hx * self.GAZE_MAX_YAW_DEG))
        target_pitch = max(-self.GAZE_MAX_PITCH_DEG,
                           min( self.GAZE_MAX_PITCH_DEG, -hy * self.GAZE_MAX_PITCH_DEG))
        self._gaze_yaw   += self.GAZE_LERP * (target_yaw   - self._gaze_yaw)
        self._gaze_pitch += self.GAZE_LERP * (target_pitch - self._gaze_pitch)

    def draw(self, sun_eye, time_s: float) -> None:
        glPushMatrix()
        # Combine eye-tracking gaze with subtle drift so the eye both follows
        # the viewer and retains organic micro-motion. Pure object transform;
        # does NOT touch the camera / parallax / off-axis math.
        drift_yaw   = self.DRIFT_DEG       * math.sin(self.t * 0.13)
        drift_pitch = self.DRIFT_DEG * 0.6 * math.sin(self.t * 0.097 + 1.0)
        yaw   = self._gaze_yaw   + drift_yaw
        pitch = self._gaze_pitch + drift_pitch
        glRotatef(yaw,   0.0, 1.0, 0.0)
        glRotatef(pitch, 1.0, 0.0, 0.0)

        glUseProgram(self.prog)
        bind_texture_unit(0, self.tex_diffuse)
        bind_texture_unit(1, self.tex_normal)
        bind_texture_unit(2, self.tex_specular)
        self.u.i("u_diffuse",  0)
        self.u.i("u_normal",   1)
        self.u.i("u_specular", 2)
        self.u.v3("u_sun_eye", *sun_eye)
        self.u.f("u_time",    time_s)

        glEnable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        self.mesh.draw()
        glUseProgram(0)
        glPopMatrix()


# ══════════════════════════════════════════════════════════════════════════════
#  Grid Room — wireframe "shadow box" spatial-reference environment
# ══════════════════════════════════════════════════════════════════════════════
#
# A holographic wireframe room whose FRONT RIM is the window aperture at world
# z = 0 (the glass): under the off-axis frustum that rim maps exactly to the
# screen border (sim_offaxis check 6), so the four walls, floor and ceiling
# recede BEHIND the monitor like a real shadow box. Dense, regular grid lines
# give the strong, multi-depth MOTION-PARALLAX cue a single floating body cannot
# — the dominant depth signal for a head-coupled display — and the rigid box
# lets the visual system read small tracking wobble as "I moved" rather than
# "it jittered". The receding side-wall lines converge to a vanishing point
# (one-point perspective), which is exactly the depth scaffold the illusion
# wants.
#
# Pure fixed-function GL_LINES — NO shader, so the frozen shaders are untouched.
# Per-vertex RGBA with a front→back alpha fade sinks distant lines into the clear
# colour. Geometry is cached and rebuilt only when the aperture / depth /
# divisions / colour change (e.g. a Desktop-Mode resize, or a calibrated framing).

class GridRoom:
    """Wireframe shadow-box room anchored to the off-axis window aperture.

    Drawn in WORLD space (the engine does NOT apply the Earth-anchor translate),
    so the front rim sits on the glass at z = 0 by construction.
    """

    _A_FRONT = 0.55     # line alpha at the glass (z = 0)
    _A_BACK  = 0.06     # line alpha at the back wall (z = -depth)
    _A_RIM   = 0.78     # front rim (the "glass" anchor) a touch brighter

    def __init__(self):
        self._key = None
        self._v = None      # float32 (N,3) line endpoints
        self._c = None      # float32 (N,4) per-vertex RGBA

    def _alpha_at(self, z: float, depth: float) -> float:
        """Front (z=0) bright → back (z=-depth) faint, linear in depth."""
        t = min(1.0, max(0.0, (-z) / depth)) if depth > 1e-6 else 0.0
        return self._A_FRONT + (self._A_BACK - self._A_FRONT) * t

    def _rebuild(self, half_w, half_h, depth, divisions, color) -> None:
        v, c = [], []
        r, g, b = color
        D  = max(1, int(divisions))

        def line(p0, p1, a0=None, a1=None):
            a0 = self._alpha_at(p0[2], depth) if a0 is None else a0
            a1 = self._alpha_at(p1[2], depth) if a1 is None else a1
            v.append(p0); c.append((r, g, b, a0))
            v.append(p1); c.append((r, g, b, a1))

        xs = [(-half_w + 2.0 * half_w * i / D) for i in range(D + 1)]
        ys = [(-half_h + 2.0 * half_h * i / D) for i in range(D + 1)]
        zs = [(-depth * i / D) for i in range(D + 1)]          # 0 → -depth
        zb = -depth

        # Back wall (z = -depth): vertical + horizontal grid.
        for x in xs: line((x, -half_h, zb), (x, half_h, zb))
        for y in ys: line((-half_w, y, zb), (half_w, y, zb))
        # Floor (y = -half_h) and ceiling (y = +half_h): grids in X and Z.
        for yw in (-half_h, half_h):
            for x in xs: line((x, yw, 0.0), (x, yw, zb))
            for z in zs: line((-half_w, yw, z), (half_w, yw, z))
        # Left / right walls (x = ±half_w): grids in Y and Z.
        for xw in (-half_w, half_w):
            for y in ys: line((xw, y, 0.0), (xw, y, zb))
            for z in zs: line((xw, -half_h, z), (xw, half_h, z))
        # Front rim on the glass (z = 0) — the zero-parallax window frame.
        rim = [(-half_w, -half_h, 0.0), (half_w, -half_h, 0.0),
               ( half_w,  half_h, 0.0), (-half_w, half_h, 0.0)]
        for i in range(4):
            line(rim[i], rim[(i + 1) % 4], self._A_RIM, self._A_RIM)

        self._v = np.array(v, dtype=np.float32)
        self._c = np.array(c, dtype=np.float32)

    def draw(self, half_w, half_h, depth, divisions, color,
             time_s: float = 0.0, dpi_scale: float = 1.0) -> None:
        key = (round(half_w, 3), round(half_h, 3), round(depth, 3),
               int(divisions), tuple(round(float(x), 3) for x in color))
        if key != self._key:
            self._rebuild(half_w, half_h, depth, divisions, color)
            self._key = key

        glUseProgram(0)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)           # blended lines: test, but don't write depth
        glDisable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        try:
            glEnable(GL_LINE_SMOOTH)
            glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        except Exception:
            pass
        glLineWidth(max(1.0, dpi_scale))

        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, self._v)
        glColorPointer(4, GL_FLOAT, 0, self._c)
        glDrawArrays(GL_LINES, 0, len(self._v))
        glDisableClientState(GL_COLOR_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

        try:
            glDisable(GL_LINE_SMOOTH)
        except Exception:
            pass
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        glColor4f(1.0, 1.0, 1.0, 1.0)


class PlaceableObjects:
    """World Builder — draws user-placed builtin primitives inside the Grid Room.

    Drawn in WORLD space immediately after GridRoom (no Earth-anchor translate), so
    a cell maps straight onto the grid via Worlds.placeable.grid_to_world. v1 is
    fixed-function flat/emissive colour — the frozen shaders/ are provably untouched
    and there is no live GL-compile risk (see plan §4).

    Meshes are cached singletons keyed by primitive name and built lazily on first
    use — never rebuilt per frame (the codebase is strict about per-frame
    allocation). Objects WRITE depth (solid), so they occlude the blended grid lines
    correctly, unlike GridRoom which leaves the depth mask off.
    """

    def __init__(self) -> None:
        self._meshes: dict[str, Mesh] = {}

    def _mesh(self, model: str):
        m = self._meshes.get(model)
        if m is None:
            if model == "builtin:cube":
                v, n, i = make_cube()
                m = Mesh(v, n, None, i)
            elif model == "builtin:sphere":
                v, n, u, i = make_sphere(1.0, 24, 24)
                m = Mesh(v, n, u, i)
            elif model == "builtin:cylinder":
                v, n, i = make_cylinder()
                m = Mesh(v, n, None, i)
            else:
                return None
            self._meshes[model] = m
        return m

    def draw(self, objects, half_w, half_h, depth, divisions) -> None:
        objs = sanitize_objects(objects, divisions)   # allowlist + clamp + count cap
        if not objs:
            return

        glUseProgram(0)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_LIGHTING)            # v1: flat emissive; lit look is a later option
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)             # solid → write depth so objects occlude the grid
        glDisable(GL_BLEND)

        for obj in objs:
            mesh = self._mesh(obj["model"])
            if mesh is None:
                continue
            wx, wy, wz = grid_to_world(*obj["grid_position"],
                                       half_w, half_h, depth, divisions)
            r, g, b = obj["color"]
            rx, ry, rz = obj["rotation"]
            s = obj["scale"]
            glPushMatrix()
            glTranslatef(wx, wy, wz)
            if ry:
                glRotatef(ry, 0.0, 1.0, 0.0)
            if rx:
                glRotatef(rx, 1.0, 0.0, 0.0)
            if rz:
                glRotatef(rz, 0.0, 0.0, 1.0)
            glScalef(s, s, s)
            glColor4f(r, g, b, 1.0)
            mesh.draw()
            glPopMatrix()

        glColor4f(1.0, 1.0, 1.0, 1.0)   # restore default colour for later draws


def draw_window_frame(half_w: float, half_h: float,
                      color=(0.5, 0.75, 1.0), alpha: float = 0.45,
                      inset: float = 0.965, dpi_scale: float = 1.0) -> None:
    """Thin rectangle at the glass plane (world z = 0), inset slightly so it
    reads as a floating 'this is a window' frame — a zero-parallax depth anchor.

    Opt-in per world via rendering.show_window_frame; default OFF, so the shipped
    worlds are visually unchanged. Fixed-function lines — no shader. The caller
    draws this in the base (world-space) modelview, AFTER the scene body."""
    hw, hh = half_w * inset, half_h * inset
    glUseProgram(0)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_DEPTH_TEST)
    glDepthMask(GL_FALSE)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    try:
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
    except Exception:
        pass
    glLineWidth(max(1.0, dpi_scale))
    glColor4f(color[0], color[1], color[2], alpha)
    glBegin(GL_LINE_LOOP)
    glVertex3f(-hw, -hh, 0.0)
    glVertex3f( hw, -hh, 0.0)
    glVertex3f( hw,  hh, 0.0)
    glVertex3f(-hw,  hh, 0.0)
    glEnd()
    try:
        glDisable(GL_LINE_SMOOTH)
    except Exception:
        pass
    glDepthMask(GL_TRUE)
    glDisable(GL_BLEND)
    glColor4f(1.0, 1.0, 1.0, 1.0)
