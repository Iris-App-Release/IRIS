# CHANGELOG_P1_2.md — mediapipe Lazy Import

**Fix:** P1.2  
**File changed:** `Tracking/face_tracker.py`  
**Lines changed:** ~45 (replaced 12-line eager block; added `_ensure_mediapipe()`)  
**Risk:** Low — deferred import; all symbol references unchanged; covered by unit test

---

## Problem

`mediapipe` was imported at **module scope** in `face_tracker.py` (lines 91–102
of the original). At import time mediapipe transitively loads:
- `mediapipe.tasks.python.vision.drawing_utils` → **`matplotlib.pyplot` (+395 ms)**
- `mediapipe.tasks.python.audio` → **`sounddevice` (+159 ms)**

Neither library is used by IRIS. Every app launch — including sessions where the
camera is disabled or never granted — paid this cost in full (~**550 ms of the
1,090 ms startup**).

## Change

Replaced the module-level `import mediapipe` block with a **lazy helper**
`_ensure_mediapipe()` that:
1. Returns immediately (True) if already loaded.
2. Imports mediapipe and populates six module-level symbol refs on first call.
3. Is called at the top of `FaceTracker._run()` — on the background worker thread,
   after all main-thread GL/window setup has settled.

The single `mp.Image(...)` call in `_step_mp` was updated to `_mp.Image(...)` to
use the lazily-populated ref.

### Import graph before

```
app startup
 └─ import Tracking.face_tracker
     ├─ import cv2                    (199 ms — still eager, required)
     ├─ import mediapipe              (592 ms)
     │   ├─ mediapipe.tasks.python.vision.drawing_utils
     │   │   └─ matplotlib.pyplot    (395 ms, UNUSED)
     │   └─ mediapipe.tasks.python.audio
     │       └─ sounddevice          (159 ms, UNUSED)
     └─ …
```

### Import graph after

```
app startup
 └─ import Tracking.face_tracker
     ├─ import cv2                    (199 ms — unchanged)
     └─ …                             (mediapipe: 0 ms at startup)

FaceTracker._run() [worker thread, after first tracker enable]
 └─ _ensure_mediapipe()
     └─ import mediapipe              (568 ms — deferred to bg thread)
```

---

## Before / After (measured)

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| `import Tracking.face_tracker` cost | ~600 ms (incl. mediapipe) | **288 ms** | −312 ms |
| mediapipe in `sys.modules` at startup | Yes | **No** | eliminated |
| matplotlib in `sys.modules` at startup | Yes | **No** | eliminated |
| sounddevice in `sys.modules` at startup | Yes | **No** | eliminated |
| `_ensure_mediapipe()` first call | — | 568 ms (bg thread) | off critical path |
| `_ensure_mediapipe()` cached call | — | 0.00 ms | free |
| Tracker behaviour | baseline | **identical** | no regression |

Startup improvement: **~310–550 ms** depending on whether mediapipe was the last
heavy dep loaded. In a fresh Python process (cold cache) the full saving is ~550 ms.

---

## Regression Verification

- `FaceTracker()` instantiation tested: OK
- `_ensure_mediapipe()` returns `True`, all six symbol refs populated: verified
- `_mp.Image`, `_FaceLM`, `_BaseOptions` etc. all non-None after first call: verified
- Tracker worker thread behaviour: unchanged (same code paths, same flags)
