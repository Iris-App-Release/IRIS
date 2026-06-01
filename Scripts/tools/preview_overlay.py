#!/usr/bin/env python3
"""
preview_overlay.py — Render the demo HUD over a synthetic space scene and save
PNGs, so the liquid-glass styling + text crispness can be reviewed without the
live GL window. Compositing here (src-over alpha onto an opaque background)
matches draw_gl's blend, so previews are faithful to the real look.

Run:  .venv/bin/python scripts/preview_overlay.py
Out:  docs/preview/overlay_<state>.png   (rendered at physical/Retina resolution)
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
OUT = HERE / "docs" / "preview"

WIN_W, WIN_H, SCALE = 1180, 760, 2.0


def _scene_bg(w: int, h: int) -> pygame.Surface:
    bg = pygame.Surface((w, h))
    for y in range(h):
        t = y / (h - 1)
        bg.fill((int(4 + 7 * t), int(6 + 4 * t), int(16 + 6 * t)), (0, y, w, 1))
    rng = random.Random(7)
    for _ in range(int(0.0005 * w * h)):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        b = rng.randint(60, 220)
        bg.set_at((x, y), (b, b, min(255, b + 20)))
    ecx, ecy, R = w // 2, int(h * 0.40), int(h * 0.20)
    earth = pygame.Surface((R * 2 + 4, R * 2 + 4), pygame.SRCALPHA)
    for r in range(R, 0, -1):
        t = r / R
        earth_col = (int(20 + 40 * (1 - t)), int(70 + 120 * (1 - t)), int(150 + 60 * (1 - t)))
        pygame.draw.circle(earth, earth_col, (R + 2, R + 2), r)
    pygame.draw.circle(earth, (180, 220, 255, 90), (R + 2, R + 2), R, 3)
    bg.blit(earth, (ecx - R - 2, ecy - R - 2))
    return bg


def _save(name: str, ov) -> Path:
    surf = ov.render_surface()
    frame = _scene_bg(ov.w, ov.h)
    frame.blit(surf, (0, 0))
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"overlay_{name}.png"
    pygame.image.save(frame, str(p))
    return p


def main() -> int:
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    pygame.font.init()

    import overlay_ui as ov_mod
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="iris_prev_"))
    ov_mod.CONFIG_DIR = tmp
    ov_mod.PREFS_FILE = tmp / "preferences.json"
    ov_mod.DAEMON_PID_FILE = tmp / "daemon.pid"
    ov_mod.TRACKING_OFF_FLAG = tmp / "parallax_off"
    from overlay_ui import DemoOverlay

    saved = []

    # 1. Floating preview (first-run: shows the welcome hint)
    o = DemoOverlay(WIN_W, WIN_H, scale=SCALE, daemon_running=False, desktop_paused=False)
    o.hover = "primary"
    o._hover_anim["primary"] = 1.0
    saved.append(_save("1_floating", o))

    # 2. Live tracked (after Enable Camera) — onboarded, status live
    o2 = DemoOverlay(WIN_W, WIN_H, scale=SCALE, daemon_running=False, desktop_paused=False)
    o2.live = True
    o2.onboarded = True
    o2.hover = "primary"
    o2._hover_anim["primary"] = 1.0
    saved.append(_save("2_live", o2))

    # 3. Desktop mode active (reopen with daemon running)
    o3 = DemoOverlay(WIN_W, WIN_H, scale=SCALE, daemon_running=True, desktop_paused=False)
    o3.onboarded = True
    saved.append(_save("3_desktop", o3))

    for p in saved:
        print("saved", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
