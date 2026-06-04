#!/usr/bin/env python3
"""
render_wb.py — headless render of the IRIS HUD to a PNG.

The whole overlay is composed onto an offscreen ``pygame.Surface`` by
``DemoOverlay.render_surface()`` with NO GL context, webcam, or visible window,
so we can render any tab/view to disk in a dummy-video SDL process and diff it
against the inspiration images (see ui_similarity_check.py).

Usage:
    python Scripts/ui_check/render_wb.py [--tab world_builder] [--view grid]
                                         [--out Scripts/ui_check/out/current.png]
                                         [--w 1180] [--h 760] [--scale 2.0]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Offscreen SDL — no window, no audio. MUST be set before pygame is imported.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pygame  # noqa: E402


def render(tab: str, view: str, w: int, h: int, scale: float,
           prompt: str = "") -> "pygame.Surface":
    pygame.init()
    pygame.font.init()
    # dummy driver still needs a surface created before fonts/blits behave
    pygame.display.set_mode((1, 1))

    from UI.demo_overlay import DemoOverlay

    ov = DemoOverlay(w, h, scale=scale, daemon_running=False, desktop_paused=False)
    ov._active_tab = tab
    if tab == "world_builder":
        ov._wb_view = view
    ov._wb_prompt = prompt
    ov._wb_focused = False
    ov._ctrl_alpha = 1.0
    ov._compute_layout()
    return ov.render_surface()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab", default="world_builder")
    ap.add_argument("--view", default="grid")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out" / "current.png"))
    ap.add_argument("--w", type=int, default=1180)
    ap.add_argument("--h", type=int, default=760)
    ap.add_argument("--scale", type=float, default=2.0)
    ap.add_argument("--prompt", default="")
    args = ap.parse_args()

    surf = render(args.tab, args.view, args.w, args.h, args.scale, args.prompt)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surf, str(out))
    print(f"[render_wb] {surf.get_width()}x{surf.get_height()} -> {out}")


if __name__ == "__main__":
    main()
