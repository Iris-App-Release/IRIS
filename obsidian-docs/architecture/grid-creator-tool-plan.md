---
title: World Builder — Implementation Plan
type: implementation-plan
status: proposed (not started)
related: [grid-api-customization, productification, world-system, grid-room, constraints, design-decisions, ui-reorg-architecture, menu-bar-ui, headless-simulation]
last_updated: 2026-06-02
sources:
  - Worlds/world_runtime.py
  - Worlds/world_loader.py
  - Worlds/grid_room/world.json
  - Engine/renderer.py
  - Engine/camera_math.py
  - Launcher/app_engine.py
  - Scripts/validation/sim_envelop.py
  - Licensing/entitlement.py (new)
  - UI/world_builder_tab.py (new)
---

# World Builder — Implementation Plan

> **Purpose.** A concrete, code-grounded plan to ship **World Builder** — a
> safe, Claude-assisted way for users to customize and place objects inside the [[grid-room]]
> world without touching the frozen physics/camera/shader core. Accessible as a top-bar tab,
> with a freemium model: one free world customization per user, then a premium subscription
> to unlock additional customizations. This is the *environment* half of the "creator tool"
> concept; the *object-of-interest* (sphere) half is explicitly **out of scope** (see §1.2).
> Written so it can be picked up cold in a fresh session — every file, function, and invariant
> below was verified against the live source on 2026-06-02.

---

## 0. TL;DR for a fresh session

You are implementing **World Builder**, a top-bar tab for user-customizing the Grid Room.
The grid is already a spatial stage drawn in world space; you are adding a `placeable_objects[]`
array to `world.json`, a coordinate transform, a fixed-function draw loop, bounds
clamping, hot-reload, and a headless sim. **You touch NO frozen module.** 

**Freemium model:** users get one free world customization; after that, a premium
subscription upsell appears. Entitlements and free-use counter are tracked in a new
`Licensing/` module, separate from the frozen code paths.

When the feature renders reliably, passes all sims, and the entitlement layer
is in place, the monetization track (§10) begins.

**Start by reading:** this doc → [[grid-api-customization]] → [[constraints]] →
the four `Hard rules` in `CLAUDE.md`. Then implement Phases 1→6 in order.

---

## 1. Scope

### 1.1 In scope (v1)

- **World Builder top-bar tab** — toggleable UI drawer (or dedicated panel) that appears
  alongside other tabs; opens an editable preview + Claude prompt input ("describe your world").
- A new `assets.placeable_objects[]` block in `Worlds/grid_room/world.json`.
- **Built-in primitives only:** `builtin:cube`, `builtin:sphere`, `builtin:cylinder`.
- Per-object: `grid_position`, `scale`, `color`, `emissive`, `rotation`.
- A `grid_to_world` transform that respects the **live aperture extents** (not the
  hardcoded `[-4,4]` bounds the older [[grid-api-customization]] doc assumed — see §3).
- Fixed-function colored/emissive drawing (frozen shaders untouched — see §4).
- Bounds validation/clamping so an object can never escape the box.
- Live hot-reload: editing `world.json` updates the scene with no restart.
- A headless validation sim `sim_grid_api.py`.
- **Free-tier entitlement check** — one free customization per user; subsequent ones
  trigger a premium upsell modal (see §10).
- A documented **Claude-assisted authoring flow** ("describe it → JSON").

### 1.2 Explicitly OUT of scope

- **Object-of-interest / sphere creation.** Earth/Watcher/Gem are bespoke renderer
  classes + GLSL shaders, not data. "Describe an object" there means *generating a
  shader* next to the frozen camera math — high-risk, unreliable, wrong for a hook.
  Deferred to a later, *curated* track (pre-built objects whose material/void are
  describable, not their geometry).
- **Custom `.obj`/`.gltf` mesh loading.** v1 is primitives only (always renders;
  reliability > expressiveness for a hook). Mesh import is a later phase.
- **Panning the grid.** Settled 2026-06-02: enclosure/grid worlds DO NOT PAN
  (`if world.enveloping: yaw_target = pitch_tgt = 0.0`). The anchored rim is the
  whole point; a pan shears it. See [[grids-dont-pan]] / [[constraints]]. Nothing in
  this plan reintroduces rotation.

### 1.3 Why grid-only is the right hook

Built-in primitives at integer grid cells **always render** — no shader compile, no
geometry import, no failure mode that kills the illusion mid-demo. The grid itself is
self-documenting coordinates ("put a glowing cube in cell C7, depth 8"). That
reliability is exactly what a paid hook needs.

---

## 2. Architecture grounding (verified against live source)

| Concern | Where it lives | Notes |
|---|---|---|
| UI tab system | `Launcher/app_engine.py` or new `UI/tabs.py` | World Builder is one top-bar tab alongside existing tabs. Toggles a panel/drawer for editing. [[ui-reorg-architecture]] defines the tab system. |
| World JSON load | `Worlds/world_loader.py` → `WorldLoader.load_world()` | Pure `json.load`; returns a dict. |
| Active-world + typed accessors + live poll | `Worlds/world_runtime.py` → `WorldRuntime` | Exposes `.env`, `.rendering`, `.grid_depth`, `.grid_divisions`, `.grid_color`, `.enveloping`. Polls `~/.iris/preferences.json` mtime each frame for live world switching. **This is where the `placeable_objects` accessor goes.** |
| Entitlement + free-use counter | `Licensing/entitlement.py` (new) | Tracks free customization usage per user; gates upsell modal. **Additive, far from frozen code.** Reads from `~/.iris/licensing.json` (local, per-device). |
| Grid mesh | `Engine/renderer.py` → `class GridRoom` (~line 1136) | Drawn in **world space**; front rim lands on the glass at z=0. Fixed-function `GL_LINES`, no shader. Rebuilds only on key change. |
| Primitive mesh wrapper | `Engine/renderer.py` → `class Mesh` (~line 129) | VBO-backed; `make_sphere(radius, slices, stacks)` exists at line 44. **No `make_cube`/`make_cylinder` yet — you add them.** |
| Draw dispatch | `Launcher/app_engine.py` ~line 798, `if world.primary_mesh == "room":` | The room is drawn here in world space, **before** the Earth-anchor translate. **Placeable objects draw immediately after `room.draw(...)`.** |
| Live aperture extents | `app_engine.py` line 796: `hw, hh = om.window_half_extents(aspect, win_half_h)` | The grid's half-width/height. **Dynamic** — depends on aspect + calibration. The grid spans x∈[−hw,hw], y∈[−hh,hh], z∈[0,−grid_depth]. |
| Frozen camera math | `Engine/camera_math.py` | `window_half_extents`, `off_axis_frustum`, `WINDOW_HALF_H`. **DO NOT TOUCH.** |
| Validation sims | `Scripts/validation/sim_*.py` | 10 headless sims. `sim_envelop.py` pins enclosure zoom/zero-pan. **You add `sim_grid_api.py`.** |

**Key correction over the old doc:** [[grid-api-customization]] states bounds `X:-4..+4,
Y:-3..+3, Z:0..18`. In the live engine the X/Y bounds are **not constants** — they are
`om.window_half_extents(aspect, win_half_h)`, which vary with monitor aspect and the
opt-in metric calibration. Only `grid_depth` (z) and `grid_divisions` come from JSON.
The transform in §3 must therefore be computed from the **live `hw`/`hh`** passed into
the room branch, never from literals.

---

## 3. Coordinate system & `grid_to_world`

Users address **integer grid cells**; the engine maps them to live world coordinates.

```
Inputs (per frame, already available in the room branch):
  hw, hh          # live aperture half-extents  (om.window_half_extents)
  depth = world.grid_depth        # e.g. 18.0
  D     = world.grid_divisions    # e.g. 8

Cell coordinate convention (integers):
  gx ∈ [-D/2 .. +D/2]   left → right     (0 = centre)
  gy ∈ [-D/2 .. +D/2]   down → up        (0 = centre)
  gz ∈ [0 .. D]         glass → back     (0 = on the glass, D = back wall)

grid_to_world(gx, gy, gz):
  wx = (gx / (D/2)) * hw
  wy = (gy / (D/2)) * hh
  wz = -(gz / D) * depth
  return (wx, wy, wz)
```

Notes:
- Using `D/2` for X/Y keeps `gx = ±D/2` exactly on the side walls (`±hw`), `gy = ±D/2`
  on floor/ceiling, matching the rendered grid lines.
- Y uses the same `D/2` scale against `hh` (the old doc's separate "8 cells over 6
  units" is superseded — divisions are square in cell-count, the world is just wider
  than tall because `hw ≠ hh`).
- `gz` runs 0→D into the screen so "depth 8" reads intuitively as "8 cells back".
- **Clamp before transform** (see §6): `gx,gy ∈ [-D/2, D/2]`, `gz ∈ [0, D]`.

---

## 4. Drawing the objects (frozen shaders untouched)

**Decision: fixed-function GL for v1.** Matches how `GridRoom` and the gem floor/shadow
already draw (no shader), so the frozen `shaders/` are provably untouched and there is
**no live GL-compile risk** (compiling a new shader can only be verified in a real GUI
session — see [[constraints]]). A new shader is *allowed* (additive ≠ modifying frozen
ones) but deferred — fixed-function always renders.

Per object, in the `"room"` branch right after `room.draw(...)`, in **world space**:

```python
# pseudocode — Engine/renderer.py: PlaceableObjects.draw(objects, hw, hh, depth, D)
for obj in objects:
    wx, wy, wz = grid_to_world(*obj.grid_position, hw, hh, depth, D)
    glPushMatrix()
    glTranslatef(wx, wy, wz)
    glRotatef(obj.rotation[1], 0,1,0)   # yaw; pitch/roll optional
    glScalef(obj.scale, obj.scale, obj.scale)
    # Emissive flat color (reads as "glowing" in the void). Depth WRITES on (solid),
    # unlike the blended grid lines, so objects occlude the grid correctly.
    glDisable(GL_LIGHTING)              # v1: flat emissive; lighting is a later option
    glColor4f(r, g, b, 1.0)
    mesh.draw()                         # builtin cube / sphere / cylinder Mesh
    glPopMatrix()
restore_gl_state()                      # glColor white, depth mask on, etc.
```

- Reuse `Mesh` for the VBO path. `make_sphere` exists; add `make_cube` and
  `make_cylinder` (small, static, built once and cached — same posture as the spheres).
- Keep meshes **cached as module/class singletons** keyed by primitive name — never
  rebuild per frame (the codebase is strict about per-frame allocation; see the VBO and
  no-`glGet*` notes in [[constraints]]).
- `emissive` in v1 simply selects flat color (lighting off). A later phase can add one
  directional light using the world's `sun_direction` for a lit look.

---

## 5. Schema extension

Add to `Worlds/grid_room/world.json` (and document as the public format):

```json
{
  "name": "Grid Room",
  "environment": { "primary_mesh": "room", "...": "..." },
  "rendering":   { "enveloping": true, "grid_divisions": 8, "grid_depth": 18.0, "...": "..." },
  "assets": {
    "placeable_objects": [
      {
        "id": "neon_cube_1",
        "model": "builtin:cube",
        "grid_position": [3, 2, 8],
        "scale": 0.8,
        "color": [1.0, 0.2, 0.8],
        "emissive": true,
        "rotation": [0, 45, 0]
      }
    ]
  }
}
```

**Immutable (must reject edits to):** `grid_divisions`, `grid_depth`, `primary_mesh`,
anything under `camera`/frozen. **Mutable (creator surface):** the
`placeable_objects[]` list and each object's `grid_position`, `scale`, `color`,
`emissive`, `rotation`, `model` (restricted to the `builtin:*` allowlist in v1).

`WorldRuntime` accessor to add (mirrors existing typed properties):

```python
@property
def placeable_objects(self) -> list[dict]:
    return self._def.get("assets", {}).get("placeable_objects", []) or []
```

Defaults stay empty, so every existing world is byte-identical.

---

## 6. Validation & clamping

A creator (or Claude) must never be able to break the box or the engine:

- **Allowlist `model`** to `{builtin:cube, builtin:sphere, builtin:cylinder}`; unknown →
  skip + log (never crash; mirror the lazy-load fallbacks already in `app_engine.py`).
- **Clamp** `gx,gy ∈ [-D/2, D/2]`, `gz ∈ [0, D]` before transform.
- **Clamp** `scale ∈ (0, scale_max]` (pick `scale_max` so a max-scale object can't
  exceed one... few cells — tune in `/verify`), `color` components to `[0,1]`.
- **Cap object count** (e.g. ≤ 64) to protect the 30 fps wallpaper budget on the 8 GB M2
  target ([[constraints]]).
- Malformed object → skipped individually, scene still renders. Reliability is the
  product (§1.3).

---

## 7. Implementation phases (do in order)

| Phase | Deliverable | Files | Done when |
|---|---|---|---|
| **1. Schema + accessor** | Parse `assets.placeable_objects[]`; no draw yet | `Worlds/world_runtime.py`, `Worlds/grid_room/world.json` | `world.placeable_objects` returns the list; all worlds still load. |
| **2. Primitive meshes** | `make_cube`, `make_cylinder`; cached `Mesh` singletons | `Engine/renderer.py` | Helpers return valid VBO meshes; sphere reused. |
| **3. Draw loop** | `grid_to_world` + fixed-function draw in the room branch | `Engine/renderer.py` (new `PlaceableObjects` or function), `Launcher/app_engine.py` (~line 808, after `room.draw`) | Objects appear at correct cells in the live demo; grid still anchored; sphere worlds untouched. |
| **4. Validation/clamp** | Allowlist + clamps + count cap | `Engine/renderer.py` / small helper | Out-of-bounds, junk, and overflow inputs render safely. |
| **5. Hot-reload** | Re-read `world.json` on its mtime change | `Worlds/world_runtime.py` `poll()` | Editing the JSON updates the scene live, no restart. |
| **6. Headless sim** | `sim_grid_api.py` | `Scripts/validation/sim_grid_api.py` | Transform, clamping, frozen-invariance all asserted; **all 11 sims pass**. |
| **7. World Builder tab + entitlement** | Top-bar UI tab; free-tier counter; upsell modal | `UI/world_builder_tab.py` (new), `Licensing/entitlement.py` (new), `Launcher/app_engine.py` (tab integration) | Tab toggles drawer; upsell appears on second save; entitlements checked at save time. |
| **8. Authoring flow** | Documented Claude prompt + cell reference | this doc / a `creator-guide.md` | Claude reliably turns "glowing red sphere back-left" into a clamped, valid object via tab UI. |

### Phase 5 detail — hot-reload
`WorldRuntime.poll()` currently only re-selects when the **prefs** mtime changes. Add a
second mtime watch on the **active `world.json`** so edits reload `self._def` in place
(re-running validation). Keep it mtime-cached (no per-frame disk read beyond the `stat`
already done).

### Phase 6 detail — `sim_grid_api.py` (follow the existing sim pattern)
Assert, headless (no GPU):
1. `grid_to_world` maps `[0,0,0]`→`(0,0,0)`; `[D/2,D/2,0]`→`(hw,hh,0)`;
   `[0,0,D]`→`(0,0,-depth)`.
2. Clamping pins out-of-range cells inside bounds.
3. Object count cap respected.
4. **Frozen-invariance:** loading a grid world *with* objects produces the **same camera
   matrix / zoom / zero-pan** as without — placeable objects must not perturb
   `camera_math`. (Reuse the structure of `sim_envelop.py`, which already pins enclosure
   zoom + zero pan.)
5. Sphere worlds unaffected (no `assets` block → empty list → identical path).

---

## 8. The World Builder UI & Claude-assisted authoring flow

**Top-bar tab experience:**
1. User opens **World Builder** tab (top bar, alongside other tabs).
2. A drawer/panel opens showing:
   - Live preview of the current grid world with placeable objects
   - Text input: *"Describe your world…"* prompt box
   - A "Save" button (subject to entitlement check below)

**Authoring flow (the actual hook):**
1. User types a prompt: *"a glowing red sphere in the back-left corner, and a small
   pink cube floating near the glass on the right."*
2. Claude (or a backend service) reads the current `world.json` + the cell convention
   (§3), infers grid cells, writes clamped, allowlisted objects into
   `assets.placeable_objects[]`.
3. User clicks "Save"; the daemon **hot-reloads** (Phase 5) → objects appear instantly.

**Entitlement gate (freemium):**
- On first save: allowed (free customization tracked in `~/.iris/licensing.json`).
- On second save: upsell modal appears (*"Enjoy unlimited customizations with World
  Builder Pro"*), offering a premium subscription. User can dismiss to keep using
  free tier, but each subsequent save triggers the modal again.
- Premium subscribers skip the modal (entitlement flag checked at save time).

**Labeled squares (Phase 7+ nicety):** the back wall is a `D×D` grid; overlaying cell
labels (A1…H8) in the UI — or showing them in the live preview panel — makes the
coordinate prompt foolproof. v1 can ship with the convention documented and visual
labels deferred (GL text is extra work; not on the reliability path).

**Safety:** Claude may only edit the mutable surface (§5). It cannot touch
`grid_divisions`, `grid_depth`, `primary_mesh`, camera, or shaders — the loader/clamp
layer enforces this even if a prompt asks for it.

---

## 9. Testing & the reliability gate

Two layers, matching project convention:

- **Headless (every change):** all `Scripts/validation/sim_*.py` must pass, including the
  new `sim_grid_api.py`. This is the frozen-physics tripwire — run before every commit.
- **Manual (`/verify` skill, real GUI session):** the camera/GL behaviours are only real
  in the built app (see [[constraints]]). Confirm: objects land in the right cells across
  head-lean (parallax), the grid stays bezel-anchored, no pan, 30 fps wallpaper holds with
  a full object set, hot-reload visibly works.

**"Reliable" = the gate to monetization (§10).** All of:
1. All 11 sims green.
2. `/verify` confirms correct placement + parallax + anchored rim + no perf regression.
3. Claude-assisted flow produces valid, clamped objects from 10+ varied natural-language
   prompts with zero crashes / zero out-of-box escapes.
4. Hot-reload is robust to malformed/partial JSON (skips, never crashes).

Only after this gate do we wire payments.

---

## 10. Monetization: receiving funds + payment strategy

> Detail belongs here because World Builder is the **revenue hook**. This refines
> [[productification]] §5 (Monetization) for the World Builder path specifically.

### 10.1 Freemium model — 1 free customization, then premium

Users get **one free world customization per device** (`~/.iris/licensing.json` tracks
usage locally); subsequent customizations trigger a premium upsell:

| Tier | Entitlement | Price |
|---|---|---|
| **Free** | One world customization per device; save/hot-reload works | $0 |
| **World Builder Pro** | Unlimited customizations; future: save/export/share, all current + future worlds | **$4.99–$7.99/month or $24.99/year** |

**Why this works:**
- Users hit the "magic moment" (place a glowing object, watch it parallax) with zero
  friction on the free tier — the hook lands before any paywall.
- After building something they like, the $5–8 ask is natural (competitive with coffee).
- Recurrent revenue (subscription) scales with user growth.
- Upsell modal is non-blocking: users can dismiss and keep the free tier; engagement
  data tells you if the ask resonates.

### 10.2 Free-tier boundaries

- **Customization count:** 1 per device (stored in `~/.iris/licensing.json`).
- **Scope:** free tier can edit Grid Room only (other worlds deferred to Pro).
- **Primitives:** all three (`cube`, `sphere`, `cylinder`) available free.
- **UI/UX:** upsell modal appears on attempted second save; can be dismissed.

### 10.3 Entitlement check architecture

**Location:** new `Licensing/entitlement.py` module (additive, far from frozen code).

```python
# Pseudocode
class EntitlementChecker:
    def can_save_customization(self) -> bool:
        """Check if user can save a world customization."""
        if self.is_premium():
            return True
        free_count = self.get_free_usage_count()
        return free_count < 1  # 1 free save per device
    
    def should_show_upsell(self) -> bool:
        """Return True if the upsell modal should appear on next save."""
        if self.is_premium():
            return False
        return self.get_free_usage_count() >= 1
    
    def record_customization_saved(self) -> None:
        """Increment the free-usage counter."""
        self._increment_free_usage()
```

**Read path:** `~/.iris/licensing.json` (local, per-device):
```json
{
  "device_id": "...",
  "premium_subscription": false,
  "subscription_expires_at": null,
  "free_customizations_used": 0,
  "last_checked_subscription_at": "2026-06-02T00:00:00Z"
}
```

**Never in the frozen path:** this check lives in the tab/drawer layer
(`Launcher/app_engine.py` UI section or new `UI/world_builder_tab.py`), not in
`Engine/renderer.py`, `camera_math.py`, or `Worlds/world_runtime.py`.

### 10.4 Hard prerequisite (do first, independent of code)

Per [[productification]] Milestone 1, **nobody outside this Mac can run IRIS until it is
Developer-ID signed + notarized.** No payment strategy matters before that. Sequence:
1. **Apple Developer Program** ($99/yr) — ~1 day to activate.
2. `Build/build_dmg.sh`: Developer-ID `codesign` → `xcrun notarytool` → `xcrun stapler`
   (re-sign **after** any `Info.plist` edit — see `CLAUDE.md` hard rules).
3. Publish a versioned, notarized DMG (GitHub Releases) — the distribution channel.

### 10.5 Payment channels

- **Primary: Stripe/Paddle** — subscription billing, handles taxes, recurs monthly/yearly.
  Avoids Apple's 30% tax (direct sales outside App Store).
- **Secondary (future): Mac App Store in-app purchase** — cleanest UX in OS, Apple takes 30%,
  longer review cycle. Add after launch for discoverability.

### 10.6 Also required before charging

- **Privacy policy** — camera use, all-local processing, nothing stored/transmitted.
  Mandatory for any camera app and for the App Store ([[productification]]).
- **Landing page + demo GIF** — head-tracked parallax sells itself in a screen recording.
  Cheapest acquisition asset.
- **Subscription terms** — spell out what "World Builder Pro" unlocks; auto-renew clauses
  (App Store requirement); cancellation flow (Stripe/Paddle handle this, but surface it
  clearly in the app or a help page).

---

## 11. Frozen boundaries — do not cross

Re-stated from `CLAUDE.md` + [[constraints]] so a fresh session can't miss them:

- **Do not modify** `Engine/camera_math.py`, any `shaders/`, or physics tuning. This
  feature is **fixed-function + JSON only**.
- **Do not change** `grid_divisions`, `grid_depth`, `primary_mesh`, or the `enveloping`
  zero-pan behaviour. The coordinate space and the anchored-no-pan rim are locked.
- **Do not reintroduce grid panning** in any form (see [[grids-dont-pan]]).
- **Do not** add per-frame allocation, per-frame `glGet*`, or per-frame disk reads
  (mtime-cache the hot-reload).
- **Do not** edit `Info.plist`/`BUNDLE_ID` or run `pyinstaller` bare (use
  `bash Build/build_dmg.sh`).
- Add a guard sim for anything that comes near the frozen invariants.

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| Scope creep into object/sphere "creation" (shader generation) | Hard line in §1.2 — grid + builtin primitives only for v1. |
| Live aperture bounds misread as constants | §3 transform uses live `hw/hh`; sim asserts it. |
| Per-frame cost from many objects | Object cap (§6) + cached VBO meshes + 30 fps wallpaper verify. |
| Hot-reload crashes on half-written JSON | Phase 5 wraps reload in try/except; keep last-good `_def`. |
| Touching frozen code by accident | §11 + `sim_grid_api.py` frozen-invariance assertion + all 11 sims gate every commit. |
| Entitlement check fails or bypasses | `Licensing/entitlement.py` is additive (never touches frozen paths); upsell modal is non-blocking (always allows save, just warns). |
| Tab UI interferes with core wallpaper | Phase 7 UX testing in real session; ensure tab toggle doesn't cause rendering glitches or frame drops. |
| Free-tier counter expires or resets unexpectedly | Store in `~/.iris/licensing.json` with mtime guard; simple JSON format, no encryption (trust local device). |
| Charging before reliable | §9 gate is a hard precondition for §10. |

---

## 13. Launch-in-a-new-session checklist

1. Read: this doc → [[grid-api-customization]] → [[constraints]] → `CLAUDE.md` hard rules.
2. Optionally use `/new-world` patterns for JSON conventions; use `/bug-fix` discipline if
   anything regresses.
3. Implement Phases 1→6 (§7), committing per phase with all sims green.
4. Implement Phase 7 (World Builder tab + entitlement layer) — the tab is the user-facing
   surface, so test it in real GUI sessions as you build.
5. `/verify` in a real GUI session for the camera/GL/parallax behaviours.
6. Pass the §9 reliability gate.
7. Test the upsell flow: first save → no modal; second save → upsell appears; premium user
   → no modal on any save.
8. Then — and only then — start the §10 monetization track (Apple Dev → notarize →
   Stripe/Paddle subscription → privacy policy → landing page).

---

## Related
[[grid-api-customization]] · [[productification]] · [[world-system]] · [[grid-room]] ·
[[constraints]] · [[design-decisions]] · [[ui-reorg-architecture]] · [[menu-bar-ui]] ·
[[headless-simulation]] · [[grids-dont-pan]]
