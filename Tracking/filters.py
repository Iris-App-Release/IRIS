"""
filters.py — One Euro filter + gated velocity prediction for head tracking.

Pure math: no camera, GL, threads or Cocoa, so the latency-vs-jitter trade can be
validated headlessly (Scripts/validation/sim_predict.py) exactly the way
camera_math is. Used by Tracking/face_tracker.py as the FINAL conditioning stage
on the already-smoothed head signal:

  • OneEuroFilter — an adaptive low-pass. When the signal is slow it uses a LOW
    cutoff (heavy smoothing → removes rest jitter); the cutoff RISES with speed
    (light smoothing → low lag during deliberate motion). Its internally
    low-passed derivative is a clean velocity estimate, ideal for prediction.
  • gated_predict — extrapolate `value + velocity·lead` to HIDE pipeline latency
    (MediaPipe ~34 ms + downstream smoothing + display). The lead is velocity-
    GATED so that at rest (velocity ≈ 0) it adds exactly nothing: it can only
    reduce motion lag, never inject rest jitter — the hard requirement.

Reference: Casiez, Roussel & Vogel, "1€ Filter: A Simple Speed-based Low-pass
Filter for Noisy Input in Interactive Systems", CHI 2012.
"""
from __future__ import annotations

import math


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Hermite 0→1 ramp; flat (zero slope) at both ends, so no perceptible switch."""
    if edge1 <= edge0:
        return 0.0 if x < edge1 else 1.0
    t = (x - edge0) / (edge1 - edge0)
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


class OneEuroFilter:
    """Scalar 1€ filter. Call ``filter(x, dt)`` once per sample (dt in seconds);
    read ``.value`` (filtered position) and ``.velocity`` (filtered units/sec)."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.0,
                 d_cutoff: float = 1.0) -> None:
        self.min_cutoff = float(min_cutoff)   # Hz — lower = smoother at rest (more lag)
        self.beta       = float(beta)         # speed→cutoff gain — higher = less motion lag
        self.d_cutoff   = float(d_cutoff)     # Hz — derivative (velocity) smoothing
        self._x_prev: float | None = None     # previous FILTERED value (position EMA)
        self._x_raw_prev: float | None = None # previous RAW sample (derivative)
        self._dx_prev = 0.0
        self.value    = 0.0
        self.velocity = 0.0

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        # Exponential-smoothing factor for a given cutoff frequency and timestep.
        tau = 1.0 / (2.0 * math.pi * max(cutoff, 1e-6))
        return 1.0 / (1.0 + tau / dt)

    def reset(self) -> None:
        self._x_prev = None
        self._x_raw_prev = None
        self._dx_prev = 0.0
        self.value = 0.0
        self.velocity = 0.0

    def filter(self, x: float, dt: float) -> float:
        # First sample (or a non-positive dt, e.g. a stall) → initialise without
        # smoothing and report zero velocity, so prediction stays inert.
        if self._x_prev is None or dt <= 0.0:
            self._x_prev = x
            self._x_raw_prev = x
            self._dx_prev = 0.0
            self.value = x
            self.velocity = 0.0
            return x
        # Derivative from RAW-sample differences (the canonical 1€ formulation,
        # Casiez 2012), NOT raw-vs-filtered. This matters for the predictor: with a
        # raw-vs-filtered derivative the velocity stays pinned high while the
        # position low-pass catches up *after the head has already stopped*, and the
        # predictor extrapolates that stale velocity into a large post-stop
        # overshoot. Differencing raw samples makes the velocity drop the instant
        # the input stops, so the lead collapses cleanly with no rubber-band.
        dx = (x - self._x_raw_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._x_prev
        self._x_raw_prev = x
        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self.value = x_hat
        self.velocity = dx_hat
        return x_hat


def gated_predict(value: float, velocity: float, lead_s: float,
                  v_lo: float, v_hi: float,
                  clamp_lo: float, clamp_hi: float) -> float:
    """``value + velocity·lead_s``, scaled by a speed gate and clamped.

    The gate is a smoothstep on |velocity|: 0 below ``v_lo`` (so a still head is
    returned untouched — zero added jitter), ramping to 1 at ``v_hi`` (full
    latency-hiding lead during deliberate motion). Output is clamped to the
    channel's valid range so a fast move can never push it out of bounds."""
    g = smoothstep(v_lo, v_hi, abs(velocity))
    out = value + velocity * lead_s * g
    return max(clamp_lo, min(clamp_hi, out))
