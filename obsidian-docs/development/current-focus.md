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

## Latency/perf follow-ups + bloom removal — DONE (2026-06-01)

The four flagged latency/perf items are implemented, and per a follow-up user
decision **bloom post-processing was removed entirely**. All seven headless sims
pass (six existing + the new `sim_camlag`); `py_compile` clean. Live GPU
confirmation still needs a GUI session (renderer/GL constraint).

1. **`CAM_LAG` is now frame-rate-independent** (the most likely "slightly high"
   latency culprit). The fixed per-frame 0.55 lerp became a true exponential
   time-constant: `alpha = 1 − e^(−dt/CAM_LAG_TAU)`, with `CAM_LAG_TAU` derived
   from 0.55 at the 60 fps reference. Reproduces the calibrated 60 fps feel
   exactly **and** keeps the same wall-clock responsiveness at the 30 fps
   wallpaper/desktop cap (was ~2× laggier). Touched frozen smoothing **with
   explicit user approval**; new `Scripts/validation/sim_camlag.py` proves
   backward-compat at 60 fps + frame-rate independence + the dt clamp.
2. **Bloom removed entirely** (supersedes the earlier "honour per-world
   `use_bloom`" approach). The scene now renders straight to the default
   framebuffer — no off-screen FBO, no bright-extract/blur/composite. This drops
   the glow **and** the old composite grade (Reinhard tonemap, exposure ×1.22,
   vignette, chromatic aberration) on *every* world, Earth included; the trade was
   accepted. Parallax (camera math), star twinkle (stars shader) and the gem's
   facet shimmer (gem shader) are all generated upstream and are unaffected.
   Side benefit: the scene used to render into a NON-multisampled bloom FBO, so
   MSAA never actually applied — drawing to the default framebuffer now gives real
   anti-aliasing. `bloom_postfx.py` is retained but no longer imported/used.
3. **Static meshes migrated to VBOs.** `Mesh` (Earth ×3, Nebula, Eye, Gem) and the
   `Stars` field upload geometry once instead of re-streaming ~190 k verts/frame
   through client arrays. Transparent client-array fallback if buffer creation fails.
4. **MSAA reduced in wallpaper/fullscreen** (4×→2×; demo keeps 4× for the crisp
   first impression). Now actually takes effect, since the scene draws to the
   multisampled default framebuffer (see #2). *(The bloom-downscale trim from the
   first pass was reverted along with the rest of the bloom pipeline.)*

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

## Overlay greying on hover — RESOLVED (2026-06-01)

- **Fixed.** Demo buttons no longer grey out while the cursor rests on them. The
  4 s idle fade was treating a stationary hover as idle (the mouse emits no events
  when held still), so the whole control cluster dimmed while a button was clearly
  hovered — read by the user as "the grey area is bigger than the hitbox." The
  hitbox was never the problem (`_hit` and the grey fill share one rect).
- **Fix:** `UI/demo_overlay.py:update()` — `idle = 0.0 if self.hover is not None
  else (now - _last_input)`. Full record in [[known_issues]] / [[ui-overlay]].

## Latency audit — render-path stalls removed; root cause is the frozen pipeline (2026-06-01)

- **The two user-suspected causes do NOT hold.** The [[the-gem]] checkered floor
  was already reduced to 6 verts (perf pass below). "All 3 worlds loaded at once"
  is false: `WorldRuntime` holds one world def; `Eye`/`Gem` build lazily and
  cache; only the active world draws (fast switching = caching, not concurrency).
- **Two GPU→CPU `glGetFloatv` stalls removed** (both were the "recommended next"
  below): the per-frame `_view_rot_3x3` (now `mv[:3,:3]` from the CPU matrix) and
  the **per-icon** billboard read-back in `IconOrbit.draw` (now one read + CPU
  billboard; N stalls → 1). Pixel-identical (billboard diff 1.9e-6).
- **Headline head→photon latency is dominated by the FROZEN pipeline**, not render
  cost: MediaPipe ~34 ms / 68 ms p95 + **two** smoothing layers (tracker adaptive
  lerp + a second `CAM_LAG = 0.55` per-frame exponential in `app_engine`). Because
  `CAM_LAG` is per-frame not dt-normalised, the smoothing lag **doubles at the
  30 fps wallpaper/desktop cap** (~113 ms vs ~57 ms at 60 fps) — the most likely
  "slightly high" culprit. ~~Making `CAM_LAG` dt-aware would fix it but touches
  **frozen smoothing → needs explicit approval + a new sim.**~~ — **DONE
  2026-06-01** (approved; see the follow-ups section at the top + `sim_camlag`).
- **Also flagged, not changed:** ~~bloom runs in the Gem world even though
  `gem/world.json` says `"use_bloom": false`; client-side vertex arrays still
  re-streamed each frame (VBO migration).~~ — **both DONE 2026-06-01** (top section).
- Full record in [[log]] (2026-06-01 audit entry).

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
- **Recommended next.** ~~Remove the per-icon `glGetFloatv` pipeline stall in
  [[orbital-icons]] (compute the billboard matrix on the CPU)~~ — **DONE
  2026-06-01** (see the latency-audit section above; the per-frame
  `_view_rot_3x3` stall was removed too). ~~Still open: migrate static meshes to
  VBOs; optionally cheapen bloom (MSAA 4×→2×) in wallpaper mode; honour per-world
  `use_bloom`.~~ — **all DONE 2026-06-01** (see the follow-ups section at the top).
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
