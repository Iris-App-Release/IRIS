#!/usr/bin/env python3
"""
gen_eye_textures.py — Build equirectangular eyeball maps for "The Watcher".

Fully synthetic — no photo dependency. The iris is generated procedurally
in the style of the Eye of Cthulhu: a dead-black oval pupil, vivid emerald-
green inner ring transitioning to deep royal-blue outer ring, 64-spoke radial
fiber texture, and a hard limbal ring. The sclera is near-white so the
saturated crimson vein network pops with maximum contrast.

Outputs (assets/the_watcher/):
    eye_diffuse.png   — albedo (sRGB)
    eye_normal.png    — tangent-space normal map (RGB = XYZ, 128/128/255 = flat)
    eye_specular.png  — glossiness / wet-cornea mask (grayscale)

The texture maps onto Engine.renderer.make_sphere() UVs, where the camera-
facing +Z direction is (u, v) = (0.25, 0.50). Re-run after changing any constant.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parents[2]
OUT  = HERE / "assets" / "the_watcher"

# ── Resolution ────────────────────────────────────────────────────────────────
RES_W, RES_H = 2048, 1024

# ── Iris geometry ─────────────────────────────────────────────────────────────
IRIS_HALF_ANG  = np.radians(38.0)    # iris cap angular radius from +Z
LIMBUS_FEATHER = np.radians(5.0)     # iris→sclera blend width
PUPIL_HALF_ANG = np.radians(11.5)    # pupil angular radius

# ── Iris colors (Eye-of-Cthulhu palette) ──────────────────────────────────────
# Gradient: green (inner, around pupil) → blue (outer, at limbus)
IRIS_INNER_RGB  = np.array([0.03, 0.52, 0.18])  # vivid emerald green
IRIS_OUTER_RGB  = np.array([0.05, 0.18, 0.72])  # deep royal blue
COLLARETTE_RGB  = np.array([0.18, 0.62, 0.32])  # lighter green at the collarette ring
PUPIL_RGB       = np.array([0.00, 0.00, 0.00])  # absolute void-black

# ── Sclera / vessel colors ────────────────────────────────────────────────────
SCLERA_RGB     = np.array([0.93, 0.91, 0.92])   # near-white, slight cool grey-blue
LIMBAL_RGB     = np.array([0.10, 0.02, 0.02])   # near-black limbal ring, dark red
VEIN_RGB       = np.array([0.85, 0.01, 0.01])   # vivid arterial red
VEIN_STRENGTH  = 0.95                            # full domination on sclera
ARTERY_RGB     = np.array([0.68, 0.00, 0.00])   # darker major vessel trunks
ARTERY_STRENGTH = 1.00
N_HEMORRHAGE   = 12                              # sub-conjunctival bleeding blotches
HEMM_STRENGTH  = 0.78
HEMM_RGB       = np.array([0.56, 0.00, 0.00])   # deep blood-red

# ── Normal map ────────────────────────────────────────────────────────────────
NORMAL_STRENGTH = 4.5    # vessel-relief bump strength (was 2.8 — more shadow)

SEED = 7


def _smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a + 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _periodic_noise(theta, phi, harmonics, rng, freq_phi=3.0):
    """Smooth noise periodic in longitude (theta). Sum of integer-freq sinusoids."""
    out = np.zeros_like(theta)
    for _ in range(harmonics):
        m  = rng.integers(1, 9)
        ph = rng.uniform(0, 2 * np.pi)
        nf = rng.uniform(0.5, freq_phi)
        qp = rng.uniform(0, 2 * np.pi)
        amp = rng.uniform(0.4, 1.0) / (1 + m * 0.25)
        out += amp * np.sin(m * theta + ph) * np.sin(nf * phi + qp)
    out -= out.min()
    out /= (out.max() + 1e-9)
    return out


def main() -> None:
    rng = np.random.default_rng(SEED)
    print(f"[eye] building {RES_W}x{RES_H} textures (fully synthetic)")

    # ── Equirectangular grid → sphere directions ───────────────────────────────
    u = (np.arange(RES_W) + 0.5) / RES_W
    v = (np.arange(RES_H) + 0.5) / RES_H
    uu, vv = np.meshgrid(u, v)
    theta = uu * 2.0 * np.pi        # longitude
    phi   = vv * np.pi              # latitude (0=+Y pole)
    sx = np.sin(phi) * np.cos(theta)
    sy = np.cos(phi)
    sz = np.sin(phi) * np.sin(theta)  # +Z faces the camera
    gamma = np.arccos(np.clip(sz, -1.0, 1.0))   # angle from +Z (front)
    psi   = np.arctan2(sy, sx)                   # azimuth around +Z

    # ── Synthetic iris cap ────────────────────────────────────────────────────
    # Normalized radius across the iris [0=pole/pupil-center, 1=outer limbus].
    iris_r = np.clip(gamma / IRIS_HALF_ANG, 0.0, 1.0)

    # 1. Radial fiber texture — 64 radial spokes with organic twist.
    #    The twist increases toward the limbus so fibers spiral slightly,
    #    exactly as in real iris anatomy.
    N_FIBERS  = 64
    twist     = iris_r * np.pi * 0.28 + 0.09 * np.sin(7.0 * psi)
    fib_psi   = psi + twist
    f1 = 0.5 + 0.5 * np.cos(N_FIBERS       * fib_psi)
    f2 = 0.5 + 0.5 * np.cos(N_FIBERS * 1.5 * fib_psi + 0.7)
    f3 = 0.5 + 0.5 * np.cos(N_FIBERS * 0.5 * fib_psi + 1.3)
    fibers      = f1 * 0.50 + f2 * 0.30 + f3 * 0.20   # 0=dark gap, 1=bright fiber
    # Fibers are strongest in the mid-iris; fade at the pupil boundary.
    fiber_atten = _smoothstep(np.radians(8.0), IRIS_HALF_ANG * 0.65, gamma)
    # Darker between fibers (the sulci / furrows of the iris stroma).
    fiber_dark  = (1.0 - fibers) * 0.40 * fiber_atten

    # 2. Green (inner) → blue (outer) color gradient across iris.
    iris_zone = _smoothstep(PUPIL_HALF_ANG, IRIS_HALF_ANG, gamma)   # 0=inner, 1=outer
    iris_base = (IRIS_INNER_RGB[None, None, :] * (1.0 - iris_zone[..., None])
               + IRIS_OUTER_RGB[None, None, :] *        iris_zone[..., None])

    # 3. Collarette: a lighter ring at ~28% iris radius — the boundary between
    #    the pupillary and ciliary zones, visible in real irises as a lighter
    #    or more irregular band.
    collar_gamma = 0.28 * IRIS_HALF_ANG
    collar       = np.exp(-((gamma - collar_gamma) / np.radians(2.8)) ** 2) * 0.42
    collar_in_iris = collar * _smoothstep(np.radians(6.0), np.radians(14.0), gamma)
    iris_base = (iris_base * (1.0 - collar_in_iris[..., None])
               + COLLARETTE_RGB[None, None, :] * collar_in_iris[..., None])

    # 4. Apply fiber texture (sulcal darkening).
    iris_rgb = iris_base * (1.0 - fiber_dark[..., None])

    # 5. Pupil fade to absolute black — smooth but decisive.
    pupil_alpha = _smoothstep(np.radians(6.5), PUPIL_HALF_ANG, gamma)
    iris_rgb    = iris_rgb * pupil_alpha[..., None]

    # ── Sclera + bloodshot vein network ───────────────────────────────────────
    warp       = (_periodic_noise(theta, phi, 5, rng) - 0.5) * 0.6
    base_noise = _periodic_noise(theta + warp, phi, 4, rng)
    # Near-white base — tight variation so vivid red veins pop at full contrast.
    sclera = SCLERA_RGB[None, None, :] * (0.97 + 0.03 * base_noise[..., None])

    # Density mask: veins crowd right up to the iris boundary for maximum horror.
    periph    = _smoothstep(IRIS_HALF_ANG + np.radians(1.0), np.radians(95.0), gamma)
    pole_damp = np.sin(phi) ** 0.5

    # Fine capillary network (high-frequency ridge noise).
    vein_field = _periodic_noise(theta + warp * 1.7, phi, 7, rng, freq_phi=6.0)
    ridges     = 1.0 - np.abs(2.0 * vein_field - 1.0)
    veins      = np.clip((ridges - 0.50) / 0.50, 0.0, 1.0) ** 0.72
    vein_mask  = veins * periph * pole_damp * VEIN_STRENGTH
    sclera     = (sclera  * (1.0 - vein_mask[..., None])
                + VEIN_RGB[None, None, :] * vein_mask[..., None])

    # Major artery trunks (few, thick, unmissable highways across the sclera).
    artery_field = _periodic_noise(theta + warp * 0.5, phi, 3, rng, freq_phi=1.8)
    a_ridges     = 1.0 - np.abs(2.0 * artery_field - 1.0)
    arteries     = np.clip((a_ridges - 0.74) / 0.26, 0.0, 1.0) ** 0.95
    artery_mask  = arteries * periph * pole_damp * ARTERY_STRENGTH
    sclera       = (sclera * (1.0 - artery_mask[..., None])
                  + ARTERY_RGB[None, None, :] * artery_mask[..., None])

    # Sub-conjunctival hemorrhage blotches — irregular dark-blood-red patches.
    hemm_rng  = np.random.default_rng(SEED + 42)
    hemm_mask = np.zeros((RES_H, RES_W), dtype=np.float32)
    for _ in range(N_HEMORRHAGE):
        ang      = hemm_rng.uniform(IRIS_HALF_ANG + LIMBUS_FEATHER,
                                    np.radians(135.0))
        az       = hemm_rng.uniform(0.0, 2.0 * np.pi)
        bx       = np.sin(ang) * np.cos(az)
        by       = np.cos(ang)
        bz       = np.sin(ang) * np.sin(az)
        dot      = np.clip(sx * bx + sy * by + sz * bz, -1.0, 1.0)
        blob_rad = hemm_rng.uniform(np.radians(7.0), np.radians(24.0))
        falloff  = np.clip((np.arccos(dot) - blob_rad) / np.radians(10.0), 0.0, 1.0)
        blob     = (1.0 - falloff) ** 2.5
        blob    *= _smoothstep(IRIS_HALF_ANG, IRIS_HALF_ANG + LIMBUS_FEATHER * 0.5, gamma)
        hemm_mask = np.maximum(hemm_mask, blob * hemm_rng.uniform(0.5, 1.0))
    hemm_mask = np.clip(hemm_mask * HEMM_STRENGTH, 0.0, 1.0)
    sclera    = (sclera * (1.0 - hemm_mask[..., None])
               + HEMM_RGB[None, None, :] * hemm_mask[..., None])

    # Limbal ring — hard dark boundary at the iris/sclera transition.
    ring   = np.exp(-((gamma - IRIS_HALF_ANG) / (LIMBUS_FEATHER * 0.75)) ** 2)
    sclera = (sclera * (1.0 - 0.60 * ring[..., None])
            + LIMBAL_RGB[None, None, :] * (0.60 * ring[..., None]))

    # ── Composite iris cap onto sclera across the limbus ──────────────────────
    w_iris  = 1.0 - _smoothstep(IRIS_HALF_ANG - LIMBUS_FEATHER, IRIS_HALF_ANG, gamma)
    w_iris  = w_iris[..., None]
    diffuse = iris_rgb * w_iris + sclera * (1.0 - w_iris)
    diffuse = np.clip(diffuse, 0.0, 1.0)

    # ── Normal map from luminance + vein mask ─────────────────────────────────
    lum    = diffuse.mean(axis=2)
    height = lum * 0.45 + vein_mask * 0.55   # vessels sit proud
    gy, gx = np.gradient(height.astype(np.float32))
    nx  = -gx * NORMAL_STRENGTH
    ny  = -gy * NORMAL_STRENGTH
    nz  = np.ones_like(nx)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    normal     = np.stack([nx * inv, ny * inv, nz * inv], axis=-1)
    normal_rgb = normal * 0.5 + 0.5

    # ── Specular: glass cornea over iris, moist but dull sclera ──────────────
    # High gloss over the entire iris cap (pupil too — the corneal lens covers it).
    # The shader uses this mask both for the wet specular highlight and for the
    # iris-emission term in eye.frag.
    cornea = 1.0 - _smoothstep(IRIS_HALF_ANG - LIMBUS_FEATHER,
                                IRIS_HALF_ANG + LIMBUS_FEATHER, gamma)
    spec   = 0.20 + 0.78 * cornea    # sclera ~0.20, cornea ~0.98
    spec   = spec * (0.96 + 0.04 * base_noise)
    spec   = np.clip(spec, 0.0, 1.0)

    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray((diffuse    * 255 + 0.5).astype(np.uint8)).save(OUT / "eye_diffuse.png")
    Image.fromarray((normal_rgb * 255 + 0.5).astype(np.uint8)).save(OUT / "eye_normal.png")
    Image.fromarray((spec       * 255 + 0.5).astype(np.uint8)).save(OUT / "eye_specular.png")
    print(f"[eye] wrote eye_diffuse.png / eye_normal.png / eye_specular.png "
          f"({RES_W}x{RES_H}) to {OUT}")


if __name__ == "__main__":
    main()
