---
title: Current Focus
type: reference
related: [known_issues, head-tracking, engine-loop-and-daemon, constraints, the-watcher, the-gem, productification, version-control]
last_updated: 2026-06-01
sources: [Tracking/face_tracker.py, Launcher/app_engine.py, Engine/renderer.py, Engine/bloom_postfx.py, Scripts/tools/gen_eye_textures.py]
---

# Current Focus

What's actively being worked on right now. Keep this short — move durable
conclusions into the relevant system page and bug records into [[known_issues]].

## Version control — COMPLETE (2026-06-01)

The #1 catastrophic risk from [[productification]] is resolved.

- `git init` + `.gitignore` (excludes `dist/`, `Build/Iris.app/`, `__pycache__`, `.pyi_work/`)
- Initial commit: 160 files, 17 134 insertions — full v1.5 source + Obsidian wiki
- Pushed to `github.com/Iris-App-Release/IRIS` (SSH, `~/.ssh/id_ed25519`)
- `CLAUDE.md` added to project root — auto-loads key context for new LLM sessions
- See [[version-control]] for the full record

**Immediate next (from [[productification]] §6, Action #2):**
Apple Developer Program enrollment ($99/yr) → Developer ID signing → notarization.
This is Milestone 1 in the productification path and unblocks all real distribution.

## Performance pass — desktop lag while running — DONE (quick wins) (2026-06-01)

- **Symptom.** Opening other apps stuttered and desktop responsiveness dropped
  while IRIS ran; CPU felt high. Physics was suspected.
- **Finding (evidence, not guess).** IRIS has **no physics engine** — `camera_math.py`
  is pure matrix algebra (~7 µs/frame, measured). CPU-side main-loop work totals
  ~68 µs/frame. The real cost is GPU + WindowServer compositing of a **full-screen,
  native-Retina wallpaper rendered at 60 fps when the head input is only ~30 Hz** —
  half the frames were duplicate-input redraws. Profiled on M2 / GL-via-Metal.
- **Shipped (low-risk, behaviour-preserving):**
  1. **30 fps cap for wallpaper/fullscreen/desktop** (`FPS_WALLPAPER`), demo stays
     60. ~halves GPU + compositor load. See [[engine-loop-and-daemon]] / [[constraints]].
  2. **[[the-gem]] floor 21,600 → 6 verts** (`_FLOOR_DIVS 60→1`; flat plane needs 2
     triangles) and checks 10× larger (`_FLOOR_TILE 1.0→10.0`). Pixel-identical.
  3. **State export throttled to ≤30 Hz** (was a synchronous disk write every frame).
- **Recommended next (not yet done).** Remove the per-icon `glGetFloatv` pipeline
  stall in [[orbital-icons]] (compute the billboard matrix on the CPU); migrate
  static meshes to VBOs; optionally cheapen bloom (MSAA 4×→2×) in wallpaper mode.
- Full record in [[log]] (2026-06-01 perf entry).

## Settings camera toggle re-enable — RESOLVED (2026-05-31)

- **Fixed.** Disabling then re-enabling the camera from Settings and clicking
  "Enable Camera" now correctly resumes head tracking.
- **Root cause:** `Launcher/app_engine.py` — the `tracking_requested` handler was
  guarded by `not tracker_started`, which is permanently `True` after the first
  enable. The paused worker thread was never told to resume. One-line outer-guard
  change + two-branch split (first-start vs. resume-after-pause). Full record in
  [[known_issues]].
- **No new risks introduced.** The first-time enable path is byte-for-byte
  equivalent; the new `else` branch is a single `set_tracking(True)` call.

## Camera permission + tracking — RESOLVED & verified live (2026-05-31)

- **Fixed and confirmed working in the real app.** The "Live Status On but no head
  tracking" bug is resolved. **Ultimate root cause: an invalid code signature** —
  `build_dmg.sh` edited `Info.plist` *after* PyInstaller signed the bundle, and
  macOS TCC silently denies the camera to an invalidly-signed app (no prompt; the
  request auto-denies in ~52 ms). The build now **re-signs ad-hoc after the plist
  edits and verifies** (fails loudly otherwise). Full record in [[known_issues]].
- **Camera path redesigned for robustness** (not minimal patching), per approval:
  `OPENCV_AVFOUNDATION_SKIP_AUTH=1` (app owns auth; OpenCV stops its broken
  off-thread request), `request_camera_access()` returns a tri-state that
  `start()` actually **acts on** (no more doomed worker), honest UI status in
  [[ui-overlay]] ("Starting camera…" / "Live …" / "Camera access needed"), and
  field logging to `~/.iris/iris.log` (the windowed bundle discards stdout).
- **Verified live:** reset the grant, launched `dist/Iris.app`, **Enable Camera** →
  the TCC dialog appeared → grant → pill read **"Live · head tracking on"**, the
  menu-bar camera light lit, and the [[earth]] world tracked the head. `sim_overlay`
  + `sim_latency` still pass.
- **Follow-ups / watch for.** Ad-hoc signatures change each rebuild, so macOS may
  re-prompt (or need `tccutil reset Camera com.iris.parallaxwall`) after a fresh
  build — a Developer ID signature would make grants stable
  ([[distribution-checklist]]). Source runs still can't self-authorize (no bundle
  identity) — use the `.app`.

## The Watcher — eye tracking + visual upgrade — COMPLETE (2026-05-31)

**Status:** Implemented and textures regenerated.

**Eye tracking:**
- `Eye.update(dt, hx, hy)` now receives head position from `app_engine.py` each frame.
- Gaze smoothed with `GAZE_LERP = 0.10` (intentional, deliberate movement).
- Clamped to ±15° yaw / ±10° pitch (realistic eye anatomy).
- Existing gaze drift preserved and blended on top.
- No second tracking pipeline — re-uses `hx`/`hy` from the existing `tracker.head()` call.

**Visual upgrade:**
- Sclera: jaundiced yellow-white, darker overall.
- Veins: vivid arterial red, raised from 0.55→0.82 density.
- 7 hemorrhage blotches: Gaussian dark-blood-red bleeding patches on sclera.
- Normal map relief raised (2.2→2.8) for stronger vein shadow.
- Limbal ring darkened and reddened.
- Textures regenerated: `eye_diffuse.png` (930 KB), `eye_normal.png` (269 KB).

**Preserved:** parallax, zoom, rotation, head tracking pipeline, drift animation,
existing rendering/camera/physics systems — all unchanged.

**Future opportunities:**
- The eye tracks head *position* (`hx`/`hy`). MediaPipe also provides head *orientation*
  (`yaw`/`pitch`) which could be blended in for richer tracking at close range.
- A subtle pupil *dilation* effect (specular map scaling based on `hz`) could respond
  to the viewer moving close or far.
- A sclera injection / blood-filling animation on world activate could enhance the
  "waking up" feel.

## Related

[[known_issues]] · [[head-tracking]] · [[dmg-build-process]] · [[ui-overlay]] · [[constraints]] · [[the-watcher]] · [[productification]]
