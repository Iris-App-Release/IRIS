---
title: "2026-05-31 — Fix: Settings camera toggle — re-enable does not reactivate tracking"
type: log-entry
date: 2026-05-31
category: fix
---

# Settings camera toggle: re-enable does not reactivate tracking

**Trigger.** Bug report: enable camera → Settings → disable → Settings →
re-enable → click "Enable Camera" → camera never restarts. Disable worked;
re-enable was silently dead.

**Investigation.** Read [[ui-overlay]] and [[engine-loop-and-daemon]] first.
Traced the full Settings toggle path:
1. `_set_camera_enabled(False)` in `demo_overlay.py` → removes/creates
   `~/.iris/camera_off`, sets `overlay.live = False`.
2. Engine (`app_engine.py`) detects `cam_off = True` → calls
   `tracker.set_tracking(False)` → worker thread stays alive but pauses (camera
   released). `tracker_started` is **not** cleared.
3. `_set_camera_enabled(True)` re-enables the flag file; `overlay.live` stays
   `False` (floating preview); `tracking_requested` is never set.
4. User clicks "Enable Camera" (primary CTA) → overlay sets
   `tracking_requested = True`, `live = True`, `tracking_active = False`.
5. Engine evaluates:
   `if overlay.tracking_requested and not tracker_started and not cam_off:`
   → `tracker_started` is `True` → **condition is False** → block skipped.
   `set_tracking(True)` is never called. Camera stays dead.

**Root cause.** `tracker_started` semantically conflates "was the worker ever
spawned" with "is the tracker currently running." The flag is set `True` on the
first enable and never cleared on a Settings pause, so the re-enable path that
calls `tracker.start()` / `set_tracking(True)` is **permanently blocked after
the first enable cycle**.

**Fix.** Single surgical change to `Launcher/app_engine.py`. Removed `not
tracker_started` from the outer `if` guard and added a two-branch inner split:
- `not tracker_started` → existing `tracker.start()` path (first-ever enable,
  including a full re-authorization check). Byte-for-byte unchanged from before.
- `else` → worker already running but paused: `tracker.set_tracking(True)`.
  The worker re-opens the camera on its next tick (≤ 0.3 s). No new thread, no
  re-authorization.

The overlay's `_click("enable_camera")` already resets `tracking_active = False`
before setting `tracking_requested`, so the status pill correctly shows
"Starting camera…" until frames arrive — no extra changes needed.

**Validation.**
- Disable → re-enable → "Enable Camera": tracking resumes, status advances to
  "Live · head tracking on" once frames flow.
- Multiple disable → re-enable cycles: each click correctly hits the `else`
  branch (worker is still alive; paused/resumed cleanly via `set_tracking`).
- First-time enable path: the `not tracker_started` branch is untouched.
- `sim_overlay.py` + `sim_latency.py`: pass (logic/physics tests unaffected).

**Wiki updated.** New top entry in [[known_issues]], [[current-focus]] (new
resolved item), [[ui-overlay]] (camera toggle re-enable note), and this entry.
