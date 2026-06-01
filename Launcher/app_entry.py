#!/usr/bin/env python3
"""
launcher.py — Iris entry point (thin router).

The .app bundle's executable runs THIS. It does almost nothing itself — it just
decides which engine mode to run:

  • PARALLAX_MODE=wallpaper|fullscreen  → run the background engine directly.
    (This is how the frozen app re-invokes itself for the desktop daemon, so a
    single bundled binary serves both the onboarding window and the wallpaper.)

  • otherwise  → run the engine in `demo` mode, which hosts the LIVE Earth with
    the light/glass onboarding overlay (overlay_ui.py) composited on top. The
    whole first-launch experience — alive demo → camera primer → activation →
    "Enable Desktop Mode" — lives in that one window, so the illusion is always
    behind the UI.

No Terminal, no console output, no scripts exposed to the user. The previous
dark 2-D launcher window is intentionally gone; its job is now done in-scene by
the demo overlay.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Under PyInstaller, bundled code/resources live at sys._MEIPASS; in dev the
# project directory is this file's parent's parent (since we're in Launcher/).
HERE = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent.parent)
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def main() -> None:
    mode = os.environ.get("PARALLAX_MODE", "").lower()

    # NOTE: app_engine.py reads PARALLAX_MODE at import time, so the env must be set
    # before `import app_engine`.
    if mode not in ("wallpaper", "fullscreen", "demo"):
        os.environ["PARALLAX_MODE"] = "demo"

    from Launcher.app_engine import main as engine_main
    engine_main()


if __name__ == "__main__":
    main()
