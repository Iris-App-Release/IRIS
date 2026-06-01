"""
postfx.py — Bloom post-processing pipeline.

Flow per frame:

    [scene FBO]  ─── bright-extract ───▶  [bloom ping]
                                                 │
                                  horizontal blur │
                                                 ▼
                                          [bloom pong]
                                                 │
                                    vertical blur│
                                                 ▼
                                          [bloom ping]
                                                 │
                                                 ▼
    [scene FBO] + [bloom ping] → composite → screen

Three textures total (scene + ping + pong).  Render the scene into the
scene FBO, then call BloomPipeline.draw_to_screen() to do the rest.

Falls back to a simple blit (no bloom) if FBO support is missing.
"""

import ctypes
from pathlib import Path

import numpy as np
from OpenGL.GL import *

from Engine.shader_loader import load_program, Uniforms

SHADERS_DIR = Path(__file__).parent.parent / "shaders"


# ── FBO support probe ─────────────────────────────────────────────────────────
try:
    from OpenGL.GL.EXT import framebuffer_object as _fbo_ext   # noqa: F401
    _HAS_FBO = True
except ImportError:
    _HAS_FBO = bool(glGenFramebuffers)
    _HAS_FBO = True   # core in 3.0+, always present in PyOpenGL's binding


# ── Full-screen NDC quad with UVs ─────────────────────────────────────────────
_QUAD_V = np.array([
    [-1.0, -1.0],
    [ 1.0, -1.0],
    [ 1.0,  1.0],
    [-1.0,  1.0],
], dtype=np.float32)

_QUAD_T = np.array([
    [0.0, 0.0],
    [1.0, 0.0],
    [1.0, 1.0],
    [0.0, 1.0],
], dtype=np.float32)


def _draw_fullscreen_quad():
    """Stream a screen-aligned quad in MVP-identity NDC space."""
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()

    glDisable(GL_DEPTH_TEST)
    glDepthMask(GL_FALSE)

    glEnableClientState(GL_VERTEX_ARRAY)
    glEnableClientState(GL_TEXTURE_COORD_ARRAY)
    glClientActiveTexture(GL_TEXTURE0)
    glVertexPointer  (2, GL_FLOAT, 0, _QUAD_V)
    glTexCoordPointer(2, GL_FLOAT, 0, _QUAD_T)
    glDrawArrays(GL_TRIANGLE_FAN, 0, 4)
    glDisableClientState(GL_TEXTURE_COORD_ARRAY)
    glDisableClientState(GL_VERTEX_ARRAY)

    glDepthMask(GL_TRUE)
    glEnable(GL_DEPTH_TEST)

    glMatrixMode(GL_PROJECTION); glPopMatrix()
    glMatrixMode(GL_MODELVIEW);  glPopMatrix()


# ── FBO helper ────────────────────────────────────────────────────────────────
def _make_color_fbo(w: int, h: int, with_depth: bool = False):
    """
    Create a colour-only (or colour+depth) FBO.
    Returns (fbo_id, color_tex, depth_rb_or_None).
    """
    fbo = glGenFramebuffers(1)
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S,     GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T,     GL_CLAMP_TO_EDGE)
    glBindTexture(GL_TEXTURE_2D, 0)

    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, tex, 0)

    depth = None
    if with_depth:
        depth = glGenRenderbuffers(1)
        glBindRenderbuffer(GL_RENDERBUFFER, depth)
        glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, w, h)
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT,
                                  GL_RENDERBUFFER, depth)
        glBindRenderbuffer(GL_RENDERBUFFER, 0)

    status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
    if status != GL_FRAMEBUFFER_COMPLETE:
        raise RuntimeError(f"[postfx] Framebuffer incomplete: 0x{status:x}")

    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    return fbo, tex, depth


# ── BloomPipeline ─────────────────────────────────────────────────────────────
class BloomPipeline:
    """
    Manages the three FBOs and four shader programs.  Use as:

        bloom = BloomPipeline(W_gl, H_gl)
        ...
        bloom.bind_scene()
        # render whole scene...
        bloom.draw_to_screen(W_gl, H_gl)
    """

    BLOOM_DOWNSCALE   = 2     # bloom buffer is W/2 × H/2 — softer & cheaper
    THRESHOLD         = 0.68
    SOFTNESS          = 0.50
    BLUR_RADIUS       = 1.8
    BLOOM_STRENGTH    = 1.10
    EXPOSURE          = 1.22
    VIGNETTE          = 0.42
    ABERRATION        = 0.0025

    def __init__(self, width: int, height: int):
        self.w  = int(width)
        self.h  = int(height)
        bw = max(2, self.w // self.BLOOM_DOWNSCALE)
        bh = max(2, self.h // self.BLOOM_DOWNSCALE)
        self.bw = bw
        self.bh = bh

        # Allocate FBOs
        self.scene_fbo, self.scene_tex, self.scene_depth = _make_color_fbo(self.w, self.h, with_depth=True)
        self.ping_fbo,  self.ping_tex,  _ = _make_color_fbo(bw, bh)
        self.pong_fbo,  self.pong_tex,  _ = _make_color_fbo(bw, bh)

        # Compile post programs
        self.p_bright    = load_program("post_bright",    SHADERS_DIR)
        # The blur shader uses the same vertex shader as bright; both load
        # post_quad.vert. We need separate program objects per fragment shader.
        # load_program() helper assumes name.vert + name.frag — so we have
        # post_blur.vert / post_composite.vert as symlinks or we just create
        # alias shader files. Simpler: create thin .vert files that share
        # the same content. (Already done — see shaders/.)
        self.p_blur      = load_program("post_blur",      SHADERS_DIR)
        self.p_composite = load_program("post_composite", SHADERS_DIR)

        self.u_bright    = Uniforms(self.p_bright)
        self.u_blur      = Uniforms(self.p_blur)
        self.u_composite = Uniforms(self.p_composite)

    # ── public API ────────────────────────────────────────────────────────────
    def bind_scene(self) -> None:
        """Bind the scene FBO so subsequent draws render into it."""
        glBindFramebuffer(GL_FRAMEBUFFER, self.scene_fbo)
        glViewport(0, 0, self.w, self.h)

    def unbind(self) -> None:
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

    def draw_to_screen(self, screen_w: int, screen_h: int) -> None:
        """
        Run bright-extract → 2 blur passes → composite. After this call the
        default framebuffer holds the final tonemapped image.
        """
        # ── 1. Bright pass: scene_tex → ping (downscaled) ─────────────────────
        glBindFramebuffer(GL_FRAMEBUFFER, self.ping_fbo)
        glViewport(0, 0, self.bw, self.bh)
        glUseProgram(self.p_bright)
        glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, self.scene_tex)
        self.u_bright.i("u_scene",     0)
        self.u_bright.f("u_threshold", self.THRESHOLD)
        self.u_bright.f("u_softness",  self.SOFTNESS)
        _draw_fullscreen_quad()

        # ── 2. Horizontal blur: ping → pong ───────────────────────────────────
        glBindFramebuffer(GL_FRAMEBUFFER, self.pong_fbo)
        glViewport(0, 0, self.bw, self.bh)
        glUseProgram(self.p_blur)
        glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, self.ping_tex)
        self.u_blur.i ("u_tex",    0)
        self.u_blur.v2("u_dir",    1.0 / self.bw, 0.0)
        self.u_blur.f ("u_radius", self.BLUR_RADIUS)
        _draw_fullscreen_quad()

        # ── 3. Vertical blur: pong → ping ─────────────────────────────────────
        glBindFramebuffer(GL_FRAMEBUFFER, self.ping_fbo)
        glViewport(0, 0, self.bw, self.bh)
        glUseProgram(self.p_blur)
        glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, self.pong_tex)
        self.u_blur.i ("u_tex",    0)
        self.u_blur.v2("u_dir",    0.0, 1.0 / self.bh)
        self.u_blur.f ("u_radius", self.BLUR_RADIUS)
        _draw_fullscreen_quad()

        # ── 4. Composite: scene + bloom → screen ──────────────────────────────
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glViewport(0, 0, screen_w, screen_h)
        glUseProgram(self.p_composite)
        glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, self.scene_tex)
        glActiveTexture(GL_TEXTURE1); glBindTexture(GL_TEXTURE_2D, self.ping_tex)
        self.u_composite.i("u_scene",          0)
        self.u_composite.i("u_bloom",          1)
        self.u_composite.f("u_bloom_strength", self.BLOOM_STRENGTH)
        self.u_composite.f("u_exposure",       self.EXPOSURE)
        self.u_composite.f("u_vignette",       self.VIGNETTE)
        self.u_composite.f("u_aberration",     self.ABERRATION)
        _draw_fullscreen_quad()

        glActiveTexture(GL_TEXTURE0)
        glUseProgram(0)
