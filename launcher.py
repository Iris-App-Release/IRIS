#!/usr/bin/env python3
"""
launcher.py — Iris top-level entry (PyInstaller entry script).

Thin shim so the frozen .app bundle and a plain `python launcher.py` share a
single entry point. It guarantees the project root (or, when frozen,
PyInstaller's sys._MEIPASS) is importable, then defers to
``Launcher.app_entry.main()`` which routes PARALLAX_MODE → engine mode.

The reorg into Engine/ Launcher/ Tracking/ UI/ Worlds/ left the bundle without a
root entry; this restores it without changing any engine behavior.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# matplotlib is pulled in transitively (via mediapipe). In the frozen .app,
# PyInstaller's own runtime hook points MPLCONFIGDIR at an EPHEMERAL per-launch
# temp dir, so matplotlib REBUILDS its font cache on EVERY launch — a multi-second
# (sometimes much longer) stall before the window and tracker even start. Force it
# to a persistent dir under ~/.iris so the cache is built once and reused. This
# entry script runs AFTER PyInstaller's runtime hooks but BEFORE anything imports
# matplotlib, so a hard override here wins. (setdefault would lose to the rth hook.)
_mpl_cache = Path.home() / ".iris" / "mpl-cache"
try:
    _mpl_cache.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(_mpl_cache)
except Exception:
    pass

# Own the macOS camera authorization ourselves (settled on the main thread in
# Tracking/face_tracker.start()) and stop OpenCV from issuing its own request from
# the capture worker thread — where it "can not spin main run loop from other
# thread" and so fails forever. Set as early as possible, before ANY cv2 import.
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

HERE = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent)
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from Launcher.app_entry import main

if __name__ == "__main__":
    main()
