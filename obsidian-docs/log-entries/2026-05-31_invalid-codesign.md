---
title: "2026-05-31 — Maintain: Invalid code signature — root cause: FIXED + verified live"
type: log-entry
date: 2026-05-31
category: maintain
---

# "Live Status On but no tracking" — root cause: invalid code signature (FIXED + verified live)

**Trigger.** Entering Live mode flipped the status to "Live" with **no camera
prompt**, but head tracking did not work in *either* a source "Preview" run *or*
the bundled "Desktop" app.

**Investigation (end-to-end, evidence-driven).** Read [[head-tracking]],
[[ui-overlay]], [[engine-loop-and-daemon]] first, then traced the pipeline:
overlay → `tracking_requested`/`live` → engine `tracker.start()` → worker
`cv2.VideoCapture(0)` → `head()` → camera math. Reproduced the failure live in
three layers: (1) a source probe showed `_request_camera_permission()` returning
`denied` instantly and OpenCV's worker thread spamming *"can not spin main run
loop from other thread"*; (2) running the frozen binary showed the **same** status
0 → camera-fail, and revealed the `--windowed` bundle **discards stdout** (every
camera `print()` was invisible — why this was so hard to see); (3) driving the
*running* app via screen control, the TCC status went NotDetermined → **Denied in
~52 ms with no dialog**, and `codesign --verify dist/Iris.app` reported **"invalid
Info.plist (plist or signature have been modified)."**

**Root cause.** `build_dmg.sh` edits `Info.plist` *after* PyInstaller ad-hoc-signs
the bundle and never re-signs, leaving an **invalid signature** — and macOS TCC
**silently denies** the camera to an invalidly-signed app. Secondary defects:
OpenCV self-authorizing on the worker thread (impossible), `start()` ignoring its
own permission result (doomed worker), and the overlay claiming "Live" on click
regardless of reality.

**Fix (robust redesign, per explicit approval).** `Build/build_dmg.sh`: **re-sign
ad-hoc after the plist edits + verify, failing the build otherwise** (the decisive
fix). `Tracking/face_tracker.py`: `OPENCV_AVFOUNDATION_SKIP_AUTH=1`, new
tri-state `request_camera_access()`, a result-consuming `start()` that won't spawn
a doomed worker, and file logging to `~/.iris/iris.log`. `Launcher/app_engine.py`
acts on `tracker.permission`; `UI/demo_overlay.py` shows honest status
("Starting camera…" / "Live …" / "Camera access needed") via `notify_camera_denied`.
`launcher.py`: early SKIP_AUTH + a persistent `MPLCONFIGDIR` (matplotlib, pulled
via mediapipe, had been rebuilding its font cache every launch).

**Verified live.** Rebuilt (signature now valid), `tccutil reset Camera
com.iris.parallaxwall`, launched `dist/Iris.app`, **Enable Camera** → macOS dialog
**appeared** → grant → pill **"Live · head tracking on"**, menu-bar camera light
on, Earth tracking the head; `~/.iris/iris.log`: `authorization answered:
authorized → camera opened — head tracking live`. `sim_overlay` + `sim_latency`
still pass.

**Wiki updated.** New top [[known_issues]] entry (+ relabeled the prior pyobjc
entry as "necessary, not sufficient"), [[current-focus]] (resolved), [[head-tracking]]
(new permission/threading mechanism), [[dmg-build-process]] (re-sign step + pyobjc
collect-all + ad-hoc-signing note), [[ui-overlay]] (honest status states), and this
entry.
