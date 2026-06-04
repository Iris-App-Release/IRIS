This page contains the final findings, hypotheses, and reasoning from Claude sessions that were interrupted before completion (typically due to token limits, usage limits, or manual interruption).

Entries below should be treated as active investigation notes rather than verified project documentation. They may contain partially validated discoveries, suspected root causes, file references, recommended next steps, or work-in-progress analysis.

When resuming work:

1. Read the most recent entry first.
2. Verify any claims against the codebase and wiki.
3. Promote confirmed discoveries into the appropriate permanent documentation.
4. Remove or archive resolved entries once their knowledge has been incorporated elsewhere.

---

## 2026-06-03 — World Builder UX revisions (REQUESTED, NOT YET EXECUTED)

> **[RESOLVED 2026-06-03]** Executed in full. All 7 requested changes shipped in
> `UI/demo_overlay.py` + `Licensing/entitlement.py`; no frozen modules touched.
> A new headless guard `Scripts/validation/sim_world_builder.py` pins the flow
> (Send=preview, Save=new world, Delete World + safety, unlimited gate); **all 12
> sims pass** and the three new UI states were render-verified headlessly. Summary:
> - **Send** button on the right card → runs Claude, holds objects in
>   `_wb_preview_objects` (NOT saved), draws them on the Canvas Cube and mirrors
>   them into the `grid_room` scratch `world.json` so live Preview shows them too.
> - **Save** moved to the right card bottom → commits the previewed scene as a NEW
>   `Worlds/<slug>/world.json` (grid_room copy + derived name), rescans so it joins
>   the Worlds-tab cycle, then resets the scratch. grid_room stays the blank scratch.
> - **Left card** is now a static "How It Works" explainer (usage line + Save gone).
> - **Unlimited:** `FREE_CUSTOMIZATION_LIMIT = math.inf` (gate + usage line + upsell
>   modal removed from the flow; entitlement scaffolding kept on disk for later).
> - **Settings → Delete World:** toggle list of user worlds (built-ins/grid_room
>   never listed) → "Are you sure?" Yes/No → rmtree (refuses built-ins + any path
>   that doesn't resolve to a direct child of `Worlds/`) → rescan + fall back to
>   `earth` if the deleted world was active. Durable record promoted to
>   [[grid-creator-tool-plan]] §7–8 ("as built — UX revision").
>
> The original spec is kept below as the execution reference.

User reviewed the just-shipped World Builder authoring UI (right-panel prompt
input + left-panel Save + freemium upsell — see [[grid-creator-tool-plan]] §7–8
"as built") and gave a batch of UX corrections. **User explicitly said DO NOT
EXECUTE yet** — this entry is the spec to implement in a fresh session. Verify
every file reference against the live source before editing.

### Current state (what exists now, committed)
- `UI/demo_overlay.py` — World Builder tab, grid view. Two gold panels:
  **left = "Build Settings"** (advice + usage line + Save button), **right =
  "World Builder"** (focusable `_wb_prompt` text input). `_wb_save()` runs
  prompt → `generate_world_objects` → `sanitize_objects` → writes
  `assets.placeable_objects[]` into `Worlds/grid_room/world.json`. Upsell modal
  (`_wb_upsell`) gated by `Licensing/entitlement.py` (free tier = 1 save).
- `UI/world_builder_api.py` — `generate_world_objects(prompt, world_def)` →
  Claude (`claude-sonnet-4-6`), returns sanitized list or `[]`.
- `Licensing/entitlement.py` — `EntitlementChecker` (free counter in
  `~/.iris/licensing.json`).
- Canvas drawing: `DemoOverlay._draw_builder_canvas()` draws the empty oblique
  30° grid cube; it does **not** yet draw placeable objects. Live Preview
  (`_wb_view == "preview"`) renders the real grid_room via the engine.

### Requested changes
1. **Send button on the prompt box.** Add a **Send** button to the *right*
   (prompt) panel. Send = run the Claude generation and *preview* the result
   WITHOUT saving: store the returned objects in a transient field
   (e.g. `_wb_preview_objects`) and render them. (Generation moves OFF the Save
   button.)
2. **Move Save to the right panel, at the bottom.** Save no longer lives on the
   left. Save = commit the currently-previewed world into the user's Worlds
   list (see #5).
3. **Left panel = description + prompt advice ONLY.** Strip the usage line and
   the Save button from the left panel; it becomes a static explainer of what
   World Builder is + how to write a good prompt. (Usage line goes away entirely
   given #6.)
4. **Send renders on the Canvas Cube AND in Preview.** After Send, the generated
   objects must appear (a) drawn on the oblique Canvas Cube
   (`_draw_builder_canvas` — map each object via the existing `P(gx,gy,gz)`
   oblique projection; honor color/scale), and (b) in the live **Preview** when
   the user clicks Preview. Simplest mechanism: keep `grid_room/world.json` as
   the live scratch canvas — write the previewed objects there (validated) so
   both the Canvas overlay and the engine hot-reload show them. Decide whether
   Send writes to disk (drives hot-reload/Preview for free) or holds in memory
   and only the Canvas reads it; writing the scratch world is the lower-risk
   path since Preview already reads grid_room.
5. **Save adds the world to "my worlds".** On Save, create a NEW world:
   `Worlds/<slug>/world.json` = a copy of the grid_room def with the previewed
   `assets.placeable_objects[]` baked in (and a unique `name`). Then it must show
   up in the Worlds-tab cycle (`_world_keys` / `_load_worlds` rescan). Prompt for
   / derive a world name. Keep grid_room itself as the reusable blank scratch.
6. **Unlimited prompts and worlds (for now).** Remove the freemium gate from the
   flow: no per-save limit, no upsell modal, no usage line. Keep
   `Licensing/entitlement.py` on disk but make `can_save_customization()` always
   True (e.g. a config/flag or `FREE_CUSTOMIZATION_LIMIT = math.inf`) so the
   monetization scaffolding survives for later without blocking the user now.
7. **Settings → "Delete World".** Add a **Delete World** control to the Settings
   tab. Click → show a list of the user's worlds → click one → confirmation
   popup *"Are you sure you want to delete this?"* with **Yes / No**. Yes →
   remove the world cleanly (delete `Worlds/<slug>/` dir, drop from
   `_world_keys`/`_world_names`, and if it was the active world fall back to a
   safe default like `earth`); No → dismiss, nothing changes.

### Constraints / safety to carry in
- **Frozen boundaries unchanged:** no edits to `Engine/camera_math.py`,
  `shaders/`, physics, `grid_divisions`/`grid_depth`/`enveloping`. World Builder
  stays fixed-function + JSON only.
- **Validate before every write** with `Worlds.placeable.sanitize_objects`
  (Send-preview write AND Save-to-new-world write).
- **Delete safety:** only delete inside `Worlds/`; refuse to delete the built-in
  worlds (`earth`, `gem`, `the_watcher`) and the scratch `grid_room` — offer
  only *user-created* worlds in the delete list. Resolve the path and confirm it
  is a child of `Worlds/` before `rmtree`.
- **No per-frame allocation / no per-frame disk read** — keep new state in
  `_wb_*` attributes, add the relevant fields to `_signature()` so the cached
  surface invalidates, mtime-guard any rescans.
- Update `Scripts/validation/` if any new invariant is near the frozen line;
  all 11 sims must stay green.

### Suggested implementation order
Send button + transient preview objects → Canvas Cube draws objects → write
scratch grid_room so Preview shows them → relocate Save to right panel → Save =
new world dir + Worlds-tab rescan → strip left panel to description/advice +
remove usage line → unlimited gate → Settings Delete World (list + confirm +
clean removal). Commit per logical step with sims green; `/verify` in a real GUI
session for Canvas/Preview/parallax.

---

2026-06-2: Done. Everything validates and I confirmed your hard constraint: **Earth and The Watcher are untouched** — their `world.json` files are unchanged and the object code path is byte-identical (`sim_viewing` + `sim_vertical`, which pin Earth's feel, pass unchanged).

## What I changed

I reverted the divergent enclosure machinery and made the grid worlds _be_ Earth's camera. The code got **127 lines simpler**.

**Removed** (the stuff that made grids differ from spheres):

- The **forward dolly** depth model — this is what ballooned the gem ~3.6× and made its size diverge from Earth's.
- The **`engage·amp` split look gate** and all the `DOLLY_*` / `LOOK_ENGAGE/PRELOOK/AMP` constants.

**Now, every world uses the identical camera:**

- **Zoom** → Earth's telephoto `cz = BASE_Z·e^(+ZOOM_K·hz)`. A body at the z=−10 anchor subtends the same on-screen size in every world, at every distance.
- **Look gate timing** → Earth's frozen `om.proximity(hz)` over `[0.0, 0.8]` — so the rotational exploration transitions in over the _same exact distances_, just as smoothly.

**The one difference** (option 3, the hybrid gate you pointed to): for `enveloping` worlds the look pan is multiplied by a single constant `LOOK_ENCLOSURE_AMP = 0.35`. Because it rides the proximity gate, the pan is **≈0 at rest** (rim rock-solid) and grows to a small bounded max only as you lean in — so you're naturally "in the room" before you can look, and the bezel rim never shears.

**The anchor is automatic and exact:** the front rim is drawn at world z=0, which the off-axis projection pins to the screen edges at _any_ eye position or zoom. The sim verifies it stays bezel-locked to machine precision (4.6e-13px) at **every** head-z — no longer just at neutral, since nothing carries it off-screen anymore.

I rewrote `sim_envelop.py` to pin these new invariants, and updated the 11 wiki docs that described the removed model. **All 10 headless sims pass.**

## Two things for you

1. **One live-tune knob.** [`LOOK_ENCLOSURE_AMP = 0.35`](https://claude.ai/epitaxy/Launcher/app_engine.py:227) is the only thing to feel out: toward 1.0 = more Earth-like pan (more rim shift near full lean-in); lower = tighter anchor; `0.0` = pure anchored window. The geometry is settled — this is purely your perception call. You'll want to run it and nudge.
    
2. **Gem absolute size.** The size _response_ now matches Earth exactly. But the gem's girdle radius is 2.2 vs Earth's surface 2.6, so it renders at ~85% of Earth's footprint (a deliberate artistic value, "matched to Earth's approximate footprint"). If you want it _pixel-identical_ to Earth, that's a one-line radius bump in the `Gem` mesh — say the word and I'll match it.
    

I haven't committed anything — these are working-tree changes so you can see the live feel first. Want me to launch it to verify, or commit once you've tried it?

> **[RESOLVED 2026-06-02]** Resumed and completed. Tier 1 items 1 & 2 (predictive
> tracking + 1€ jitter filter) are implemented, validated (all 8 headless sims pass),
> and the durable record is promoted to [[(26-06-1) -decision-speed-upgrade]]
> (execution log). **Correction:** the interrupted session's closing hypothesis —
> that the post-stop overshoot needed a higher `_EURO_D_CUTOFF` — was *wrong*
> (verified: raising it makes overshoot worse). The real cause was a non-canonical
> 1€ derivative `(raw − filtered_prev)` that kept the velocity pinned high during the
> position filter's catch-up; the fix was the canonical raw-difference derivative in
> `Tracking/filters.py` plus `_EURO_BETA` 0.6 → 1.5. Overshoot 126.6e-3 → 1.2e-3.
> The investigation notes below are kept as the original trail.

claude was interuppted 26/06/1, read [[(26-06-1) -decision-speed-upgrade]] my prompt: first create a obsidian doc called /7/1/26-Decision to implement genuine speed upgrade, include all 3 tiear and sub points. Then execute predicitve head tracking and better jitter filter., update the doc with your progress and then push commit.

Before writing any tracker code I need to see exactly what invariants `sim_latency.py` enforces — the prior audit noted the tracker's filtering is protected by it, and I must not silently break those (and `camera_math.py` stays frozen — prediction/filtering live entirely in the tracker, which is allowed and which you've now explicitly approved).

claudes response: Readsim_latency.py

This is a meaty task: write the decision doc, then genuinely implement predictive tracking + a better jitter filter. Key constraints I'll respect:

- **`camera_math.py` stays frozen** — prediction/filtering live entirely in `Tracking/`.
- **Keep `_resp_boost` + the `_LERP_/_RESP_` constants intact** so `sim_latency.py`'s invariants still hold (it tests those building blocks directly).
- The new work is **additive**: a One Euro filter (better jitter rejection) + a velocity-gated predictor (hides latency) as a final conditioning stage, validated by a new headless sim.

Let me set up a task list and write the decision doc + the new filter module first.

Used 7 tools

Now the decision doc and the filter module (independent — writing both):

Created 2 files, used 3 tools

Created7-1-26-decision-speed-upgrade.md+92-0

Createdfilters.py+95-0

Updated todos

Updated todos

Updated todos

Now wire it into the tracker. First the import:

Editedface_tracker.py+2-0

Add the prediction/filter constants after the `_RESP_*` block:

Editedface_tracker.py+23-0

Now the `__init__` state. Let me add filter instances + velocity/timestamp state:

Editedface_tracker.py+12-0

Now replace `head()` with the predictive version:

Editedface_tracker.py+23-2

Now replace `_write` with `_publish` (the 1€-filter + velocity store):

Editedface_tracker.py+18-4

Now route all `_write` call sites to `_publish`. Let me find them all:

Ran 2 commands

All call sites rerouted and the linter formatting is intact. Now compile-check and update the task:

RanCompile and quick smoke test of tracker prediction

The smoke test used an unrealistic 2 ms publish interval (10× faster than the real 30 Hz), which left a stale velocity spike — that's a test artifact, not a bug. The real validation needs realistic 30 Hz timing. Let me write `sim_predict.py` to properly validate the latency/jitter trade and tune against it:

Created a file, ran a command, used 2 tools

Excellent results except one real issue: **post-stop overshoot of 0.127 units** (42% of the move) — the predictor keeps leading after the head stops because the velocity estimate decays too slowly (`d_cutoff` too low). Everything else is strong: the 1€ filter halves rest jitter vs the old lerp (0.00104 vs 0.00204), and prediction cuts motion lag 133 ms. Let me sweep `d_cutoff` to kill the overshoot while keeping the wins:

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