---
title: Ingestion Log
type: metadata
related: [index]
last_updated: 2026-06-01
sources: []
---

# Ingestion Log

Append-only record of how this wiki was built. Newest entries at the bottom.

---

## [2026-05-31] ingest | Full IRIS APP codebase — initial build

**Scope.** First comprehensive, read-only ingest of `~/Documents/IRIS APP/`. No
source files were modified. The wiki was built using the LLM-wiki pattern: read
the whole tree once, extract and synthesize, and leave a cross-referenced,
self-maintaining markdown knowledge base.

**Explored.**
- Mapped the directory tree; excluded the bundled `dist/` (third-party
  pygame/mediapipe/cv2) and caches/venv as non-source.
- ~10K lines of project source (Python + GLSL).
- Read every project source file: `Engine/` (camera_math, renderer,
  shader_loader, bloom_postfx, orbital_icons), `Tracking/face_tracker`,
  `Launcher/` (app_engine, app_entry) + root `launcher.py`, `UI/demo_overlay`,
  `Worlds/` (world_loader, world_runtime, both `world.json`), all six
  `Scripts/validation/sim_*`, all four `Scripts/tools/`, `parallaxctl.py` (+
  wrapper), `Build/build_dmg.sh`, `Iris.spec`, `requirements.txt`, key shaders,
  and all 12 hand-written docs.

**Key findings that shaped the schema.**
- The project is **Python/OpenGL**, not the TypeScript the template assumed — the
  generic schema was adapted (e.g. "eye-tracking" → [[head-tracking]],
  "window-management" → [[engine-loop-and-daemon]]).
- **Two worlds** ship: [[earth]] and [[the-watcher]] (the template assumed one).
- **Not a git repo** → [[version-history]] is reconstructed from the DMG
  artifacts (v0.0 → 1.3) and dated docs.
- Per user direction, pages describe the **current code state** and do not audit
  where older source comments/docs diverge from it.

**Created — 22 pages.**
- 10 systems: [[off-axis-projection]], [[head-tracking]], [[rendering-engine]],
  [[world-system]], [[engine-loop-and-daemon]], [[ui-overlay]], [[orbital-icons]],
  [[headless-simulation]], [[asset-pipeline]], [[daemon-control]].
- 3 worlds: [[earth]], [[the-watcher]], [[worlds-index]].
- 3 releases: [[dmg-build-process]], [[version-history]], [[distribution-checklist]].
- 3 architecture: [[system-interactions]], [[constraints]], [[design-decisions]].
- 1 docs: [[docs-index]].
- 2 metadata: `index.md`, `log.md`.

**Cross-referencing.** Every page carries YAML frontmatter
(`title/type/related/last_updated/sources`), uses Obsidian `[[wiki-links]]`, and
links are bidirectional. `system-interactions` includes mermaid diagrams of the
per-frame data flow and the file-based IPC bus.

**Not modified.** All source code, configs, assets, and the existing `Docs/` are
untouched; the wiki lives entirely under `obsidian-docs/`.

---

## [2026-05-31] maintain | Camera-permission bug investigation & fix

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

---

## [2026-05-31] maintain | "Live Status On but no tracking" — root cause: invalid code signature (FIXED + verified live)

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

---

## [2026-05-31] fix | Settings camera toggle: re-enable does not reactivate tracking

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

---

## [2026-05-31] strategy | Productification roadmap created

**Trigger.** Requested a complete commercial-progression analysis of IRIS: milestones, business model, risk factors, and immediate next actions.

**Method.** Full vault and source review before writing: `index.md`, `Handover.md`, `log.md`, all architecture pages ([[design-decisions]], [[constraints]], [[system-interactions]]), all release pages ([[version-history]], [[distribution-checklist]], [[dmg-build-process]]), `Docs/IRIS_OVERVIEW.txt`, `Docs/FIRST_LAUNCH_AND_DMG_DESIGN.md`, `PRODUCTIZATION_PHASE_SUMMARY.md`, and [[worlds-index]].

**Created.** `obsidian-docs/productification.md` — 23 KB, covering:
- Current state: technical + product readiness matrices (6 tables)
- Productification path: 6-stage progression diagram
- Six milestone definitions with objectives, success criteria, dependencies, and risks
- Business model evaluation: 7 revenue streams scored; freemium + one-time Pro ($7.99) recommended
- Success factors, biggest risks (with mitigation), biggest opportunities
- Immediate next actions: 10-item ordered table

**Cross-references added.** Backlinks inserted (frontmatter + body) in: `index.md` (new table row), `Handover.md` (frontmatter + Next Steps callout), `design-decisions.md` (Related section), `version-history.md` (Dependencies), `distribution-checklist.md` (Dependencies), `current-focus.md` (Related section), `worlds-index.md` (new Related section). All links are bidirectional.

**Key finding.** The single most critical non-technical action is `git init` — the project has no version control and the Obsidian wiki is the only persistent record. Source loss at this stage would be catastrophic.

---

## [2026-05-31] feature | The Watcher — eye tracking + visual upgrade

**Scope.** Two additions to [[the-watcher]] world: (1) the iris now actively
follows the viewer's head position, and (2) the eye textures were upgraded to a
horror/atmospheric quality.

### Investigation

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

### Implementation

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

### Validation

- `Eye.update()` signature: default args `hx=0.0, hy=0.0` so all existing call sites
  that pass only `dt` (e.g. headless sims, tests) continue to work unchanged.
- Gaze drift is preserved: `drift_yaw`/`drift_pitch` still computed and added.
- Parallax, zoom, rotation, camera math, bloom: none of these code paths were
  touched. `glPushMatrix`/`glPopMatrix` scope is unchanged.
- Clamping ensures gaze never exceeds ±15°/±10° regardless of `hx`/`hy` range.
- Texture generator: `main()` ran cleanly; output paths and filenames identical.
- Existing `CREDITS.md` attribution retained (same CC BY-SA 4.0 source photo).

### Limitations

- Live camera testing requires the signed `.app` bundle (same constraint as before;
  source runs have no camera access per the macOS TCC rules in [[constraints]]).
- Eye tracking uses head *position* (`hx`/`hy`), not head *orientation*. At close
  range, MediaPipe `yaw`/`pitch` could be blended in for richer tracking.

**Wiki updated.** [[the-watcher]] (eye tracking section, texture upgrade section,
data-flow diagram), [[head-tracking]] (eye integration note in Dependencies),
[[constraints]] (eye tracking constraints block), [[current-focus]] (feature
complete entry with future opportunities), and this log entry.

---

## [2026-05-31] feature | The Gem — third world, rotating brilliant-cut gemstone

**Scope.** Implemented [[gem]], the third IRIS world: a brilliant hot-pink
faceted gemstone rotating in pure white space. This activates the pre-existing
`Gem` class and `gem` shader that were already in the renderer but not wired into
the world system.

### Pre-implementation review

Full vault review before any code change. Key findings from reading
[[rendering-engine]], [[world-system]], [[worlds-index]], [[design-decisions]],
[[off-axis-projection]], [[head-tracking]], [[constraints]], and [[system-interactions]]:

- `Gem` class and `gem.vert/frag` shaders already existed in `Engine/renderer.py`
  and `shaders/` — functional but unexposed.
- `make_gem(n=8)` generated only 32 flat-shaded triangles; increasing to n=32
  gives 128 for a much richer brilliant-cut appearance.
- `Gem` had no `update()` method (no rotation); needed to add one.
- No `Worlds/gem/world.json` → world system couldn't discover or select the gem.
- `app_engine.py` only dispatched `primary_mesh == "eye"` and `earth`; a `gem`
  branch was needed.
- **Bloom conflict**: the vignette in the post-composite (VIGNETTE=0.42) would
  darken the pure-white background edges. Bloom must be off for The Gem.
- Fill light (`u_fill_eye`): the gem shader already accepted it, but the engine
  never computed a fill direction. Added `fill_world` alongside `sun_world`.

### Changes made

**`Engine/renderer.py`:**
- `make_gem(n=8 → n=32)`: 128 flat-shaded triangles (4× more facets). Geometry
  dimensions unchanged (r_girdle=1.45, h_crown=0.52, h_pav=1.85).
- `Gem.__init__`: added `self._spin_y = 0.0`, `self._spin_x = 0.0`.
- `Gem.update(dt)`: new method — spins `_spin_y` at 22°/s (primary yaw) and
  `_spin_x` at 7°/s (slow tilt).
- `Gem.draw()`: wrapped `glPushMatrix / glRotatef(_spin_y, Y) / glRotatef(_spin_x, X)
  / … / glPopMatrix`. Rotation is model-space only; camera math is untouched.

**`shaders/gem.frag`:**
- Base color: `vec3(0.88, 0.10, 0.55)` → `vec3(1.0, 0.06, 0.48)` (true hot pink).
- Key specular shininess: 96 → 256 (narrow diamond flash).
- Fill specular shininess: 64 → 128; cooler blue-white tint.
- Key spec weight: 1.4 → 2.2; fill: 1.1 → 1.2.
- Fresnel power: 3.2 → 4.5 (tighter, more saturated rim glow).
- Emissive: stronger hot-pink centre `vec3(1.0, 0.12, 0.55)`, cooler edge `vec3(0.95, 0.50, 0.75)`.
- Iridescence: shifted to blue-violet `vec3(0.35, 0.05, 0.80)` for more contrast
  against the pink body.

**`Worlds/gem/world.json` (new):**
- `primary_mesh: "gem"`, `background: "void"`, `clear_color: [1, 1, 1]`,
  `use_bloom: false`, `show_icons: false`.

**`Launcher/app_engine.py`:**
- Added `Gem` to renderer import.
- Added `fill_world = [-0.72, -0.30, 0.65]` (left-low-front, ~120° from key),
  normalized; computed once at startup.
- Added per-frame `fill_eye = (view_rot @ fill_world).tolist()` after `sun_eye`.
- Added `gem = None` lazy handle alongside `eye = None`.
- Added `gem.update(dt)` in the animation block.
- Added `elif world.primary_mesh == "gem"` dispatch branch with the same lazy-init
  + fallback pattern as `eye`.

### Validation

- All 6 headless sims (`sim_orbit`, `sim_offaxis`, `sim_viewing`, `sim_latency`,
  `sim_vertical`, `sim_overlay`) still print "RESULT: all checks passed".
- `make_gem(n=32)` geometry check: 384 vertices / 128 flat-shaded triangles;
  Y range [-1.85, 0.52], XZ radius max 1.45. Correct.
- Python syntax check on `Engine/renderer.py` and `Launcher/app_engine.py`: OK.
- `Worlds/gem/world.json` parses correctly as JSON.
- GL compilation can only be verified in a live GUI session (camera / GL shader
  restriction from agent shell — same constraint as all prior renderer work).

### Architecture notes

- The gem sits at the Earth anchor (`z = -10, pf = 0`) and inherits the **full
  off-axis parallax, zoom, and rotation pipeline** unchanged.
- The gem's model rotation (`glRotatef`) is layered on top of the camera math,
  not substituting for it. Normals include the model rotation via `gl_NormalMatrix`,
  so per-facet lighting is physically correct as the gem spins.
- The fill light is computed per-frame (`view_rot @ fill_world`) so it tracks the
  camera orientation correctly as the viewer moves.
- The gem is fully procedural — no texture assets required.

**Wiki updated.** New [[gem]] page (full world reference); [[worlds-index]]
(third world added to comparison table, "Not yet a world" section removed);
[[rendering-engine]] (`Gem` entry updated — now a real world with n=32);
[[design-decisions]] (The Gem design rationale added); `index.md` (third world
in prose + worlds table); and this log entry.

---

## [2026-05-31] polish | The Gem — size, tilt constraint, shadow

**Scope.** Three UX-driven changes to [[gem]] based on first impressions at
working distance. No camera math, world JSON, or shader code touched.

### Changes

**`Engine/renderer.py` — `make_gem` defaults:**
- `n`: 32 → 16 (64 flat-shaded triangles instead of 128). At n=32 the facets were
  too numerous to read individually; n=16 gives clear, distinct facet flashes.
- `r_girdle`: 1.45 → 2.2 (+52%). At working distance (BASE_Z=11.5, scene z=−10)
  the old gem subtended ~3.9° of view; the new size gives ~5.8° — comfortably
  visible without dominating. Crown / pavilion scaled proportionally:
  `h_crown` 0.52 → 0.79, `h_pav` 1.85 → 2.80.

**`Engine/renderer.py` — `Gem` class, rotation:**
- Removed: `_ROT_PITCH_DEG_S = 7.0` and the accumulating `_spin_x` (which could
  tilt the gem to 90° / sideways over time).
- Added: `_TILT_MAX_DEG = 25.0` and `_TILT_SPEED = 0.38 rad/s`. The X-axis tilt
  is now `25° × sin(tilt_phase)`, oscillating with period ≈ 16.5 s. The gem rocks
  gently ±25° from vertical and never approaches sideways.

**`Engine/renderer.py` — `Gem` class, shadow:**
- New `_build_shadow()`: 48-segment triangle-fan disk at `y = −3.30` (0.5 below the
  culet), `r = 3.50`, centre alpha 0.28 fading to 0 at the edge. Built once at
  `__init__` into numpy arrays.
- New `_draw_shadow()`: fixed-function pipeline, vertex colour array, depth writes
  off (`glDepthMask(GL_FALSE)`), blend on. Shadow is drawn first in `Gem.draw()`
  before the `glPushMatrix/glRotatef` for the gem spin, so it remains a flat
  horizontal disk on the "floor" regardless of gem tilt — always visually grounding.

### Validation

- All 6 headless sims still print "RESULT: all checks passed".
- Geometry check: 192 vertices / 64 flat triangles, Y ∈ [−2.80, 0.79], XZ r = 2.20.
- Python syntax check on `Engine/renderer.py`: OK.

**Wiki updated.** [[gem]] (How it renders, Constraints sections rewritten);
[[worlds-index]] (rotation row + new shadow row); [[rendering-engine]] (Gem entry);
and this log entry.

---

## [2026-06-01] texture-replacement | The Watcher — eye diffuse replaced with supplied photo

**Scope.** Texture-only replacement task. No shader, physics, animation, tracking,
or parallax systems were modified.

### Asset replaced

| Asset | Previous | New |
|---|---|---|
| `assets/the_watcher/eye_diffuse.png` | Procedural Eye-of-Cthulhu iris (gen_eye_textures.py) | Photo-based: `something-i-made-for-my-friends.gif` |
| `assets/the_watcher/eye_normal.png` | Derived from procedural diffuse | Re-derived from new diffuse luminance |
| `assets/the_watcher/eye_specular.png` | Procedural cornea mask | Regenerated; same angular definition (IRIS_HALF_ANG = 38°) |

Source image: `obsidian-docs/worlds/something-i-made-for-my-friends.gif` (220×294, grayscale, high-contrast B&W photo of a human eye).

### Files modified

- `assets/the_watcher/eye_diffuse.png` — replaced
- `assets/the_watcher/eye_normal.png` — regenerated
- `assets/the_watcher/eye_specular.png` — regenerated
- `Scripts/tools/map_photo_eye.py` — new script (companion to gen_eye_textures.py)
- `dist/Iris.app` — hot-swapped via hotswap.sh

### Mapping approach

Orthographic projection (parallel projection from +Z, the camera-facing direction).

The photo center (iris/pupil) maps to UV (0.25, 0.50) — the +Z pole on
`make_sphere()`'s equirectangular grid. The photo's shorter dimension (width = 220 px)
defines the hemisphere radius so the full horizontal extent of the photo fills the
sphere's visible face without stretching. Bilinear interpolation upsamples the
220×294 source to the 2048×1024 equirectangular target.

Back hemisphere (sz < 0) is filled pure black — it sits against the void and is
never normally visible.

The specular map retains the same 38° cornea cap angular definition as before so
the wet-glass specular highlight and iris emission (`eye.frag`) stay correctly
aligned with the iris region in the new photo.

The normal map is re-derived from the new diffuse's luminance gradient (same
NORMAL_STRENGTH = 4.5 as before) so surface relief follows the photo's actual
light/dark detail rather than the old procedural veins.

### Validation

- `eye_diffuse.png` at UV (0.25, 0.50): brightness = 0 (dark iris/pupil, correct).
- Specular peak at UV ≈ (0.241, 0.315), value 250/255 ≈ 0.98 (full cornea gloss, correct).
- No shader changes.
- No renderer changes.
- No physics, tracking, parallax, rotation, or animation changes.
- `hotswap.sh` completed with valid code signature.

**Wiki updated.** [[the-watcher]] (Asset inventory section); this log entry.

---

## [2026-06-01] polish | The Watcher — eyeball texture zoom and shader simplification

**Scope.** Modified texture mapping tool and simplified eyeball fragment shader.

### Changes

- **Texture Mapping:**
  - Shifted projection center in `map_photo_eye.py` from geometric image center `(110, 147)` to actual pupil center `(114, 165)`.
  - Reduced hemisphere mapping radius (`half`) from `110.0` to `65.0` pixels, zooming/enlarging the eye features by ~1.7×.
  - Adjusted `IRIS_HALF_ANG` from 38° to 25° to match the new scaled iris.
- **Shader:**
  - Simplified `shaders/eye.frag` to render only the raw B&W diffuse texture.
  - Removed wrap diffuse, normal mapping, cornea specular, iris emission, and rim glow. This allows the high-contrast B&W photo to pop cleanly without any coloring or shading.

### Validation

- Re-ran `map_photo_eye.py` to regenerate all textures.
- Ran all 6 headless simulation checks successfully.

---

## [2026-06-01] perf | Desktop-lag audit — frame-rate cap, gem-floor geometry, state-write throttle

**Trigger.** "Running IRIS makes opening other apps lag, desktop feels sluggish,
CPU looks high." Physics was the prime suspect; the brief asked for an
evidence-driven audit before any rewrite.

**Method.** Wiki-first: read [[engine-loop-and-daemon]], [[rendering-engine]],
[[head-tracking]], [[constraints]], [[known_issues]] before source, then read the
hot paths (`app_engine.py` main loop, `renderer.py`, `bloom_postfx.py`,
`camera_math.py`, `face_tracker.py`). **Measured** the CPU-side per-frame work in
the venv rather than guessing.

**Findings (evidence).**
- **There is no physics engine.** `camera_math.py` is pure matrix algebra —
  measured **6.9 µs/frame**. No collision/raycast/rigid-body work runs in the loop
  (`segment_hits_sphere` is only the *separate* icons app's hit-test). Suspicion
  retired.
- Total CPU-side main-loop overhead **~68 µs/frame** (~4 ms/s): state-file write
  **55 µs** (synchronous disk I/O, the largest), matrices 7 µs, flag stats 5 µs,
  prefs stat 1 µs. **CPU is not the bottleneck.**
- MediaPipe: 1.6 ms with no face / ~34 ms with a face (per [[head-tracking]]), on
  its own thread at ~30 Hz — real but secondary and necessary.
- **Root cause = a full-screen, native-Retina wallpaper rendered at 60 fps while
  the head input is only ~30 Hz.** Half the frames are duplicate-input redraws,
  and as a desktop-level layer the macOS WindowServer must recomposite it under
  every other window every frame (M2 runs GL translated to Metal). That is the
  desktop stutter.
- Active world at audit time was **[[the-gem]]**, whose checkered floor — a flat,
  unlit plane — was over-subdivided to **60×60 = 21,600 verts re-streamed every
  frame** through the client-side-array path.
- Per-frame `glGetFloatv(GL_MODELVIEW_MATRIX)` pipeline stalls: 1 in
  `_view_rot_3x3` + 1 per icon in `IconOrbit.draw` ([[orbital-icons]]).

**Changes shipped (low-risk, behaviour-preserving).**
- `Launcher/app_engine.py`: added `FPS_DEMO = 60` / `FPS_WALLPAPER = 30`;
  `clock.tick()` now caps wallpaper/fullscreen/`desktop_active` to 30 fps
  (demo stays 60). ~halves GPU + compositor load — **the primary fix**.
- `Engine/renderer.py` (`Gem`): `_FLOOR_DIVS 60 → 1` (21,600 → **6 verts**;
  perspective-correct UV interpolation makes a 2-triangle plane pixel-identical)
  and `_FLOOR_TILE 1.0 → 10.0` (checks ~10× larger — they read far too small).
  *(The larger checks were a user request that matched the profiling.)*
- `Launcher/app_engine.py`: `~/.parallax_earth_state.json` export **throttled to
  ≤30 Hz** (was a synchronous write every frame of values that only change at
  ~30 Hz).

**Recommended next (not done — would exceed "low-risk").** Replace the per-icon
`glGetFloatv` with a CPU-built billboard matrix (pass the modelview into
`IconOrbit.draw`); migrate static meshes (Earth spheres, stars, nebula) to VBOs;
optionally drop MSAA 4×→2× / increase bloom downscale in wallpaper mode.

**Industry grounding.** Avoid `glGet*` round-trips (Khronos: pipeline stall);
prefer VBOs over client-side arrays (OpenGL Wiki); match render rate to
input/sim rate; minimise compositor pressure for desktop-level layers.

**Validation.** `ast.parse` clean on both edited files; floor mesh re-derivation
confirms 6 verts and correct `GL_REPEAT` UVs (960 checks across the floor);
changes are localized. Live GPU-profiler confirmation needs a GUI session (same
constraint as all renderer work — see [[constraints]]).

**Wiki updated.** [[constraints]] (frame-rate caps + new "Performance posture"),
[[engine-loop-and-daemon]] (frame-rate section + throttled state export),
[[the-gem]] (floor plane description + fully-procedural note), [[current-focus]]
(perf entry), and this log entry.


---

## [2026-06-01] fix + audit | Overlay idle-fade-on-hover; render-path latency audit

**Two user reports.** (1) Demo buttons "grey out a couple seconds after I hover,
over an area bigger than the hitbox." (2) "Latency is slightly high for the
illusion to be believable" — suspected the [[the-gem]] checkered floor and/or
"all 3 worlds loaded at once."

### 1. Overlay greying — root cause found (not the hitbox)

**Reproduced headlessly.** With the cursor resting on the primary button
(`hover == "primary"`, `hover_t == 1.0`), the whole control cluster still faded to
`_ctrl_alpha = 0.34` after the 4 s idle timeout.

**Root cause.** `DemoOverlay.update()` computed `idle = now - _last_input`, and
`_last_input` only refreshes on `MOUSEMOTION` / `MOUSEBUTTONDOWN`. A mouse emits
no events while held still, so a *stationary hover* — an actively-engaged state —
was treated as idle and the entire control layer (status pill + every button +
scrim) dimmed. That whole-layer dim is the "area bigger than the hitbox" the user
saw; the hitbox itself is fine (`_hit` uses the same rect that draws the grey
fill — `sim_overlay` check 7 confirms exact hit-testing). The user's hitbox
hypothesis was a red herring.

**Fix.** `UI/demo_overlay.py:update()` — treat an active hover as engagement:
`idle = 0.0 if self.hover is not None else (now - _last_input)`. Controls stay lit
while the cursor rests on any control; idle-fade resumes when it moves away.

### 2. Latency audit — the two suspected causes do NOT hold

- **Checkered floor:** already fixed in the 2026-06-01 perf pass (60×60 = 21,600 →
  **6 verts**, mipmapped `GL_REPEAT` texture). It is now a 2-triangle plane + one
  texture lookup — not a measurable per-frame cost.
- **"All 3 worlds loaded at once":** false. `WorldRuntime` holds exactly **one**
  world definition (`self._def`); `Eye`/`Gem` renderers are built lazily on first
  selection and cached, and only the *active* world's mesh is drawn (the draw path
  branches on `world.primary_mesh`). Switching is instant because the heavy
  `Earth`/`Stars`/`Nebula` objects are pre-built at startup and Gem/Eye persist —
  intentional caching, **not** concurrent rendering. ([[world-system]])

### 2b. Real render-path costs — two GPU→CPU stalls removed

Both were flagged "recommended next" in the 2026-06-01 entry; now done.

- `Launcher/app_engine.py`: removed `_view_rot_3x3()` and its per-frame
  `glGetFloatv(GL_MODELVIEW_MATRIX)`. The view rotation is now sliced from the
  `mv` matrix already built on the CPU (`view_rot = mv[:3, :3]`). Pixel-identical;
  one pipeline stall gone **every frame, every world**.
- `Engine/renderer.py` (`IconOrbit.draw`): replaced the **per-icon** `glGetFloatv`
  with a single Earth-origin modelview read + a CPU billboard (`diag(ICON_SIZE)`
  3×3, eye-space origin via one mat·vec). **N stalls/frame → 1** in the Earth
  world. Verified numerically identical to the old read-back (max abs matrix diff
  1.9e-6 = float32 noise).

### 2c. Findings flagged, NOT changed (frozen / risk)

- **Headline head→photon latency is dominated by the FROZEN pipeline, not render
  cost.** MediaPipe VIDEO ~34 ms mean / 68 ms p95, then **two** smoothing layers:
  the tracker's velocity-adaptive lerp (frozen; `sim_latency`) **plus** a second
  `CAM_LAG = 0.55` per-frame exponential in `app_engine`. Because `CAM_LAG` is
  applied **per frame, not dt-normalised**, its time-constant is frame-rate
  dependent: ~57 ms to 90 % at the 60 fps demo vs **~113 ms at the 30 fps
  wallpaper/desktop cap** — so the illusion genuinely feels laggier once Desktop
  Mode drops to 30 fps. This is the most likely source of the "slightly high"
  perception. Making `CAM_LAG` dt-aware would fix it but touches frozen smoothing
  — **needs explicit approval + a new sim**; not done. ([[constraints]])
- **Bloom runs in the Gem world even though `gem/world.json` sets
  `"use_bloom": false`** — the engine's `bloom_enabled` is global and never reads
  the per-world flag. Wasted full-screen post-process in a world that asked for it
  off. Recommend honouring per-world `use_bloom`; not changed (behaviour/risk).
- Client-side vertex arrays still re-streamed every frame (Earth = 3 spheres,
  96×96). VBO migration still recommended.

**Validation.** `sim_overlay` (26 checks), `sim_latency`, `sim_orbit` all pass;
`py_compile` clean on all three edited files; billboard equivalence checked
numerically (1.9e-6).

**Wiki updated.** [[known_issues]] (overlay fix), [[current-focus]] (audit +
stalls done), [[constraints]] (glGet stalls removed; CAM_LAG frame-rate note),
[[ui-overlay]] (idle-fade respects hover), and this log entry.
