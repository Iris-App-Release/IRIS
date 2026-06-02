This page contains the final findings, hypotheses, and reasoning from Claude sessions that were interrupted before completion (typically due to token limits, usage limits, or manual interruption).

Entries below should be treated as active investigation notes rather than verified project documentation. They may contain partially validated discoveries, suspected root causes, file references, recommended next steps, or work-in-progress analysis.

When resuming work:

1. Read the most recent entry first.
2. Verify any claims against the codebase and wiki.
3. Promote confirmed discoveries into the appropriate permanent documentation.
4. Remove or archive resolved entries once their knowledge has been incorporated elsewhere.

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