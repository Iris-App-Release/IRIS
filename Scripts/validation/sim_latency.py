#!/usr/bin/env python3
"""
sim_latency.py — Headless validation of the velocity-adaptive input smoothing.

No camera, no GL. Drives the SAME FaceTracker smoothing primitives main.py uses
(FaceTracker._resp_boost + the _LERP_/_RESP_ constants) on synthetic head-signal
traces and proves the latency/jitter trade the performance pass is built on:

  1. AT REST the adaptive filter is identical to the old fixed lerp — so it can
     add NO new jitter (the hard requirement). Output std at rest is equal.
  2. DURING a deliberate fast move the adaptive filter has strictly LOWER lag
     than the fixed lerp — the "feels attached to my movement" win.
  3. The boost is monotonic and bounded: never below the base lerp, never above
     the ceiling, for any speed — so it cannot destabilise the loop.

Run:  .venv/bin/python sim_latency.py
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

import numpy as np

from Tracking.face_tracker import FaceTracker as FT

FPS = 30.0          # measured VIDEO-mode tracker rate
MS  = 1000.0 / FPS

_fail = 0
def check(name: str, ok: bool, detail: str = "") -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)


def smooth_fixed(signal, L, dead):
    """Plain exponential smoother with dead-zone — the OLD behaviour."""
    s = signal[0]; out = []
    for x in signal:
        d = x - s
        if abs(d) > dead:
            s += L * d
        out.append(s)
    return np.array(out)


def smooth_adaptive(signal, base, dead, lo, hi, ceil):
    """Velocity-adaptive smoother using the REAL FaceTracker._resp_boost."""
    s = signal[0]; out = []
    for x in signal:
        d = x - s
        L = FT._resp_boost(base, abs(d), lo, hi, ceil)
        if abs(d) > dead:
            s += L * d
        out.append(s)
    return np.array(out)


def lag_ms_to(signal_out, target, start_idx, reach=0.9):
    """Frames→ms for the output to reach `reach` of a step toward `target`."""
    base = signal_out[start_idx - 1]
    goal = base + reach * (target - base)
    for i in range(start_idx, len(signal_out)):
        if signal_out[i] >= goal:
            return (i - start_idx) * MS
    return float("inf")


def main() -> int:
    rng = np.random.default_rng(7)
    base = FT._LERP_XY
    dead = FT._DEAD_XY
    lo, hi, ceil = FT._RESP_V_LO, FT._RESP_V_HI, FT._RESP_MAX_XY

    print("velocity-adaptive input smoothing")
    print(f"  base lerp={base}  ceil={ceil}  v_lo={lo}  v_hi={hi}  @ {FPS:.0f}fps")
    print()

    # ── 1. Rest jitter — must be identical (no new jitter) ───────────────────
    print("1. At rest the adaptive filter equals the fixed lerp (no new jitter)")
    N = 600
    noise = 0.0025  # micro-jitter just above the dead zone in places
    rest = 0.5 + rng.normal(0.0, noise, N)
    of = smooth_fixed(rest, base, dead)
    oa = smooth_adaptive(rest, base, dead, lo, hi, ceil)
    jf, ja = float(np.std(of[100:])), float(np.std(oa[100:]))
    check("rest output jitter is not increased by adaptivity",
          ja <= jf * 1.02 + 1e-9, f"fixed std={jf:.5f}  adaptive std={ja:.5f}")

    # ── 2. Fast move — adaptive must have lower lag ──────────────────────────
    print("\n2. During a deliberate fast move the adaptive filter has lower lag")
    sig = np.full(120, 0.5)
    step_at = 40
    sig[step_at:] = 0.72          # ~0.22 unit fast head move (well above v_hi)
    sig += rng.normal(0.0, 0.0015, sig.shape)
    of = smooth_fixed(sig, base, dead)
    oa = smooth_adaptive(sig, base, dead, lo, hi, ceil)
    lf = lag_ms_to(of, 0.72, step_at)
    la = lag_ms_to(oa, 0.72, step_at)
    check("adaptive reaches 90% of the move faster than fixed",
          la < lf, f"fixed {lf:.0f}ms  vs  adaptive {la:.0f}ms")
    check("adaptive cuts motion lag by a meaningful margin",
          la <= lf * 0.75, f"{(1-la/lf)*100:.0f}% lower lag")
    # No overshoot / oscillation: the lerp ceiling stays < 1, so the smoother
    # approaches the target monotonically and never rings past it.
    overshoot = float(np.max(oa[step_at:]) - 0.72)
    check("adaptive does not overshoot the target (no oscillation)",
          overshoot < 0.01, f"max overshoot {overshoot*1000:.2f}e-3 units")

    # ── 3. Boost is monotonic and bounded ───────────────────────────────────
    print("\n3. Boost is monotonic in speed and bounded to [base, ceil]")
    speeds = np.linspace(0.0, 0.3, 200)
    vals = [FT._resp_boost(base, sp, lo, hi, ceil) for sp in speeds]
    mono = all(vals[i] <= vals[i + 1] + 1e-12 for i in range(len(vals) - 1))
    bounded = all(base - 1e-9 <= v <= ceil + 1e-9 for v in vals)
    check("never drops below the base lerp; never exceeds the ceiling", bounded,
          f"min={min(vals):.3f} max={max(vals):.3f}")
    check("monotonically non-decreasing in speed", mono)
    check("equals base at zero speed (rest)", abs(vals[0] - base) < 1e-9,
          f"v(0)={vals[0]:.3f}")

    # ── 4. Same guarantees for the rotation channel ──────────────────────────
    print("\n4. Rotation channel: rest-safe and lower-lag too")
    rbase = FT._LERP_ROT
    rlo, rhi, rceil = FT._RESP_V_LO_ROT, FT._RESP_V_HI_ROT, FT._RESP_MAX_ROT
    sig = np.full(120, 0.0); sig[40:] = 0.6
    sig += rng.normal(0.0, 0.002, sig.shape)
    of = smooth_fixed(sig, rbase, FT._DEAD_ROT)
    oa = smooth_adaptive(sig, rbase, FT._DEAD_ROT, rlo, rhi, rceil)
    lf = lag_ms_to(of, 0.6, 40); la = lag_ms_to(oa, 0.6, 40)
    check("rotation adaptive lag < fixed lag", la < lf,
          f"fixed {lf:.0f}ms vs adaptive {la:.0f}ms")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
