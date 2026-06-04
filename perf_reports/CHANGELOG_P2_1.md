# CHANGELOG_P2_1.md — Occlusion-Aware Render Pause

**Fix:** P2.1  
**Files changed:** `Launcher/app_engine.py`  
**Lines added:** ~25 (helper function + loop guard)  
**Risk:** Low-Medium — macOS API, well-documented, safe default (render on error)

---

## Problem

The wallpaper daemon rendered at **30 fps continuously**, even when:
- Fully covered by a fullscreen app (Mission Control, browser, fullscreen game).
- Camera disabled (no visual change, but GPU still churning).
- Display sleeping (this was already handled by the OS, but app side had no check).

Each rendered frame recomposited the entire Retina wallpaper under every window
above it — the **WindowServer stutter** when opening other apps originated here:
opening an app that covers the wallpaper triggered a full-screen compositor
reschedule while IRIS kept submitting frames at 30 fps.

## Change

Added `_window_is_occluded()` using macOS `NSWindowOcclusionState`:

```python
_VISIBLE_BIT = 2   # NSWindowOcclusionStateVisible = 1 << 1
for w in NSApp.windows():
    if w.occlusionState() & _VISIBLE_BIT:
        return False          # at least one window still visible
return True                   # all windows fully occluded
```

When `_window_is_occluded()` returns True in wallpaper (or in-process Desktop)
mode:
```python
pygame.event.pump()   # keep SDL alive (handles un-occlusion events)
time.sleep(0.033)     # ~30 Hz poll, near-zero CPU
continue              # skip the entire render path
```

On un-occlusion, rendering resumes **immediately on the next loop tick** with no
reload or restart — the GL context, textures, and all scene state are preserved.

Occlusion transitions are logged:
```
[main] Wallpaper occluded — pausing render
[main] Wallpaper visible — resuming render
```

---

## Expected CPU / GPU savings

| Scenario | Before | After |
|---|---|---|
| Wallpaper fully covered | ~3 ms GPU/frame × 30 fps = **90 ms GPU/s** | **~0.033 ms/s** (sleep only) |
| WindowServer compositor load when covered | Active recomposite | **None** |
| CPU (main thread) while covered | ~1 ms/frame × 30 fps | **~0** |
| Recovery time on un-occlude | 0 ms (already rendering) | **<33 ms** (1 sleep interval) |

This directly targets the reported "stutter when opening other apps": once the
covering app is fullscreen IRIS pauses render entirely; the compositor handles
only the foreground window stack.

---

## Scope

- **Wallpaper mode and in-process Desktop Mode only**: the interactive onboarding
  demo window is never paused (it's a window the user is actively looking at).
- **Safe default**: if Cocoa is unavailable or `occlusionState()` raises,
  `_window_is_occluded()` returns `False` and rendering continues normally.
- **Non-macOS**: `_HAVE_COCOA = False` branch returns `False` immediately — no
  change to cross-platform behaviour.
- The existing master-pause (`TRACKING_OFF_FLAG`) path is unchanged and still
  takes priority.
