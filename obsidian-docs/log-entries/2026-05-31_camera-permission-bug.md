---
title: "2026-05-31 — Maintain: Camera-permission bug investigation & fix"
type: log-entry
date: 2026-05-31
category: maintain
---

# Camera-permission bug investigation & fix

**Trigger.** "Enable Camera" never surfaced the macOS TCC dialog and head tracking
never started (Desktop Mode was affected too).

**Method.** Wiki-first investigation: read [[head-tracking]], [[constraints]],
[[engine-loop-and-daemon]], [[ui-overlay]], [[dmg-build-process]] and
[[design-decisions]] *before* any source, formed hypotheses, then inspected only
the "Relevant Files" those pages name (`face_tracker.py`, `app_engine.py`,
`demo_overlay.py`, the launcher chain, `Iris.spec`, `build_dmg.sh`) plus the
runtime flag files and the shipped `Info.plist`.

**Root cause.** `FaceTracker.start()` relied on a bare `cv2.VideoCapture(0)` to
surface the permission prompt; the purpose-built `_request_camera_permission()`
(AVFoundation `requestAccess` + main-run-loop pump) existed but was **dead code**.
The bundle id and `NSCameraUsageDescription` were correctly present in the build,
so the issue was solely the missing request. Full record in [[known_issues]].

**Fix (source — first change since the initial ingest).** Wired
`_request_camera_permission()` into `start()` on the main thread and removed the
misleading cv2 probe. `Tracking/face_tracker.py` only — no camera math or parallax
physics touched.

**Wiki updated.** [[head-tracking]] (corrected camera-lifecycle description), new
[[known_issues]] and [[current-focus]] pages, the master `index.md` navigation,
and this entry. Validated headlessly with `sim_latency` + `sim_overlay` and a
`start()` control-flow test; live validation pending a real session.
