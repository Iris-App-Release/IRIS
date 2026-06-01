This page contains the final findings, hypotheses, and reasoning from Claude sessions that were interrupted before completion (typically due to token limits, usage limits, or manual interruption).

Entries below should be treated as active investigation notes rather than verified project documentation. They may contain partially validated discoveries, suspected root causes, file references, recommended next steps, or work-in-progress analysis.

When resuming work:

1. Read the most recent entry first.
2. Verify any claims against the codebase and wiki.
3. Promote confirmed discoveries into the appropriate permanent documentation.
4. Remove or archive resolved entries once their knowledge has been incorporated elsewhere.

See  26/05/31 - 3:48 AM --- **[ARCHIVED / RESOLVED 2026-05-31]** The investigation below ran to completion.
Confirmed root cause: pyobjc (`objc`/`Foundation`/`AVFoundation`) was bundled as
`.so` cores only — no pure-Python modules / `__init__.py` — because the imports
are lazy inside a `try/except`, so PyInstaller never collected them and
`_request_camera_permission()` returned `False` instantly in the frozen app.
Fixed by force-collecting the three pyobjc packages in `Build/build_dmg.sh`
(and `Iris.spec`); the rebuilt bundle now contains all the modules. Full durable
record promoted to [[known_issues]] (top entry). Only the live GUI click-test
remains. The notes below are kept as the original investigation trail.

**Major finding.** The log shows OpenCV's own backend message — `OpenCV: not authorized to capture video (status 0), requesting...` — repeated 4 times in ~9s. Status 0 means **NotDetermined**, not Denied (so my denial hypothesis was wrong — good thing I checked). But notice: the worker thread's `cv2.VideoCapture(0)` is firing _repeatedly and immediately_. If `_request_camera_permission()` were actually blocking the main thread pumping the run loop (up to 60s), the worker couldn't be retrying cv2 within 9s. That strongly implies **`_request_camera_permission()` is returning instantly** — i.e. the AVFoundation import/call is failing inside the frozen bundle, so the main-thread prompt never fires.

The Python `[tracker]` prints were lost to stdout buffering when I killed it. Let me re-run with unbuffered output to see exactly what the permission path does.

RanRe-run unbuffered to capture tracker permission prints

Now it's definitive. The unbuffered run reveals the real failure:

```
OpenCV: not authorized to capture video (status 0), requesting...OpenCV: can not spin main run loop from other thread, set OPENCV_AVFOUNDATION_SKIP_AUTH=1 ...OpenCV: camera failed to properly initialize!
```

This is the smoking gun. The **worker thread's `cv2.VideoCapture(0)` is the thing trying to authorize** — and failing because it can't spin the main run loop off-thread. Critically, the status is **still 0 (NotDetermined)** when the worker runs, and the worker retries immediately. If `_request_camera_permission()` had actually run and blocked on the main thread pumping the run loop (presenting the dialog), the worker couldn't be retrying within seconds with status still 0. **So the main-thread permission request is producing no grant in the real bundle** — the "fix" is inert at runtime.

Let me pin down _why_ by checking whether pyobjc's AVFoundation actually imports inside the frozen app (PyInstaller frequently drops pyobjc's lazy framework bindings).

RanInspect bundled pyobjc completeness and spec hidden imports

The bundled `AVFoundation/` ships only the `.so` binaries — and crucially **`Iris.spec`/`build_dmg.sh` declare no pyobjc handling whatsoever** (no `collect_all`/hidden-import for `AVFoundation`, `Foundation`, or `objc`). pyobjc got pulled in only transitively. pyobjc is notoriously incomplete under PyInstaller because its framework bindings load dynamically. Let me check whether the PYZ actually contains the pure-Python pyobjc modules `_request_camera_permission` needs.