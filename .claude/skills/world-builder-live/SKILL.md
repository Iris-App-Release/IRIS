---
name: world-builder-live
description: Drive the REAL IRIS World Builder pipeline from a natural-language prompt — the exact code path the in-app Send button runs (UI/world_builder_api.generate_world_objects → Claude → sanitize → grid_room). Use when the user wants to actually test the live World Builder: generate a world from a description, PREVIEW it in the running app, SAVE it as a new world, or DELETE a world. This calls Claude for real (needs an API key); for hand-authored objects with no API call, use /world-builder instead.
---

# World Builder — LIVE (real Claude pipeline)

This skill is the terminal driver for the **real** World Builder feature. Unlike
`/world-builder` (which has *you* hand-author the JSON), this runs the **same code
the in-app Send button runs** — `UI/world_builder_api.generate_world_objects`
(Claude call) → `Worlds/placeable.sanitize_objects` → the grid_room scratch /
a new world. So a prompt that works here works identically in the app.

Everything routes through one harness:
```
.venv/bin/python Scripts/world_builder_cli.py <subcommand> [...]
```
It never touches the frozen camera/physics/shader core; every object Claude
returns is clamped + allowlisted before it can reach disk.

## Step 0 — Readiness (always run first)

```
.venv/bin/python Scripts/world_builder_cli.py status
```
Reports the two real-time gates:
- **anthropic SDK installed** — `pip install anthropic` (already in requirements.txt).
- **API key present** — resolved from `ANTHROPIC_API_KEY` / `IRIS_OPENAI_KEY`, else
  `~/.iris/anthropic_key`, else `~/.iris/config.json` (`{"anthropic_api_key": "..."}`).

If `READY for real-time: False`, tell the user exactly which gate is missing and the
fix line `status` prints. Do NOT call `preview`/`save` (real) until ready — they'll
return "No objects generated". (You can still demo the data-plane offline with
`--objects`, see below.)

## Step 1 — PREVIEW (= the in-app Send button)

```
.venv/bin/python Scripts/world_builder_cli.py preview "a glowing red sphere back-left, a small pink cube near the glass on the right"
```
Generates objects (real Claude call), writes them into the **grid_room scratch**
(`Worlds/grid_room/world.json`), and switches the active world to `grid_room`. If the
app is running it **hot-reloads within a frame** — the user sees the preview live, no
restart. The command prints the generated object JSON; relay it in plain language
(what, where in "back-left / near the glass" terms + the `grid_position`), and note
that render confirmation is a GUI thing (offer `/run` or `/verify` if the app isn't up).

## Step 2 — SAVE (= the in-app Save button)

```
.venv/bin/python Scripts/world_builder_cli.py save "a neon city at dusk" [--name "Neon City"]
```
Generates → commits a **new** `Worlds/<slug>/world.json` (a grid_room copy with the
objects baked in and a prompt-derived name) that joins the Worlds-tab cycle, then
resets the scratch. View it with `use <slug>` or by cycling the Worlds tab.

## Step 3 — DELETE (= Settings → Delete World)

```
.venv/bin/python Scripts/world_builder_cli.py list           # see user vs built-in worlds
.venv/bin/python Scripts/world_builder_cli.py delete <slug>  # user worlds only
```
Refuses built-ins (`earth`, `gem`, `the_watcher`, `grid_room`) and any path-escaping
slug. If the deleted world was active, falls back to `earth`.

## Other subcommands

- `use <slug>` — set the active world (`~/.iris/preferences.json`); a running app
  switches live.
- `clear` — blank the grid_room scratch (empty preview).
- `selftest` — offline end-to-end of preview→save→delete on canned objects in a temp
  dir (no network, no `~/.iris` writes). Exit 0 = data-plane healthy.

## Offline / hand-authored objects (no API call)

`preview` and `save` accept `--objects '<json-array>'` to inject a ready-made object
list **instead of** calling Claude — same clamp/allowlist path, so it's the bridge
for `/world-builder`'s hand-authored JSON and for testing without a key. Example:
```
.venv/bin/python Scripts/world_builder_cli.py save "demo" --objects '[{"id":"a","model":"builtin:sphere","grid_position":[-3,2,8],"scale":1.0,"color":[1,0.1,0.1],"emissive":true,"rotation":[0,0,0]}]'
```

## Coordinate frame (for reading prompts/results back to the user)

Engine-native `grid_position` (what the CLI writes), with `D = grid_divisions` (default 8):
- `gx ∈ [-D/2 .. +D/2]` left→right (0 = centre)
- `gy ∈ [-D/2 .. +D/2]` down→up (0 = centre)
- `gz ∈ [0 .. D]` glass→back (**0 = on the glass/front**, D = back wall)

So "back-left on the floor" ≈ `[-4, -4, 8]`, "near the glass dead centre" ≈ `[0, 0, 0]`.
Source of truth for ranges/clamps: `Worlds/placeable.py` — never invent ranges.

## Frozen boundaries — never cross (CLAUDE.md + plan §11)

- Only `assets.placeable_objects[]` + the new world's `name` are written. Never
  `grid_divisions`, `grid_depth`, `primary_mesh`, `enveloping`, `camera`, or any
  `shaders/`. The sanitize layer enforces this even against a hostile prompt.
- Never reintroduce grid panning. Never touch `Engine/camera_math.py` or physics.
- Reliability is the product: a malformed object is skipped, never a crash.

## Related
- `/world-builder` — manual authoring (you write the JSON; no API call).
- `obsidian-docs/architecture/grid-creator-tool-plan.md` — the plan this implements.
- `Scripts/validation/sim_world_builder.py`, `sim_grid_api.py` — headless guards.
