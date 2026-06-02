---
title: Ingestion Log
type: metadata
related: [index]
last_updated: 2026-06-02
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


---

## [2026-06-01] perf+latency | The four flagged follow-ups executed (CAM_LAG dt-aware, per-world bloom, VBOs, wallpaper MSAA/bloom trims)

**Trigger.** User: execute the four unfinished latency-related fixes the prior
audit + perf passes had flagged as "recommended / not done." Item #1 touches the
FROZEN smoothing — executed under **explicit user approval** (the standing rule
requires it) and accompanied by a new validation sim, as the rule demands.

### 1. `CAM_LAG` → frame-rate-independent (the headline latency fix)

`Launcher/app_engine.py`. The camera smoothing was a FIXED per-frame factor
(`cam += 0.55·(target−cam)`), which makes the time-constant frame-rate dependent:
the same 0.55 reaches target ~2× slower in wall-clock at the 30 fps wallpaper cap
than at the 60 fps demo — the audit's most likely "slightly high latency" cause.
Replaced with a true exponential time-constant: `CAM_LAG_TAU` is derived from the
legacy 0.55 **at the 60 fps reference rate** (`tau = −(1/60)/ln(1−0.55) ≈ 20.9 ms`),
and each frame uses `cam_alpha = 1 − e^(−min(dt,CAM_LAG_DT_MAX)/CAM_LAG_TAU)`,
applied to all five smoothers (cam_x/y/z/yaw/pitch). Reproduces the calibrated
60 fps feel **byte-for-byte** (alpha(1/60)=0.55 exactly) and holds the SAME
wall-clock responsiveness at 30 fps. A `CAM_LAG_DT_MAX = 0.10 s` clamp stops a
long stall (resume-from-pause / first frame) from snapping in one step. The legacy
`CAM_LAG = 0.55` constant is retained as the reference factor the tau is derived
from. No other frozen module touched (camera_math, tracker smoothing untouched).

**New sim — `Scripts/validation/sim_camlag.py`** (the rule's "+ a new sim"):
proves (1) alpha(1/60) == 0.55 to float precision, (2) 30 fps and 60 fps reach
90 % of a step in the same wall-clock time, (3) the OLD scheme was frame-rate
dependent (~2× at 30 fps) and the fix lowers the 30 fps lag, (4) the dt clamp
bounds the step. RESULT: all checks passed.

### 2. Per-world `use_bloom` honoured

`Worlds/world_runtime.py`: new `use_bloom` property (default **True** → Earth and
any world omitting the flag are unchanged). `Launcher/app_engine.py`: per-frame
`use_bloom_now = bloom_enabled and world.use_bloom` gates both bloom passes; when
off, the scene renders straight to the default framebuffer (viewport reset to the
full drawable so a live switch from a bloom world is clean). Skips the
bright→2×blur→composite full-screen passes for worlds that asked bloom off.
**Behavioural note:** BOTH [[the-gem]] and [[the-watcher]] declare
`"use_bloom": false`, so both now also lose the composite's exposure (1.22),
vignette (0.42) and chromatic aberration — those effects lived in the bloom
composite. Earth (`use_bloom: true`) is pixel-identical.

### 3. Static meshes → VBOs

`Engine/renderer.py`. `Mesh` (Earth ×3 spheres, Nebula, Eye, Gem facet-soup) and
the `Stars` point field now upload their attribute/index arrays to GL buffer
objects ONCE at construction (`GL_STATIC_DRAW`) instead of re-streaming every
vertex from the CPU each frame (~190 k verts/frame for Earth+Nebula alone). Draw
binds the buffers + byte-offset pointers and **unbinds to 0 afterwards** so the
floor/shadow/icon/bloom client-array draws that share GL state are unaffected.
Both classes keep a transparent **client-array fallback** if buffer creation
fails (no behavioural change, just the old cost). All geometry is static — all
motion is via the modelview, so a one-time upload is exactly equivalent.

### 4. Wallpaper-mode GPU trims

`Launcher/app_engine.py` + `Engine/bloom_postfx.py`. MSAA samples are now
`4 if DISPLAY_MODE == "demo" else 2` (set at context creation; the in-process
demo→Desktop switch keeps its 4× since MSAA can't change live, but the standalone
wallpaper daemon launches at 2×). `BloomPipeline` gained a `downscale` arg; the
demo passes 2× (crisp), wallpaper/fullscreen/desktop pass 4× (softer + cheaper
blur buffers). Both are imperceptible at desktop scale and cut GPU/compositor load.

**Validation.** `py_compile` clean on all four edited files + the new sim. All
seven headless sims pass: the six existing (`sim_orbit/offaxis/viewing/latency/
vertical/overlay`) + the new `sim_camlag`. The renderer VBO path, the per-world
bloom gate, MSAA and bloom-downscale changes are GL-side and can only be
confirmed live in a GUI session (the standing renderer/GL constraint) — the code
preserves exact visual output with fallbacks, and Earth is unchanged by design.

**Wiki updated.** [[current-focus]] (new top section + three stale "recommended
next" notes struck through), and this log entry.


---

## [2026-06-01] decision | Bloom post-processing removed entirely (supersedes the per-world `use_bloom` gate)

**Trigger.** Follow-up to the entry above. Asked what bloom contributes
(answer: purely visual — soft glow on bright pixels, plus the composite's Reinhard
tonemap + exposure ×1.22 + vignette + chromatic aberration; zero functional role,
and it *costs* GPU). User then chose to **remove all glow and bloom on every world
including Earth**, with the only requirement that parallax, star twinkle and gem
shimmer keep working.

**Why it's safe for the three things that matter.** All three are generated
*upstream* of bloom and are untouched: parallax is `camera_math` (off-axis
frustum + view matrix), star twinkle is animated in `stars.frag` from `u_time`,
and the gem's facet shimmer is `gem.frag` specular/fresnel/emissive/iridescence.
Bloom only added a soft halo around the brightest pixels and the screen grade.

**Change.** `Launcher/app_engine.py`: removed the `BloomPipeline` import, its
construction, the Desktop-Mode FBO rebuild, and both render passes. The scene now
draws **straight to the default framebuffer** (the previous "FBO setup failed"
fallback path, now the only path). Reverted the two now-moot pieces from the entry
above: `WorldRuntime.use_bloom` (deleted) and the `BloomPipeline(downscale=…)`
parameter (`Engine/bloom_postfx.py` back to its original signature). The MSAA
4×→2× wallpaper trim from that entry is **kept** — and now actually matters:
because the scene previously rendered into a NON-multisampled bloom FBO, MSAA had
never applied; drawing to the multisampled default framebuffer means real
anti-aliasing for the first time. `bloom_postfx.py` is left in the tree (unused).

**Accepted visual change.** Every world loses the glow and the grade. Earth is
~22 % dimmer and flatter (lost the exposure multiplier + vignette + the gamma/
Reinhard tonemap); The Gem and The Watcher lose the glow halo and grade too. This
was explicitly chosen over the "keep the cheap grade, drop the glow" alternative.

**Validation.** `py_compile` clean (app_engine, renderer, bloom_postfx,
world_runtime). All seven headless sims pass (six existing + `sim_camlag`). The
GL/visual result needs a live GUI session to confirm (standing renderer
constraint), but the path is the proven no-FBO fallback.

**Wiki updated.** [[current-focus]] (top section rewritten — bloom removal
replaces the per-world gate), and this log entry.

---

## [2026-06-02] docs | The Grid Room — world page + index integration

**Scope.** The Grid Room world (`Worlds/grid_room/world.json`, `GridRoom` renderer
class in `Engine/renderer.py`) existed in the source tree and was documented in
the architecture-layer [[grid-api-customization]] page but was **not documented as
a playable world**. Created a dedicated world page and updated all world-related
indexes to list it as the fourth available world.

### Created

- **New page:** `obsidian-docs/worlds/grid-room.md` — comprehensive world reference
  (92 KB) covering what the Grid Room is (spatial-reference scaffold), how it renders
  (wireframe cyan `GL_LINES` shadow-box in world space), dimensions (±11.33 × ±6.375
  × 18 deep, 8×8 grid cells), constraints (no shaders, alpha fade front→back, mesh
  cached), and integration with parallax. Related links tie it to [[gem]] (which shares
  grid dimensions), [[grid-api-customization]], and [[world-system]].

### Updated

- **`obsidian-docs/index.md`:** Intro text updated "Three worlds ship" → "Four worlds
  are available". Added Grid Room row to the worlds table (summary: "wireframe
  spatial-reference calibration tool").
- **`obsidian-docs/worlds/worlds-index.md`:** Expanded comparison table from 3 columns
  to 4. Now includes Grid Room properties: `primary_mesh: "room"`, `GridRoom` renderer,
  **no shaders** (fixed-function only), cyan color, 18.0 depth, 8 divisions (matching
  Gem), use case (reference/calibration vs. scenic). Updated intro to "Four worlds:
  three scenic, one utility/calibration". Updated "Systems every world uses" and
  "Adding a world" sections to list `room` as a valid `primary_mesh` type.
- **Related links:** Backlinks added to [[gem]] (which references grid dimensions),
  [[grid-api-customization]] (the design-decision that describes the grid API), and
  [[world-system]].

### Design notes

The Grid Room is **not a scenic experience** but a **spatial-reference utility and
API surface** for the [[grid-api-customization]] safe-customization framework. Its
receding wireframe grid teaches users/Claude the coordinate system directly on
screen; the converging lines provide the parallax illusion with a strong motion-
parallax cue; the rigid box helps the visual system distinguish head motion from
tracking jitter. No shaders (frozen GLSL is untouched); fully procedural geometry
(cached based on aperture dimensions, rebuilt only on resize). The cyan color was
chosen to complement both white-background worlds ([[gem]]) and blue starfields
([[earth]]).

**Wiki updated.** `[[grid-room]]` (new page), `[[worlds-index]]`, `[[index.md]]`,
and this log entry.

---

## [2026-06-02] feature | The Gem — checkered enclosure box (floor → full grid box)

**Scope.** First of two requested Gem updates. Replaced the Gem world's single
flat checkered floor with a full **checkered enclosure box** — the pink gem now
floats inside a pink-and-white checker room that shares the [[grid-room]]'s
dimensions, with each checker square sized to exactly one grid cell ("the checker
IS the grid"). No camera math, physics, or shader code touched.

### What changed

**`Engine/renderer.py` — `Gem` class.**
- Removed the old infinite flat floor (`_build_floor_mesh` / `_draw_floor`,
  `_FLOOR_HALF=600`, `_FLOOR_DIVS`, `_FLOOR_TILE`, `_FLOOR_Y`).
- Renamed `_build_floor_texture` → `_build_checker_texture` (unchanged pink/white
  8×8 `GL_REPEAT` checker; pink `(255,182,193)`, white `(255,255,255)`).
- New `_build_box_mesh(half_w, half_h, depth, divisions)`: five interior faces —
  floor, ceiling, back wall, left/right walls — as textured quads in WORLD space
  (front rim on the glass at z = 0, back wall at z = −depth, floor/ceiling at
  y = ∓half_h, walls at x = ±half_w). Each face's UVs run `0..(divisions/8)`, so
  the 8×8 checker lays down exactly `divisions` checks across the `divisions`
  cells of every face → **one check per grid cell**, the checks stretched to match
  each face's (non-square) cell aspect. 30 verts / 30 UVs, rebuilt + cached on a
  dimension key like [[grid-room]].
- New `draw_box(...)`: draws the cached faces (flat, unlit, fixed-function,
  `GL_CULL_FACE` off so interior faces always show) + the grounding shadow.
- Shadow disk rebuilt in the `y = 0` plane and re-positioned by `draw_box` onto
  the box floor (`y = −half_h`) directly beneath the gem anchor (`_GEM_ANCHOR_Z =
  −10`), instead of the old fixed `y = −3.30` mid-air disk.
- `Gem.draw()` is now gem-mesh-only (spin + tilt + shader unchanged).

**`Launcher/app_engine.py`.** The gem world builds the gem lazily and calls
`gem.draw_box(hw, hh, world.grid_depth, world.grid_divisions)` in WORLD space
**before** the Earth-anchor translate (like the Grid Room), then draws the gem at
the z = −10 anchor so it floats inside the box. The in-translate gem branch is now
draw-only.

**`Worlds/gem/world.json`.** Added `grid_depth: 18.0` + `grid_divisions: 8`
(explicit; they also match the `WorldRuntime` defaults and the [[grid-room]]).
Removed the now-unused `floor_texture` key (the checker is generated in-memory).
Bumped to v1.1.

### Dimensions

Aperture-derived: `half_w = WINDOW_HALF_H·aspect ≈ 11.33` (16:9), `half_h =
WINDOW_HALF_H ≈ 6.375`, `depth = 18`, `divisions = 8`. Per-cell (= per-check)
sizes: X 2.833, Y 1.594, Z 2.250 world units. The gem (girdle r = 2.2, y ∈
[−2.80, 0.79], z = −10) sits fully inside the box, floating ≈3.57 u above the
checker floor.

### Validation

- `py_compile` clean on `renderer.py` + `app_engine.py`; `gem/world.json` parses.
- All **9** headless sims pass (`sim_calibration/camlag/latency/offaxis/orbit/
  overlay/predict/vertical/viewing` — RESULT: all checks passed), run under the
  `.venv` (pygame).
- Standalone numeric check of `_build_box_mesh`: 30 verts, UV span 0..1 at
  divisions = 8 (exactly one check per cell), box extents ±11.33 × ±6.375 ×
  0..−18, gem fully enclosed.
- The GL/visual result needs a live GUI session to confirm (standing renderer
  constraint); the path is the proven fixed-function textured-quad + client-array
  shadow already used by the old floor.

**Wiki updated.** [[gem]] / [[the-gem]] (floor → checkered box), [[worlds-index]]
(floor/shadow rows), and this log entry.

---

## [2026-06-02] fix | Per-world enveloping zoom + late look-gate for enclosure worlds

**Symptom (user, in the Grid Room).** Moving CLOSER made the grid *shrink* —
reading as "zooming out" — instead of enveloping the viewer, and the rotational
"look" was active at ordinary forearm distance, letting the viewer rotate the
z = 0 window plane and **peer past the bezel-locked front rim**. The desired
behaviour: all motion translational and rim-locked during approach, with
rotational look engaging only once *enveloped* (~10–15 cm from the camera).

**Root cause (two consuming-layer issues, NOT frozen camera_math).**
1. *Zoom direction.* `Launcher/app_engine.py` mapped `cz = BASE_Z·e^(+ZOOM_K·hz)`
   for every world, so leaning IN *increased* cz → narrower telephoto frustum.
   That is the calibrated, deliberate feel for a single FOREGROUND object (the
   Earth grows on approach — pinned by `sim_viewing`/`sim_vertical`), but it is
   backwards for an ENVIRONMENT you enter: a real shadow-box envelops you as the
   eye nears the glass (smaller cz → wider frustum). The window-correct sense is
   the one [[off-axis-projection]] already documents.
2. *Rotation gate.* `om.proximity(hz)` used the frozen default window `[0.0, 0.8]`,
   so rotation began the instant the viewer leaned past neutral — un-pinning the
   rim at forearm distance.

**Why per-world, not global.** A global zoom flip would (a) invert the Earth's
deliberately-calibrated telephoto zoom and (b) break `sim_viewing` checks 1–2 and
gut `sim_vertical`'s near-field "push the planet off-screen" exploration (a wide
close-range frustum can't pan a foreground object past half-FOV under the 46°
anti-nausea clamp). Both were explored and rejected with the user; the chosen
scope is **enclosure worlds only**.

**Fix.** A declarative `rendering.enveloping` flag (default **False** → object
worlds byte-identical). New `WorldRuntime.enveloping` property; set `true` in
`Worlds/grid_room/world.json` and `Worlds/gem/world.json`. In `app_engine.py`:
- `zoom_sign = -1.0 if world.enveloping else 1.0` → enclosure `cz = BASE_Z·e^(−ZOOM_K·hz)`
  (lean IN → cz 11.5→5.0, FOV 58°→104°, envelopment); object path unchanged.
- enclosure rotation uses `om.proximity(hz, lo=ROT_GATE_LO=0.7, hi=ROT_GATE_HI=1.0)`
  (zero look until enveloped, smooth ramp to full at hz=1.0); object path keeps the
  frozen default gate. **camera_math.py untouched** (lo/hi passed as args).

**Validation.** New guard `Scripts/validation/sim_envelop.py` (window-correct zoom
monotone, rim bezel-locked at every approaching eye, look gated to envelopment +
C¹, per-world sign genuinely flips). **All 10 headless sims pass**; `sim_viewing`
and `sim_vertical` are **byte-identical to before** (object path preserved), so the
Earth/Watcher feel + their guards are intact. Live GL confirmation in the Grid Room
still needs a GUI session (standing renderer constraint).

**Files.** `Launcher/app_engine.py`, `Worlds/world_runtime.py`,
`Worlds/grid_room/world.json`, `Worlds/gem/world.json`,
`Scripts/validation/sim_envelop.py` (new). Records: [[known_issues]],
[[current-focus]], [[constraints]], [[off-axis-projection]], [[grid-room]].

---

## [2026-06-02] change | Enclosure depth model → forward dolly (replaces the same-day frustum-widen)

**Trigger.** With the enclosure model from the entry above shipped, leaning IN to
the Grid Room / Gem made the grid squares *expand and stretch* (perceived depth
~doubled) and the floating gem *shrink* — the opposite of the wanted "move in =
zoom in." The ~15 cm rotational look also sheared/distorted the still-visible grid
instead of cleanly rotating once enveloped.

**Why the previous model did that (not a bug — geometry).** The earlier fix used
`cz = BASE_Z·e^(−ZOOM_K·hz)`, so leaning in shortened `cz` and WIDENED the off-axis
frustum. That is the geometrically-correct *fixed-window* result, but a foreground
object at `z = −10` has on-screen size ∝ `cz/(cz+10)`, so a smaller `cz` shrinks it
and stretches the receding grid. Window-correct, wrong feel.

**Fix — forward dolly (per-world mechanism, user-chosen).** For `enveloping = true`
worlds the engine now HOLDS `cz = BASE_Z` (FOV constant at 58° — no lens zoom) and
translates the whole scene toward the eye by `dolly = clamp(DOLLY_GAIN·hz,
[DOLLY_MIN, DOLLY_MAX])` world units along −z, baked into the modelview
(`mv = view_matrix(...) @ T(0,0,dolly)`). Leaning in dollies the camera INTO the
room: the gem grows with honest perspective (≈2.5× at full lean), the walls slide
past, and the front rim expands off-screen until it clears the near plane
(enveloped). Look-gate tightened to `om.proximity(hz, lo=ROT_GATE_LO=0.88,
hi=ROT_GATE_HI=1.0)`, tuned so the rim is already off-screen before any pan engages
— so the look can never shear a visible grid edge. Object worlds set `dolly ≡ 0`
and keep telephoto `cz` → byte-identical (`max |Δcz| = 0`). `DOLLY_GAIN = 13`,
`DOLLY_MAX = 14`, `DOLLY_MIN = 0` (a hard zoom-out floor — leaning back past the
neutral, bezel-locked framing does NOT pull the camera further out; you dolly in
from there and back out only to it). **camera_math.py untouched** (dolly is a
modelview translate; gate lo/hi are call args).

**Validation.** Rewrote `Scripts/validation/sim_envelop.py` to pin the dolly
invariants: constant FOV; monotone forward dolly; foreground gem GROWS on lean-in
(208→747 px, 2.53× neutral→enveloped); rim past the near plane when enveloped and
bezel-locked exactly at neutral; look zero through the approach with the rim already
off-screen the moment it engages; C¹ gate; object path untouched. **All 10 headless
sims pass** (`sim_viewing` / `sim_vertical` / `sim_offaxis` / `sim_orbit`
unchanged). Live GL "feel" tuning of `DOLLY_GAIN` / `ROT_GATE_LO` still needs a GUI
session (standing renderer constraint).

**Files.** `Launcher/app_engine.py` (DOLLY_* constants, per-world depth-response
block, modelview dolly, raised ROT_GATE_LO), `Worlds/world_runtime.py`
(`enveloping` docstring), `Scripts/validation/sim_envelop.py` (rewritten). World
JSONs unchanged. Records: [[known_issues]], [[current-focus]], [[constraints]],
[[off-axis-projection]], [[grid-room]], [[the-gem]].

---

## [2026-06-02] tune | Enclosure rotational look — engage earlier + much smoother ramp

**Trigger.** User, in the enclosure worlds ([[grid-room]] / [[the-gem]]): enable the
rotational "look" ~5–10 cm further from the screen than it engages now (begin around
the 15–20 cm proximity band), and **vastly smooth** the transition.

**What the knobs are.** The look is gated by `om.proximity(hz, lo=ROT_GATE_LO,
hi=ROT_GATE_HI)` — a smoothstep on the tracker's head-z (`hz`, face-size based;
**no documented cm mapping**, so the cm targets translate to an hz threshold tuned
live). The forward dolly carries the front rim off-screen at `dolly > BASE_Z − NEAR
≈ 11.2` (`dolly = DOLLY_GAIN·hz`). The standing design rule (and `sim_envelop.py`)
requires the **rim gone BEFORE the look engages**, else a pan shears a still-visible
grid edge — the exact "grid distorts" regression the user reported on 2026-06-02 and
the reason the gate had been raised to 0.88.

**Decision (user-chosen: "earlier + keep it clean").** Lower the gate AND raise the
dolly gain together so the rim still clears first — earlier look with **no** shear,
at the cost of dollying into the room a little faster (explicitly accepted).

**Change (consuming layer only — `camera_math.py` untouched; lo/hi/gain are
args/constants in `app_engine.py`).**
- `ROT_GATE_LO` **0.88 → 0.75** — look begins further from the screen.
- `ROT_GATE_HI` 1.0 (unchanged) → window **[0.75, 1.0]** vs old [0.88, 1.0]: ~2×
  wider, so the smoothstep ramp is ~2× gentler (the "vastly smoother" fade).
- `DOLLY_GAIN` **13.0 → 15.5** — rim now clears at `hz ≈ 0.72` (= 11.2/15.5),
  *before* the 0.75 gate, preserving "rim gone first."
- `DOLLY_MAX` **14.0 → 16.0** — keeps `dolly` rising past the old clamp so the
  foreground body still grows **monotonically all the way to hz = 1.0** (gem now
  ≈3.6× at full lean vs the prior ≈2.5×; honest consequence of the faster dolly).
- `DOLLY_MIN` 0.0 (unchanged) — the bezel-locked zoom-out floor is intact.

**Validation.** `sim_envelop.py` updated in sync (constants + the check-5 zero-look
assertion list, which had pinned `prox(0.8)==0` — now `prox(0.7)==0`, since 0.8 sits
inside the new engagement window). The rim-clears-before-look invariant re-verified:
rim eye_z = **+0.12** at the new gate hz = 0.75 (> −NEAR, off-screen). **All 10
headless sims pass**; `py_compile` clean. Live GL "feel" confirmation of the exact
cm landing point still needs a GUI session (standing renderer constraint) — the hz
threshold is the live-calibration knob.

**Files.** `Launcher/app_engine.py` (DOLLY_*, ROT_GATE_LO + comments),
`Scripts/validation/sim_envelop.py` (synced constants + assertion). Records:
[[grid-room]], [[the-gem]], and this entry.

---

## [2026-06-02] merge | Grid + sphere merge — enclosures gain Earth's blended look while keeping their bezel anchor

**Trigger.** User decision: "take the good parts of the grid worlds and the good
parts of the sphere worlds and merge them." The [[earth]] (sphere/object) world has
the better **zooming + eye-looking** — rotation and translation coexist across a wide
proximity band, so it feels like *moving around* the scene. The enclosure worlds
([[grid-room]], [[the-gem]]) have the better **screen anchor** — the bezel-locked
front rim. The standing analysis page [[what-makes-perspective-optimal]] had already
diagnosed why and proposed the path; this entry **executes the proposed update**.

**What was wrong.** Enclosures deferred ALL rotational look until the viewer was
nearly enveloped (`om.proximity(hz, [0.75, 1.0])`), giving a SEQUENTIAL "first move
in, THEN look around" feel — the opposite of Earth's blended band [0.0, 0.8]. We
couldn't simply open the gate early, because rotating while the front rim is still on
screen shears the visible grid (the prior "grid distorts" regression).

**Fix — amplitude-gated early look (the option-4 path from the analysis page;
consuming layer only).** The single enclosure look weight is split into two
smoothstep factors, `prox = engage(hz)·amp(hz)`:
- `engage = om.proximity(hz, lo=LOOK_ENGAGE_LO=0.35, hi=LOOK_ENGAGE_HI=1.0)` — opens
  EARLY and WIDE, mirroring Earth's band, so the look blends with the forward dolly
  across the whole approach. `engage(0)=0`, so the resting rim stays bezel-locked.
- `amp = LOOK_PRELOOK_AMP + (1−LOOK_PRELOOK_AMP)·om.proximity(hz, [LOOK_AMP_LO,
  LOOK_AMP_HI])` — caps the look AMPLITUDE to `LOOK_PRELOOK_AMP = 0.22` while the
  front rim is still on screen, then ramps to full as the rim clears the near plane.
  `LOOK_AMP_LO = (BASE_Z − NEAR)/DOLLY_GAIN ≈ 0.72` is **derived** from `DOLLY_GAIN`,
  so cap-release always tracks the actual rim clear (they stay coupled if either is
  retuned); `LOOK_AMP_HI ≈ 0.92`.

**Why it's shear-free (verified numerically).** The bezel-locked rim leaves the
*screen* the instant the dolly starts — its corners are off-screen by hz ≈ 0.02, the
whole frame gone shortly after — i.e. long before the look engages at hz ≈ 0.35. So
during its on-screen exit the look is exactly zero and the rim never shears. After
that, the only still-visible geometry that could shear is the receding interior grid,
and the amplitude cap keeps that pan gentle until envelopment. Full-strength look
arrives only once enveloped (rim long gone). The product of two smoothsteps is
monotone and C¹ — no felt mode switch.

**Scope discipline.** `Engine/camera_math.py` is **untouched** — every `lo/hi` is a
`proximity()` call argument; the frozen smoothstep is unchanged. Object worlds keep
the frozen `om.proximity(hz)` gate ([0.0, 0.8]) and never amplitude-cap, so
Earth/The Watcher are byte-identical. The forward-dolly *depth* model and the
`DOLLY_MIN = 0` zoom-out floor are unchanged. The old `ROT_GATE_LO/HI` constants are
replaced by the `LOOK_*` block.

**Validation.** Rewrote `Scripts/validation/sim_envelop.py` check-5 to pin the merged
invariants: (a) zero look at neutral/lean-out (rim bezel-locked); (b) the MERGE — the
look engages EARLY (prox(0.5) > 0) where the old sequential gate was exactly 0; (c)
look amplitude capped ≤ 0.22 until the rim clears, and the capped early pan is a small
fraction of the enveloped pan; (d) full amplitude + significant reveal once enveloped;
(e) monotone reveal; (f) C¹ (max step 0.0026). Measured: prox(0.5)=0.030,
reveal grows 0→307 px, gem still grows 3.58× on lean-in (depth model intact). **All 10
headless sims pass**; `sim_viewing` / `sim_vertical` / `sim_offaxis` / `sim_orbit`
unchanged (object path preserved); `py_compile` clean. Live GL "feel" calibration of
`LOOK_ENGAGE_LO` / `LOOK_PRELOOK_AMP` still wants a GUI pass (standing renderer
constraint) — the geometry/invariants are settled; the perception threshold is the
human's call.

**Files.** `Launcher/app_engine.py` (replaced the `ROT_GATE_*` block with the merged
`LOOK_*` block + per-world `prox = engage·amp`; updated the DOLLY_GAIN comment),
`Worlds/world_runtime.py` (`enveloping` docstring), `Scripts/validation/sim_envelop.py`
(constants + helpers + check-5 + docstring rewritten).

**Wiki updated.** [[what-makes-perspective-optimal]] (the proposal page — now marked
implemented, with the shipped design + remaining live-feel pass), [[viewing-models]]
(Method B look), [[off-axis-projection]] (rotation component), [[constraints]]
(per-world depth response), [[grid-room]] + [[the-gem]] (enclosure look),
[[current-focus]] (new top entry), [[known_issues]] (update note on the dolly entry),
and this log entry.
