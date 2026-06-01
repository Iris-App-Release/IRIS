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

import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from OpenGL.GL import *

from Engine import camera_math as om
from Engine.shader_loader import (
    load_program, load_texture_2d, bind_texture_unit, Uniforms,
)

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


# ══════════════════════════════════════════════════════════════════════════════
#  Indexed mesh wrapper (uses client-side arrays — fine for our vertex counts)
# ══════════════════════════════════════════════════════════════════════════════

class Mesh:
    """Lightweight wrapper around per-attribute numpy arrays + element index."""

    def __init__(self, verts, norms, uvs=None, indices=None):
        self.verts = np.ascontiguousarray(verts, dtype=np.float32)
        self.norms = np.ascontiguousarray(norms, dtype=np.float32)
        self.uvs   = np.ascontiguousarray(uvs,   dtype=np.float32) if uvs is not None else None
        self.idx   = np.ascontiguousarray(indices, dtype=np.uint32) if indices is not None else None
        self.n_indices = len(self.idx) if self.idx is not None else len(self.verts)

    def draw(self):
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)
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

    # Shadow disk
    _SHADOW_Y     = -3.30
    _SHADOW_R     =  3.50
    _SHADOW_ALPHA =  0.28

    # Floor plane
    _FLOOR_HALF  = 600.0  # half-extent in world units (X and Z)
    # The floor is a FLAT, unlit plane textured with a GL_REPEAT checker, so the
    # subdivision adds nothing — perspective-correct UV interpolation gives the
    # same horizon convergence with 2 triangles as with thousands. Dropped from
    # 60 (= 21,600 verts re-streamed every frame through the slow client-side
    # array path) to 1 (= 6 verts). Pure per-frame win, pixel-identical result.
    _FLOOR_DIVS  = 1      # grid subdivisions per axis (flat plane → 1 is exact)
    # World units per full texture repeat. The generated checker texture is 8
    # checks across, so each check = _FLOOR_TILE / 8 world units. Raised 1.0 → 10.0
    # so the checks are ~10× larger (they read far too small at 1.0).
    _FLOOR_TILE  = 10.0   # one texture repeat = 10 world units (≈1.25u per check)
    _FLOOR_Y     = -3.30  # coplanar with shadow disk

    def __init__(self):
        v, n = make_gem()
        uvs = np.zeros((len(v), 2), dtype=np.float32)
        self.mesh = Mesh(v, n, uvs)
        self.prog = load_program("gem", SHADERS_DIR)
        self.u    = Uniforms(self.prog)
        self._spin_y     = 0.0
        self._tilt_phase = 0.0
        self._shadow_v, self._shadow_c = self._build_shadow()
        self._floor_tex            = self._build_floor_texture()
        self._floor_v, self._floor_uv = self._build_floor_mesh()

    # ── Floor ─────────────────────────────────────────────────────────────────

    def _build_floor_texture(self, size: int = 512, checks: int = 8) -> int:
        """
        Procedurally generate a pink/white checkerboard GL texture.
        Each pair of checks maps to one tile period; GL_REPEAT tiles it
        across the floor.  Returns the texture ID.
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

    def _build_floor_mesh(self):
        """
        Subdivided XZ plane at _FLOOR_Y.  UVs are world-space
        (x / tile, z / tile) so each tile = one checker square.
        OpenGL's own perspective projection gives the natural
        one-point-perspective convergence of grid lines to the horizon.
        """
        H    = self._FLOOR_HALF
        D    = self._FLOOR_DIVS
        Y    = self._FLOOR_Y
        tile = self._FLOOR_TILE
        xs   = np.linspace(-H, H, D + 1, dtype=np.float32)
        zs   = np.linspace(-H, H, D + 1, dtype=np.float32)

        verts, uvs = [], []
        for i in range(D):
            for j in range(D):
                for cx, cz in [
                    (xs[j],   zs[i]),   (xs[j+1], zs[i]),   (xs[j+1], zs[i+1]),
                    (xs[j],   zs[i]),   (xs[j+1], zs[i+1]), (xs[j],   zs[i+1]),
                ]:
                    verts.append((cx, Y, cz))
                    uvs.append((cx / tile, cz / tile))

        return (np.array(verts, dtype=np.float32),
                np.array(uvs,   dtype=np.float32))

    def _draw_floor(self) -> None:
        """Draw the textured checkerboard floor (fixed-function pipeline)."""
        glUseProgram(0)
        glEnable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self._floor_tex)
        glColor3f(1.0, 1.0, 1.0)   # no colour tint

        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_TEXTURE_COORD_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, self._floor_v)
        glTexCoordPointer(2, GL_FLOAT, 0, self._floor_uv)
        glDrawArrays(GL_TRIANGLES, 0, len(self._floor_v))
        glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

        glDisable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, 0)

    # ── Shadow disk ───────────────────────────────────────────────────────────

    def _build_shadow(self, n_pts: int = 48):
        """Flat triangle-fan disk at _SHADOW_Y with centre-to-edge alpha fade."""
        verts  = [(0.0, self._SHADOW_Y, 0.0)]
        colors = [(0.0, 0.0, 0.0, self._SHADOW_ALPHA)]
        for i in range(n_pts + 1):
            a = 2.0 * math.pi * i / n_pts
            verts.append((self._SHADOW_R * math.cos(a),
                          self._SHADOW_Y,
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
        # 1. Floor — drawn first so depth buffer is correct.
        self._draw_floor()
        # 2. Shadow soft disk — alpha-blended over the floor.
        self._draw_shadow()

        # 3. Gem — rotated in model space, unaffected by floor/shadow transforms.
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
        for ico in self.icons:
            angle  = om.icon_angle(ico["phase"], self.t)
            radius = om.icon_radius(self.t, ico["bob_phase"])
            lx, ly, lz = om.orbital_local_pos(angle, radius)

            glPushMatrix()
            glTranslatef(float(lx), float(ly), float(lz))

            # Billboard: overwrite the modelview 3×3 with a scaled identity but
            # keep the translation column → true depth + perspective scaling.
            m = np.array(glGetFloatv(GL_MODELVIEW_MATRIX), dtype=np.float32)
            s = om.ICON_WORLD_SIZE
            for c in range(3):
                for r in range(3):
                    m[c][r] = s if c == r else 0.0
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
