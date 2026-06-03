---
title: "2026-05-31 — Feature: The Watcher — eye tracking + visual upgrade"
type: log-entry
date: 2026-05-31
category: feature
---

# The Watcher — eye tracking + visual upgrade

**Scope.** Two additions to [[the-watcher]] world: (1) the iris now actively
follows the viewer's head position, and (2) the eye textures were upgraded to a
horror/atmospheric quality.

## Investigation

Read the full Obsidian wiki before touching any code. Key findings:

- `Eye.draw()` already uses `glRotatef()` for the drift animation — the exact
  same mechanism needed for tracking. No shader changes required.
- `hx`/`hy` from `tracker.head()` are in scope in `app_engine.py` at the same
  line that calls `eye.update(dt)`. Zero plumbing needed beyond adding the args.
- The iris is at the +Z pole of the UV sphere (UV 0.25, 0.50). Rotating the sphere
  around Y/X moves the iris exactly as expected. The sign conventions were verified:
  `hx = +1` (viewer left) → `−hx` yaw → iris rotates left → tracks viewer. ✓
- The head tracking values passed to the eye are the same pre-smoothed five-tuple
  already used by off-axis projection. No second tracking pipeline exists or was
  created.

## Implementation

**`Engine/renderer.py` — `Eye` class:**
- Added `GAZE_MAX_YAW_DEG = 15.0`, `GAZE_MAX_PITCH_DEG = 10.0`, `GAZE_LERP = 0.10`.
- Added `self._gaze_yaw = 0.0` / `self._gaze_pitch = 0.0` to `__init__`.
- `update(dt)` → `update(dt, hx=0.0, hy=0.0)`: computes clamped target gaze angles,
  lerps `_gaze_yaw`/`_gaze_pitch` toward them.
- `draw()`: total yaw/pitch = `_gaze_yaw + drift_yaw`, `_gaze_pitch + drift_pitch`.
  The existing `glRotatef` calls are unchanged in structure; only the angle values now
  include the tracking contribution.

**`Launcher/app_engine.py`:**
- `eye.update(dt)` → `eye.update(dt, hx, hy)`. One-word change.

**`Scripts/tools/gen_eye_textures.py` — horror texture upgrade:**
- `SCLERA_RGB`: `[0.86,0.81,0.76]` → `[0.76,0.70,0.58]` (jaundiced yellow-white)
- `VEIN_RGB`: `[0.62,0.10,0.09]` → `[0.72,0.03,0.03]` (vivid dark arterial red)
- `VEIN_STRENGTH`: `0.55` → `0.82` (dense horror-level network)
- `LIMBAL_RGB`: `[0.32,0.26,0.22]` → `[0.28,0.10,0.08]` (dark reddish limbal ring)
- Added `N_HEMORRHAGE = 7`, `HEMM_STRENGTH = 0.55`, `HEMM_RGB = [0.55,0.02,0.02]`.
- New `hemm_mask` loop: 7 Gaussian dark-red blotches placed at random angles on the
  sclera (outside the iris cap), composited with `np.maximum` so they accumulate
  without artifacts.
- Normal map strength: `2.2` → `2.8` for deeper vein shadows.
- Textures regenerated: `eye_diffuse.png` 831 KB → 930 KB, `eye_normal.png` 224 KB → 269 KB.

## Validation

- `Eye.update()` signature: default args `hx=0.0, hy=0.0` so all existing call sites
  that pass only `dt` (e.g. headless sims, tests) continue to work unchanged.
- Gaze drift is preserved: `drift_yaw`/`drift_pitch` still computed and added.
- Parallax, zoom, rotation, camera math, bloom: none of these code paths were
  touched. `glPushMatrix`/`glPopMatrix` scope is unchanged.
- Clamping ensures gaze never exceeds ±15°/±10° regardless of `hx`/`hy` range.
- Texture generator: `main()` ran cleanly; output paths and filenames identical.
- Existing `CREDITS.md` attribution retained (same CC BY-SA 4.0 source photo).

## Limitations

- Live camera testing requires the signed `.app` bundle (same constraint as before;
  source runs have no camera access per the macOS TCC rules in [[constraints]]).
- Eye tracking uses head *position* (`hx`/`hy`), not head *orientation*. At close
  range, MediaPipe `yaw`/`pitch` could be blended in for richer tracking.

**Wiki updated.** [[the-watcher]] (eye tracking section, texture upgrade section,
data-flow diagram), [[head-tracking]] (eye integration note in Dependencies),
[[constraints]] (eye tracking constraints block), [[current-focus]] (feature
complete entry with future opportunities), and this log entry.
