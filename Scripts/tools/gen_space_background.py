#!/usr/bin/env python3
"""
gen_space_background.py — generate the deep-space skydome backdrop.

Produces an equirectangular (2:1) image of space — soft nebula clouds, a faint
Milky-Way band, and a dusting of background stars — written to
    assets/stars/space_background.jpg

Design goals:
  • Lightweight: pure numpy + Pillow, no downloads, ~0.5 MB JPG, 4K equirect.
  • Seamless: all cloud noise is periodic in the horizontal (longitude) axis so
    the texture wraps cleanly on the inside-rendered Nebula sphere (no seam).
  • Tasteful: this is the BACKDROP. The crisp foreground stars come from the
    parallax `Stars` layer, so the stars here are deliberately faint/small and
    the nebula is restrained — it reads as deep space, not a poster.

Re-run any time:  .venv/bin/python scripts/gen_space_background.py
"""
from __future__ import annotations

import os
import numpy as np
from PIL import Image, ImageFilter

W, H = 4096, 2048
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "stars", "space_background.jpg")
OUT = os.path.normpath(OUT)

rng = np.random.default_rng(20260529)


def wrap_noise(grid_w: int, grid_h: int) -> np.ndarray:
    """Smooth value-noise in [0,1], periodic across the W (longitude) axis."""
    g = rng.random((grid_h, grid_w)).astype(np.float32)
    # Duplicate the first column on the end so bicubic upsampling is continuous
    # across the 0/2pi seam, then crop back to W.
    g = np.concatenate([g, g[:, :1]], axis=1)
    img = Image.fromarray((g * 255).astype(np.uint8), mode="L")
    img = img.resize((W + W // grid_w, H), Image.BICUBIC)
    a = np.asarray(img, dtype=np.float32)[:, :W] / 255.0
    return a


def fbm(octaves) -> np.ndarray:
    """Fractional Brownian motion: sum of wrapping noise octaves."""
    out = np.zeros((H, W), dtype=np.float32)
    amp_sum = 0.0
    for grid_w, grid_h, amp in octaves:
        out += amp * wrap_noise(grid_w, grid_h)
        amp_sum += amp
    out /= amp_sum
    return out


print("building cloud fields…")
# Large soft structure + finer detail, all horizontally periodic.
clouds = fbm([(6, 3, 1.0), (12, 6, 0.55), (24, 12, 0.30), (48, 24, 0.16)])
dust   = fbm([(8, 4, 1.0), (20, 10, 0.5), (40, 20, 0.25)])
tintn  = fbm([(5, 3, 1.0), (10, 6, 0.5)])

# Vertical coordinate 0..1 (latitude) for the Milky-Way band.
vv = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None]
uu = np.linspace(0.0, 1.0, W, dtype=np.float32)[None, :]

# Milky-Way band: a diagonal lane across the sphere, softened and broken up by
# the cloud noise so it isn't a clean stripe.
band_center = 0.52 + 0.12 * np.sin(uu * 2.0 * np.pi)          # gently wavy
band = np.exp(-((vv - band_center) ** 2) / (2.0 * 0.10 ** 2))  # gaussian band
band = band * (0.45 + 0.55 * clouds)                           # mottled

# ── Compose colour ────────────────────────────────────────────────────────────
# Deep-space base: near-black with a faint cool gradient.
base = np.stack([
    np.full((H, W), 3.0, np.float32),
    np.full((H, W), 4.0, np.float32),
    np.full((H, W), 9.0, np.float32),
], axis=-1)

# Cloud nebulosity — two tints (cool teal-blue and a faint warm magenta) chosen
# by the low-frequency tint field, kept dim so it's atmosphere not decoration.
cool = np.array([26.0, 44.0, 78.0], np.float32)   # blue
warm = np.array([60.0, 26.0, 54.0], np.float32)   # muted violet/magenta
c = np.clip((clouds - 0.45) / 0.55, 0.0, 1.0) ** 1.6          # only denser parts glow
tint = tintn[..., None]
neb_color = cool[None, None, :] * (1.0 - tint) + warm[None, None, :] * tint
nebula = neb_color * c[..., None] * 0.9

# Milky-Way band light (slightly warm white) with dark dust lanes subtracted.
band_light = np.array([42.0, 40.0, 46.0], np.float32)
milky = band_light[None, None, :] * band[..., None]
milky *= (0.55 + 0.45 * dust[..., None])           # dust lanes darken the band

img = base + nebula + milky

# ── Background stars (faint + small; the foreground parallax layer has the
#    bright crisp ones, so these just fill the void) ──────────────────────────
print("scattering background stars…")
n_faint = 14000
xs = rng.integers(0, W, n_faint)
ys = rng.integers(0, H, n_faint)
# brightness skewed faint
b = (rng.random(n_faint) ** 3.2) * 150.0 + 12.0
# colour temperature: mostly white, some blue, some warm
temp = rng.random(n_faint)
for x, y, bb, tt in zip(xs, ys, b, temp):
    if tt < 0.65:
        col = (bb, bb, bb)
    elif tt < 0.85:
        col = (bb * 0.78, bb * 0.86, bb)          # blue-white
    else:
        col = (bb, bb * 0.85, bb * 0.66)          # warm
    img[y, x, 0] += col[0]
    img[y, x, 1] += col[1]
    img[y, x, 2] += col[2]

# A few hundred brighter stars with a tiny bloom
n_bright = 320
xb = rng.integers(2, W - 2, n_bright)
yb = rng.integers(2, H - 2, n_bright)
bb2 = rng.random(n_bright) * 90.0 + 150.0
for x, y, val in zip(xb, yb, bb2):
    img[y, x] += val
    img[y - 1:y + 2, x] += val * 0.25
    img[y, x - 1:x + 2] += val * 0.25

img = np.clip(img, 0, 255).astype(np.uint8)
out = Image.fromarray(img, mode="RGB")
# Tiny blur softens star edges & cloud banding without smearing the band.
out = out.filter(ImageFilter.GaussianBlur(0.4))
out.save(OUT, quality=88)
print(f"wrote {OUT}  ({os.path.getsize(OUT)//1024} KB, {W}x{H})")
