#!/usr/bin/env python3
"""
make_earth_icon.py — draw a little cartoon Earth and apply it as the custom
Finder icon of the "Parallax Wall" desktop shortcut.

  • Generates assets/icon/earth_icon.png  (1024², transparent).
  • Sets it as the file icon of  ~/Desktop/Parallax Wall.command  via
    NSWorkspace.setIcon:forFile:options: (pyobjc).

Fully vectorised with numpy — no per-pixel Python loops (the old version
allocated 2048² and looped in Python, which OOM-killed on 8 GB). This renders a
1024² icon in a fraction of a second with a few MB of working set.

Re-run:  .venv/bin/python scripts/make_earth_icon.py
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

HERE      = Path(__file__).resolve().parent
ICON_DIR  = HERE.parent / "assets" / "icon"
ICON_PNG  = ICON_DIR / "earth_icon.png"
SHORTCUT  = Path.home() / "Desktop" / "Parallax Wall.command"

N  = 1024
R  = 0.46 * N            # globe radius (px)
CX = CY = N / 2.0


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def draw_globe() -> Image.Image:
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    px = xx - CX
    py = yy - CY
    dist = np.hypot(px, py)

    # Sphere normal (z toward viewer). Outside the disc nz is clamped to 0.
    nx = np.clip(px / R, -1, 1)
    ny = np.clip(py / R, -1, 1)
    nz = np.sqrt(np.clip(1.0 - nx * nx - ny * ny, 0.0, 1.0))

    # Light from upper-left, slightly toward viewer.
    L = np.array([-0.45, -0.55, 0.70], np.float32)
    L /= np.linalg.norm(L)
    lambert = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0.0, 1.0)
    shade   = 0.30 + 0.70 * lambert            # ambient + diffuse

    # ── Continents: union of soft circular blobs in normalised globe space ──
    # Coordinates normalised to [-1,1] across the globe so shapes are resolution
    # independent. Each continent is a cluster of overlapping discs (cartoon).
    u = px / R
    v = py / R
    blobs = [
        # (cx, cy, r)  — clusters that read as friendly landmasses
        (-0.42, -0.30, 0.26), (-0.30, -0.42, 0.18), (-0.20, -0.18, 0.20),
        ( 0.30, -0.18, 0.24), ( 0.42, -0.32, 0.16), ( 0.22,  0.02, 0.16),
        (-0.10,  0.40, 0.22), (-0.26,  0.50, 0.14), ( 0.06,  0.52, 0.15),
        ( 0.42,  0.34, 0.18), ( 0.55,  0.22, 0.12),
    ]
    land = np.zeros((N, N), np.float32)
    for bx, by, br in blobs:
        d = np.hypot(u - bx, v - by)
        land = np.maximum(land, _smoothstep(br, br - 0.05, d))   # soft edge

    # ── Colours ───────────────────────────────────────────────────────────────
    ocean_lit = np.array([90, 190, 240], np.float32)
    ocean_dk  = np.array([14, 54, 120],  np.float32)
    land_lit  = np.array([120, 205, 120], np.float32)
    land_dk   = np.array([40, 110, 58],   np.float32)

    s = shade[..., None]
    ocean = ocean_dk + (ocean_lit - ocean_dk) * s
    grass = land_dk + (land_lit - land_dk) * s
    rgb = ocean * (1.0 - land[..., None]) + grass * land[..., None]

    # Specular gloss highlight (small bright spot upper-left).
    H = L + np.array([0, 0, 1], np.float32)
    H /= np.linalg.norm(H)
    spec = np.clip(nx * H[0] + ny * H[1] + nz * H[2], 0.0, 1.0) ** 48.0
    rgb += (255.0 - rgb) * (spec[..., None] * 0.6)

    rgb = np.clip(rgb, 0, 255)

    # ── Alpha: anti-aliased globe disc + soft outer atmosphere glow ──────────
    aa = 1.5
    disc = _smoothstep(R + aa, R - aa, dist)                    # 1 inside globe
    glow = np.exp(-np.clip(dist - R, 0, None) / (R * 0.10)) * 0.55
    glow *= _smoothstep(R * 1.35, R, dist)                       # fade out
    alpha = np.clip(disc + glow * (1.0 - disc), 0.0, 1.0)

    # Tint the glow ring blue where it's outside the globe.
    glow_rgb = np.array([110, 180, 255], np.float32)
    outside = (1.0 - disc)[..., None]
    rgb = rgb * (1.0 - outside) + glow_rgb * outside

    out = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def apply_icon(png_path: Path, target: Path) -> bool:
    try:
        from AppKit import NSImage, NSWorkspace
    except Exception as e:                       # pragma: no cover
        print(f"[icon] pyobjc unavailable: {e}")
        return False
    if not target.exists():
        print(f"[icon] target not found: {target}")
        return False
    image = NSImage.alloc().initWithContentsOfFile_(str(png_path))
    if image is None:
        print("[icon] failed to load PNG into NSImage")
        return False
    ok = NSWorkspace.sharedWorkspace().setIcon_forFile_options_(image, str(target), 0)
    print(f"[icon] setIcon → {target.name}: {'OK' if ok else 'FAILED'}")
    return bool(ok)


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    print("[icon] drawing cartoon Earth (vectorised)…")
    img = draw_globe()
    img.save(ICON_PNG)
    print(f"[icon] wrote {ICON_PNG} ({os.path.getsize(ICON_PNG)//1024} KB)")
    apply_icon(ICON_PNG, SHORTCUT)


if __name__ == "__main__":
    main()
