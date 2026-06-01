"""
shader_util.py — GLSL 120 compile/link helpers + texture loading.

Targets OpenGL 2.1 compatibility profile (the only legacy profile macOS supports
alongside Apple Silicon Metal-translated GL).  GLSL 120 has access to all the
fixed-function matrix uniforms (gl_ModelViewProjectionMatrix, gl_NormalMatrix,
etc.) which is exactly what we want — shaders layer on top of the existing
gluLookAt camera math without rewriting the perspective system.
"""

from pathlib import Path
import pygame
import numpy as np

from OpenGL.GL import (
    glCreateShader, glShaderSource, glCompileShader,
    glGetShaderiv, glGetShaderInfoLog,
    glCreateProgram, glAttachShader, glLinkProgram,
    glGetProgramiv, glGetProgramInfoLog,
    glUseProgram, glDeleteShader,
    glGetUniformLocation, glGetAttribLocation,
    glUniform1i, glUniform1f, glUniform2f, glUniform3f, glUniform4f,
    glUniform3fv, glUniformMatrix3fv, glUniformMatrix4fv,
    glGenTextures, glBindTexture, glTexImage2D, glTexParameteri,
    glGenerateMipmap, glPixelStorei, glActiveTexture,
    GL_VERTEX_SHADER, GL_FRAGMENT_SHADER,
    GL_COMPILE_STATUS, GL_LINK_STATUS, GL_FALSE,
    GL_TEXTURE_2D, GL_RGB, GL_RGBA, GL_UNSIGNED_BYTE,
    GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T,
    GL_LINEAR, GL_LINEAR_MIPMAP_LINEAR, GL_REPEAT, GL_CLAMP_TO_EDGE,
    GL_UNPACK_ALIGNMENT, GL_TEXTURE0,
)


# ── Shader compilation ────────────────────────────────────────────────────────

def _compile(src: str, kind: int, label: str) -> int:
    sid = glCreateShader(kind)
    glShaderSource(sid, src)
    glCompileShader(sid)
    if glGetShaderiv(sid, GL_COMPILE_STATUS) == GL_FALSE:
        log = glGetShaderInfoLog(sid).decode("utf-8", errors="replace")
        raise RuntimeError(f"[shader] {label} compile error:\n{log}\n──── source ────\n{src}")
    return sid


def make_program(vs_src: str, fs_src: str, label: str = "<unnamed>") -> int:
    """Compile, link, and return a shader program ID.  Raises on failure."""
    vs = _compile(vs_src, GL_VERTEX_SHADER,   f"{label}.vert")
    fs = _compile(fs_src, GL_FRAGMENT_SHADER, f"{label}.frag")
    prog = glCreateProgram()
    glAttachShader(prog, vs)
    glAttachShader(prog, fs)
    glLinkProgram(prog)
    if glGetProgramiv(prog, GL_LINK_STATUS) == GL_FALSE:
        log = glGetProgramInfoLog(prog).decode("utf-8", errors="replace")
        raise RuntimeError(f"[shader] {label} link error:\n{log}")
    glDeleteShader(vs)
    glDeleteShader(fs)
    return prog


def load_program(name: str, shader_dir: Path | str = "shaders") -> int:
    """
    Load and compile shaders/<name>.vert + shaders/<name>.frag.
    Files share a base name; the function appends the extensions.
    """
    base = Path(shader_dir) / name
    vs   = (base.with_suffix(".vert")).read_text()
    fs   = (base.with_suffix(".frag")).read_text()
    return make_program(vs, fs, label=name)


# ── Uniform helpers ───────────────────────────────────────────────────────────

class Uniforms:
    """Cached uniform-location lookup — avoids glGetUniformLocation per frame."""

    def __init__(self, program: int):
        self.program = program
        self._cache: dict = {}

    def _loc(self, name: str) -> int:
        if name not in self._cache:
            self._cache[name] = glGetUniformLocation(self.program, name)
        return self._cache[name]

    # scalar / vector setters
    def i (self, name: str, v: int)             -> None: glUniform1i(self._loc(name), v)
    def f (self, name: str, v: float)           -> None: glUniform1f(self._loc(name), v)
    def v2(self, name: str, x: float, y: float) -> None: glUniform2f(self._loc(name), x, y)
    def v3(self, name: str, x, y=None, z=None)  -> None:
        if y is None:
            x, y, z = x  # passed as 3-tuple
        glUniform3f(self._loc(name), x, y, z)
    def v4(self, name: str, x, y, z, w)         -> None: glUniform4f(self._loc(name), x, y, z, w)
    def mat3(self, name: str, m: np.ndarray)    -> None:
        glUniformMatrix3fv(self._loc(name), 1, GL_FALSE, m.astype(np.float32).flatten('F'))
    def mat4(self, name: str, m: np.ndarray)    -> None:
        glUniformMatrix4fv(self._loc(name), 1, GL_FALSE, m.astype(np.float32).flatten('F'))


# ── Texture loading ───────────────────────────────────────────────────────────

def load_texture_2d(
    path: str | Path,
    *,
    mipmap: bool = True,
    wrap_s: int  = GL_REPEAT,
    wrap_t: int  = GL_CLAMP_TO_EDGE,
    flip_v: bool = True,
) -> int:
    """
    Load an image file from disk as an OpenGL 2-D texture.
    Returns the texture ID.  Uses pygame.image for JPEG / PNG / BMP.
    """
    path = str(path)
    surf = pygame.image.load(path)
    # Convert to canonical format pygame uses for raw bytes
    if surf.get_alpha():
        surf = surf.convert_alpha()
        fmt  = "RGBA"
        gl_fmt = GL_RGBA
    else:
        surf = surf.convert(24)
        fmt  = "RGB"
        gl_fmt = GL_RGB

    w, h = surf.get_size()
    data = pygame.image.tostring(surf, fmt, flip_v)

    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    glTexImage2D(GL_TEXTURE_2D, 0, gl_fmt, w, h, 0, gl_fmt, GL_UNSIGNED_BYTE, data)

    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER,
                    GL_LINEAR_MIPMAP_LINEAR if mipmap else GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wrap_s)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wrap_t)

    if mipmap:
        glGenerateMipmap(GL_TEXTURE_2D)

    glBindTexture(GL_TEXTURE_2D, 0)
    print(f"[tex] loaded {Path(path).name:<28} {w}×{h}")
    return tex


def bind_texture_unit(unit: int, tex_id: int) -> None:
    """Bind texture to a numbered texture unit (0-based)."""
    glActiveTexture(GL_TEXTURE0 + unit)
    glBindTexture(GL_TEXTURE_2D, tex_id)
