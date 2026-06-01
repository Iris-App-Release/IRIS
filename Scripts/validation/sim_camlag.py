#!/usr/bin/env python3
"""
sim_camlag.py — Headless validation of the frame-rate-independent camera
smoothing (CAM_LAG → exponential time-constant).

No camera, no GL. Drives the SAME smoothing math the main loop uses
(`cam += alpha·(target − cam)` with `alpha = 1 − e^(−dt/CAM_LAG_TAU)`) on a
step input at 30 fps and 60 fps and proves the property the 2026-06-01 latency
audit asked for:

  1. BACKWARD COMPATIBILITY — at the 60 fps reference rate the dt-aware factor
     equals the legacy fixed factor CAM_LAG (0.55) to float precision, so the
     calibrated demo feel is preserved byte-for-byte.
  2. FRAME-RATE INDEPENDENCE — the wall-clock time to reach 90 % of a step is
     the SAME at 30 fps and 60 fps (the bug: it used to be ~2× slower at 30).
  3. The OLD fixed-factor scheme was frame-rate DEPENDENT — reproduced here to
     document exactly what is being fixed (30 fps was ~2× the 60 fps lag).
  4. The dt clamp (CAM_LAG_DT_MAX) bounds the per-frame step so a long stall
     (resume-from-pause / first frame) cannot snap to target in a single frame.

Run:  .venv/bin/python Scripts/validation/sim_camlag.py
Exit 0 = all checks pass, 1 = a check failed.
"""
from __future__ import annotations

# --- reorg path shim (validation harness) ---
import sys as _s
from pathlib import Path as _P
_root = str(_P(__file__).resolve().parents[2])
if _root not in _s.path:
    _s.path.insert(0, _root)

import math
import sys

from Launcher.app_engine import (
    CAM_LAG, CAM_LAG_REF_FPS, CAM_LAG_TAU, CAM_LAG_DT_MAX,
)

_fail = 0
def check(name: str, ok: bool, detail: str = "") -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)


def alpha_dt(dt: float) -> float:
    """The main loop's per-frame smoothing factor (with the dt clamp)."""
    return 1.0 - math.exp(-min(dt, CAM_LAG_DT_MAX) / CAM_LAG_TAU)


def lag_ms(fps: float, factor_fn, target: float = 1.0, reach: float = 0.9) -> float:
    """Wall-clock ms for a first-order filter to reach `reach` of a unit step.

    `factor_fn(dt)` returns the per-frame lerp factor; `fps` sets dt and the
    ms-per-frame conversion."""
    dt = 1.0 / fps
    s = 0.0
    frames = 0
    while s < reach * target and frames < 100000:
        s += factor_fn(dt) * (target - s)
        frames += 1
    return frames * (1000.0 / fps)


def main() -> int:
    print("frame-rate-independent camera smoothing (CAM_LAG → tau)")
    print(f"  legacy factor CAM_LAG={CAM_LAG}  ref={CAM_LAG_REF_FPS:.0f}fps"
          f"  tau={CAM_LAG_TAU*1000:.2f}ms  dt_max={CAM_LAG_DT_MAX*1000:.0f}ms")
    print()

    # ── 1. Backward compatibility at the reference rate ──────────────────────
    print("1. At the 60 fps reference rate the dt-aware factor equals legacy 0.55")
    a60 = alpha_dt(1.0 / CAM_LAG_REF_FPS)
    check("alpha(1/60) == CAM_LAG to float precision",
          abs(a60 - CAM_LAG) < 1e-9, f"alpha={a60:.9f}  CAM_LAG={CAM_LAG}")

    # ── 2. Frame-rate independence (the fix) ─────────────────────────────────
    print("\n2. Wall-clock 90% lag is the SAME at 30 and 60 fps (dt-aware)")
    l30 = lag_ms(30.0, alpha_dt)
    l60 = lag_ms(60.0, alpha_dt)
    # Equal up to one frame of 30 fps quantisation (~33 ms).
    check("30 fps and 60 fps reach 90% in the same wall-clock time",
          abs(l30 - l60) <= 1000.0 / 30.0 + 1e-6,
          f"30fps {l30:.1f}ms  vs  60fps {l60:.1f}ms")

    # ── 3. The OLD fixed-factor scheme WAS frame-rate dependent (the bug) ─────
    print("\n3. The old fixed 0.55-per-frame scheme was frame-rate dependent")
    fixed = lambda dt: CAM_LAG          # noqa: E731 — old behaviour: ignores dt
    f30 = lag_ms(30.0, fixed)
    f60 = lag_ms(60.0, fixed)
    check("old scheme: 30 fps lag was ~2× the 60 fps lag",
          f30 >= f60 * 1.8, f"30fps {f30:.1f}ms  vs  60fps {f60:.1f}ms")
    # And the fix actually improves the 30 fps case versus the old scheme.
    check("dt-aware 30 fps lag is lower than the old fixed 30 fps lag",
          l30 < f30, f"dt-aware {l30:.1f}ms  vs  fixed {f30:.1f}ms")

    # ── 4. dt clamp prevents a one-frame snap on a long stall ────────────────
    print("\n4. The dt clamp bounds a long-stall step (no one-frame snap)")
    a_big = alpha_dt(5.0)               # a 5 s stall, clamped to CAM_LAG_DT_MAX
    a_cap = 1.0 - math.exp(-CAM_LAG_DT_MAX / CAM_LAG_TAU)
    check("a huge dt is clamped to the CAM_LAG_DT_MAX factor",
          abs(a_big - a_cap) < 1e-9 and a_big < 1.0,
          f"alpha(5s)={a_big:.4f}  cap={a_cap:.4f}")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
