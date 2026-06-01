#!/usr/bin/env python3
"""
map_photo_eye.py — Map the supplied eye photo onto the equirectangular sphere
texture used by "The Watcher" world in Engine/renderer.py.

Projection: orthographic (parallel projection from +Z).  The photo center
(iris/pupil) maps to UV (0.25, 0.50) — the +Z camera-facing pole on the
equirectangular sphere produced by make_sphere().  Using the photo's shorter
dimension (width) as the hemisphere diameter so the full horizontal extent of
the photo fills the sphere's visible face without stretching.

Outputs (assets/the_watcher/):
    eye_diffuse.png   — albedo from photo, equirectangular 2048×1024
    eye_normal.png    — tangent-space normal map derived from diffuse luminance
    eye_specular.png  — cornea/iris gloss mask (same angular definition as before)

The normal and specular maps are regenerated so they align with the new texture;
no shader changes are made.
"""

from __future__ import annotations
from pathlib import Path

import numpy as np
from PIL import Image

HERE   = Path(__file__).resolve().parents[2]
SOURCE = HERE / "assets" / "the_watcher" / "ChatGPT Image Jun 1, 2026, 01_30_14 AM.png"
OUT    = HERE / "assets" / "the_watcher"

RES_W, RES_H = 2048, 1024

# Iris cap angular radius — kept identical to gen_eye_textures.py so the
# specular map (cornea gloss mask) aligns with the iris in the photo.
IRIS_HALF_ANG  = np.radians(25.0)
LIMBUS_FEATHER = np.radians(5.0)

# Normal map relief strength — kept at the same value as the previous texture.
NORMAL_STRENGTH = 4.5


def _smoothstep(a: float | np.ndarray, b: float | np.ndarray,
                x: np.ndarray) -> np.ndarray:
    t = np.clip((x - a) / (b - a + 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def main() -> None:
    # ── Load source photo ──────────────────────────────────────────────────────
    src = Image.open(SOURCE).convert("RGB")
    src_w, src_h = src.size
    src_arr = np.array(src, dtype=np.float32) / 255.0
    # Compute luminance for eye region detection
    lum = (src_arr * [0.2126, 0.7152, 0.0722]).sum(axis=2)
    print(f"[eye] source: {SOURCE.name}  {src_w}×{src_h}")

    # ── Equirectangular grid → unit sphere directions ──────────────────────────
    # Convention from Engine/renderer.py make_sphere():
    #   theta = u * 2π  (longitude)
    #   phi   = v * π   (colatitude, 0 = +Y pole)
    #   sx = sin(phi)*cos(theta)   Y-right
    #   sy = cos(phi)              Y-up
    #   sz = sin(phi)*sin(theta)   +Z = camera-facing iris center, at (u=0.25, v=0.50)
    u = (np.arange(RES_W) + 0.5) / RES_W
    v = (np.arange(RES_H) + 0.5) / RES_H
    uu, vv = np.meshgrid(u, v)
    theta = uu * 2.0 * np.pi
    phi   = vv * np.pi
    sx = np.sin(phi) * np.cos(theta)
    sy = np.cos(phi)
    sz = np.sin(phi) * np.sin(theta)   # +1 = iris center front, -1 = back

    # Angular distance from +Z — used for specular mask.
    gamma = np.arccos(np.clip(sz, -1.0, 1.0))

    # ── Orthographic photo projection ──────────────────────────────────────────
    # Orthographic projects the front hemisphere as a unit disk:
    #   (sx, sy) are the projected x/y coords, both in [-1, +1].
    # Scale: use width/2 as the hemisphere radius in pixels so the photo's
    # full horizontal span fills the visible sphere face.
    # Compute centroid of the bright eye region (ignore black background)
    thresh = 0.1  # luminance threshold (0‑1)
    mask = lum > thresh
    ys, xs = np.where(mask)
    if len(xs) == 0:
        # fallback to image centre if no bright region detected
        cx = src_w / 2.0
        cy = src_h / 2.0
    else:
        cx = float(xs.mean())
        cy = float(ys.mean())
    # Zoom factor: proportion of image width visible on sphere (0‑1). Smaller => more zoom.
    ZOOM = 0.25  # show ~25% of width, cropping black border
    half = src_w * ZOOM

    # Debug output
    print(f"[debug] cx={cx:.2f}, cy={cy:.2f}, half={half:.2f}")
    # Photo sample coords in pixel space (float, before integer lookup).
    #   +sx → right in photo  (photo x increases rightward)
    #   +sy → up on sphere  → up in real space → smaller y in image (y=0 = top)
    px = cx + sx * half          # 0 … src_w
    py = cy - sy * half          # 0 … src_h  (inverted: +up → smaller y)

    # Clamp to valid photo bounds.
    px = np.clip(px, 0.0, src_w - 1.0)
    py = np.clip(py, 0.0, src_h - 1.0)

    # Bilinear interpolation.
    x0 = np.floor(px).astype(np.int32)
    y0 = np.floor(py).astype(np.int32)
    x1 = np.minimum(x0 + 1, src_w - 1)
    y1 = np.minimum(y0 + 1, src_h - 1)
    fx = (px - x0)[..., None].astype(np.float32)
    fy = (py - y0)[..., None].astype(np.float32)

    sampled = (src_arr[y0, x0] * (1.0 - fx) * (1.0 - fy)
             + src_arr[y0, x1] *        fx   * (1.0 - fy)
             + src_arr[y1, x0] * (1.0 - fx) *        fy
             + src_arr[y1, x1] *        fx   *        fy)

    # Back hemisphere (sz < 0) → pure black (void; never normally visible).
    front = (sz >= 0.0)[..., None].astype(np.float32)
    diffuse = np.clip(sampled * front, 0.0, 1.0)

    # ── Normal map from diffuse luminance ──────────────────────────────────────
    lum = diffuse.mean(axis=2).astype(np.float32)
    gy, gx = np.gradient(lum)
    nx = -gx * NORMAL_STRENGTH
    ny = -gy * NORMAL_STRENGTH
    nz = np.ones_like(nx)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    normal_rgb = np.clip(np.stack([nx * inv, ny * inv, nz * inv], axis=-1) * 0.5 + 0.5,
                         0.0, 1.0)

    # ── Specular / cornea gloss mask ───────────────────────────────────────────
    # High gloss (≈0.98) over the iris cap (same angular radius as before so the
    # iris emission term and wet-glass specular in eye.frag stay aligned with the
    # actual iris area in the photo).  Sclera stays at ≈0.20.
    cornea = 1.0 - _smoothstep(IRIS_HALF_ANG - LIMBUS_FEATHER,
                                IRIS_HALF_ANG + LIMBUS_FEATHER, gamma)
    spec = np.clip(0.20 + 0.78 * cornea, 0.0, 1.0)
    # Zero on back hemisphere.
    spec *= (sz >= 0.0).astype(np.float32)

    # ── Write outputs ──────────────────────────────────────────────────────────
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray((diffuse     * 255 + 0.5).astype(np.uint8)).save(OUT / "eye_diffuse.png")
    Image.fromarray((normal_rgb  * 255 + 0.5).astype(np.uint8)).save(OUT / "eye_normal.png")
    Image.fromarray((spec        * 255 + 0.5).astype(np.uint8)).save(OUT / "eye_specular.png")

    print(f"[eye] wrote eye_diffuse / eye_normal / eye_specular "
          f"({RES_W}×{RES_H}) → {OUT}")


if __name__ == "__main__":
    main()
