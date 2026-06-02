#!/usr/bin/env python3
"""
sim_predict.py — Headless validation of the predictive conditioning stage.

No camera, no GL. Drives the SAME primitives the live tracker uses
(Tracking/filters.OneEuroFilter + gated_predict, with the FaceTracker constants)
on synthetic head traces at the real ~30 Hz sample rate, and proves the
latency/jitter trade the speed upgrade is built on:

  1. REST JITTER is REDUCED, not added — the 1€ filter's rest output has lower
     std than the raw signal AND lower than the old fixed lerp (it is a *better*
     jitter filter), and the predictor adds nothing on top at rest.
  2. PREDICTION LOWERS MOTION LAG — on a deliberate move the predicted output
     reaches 90 % of the target sooner than the filtered-only output.
  3. REST-SAFE PREDICTOR — gated_predict at (near-)zero velocity returns the value
     untouched, so it can never inject rest jitter (the hard requirement).
  4. BOUNDED — output is always clamped to the channel's valid range, even for an
     adversarially fast move.
  5. STABLE — no runaway: a held target settles back with only bounded overshoot,
     and a sinusoid is not amplified.

Run:  .venv/bin/python sim_predict.py
Exit 0 = all checks pass, 1 = a check failed.
"""
from __future__ import annotations

# --- reorg path shim (validation harness) ---
import sys as _s
from pathlib import Path as _P
_root = str(_P(__file__).resolve().parents[2])
if _root not in _s.path:
    _s.path.insert(0, _root)

import sys

import numpy as np

from Tracking.filters import OneEuroFilter, gated_predict
from Tracking.face_tracker import FaceTracker as FT

FPS = 30.0
DT  = 1.0 / FPS
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


# Tracker's live constants, so the sim tracks whatever is shipped.
MINCUT, BETA, DCUT = FT._EURO_MIN_CUTOFF, FT._EURO_BETA, FT._EURO_D_CUTOFF
LEAD               = FT._PREDICT_LEAD
PV_LO, PV_HI       = FT._PV_LO, FT._PV_HI


def euro_only(signal, dt=DT):
    f = OneEuroFilter(MINCUT, BETA, DCUT)
    return np.array([f.filter(x, dt) for x in signal])


def euro_predict(signal, dt=DT, lead=LEAD, clamp=(-1.0, 1.0)):
    f = OneEuroFilter(MINCUT, BETA, DCUT)
    out = []
    for x in signal:
        fv = f.filter(x, dt)
        out.append(gated_predict(fv, f.velocity, lead, PV_LO, PV_HI, clamp[0], clamp[1]))
    return np.array(out)


def fixed_lerp(signal, L, dead):
    s = signal[0]; out = []
    for x in signal:
        d = x - s
        if abs(d) > dead:
            s += L * d
        out.append(s)
    return np.array(out)


def lag_ms_to(series, base, target, start_idx, reach=0.9):
    goal = base + reach * (target - base)
    for i in range(start_idx, len(series)):
        if series[i] >= goal:
            return (i - start_idx) * MS
    return float("inf")


def main() -> int:
    rng = np.random.default_rng(11)
    print("predictive conditioning (1€ filter + gated prediction)")
    print(f"  min_cutoff={MINCUT} beta={BETA} d_cutoff={DCUT} lead={LEAD*1000:.0f}ms "
          f"gate=[{PV_LO},{PV_HI}]u/s  @ {FPS:.0f}fps\n")

    # ── 1. Rest jitter is reduced (better jitter filter) ─────────────────────
    print("1. At rest the 1€ filter REDUCES jitter (vs raw and vs the old lerp)")
    N = 600
    noise = 0.0035
    rest = 0.0 + rng.normal(0.0, noise, N)
    raw_std = float(np.std(rest[100:]))
    eo = euro_only(rest)
    lerp = fixed_lerp(rest, FT._LERP_XY, FT._DEAD_XY)
    eo_std, lerp_std = float(np.std(eo[100:])), float(np.std(lerp[100:]))
    check("1€ rest jitter < raw input jitter", eo_std < raw_std,
          f"raw={raw_std:.5f}  1€={eo_std:.5f}")
    check("1€ rest jitter <= old fixed-lerp jitter", eo_std <= lerp_std + 1e-9,
          f"lerp={lerp_std:.5f}  1€={eo_std:.5f}")
    # Predictor must not re-introduce jitter at rest.
    ep = euro_predict(rest)
    ep_std = float(np.std(ep[100:]))
    check("predictor adds no rest jitter (std not increased)",
          ep_std <= eo_std * 1.05 + 1e-9, f"1€={eo_std:.5f}  1€+predict={ep_std:.5f}")

    # ── 2. Prediction lowers motion lag ──────────────────────────────────────
    print("\n2. On a deliberate move the predictor reaches the target sooner")
    M = 120
    step_at = 30
    target = 0.30
    sig = np.zeros(M)
    ramp = np.linspace(0.0, target, 8)          # ~0.27 s move → ~1.1 u/s (gate≈1)
    sig[step_at:step_at + 8] = ramp
    sig[step_at + 8:] = target
    sig += rng.normal(0.0, 0.0015, M)
    eo = euro_only(sig)
    ep = euro_predict(sig)
    base = float(np.mean(sig[:step_at]))
    l_eo = lag_ms_to(eo, base, target, step_at)
    l_ep = lag_ms_to(ep, base, target, step_at)
    check("predicted reaches 90% sooner than filtered-only", l_ep < l_eo,
          f"1€={l_eo:.0f}ms  1€+predict={l_ep:.0f}ms")
    check("prediction cuts motion lag by a meaningful margin",
          l_ep <= l_eo - MS, f"{l_eo - l_ep:.0f}ms sooner (≥{MS:.0f}ms)")

    # ── 3. Rest-safe predictor (zero velocity → identity) ────────────────────
    print("\n3. gated_predict is identity at zero velocity (no rest jitter)")
    ident = all(
        abs(gated_predict(v, 0.0, LEAD, PV_LO, PV_HI, -1.0, 1.0) - v) < 1e-12
        for v in (-0.8, -0.2, 0.0, 0.3, 0.9)
    )
    check("zero-velocity prediction returns the value exactly", ident)
    # Below the gate's lower speed threshold prediction is still inert.
    sub = gated_predict(0.2, PV_LO * 0.5, LEAD, PV_LO, PV_HI, -1.0, 1.0)
    check("below-gate slow drift is not extrapolated", abs(sub - 0.2) < 1e-9,
          f"out={sub:.6f}")

    # ── 4. Bounded output even for an adversarial fast move ──────────────────
    print("\n4. Output is clamped to the channel range")
    fast = np.concatenate([np.zeros(10), np.linspace(0.0, 5.0, 40)])  # 5 u over ~1.3s
    epf = euro_predict(fast, clamp=(-1.0, 1.0))
    check("never exceeds +1.0 / falls below -1.0",
          float(np.max(epf)) <= 1.0 + 1e-9 and float(np.min(epf)) >= -1.0 - 1e-9,
          f"min={np.min(epf):.3f} max={np.max(epf):.3f}")

    # ── 5. Stable: bounded post-stop overshoot + no sinusoid blow-up ─────────
    print("\n5. Stable — bounded overshoot after a stop, sinusoid not amplified")
    overshoot = float(np.max(ep[step_at:]) - target)
    check("post-stop overshoot is bounded", overshoot < 0.06,
          f"max overshoot {overshoot*1000:.1f}e-3 units")
    tt = np.arange(300) * DT
    sine = 0.3 * np.sin(2 * np.pi * 0.5 * tt)        # 0.5 Hz, amplitude 0.3
    eps = euro_predict(sine)
    amp = float(np.max(np.abs(eps[60:])))
    check("0.5 Hz sinusoid amplitude not blown up (<1.4x)", amp < 0.3 * 1.4,
          f"in amp 0.300  out amp {amp:.3f}")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
