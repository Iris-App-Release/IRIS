# BACKGROUND_ACTIVITY_REPORT.md

**Phase 10 — Background Work Audit**
Method: source audit for threads/timers/polling/watchers + per-frame I/O counted
in cProfile (`posix.stat` 3,067 calls / 600 frames). Apple M2.

---

## 1. Threads / processes spawned (complete list)

| Mechanism | Where | Lifetime | Idle behaviour |
|---|---|---|---|
| **`FaceTracker` daemon thread** | face_tracker:362 | whole session | Releases camera + `sleep(0.25)` when tracking off; busy-loops camera+inference when on |
| `subprocess.run(["pgrep"…])` | demo_overlay:548 | one-shot | Demo only, on user action (detect running daemon) |
| `subprocess.Popen(...)` | demo_overlay:2045 | one-shot | Demo only, on user action (spawn wallpaper daemon) |

**Exactly one long-lived thread.** No timer objects, no thread pools, no asyncio,
no multiprocessing. The wallpaper daemon is single render thread + one tracker
thread.

---

## 2. Continuous per-frame / periodic work (while rendering)

| Activity | Rate | Cost | Runs when… |
|---|---|---|---|
| **`EARTH_STATE_FILE` JSON write** (`~/.parallax_earth_state.json`) | **30 Hz** | ~55 µs/write (authors' note, app_engine:692) → **~1.65 ms/s** + constant SSD writes | every rendered frame (throttled to 30 Hz), **Earth world** |
| **Orbital-Apps folder rescan** (`/Applications/Orbital Apps` iterdir + alias resolve) | **1 Hz** | filesystem scan | every second, **Earth world**, in `IconOrbit.update` (RESCAN_INTERVAL=1.0) |
| Flag-file polls: `CAMERA_OFF_FLAG`, `TRACKING_OFF_FLAG`, `ICONS_OFF_FLAG` `.exists()` | per frame | ~5–6 `stat()`/frame (cProfile: 5.1/frame) = **~150/s @30fps** | every frame |
| `world.poll()` mtime stat (prefs + world.json) | per frame | 2 `stat()`/frame | every frame |
| `calib.poll()` mtime stat | per frame | 1 `stat()` (skipped when disabled) | every frame |

The **30 Hz state-file write** is the most notable: it is a synchronous disk write
**30 times per second, continuously, for the entire session**, serialising the
camera state for the *separate* `orbital_icons.py` desktop process. **If that
process isn't running** (it's an optional decorative desktop-icon overlay), these
writes are **pure waste** — 30 SSD writes/s forever.

---

## 3. Behaviour while idle / hidden / inactive — the important matrix

| State | How entered | Render thread | Tracker thread | Background I/O |
|---|---|---|---|---|
| **Engine paused** (master off) | `~/.parallax_off` flag | **Stops drawing** — `sleep(0.25)`+continue, window `orderOut` | `set_tracking(False)` → camera released, idles | Still polls flag 4×/s; **no 30 Hz write** (loop `continue`s before it) |
| **Camera off** (engine on) | `~/.iris/camera_off` | **Keeps rendering @30 fps** (idle/drifted head) | camera released, idles | **30 Hz write + 1 Hz rescan continue** |
| **Window occluded** (other app fullscreen over wallpaper) | macOS compositing | **Keeps rendering @30 fps** — app can't tell it's covered | unchanged | unchanged |
| **Active wallpaper** | default | 30 fps | ~30 Hz camera+inference | 30 Hz write + 1 Hz rescan |

### The key issue: rendering while not visible
- When **camera is disabled but engine on**, the wallpaper **still renders the full
  scene at 30 fps** (it only stops *tracking*, not *drawing*). The frame is ~4 ms
  GPU but it is **recomposited by WindowServer under every window** — the exact
  cause of the "opening other apps stutters" symptom the project notes
  (app_engine:92-103).
- When **fully occluded**, IRIS has **no occlusion check** and keeps drawing. macOS
  may throttle a fully-covered desktop-level window, but the app does nothing to
  help (no `NSWindowOcclusionState` observer).
- The **master pause** path is the only one that truly stops drawing — and it's
  good (sleeps, hides window, releases camera).

---

## 4. Recommendations (→ ROADMAP)

1. **Gate the 30 Hz state-file write on the icons process actually being present**
   (or on `~/.parallax_icons_off` absent). If no consumer, skip it entirely. Removes
   30 synchronous SSD writes/s for the common case where the desktop-icons overlay
   isn't installed. **(P2, trivial)**
2. **Observe `NSWindowOcclusionState`** (or app-active / display-sleep) and **pause
   rendering when the wallpaper is fully covered or the display is asleep** — drop
   to a slow poll like the master-pause path. Directly attacks the compositor
   stutter and idle GPU/power draw. **(P2)**
3. **Throttle the Orbital-Apps rescan** from 1 Hz to e.g. 5–10 s, or make it
   event-driven (FSEvents) — a folder that rarely changes doesn't need a scan every
   second. **(P3, tiny)**
4. **Coalesce flag polls**: the 3 flag-file `.exists()` + 3 mtime `stat()` per frame
   (~180 syscalls/s) could be one mtime check on a single combined state file, or
   polled at 5–10 Hz instead of per-frame. Low impact (syscalls are cheap) but
   reduces constant kernel traffic. **(P3)**
