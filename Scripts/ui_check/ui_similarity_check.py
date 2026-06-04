#!/usr/bin/env python3
"""
ui_similarity_check.py — objective "visual match score" for the IRIS UI upgrade.

Compares a rendered HUD screenshot against the inspiration images and prints a
0–100 score, so the redesign loop has a metric instead of pure eyeballing.

The window aspect (≈1.55:1) differs from the ChatGPT inspiration crops
(≈1.42:1), and the inspiration adds elements the app doesn't (logo, suggestion
list). So a raw full-frame SSIM would be dominated by layout mismatch and is a
poor *absolute* truth — but a STABLE, consistently-preprocessed blend of
structure + palette + tone is a good *relative* signal: as the app moves from
dark/flat to warm/light/elevated, the score climbs. Treat it as a progress
gauge, not ground truth; the eye is still the final judge.

Score = 100 * (0.45*SSIM + 0.30*palette + 0.15*brightness + 0.10*warmth),
each sub-metric in 0..1, reported individually. No scipy/skimage required —
SSIM uses a PIL box-blur windowing; everything else is numpy.

Usage:
    python Scripts/ui_check/ui_similarity_check.py CURRENT.png [REF1.png REF2 ...]
    # with no refs, auto-globs "ChatGPT Image*.png" at the repo root
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parents[2]
TARGET = (768, 540)            # common canvas; both images stretched to this
_C1 = (0.01 * 255) ** 2
_C2 = (0.03 * 255) ** 2


def _load(path: str, size=TARGET) -> Image.Image:
    im = Image.open(path).convert("RGB")
    # Flatten onto white in case of alpha-derived fringes (PNG already RGB here).
    return im.resize(size, Image.LANCZOS)


def _box(arr: np.ndarray, radius: int = 7) -> np.ndarray:
    """Local mean via PIL BoxBlur (separable, fast) on a float plane."""
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.BoxBlur(radius)), dtype=np.float64)


def ssim(a_gray: np.ndarray, b_gray: np.ndarray, radius: int = 7) -> float:
    """Windowed SSIM (uniform window) — global mean of the SSIM map."""
    a = a_gray.astype(np.float64)
    b = b_gray.astype(np.float64)
    mu_a, mu_b = _box(a, radius), _box(b, radius)
    mu_a2, mu_b2, mu_ab = mu_a * mu_a, mu_b * mu_b, mu_a * mu_b
    sa = _box(a * a, radius) - mu_a2
    sb = _box(b * b, radius) - mu_b2
    sab = _box(a * b, radius) - mu_ab
    num = (2 * mu_ab + _C1) * (2 * sab + _C2)
    den = (mu_a2 + mu_b2 + _C1) * (sa + sb + _C2)
    return float(np.clip((num / den).mean(), 0.0, 1.0))


def _gray(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.299, 0.587, 0.114])


def palette_match(a: np.ndarray, b: np.ndarray, bins: int = 6) -> float:
    """Histogram-intersection over a coarse RGB cube — overall colour agreement."""
    def hist(x):
        idx = np.clip((x / 256 * bins).astype(int), 0, bins - 1)
        flat = (idx[..., 0] * bins + idx[..., 1]) * bins + idx[..., 2]
        h = np.bincount(flat.ravel(), minlength=bins ** 3).astype(np.float64)
        return h / h.sum()
    ha, hb = hist(a), hist(b)
    return float(np.minimum(ha, hb).sum())


def score(cur_path: str, ref_paths: list[str]) -> dict:
    cur = _load(cur_path)
    cur_rgb = np.asarray(cur, dtype=np.float64)
    cur_gray = _gray(cur_rgb)

    subs = []
    for rp in ref_paths:
        ref_rgb = np.asarray(_load(rp), dtype=np.float64)
        ref_gray = _gray(ref_rgb)
        s_struct = ssim(cur_gray, ref_gray)
        s_pal = palette_match(cur_rgb, ref_rgb)
        # brightness: closeness of mean luma (the "too dark" axis)
        b_cur, b_ref = cur_gray.mean(), ref_gray.mean()
        s_bright = 1.0 - abs(b_cur - b_ref) / 255.0
        # warmth: closeness of mean (R-B) — the gold/warm axis
        w_cur = (cur_rgb[..., 0] - cur_rgb[..., 2]).mean()
        w_ref = (ref_rgb[..., 0] - ref_rgb[..., 2]).mean()
        s_warm = 1.0 - min(1.0, abs(w_cur - w_ref) / 40.0)
        total = 0.45 * s_struct + 0.30 * s_pal + 0.15 * s_bright + 0.10 * s_warm
        subs.append({
            "ref": Path(rp).name, "ssim": s_struct, "palette": s_pal,
            "brightness": s_bright, "warmth": s_warm, "score": total * 100,
            "_mean_luma": b_cur, "_mean_luma_ref": b_ref,
        })

    best = max(subs, key=lambda d: d["score"])
    avg = sum(d["score"] for d in subs) / len(subs)
    return {"per_ref": subs, "best": best, "avg": avg}


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cur = sys.argv[1]
    refs = sys.argv[2:] or sorted(glob.glob(str(REPO / "ChatGPT Image*.png")))
    if not refs:
        print("no reference images found")
        sys.exit(1)
    res = score(cur, refs)
    print(f"\n  CANDIDATE: {Path(cur).name}")
    print(f"  {'reference':<34} {'SSIM':>6} {'palette':>8} {'bright':>7} {'warmth':>7} {'score':>7}")
    print("  " + "-" * 74)
    for d in res["per_ref"]:
        print(f"  {d['ref']:<34} {d['ssim']:>6.3f} {d['palette']:>8.3f} "
              f"{d['brightness']:>7.3f} {d['warmth']:>7.3f} {d['score']:>7.1f}")
    print("  " + "-" * 74)
    print(f"  BEST score : {res['best']['score']:.1f}  (vs {res['best']['ref']})")
    print(f"  AVG score  : {res['avg']:.1f}")
    print(f"  cand mean-luma {res['per_ref'][0]['_mean_luma']:.0f} | "
          f"ref mean-luma {res['per_ref'][0]['_mean_luma_ref']:.0f}\n")


if __name__ == "__main__":
    main()
