---
title: 3D Scan Import — Architecture
type: architecture
related: [TEXT_TO_3D_RESEARCH, WORLD_SCHEMA, grid-creator-tool-plan, IMPLEMENTATION_ROADMAP, constraints, design-decisions, world-system]
last_updated: 2026-06-05
sources:
  - Engine/renderer.py
  - Engine/camera_math.py
  - Worlds/world_runtime.py
  - Worlds/placeable.py
  - Launcher/app_engine.py
  - obsidian-docs/architecture/constraints.md
---

# 3D Scan Import — Architecture (Phase 7)

> **Purpose.** Design a premium workflow that turns a user's 3D scan into IRIS content:
> a **room scan** becomes a portal world (the monitor is a window into *their* room), and
> an **object scan** becomes a placeable inside the Grid Room or a Void world. Formats:
> **GLB, GLTF, USDZ, OBJ**. Architecture only — no code in this phase.
>
> **The Apple-native hook.** iPhone/iPad **RoomPlan** exports room scans as **USDZ**, and
> **Object Capture** (photogrammetry) exports objects as USDZ. "Scan your room on your
> phone → AirDrop it → your monitor becomes a window into that room" is a uniquely
> Mac-ecosystem premium feature that no webcam-parallax competitor can easily match.

---

## 1. Shared foundation: the mesh-import pipeline

Scan import and text-to-3D ([[TEXT_TO_3D_RESEARCH]]) need the **same** core: load an
external mesh and draw it in the frozen GL 2.1 renderer. Build it once.

```
file (GLB/GLTF/OBJ via trimesh/pygltflib; USDZ via Model I/O or usd-core → glTF)
  → normalize: vertices, normals, uv, indices   (+ embedded textures)
  → Engine.renderer.Mesh(v, n, u, i)             ← VBO class ALREADY EXISTS
  → texture upload                               ← Earth already textures a mesh
  → cache by content hash under the world's asset_dir
```

Fixed-function, textured — exactly like Earth and the primitives, so the frozen `shaders/`
are untouched and there is no live-compile risk ([[constraints]]). All heavy work
(parsing, plane detection, decimation) happens **at import time**, never per frame.

**Safety budget.** Scans are large. Import must **decimate to a vertex/triangle cap**,
clamp texture sizes, and reject files over a size limit — to protect the 30 fps wallpaper
budget on the 8 GB M2 target. A scan that can't be made cheap enough is rejected with a
clear message, never shipped to the draw loop.

---

## 2. Part A — Room scans → portal worlds

A room scan should make the monitor a window into that room: the **monitor bezel is the
glass (world z = 0)** and the room recedes behind it (−z), using the existing enclosure
model (`enveloping = true`: anchored rim, telephoto zoom + parallax, **no pan** — see
[[grids-dont-pan]]).

### Pipeline

1. **Load & clean** — import mesh; drop degenerate faces; unify scale to metres (USDZ/glTF
   carry units; OBJ often doesn't → ask or assume metres).
2. **Plane detection (RANSAC)** — find dominant planar surfaces and their normals:
   - **Floor** = large plane with normal ≈ gravity-up (+Y). Establishes "up".
   - **Walls** = large vertical planes. The **dominant wall** = the largest vertical plane
     (usually the one a webcam-at-monitor would face).
   - **Ceiling** = high plane, normal ≈ −Y (optional).
3. **Orient** — rotate the scan so floor-normal = +Y and the dominant wall is parallel to
   the screen plane (its normal aligned to +Z, facing the viewer).
4. **Anchor to the bezel** — translate/scale so the room's **opening (front extent) sits at
   z = 0** (the glass) and the dominant wall lands at the back (z ≈ −`grid_depth`-equivalent),
   fitting the room's width/height to the live aperture `hw/hh`
   (`om.window_half_extents`). The bezel plane = the room's window.
5. **Emit a world** — `primary_mesh: "scan"`, `enveloping: true`, `asset_dir` → the cached
   mesh + textures, plus the computed transform (rotation, scale, z-offset). Joins the
   Worlds-tab cycle like any saved world; hot-reloads via `world_runtime`.

### Why this fits the engine

The enclosure path already anchors a rim on the glass at z = 0 and recedes into −z with
correct off-axis parallax and **zero pan** — a scanned room is just a richer enclosure than
the wireframe Grid Room. No camera-math change: we only feed a new mesh + a precomputed
model transform into the existing `enveloping` branch in `app_engine.py`.

### Alignment data written to `world.json`

```json
{
  "environment": { "primary_mesh": "scan", "background": "void" },
  "rendering":   { "enveloping": true, "use_parallax": true, "show_window_frame": true },
  "assets": {
    "asset_dir": "scan_assets",
    "mesh": "living_room.glb",
    "scan_transform": {
      "rotation_euler_deg": [rx, ry, rz],   // floor→+Y, dominant wall→+Z
      "scale": s,                            // fit width/height to aperture
      "z_offset": dz,                        // front opening → z=0 (glass)
      "detected": { "floor_normal": [..], "dominant_wall_normal": [..] }
    }
  }
}
```

`scan_transform` is **immutable** content (like `grid_depth`) — produced by the importer,
not user-editable, so a hand-edit can't shear the room off the bezel.

---

## 3. Part B — Object scans → Grid Room / Void

An object scan (a single artifact, e.g. a sculpture from Object Capture) becomes either a
**placeable** in the Grid Room or the hero of a **Void world** (one object in empty space).

### Pipeline

1. **Load & clean** — as §1; decimate to the per-object triangle cap.
2. **Measure** — axis-aligned **bounding box**, **centre**, longest axis.
3. **Normalize** — translate centre to the mesh origin; uniformly scale so the longest axis
   ≈ 1 grid cell (so `scale` in [[WORLD_SCHEMA]] behaves like it does for primitives).
4. **Register as a mesh primitive** — extend the allowlist: `model: "mesh:<asset_id>"`
   alongside `builtin:*`. The asset lives under the world's `asset_dir`; `sanitize_objects`
   accepts `mesh:` only when the asset exists (else skip, never crash — same posture as
   the `builtin:` allowlist).
5. **Place** —
   - **Grid Room:** it's just another `placeable_objects[]` entry — `grid_position`, `scale`,
     `rotation` all work unchanged, and it maps through the **same** `grid_to_world` /
     `grid_to_canvas_cell` (so it appears correctly on *both* the oblique grid and the
     parallax — the unified pipeline from [[WORLD_BUILDER_AUDIT]] extends to meshes for free).
   - **Void mode:** a minimal world (`background: void`, no grid) with a single centred mesh
     — a clean "display pedestal" for one scanned object.

> Object scans inherit the entire World Builder coordinate + safety stack. The only new
> piece is the loader + the `mesh:` allowlist entry.

---

## 4. USDZ specifics (the Apple path)

- **RoomPlan** → parametric room USDZ (walls/floor/openings as planes) — *already* gives us
  the plane data §2 step 2 would otherwise compute via RANSAC. A USDZ from RoomPlan can
  shortcut straight to orientation/anchoring.
- **Object Capture** → photogrammetric object USDZ — feeds §3 directly.
- **Parsing on macOS:** USDZ is a zip of USDC + textures. Options: Apple **Model I/O** via
  pyobjc (native, no extra dep, Mac-only — fine, IRIS is Mac-only), or **`usd-core` (pxr)**,
  or convert USDZ→glTF at import. Prefer Model I/O to avoid a heavy dependency in the
  PyInstaller bundle (note: any new lazy-imported native dep needs a `--collect-all` in
  `Iris.spec`, same class as the pyobjc camera imports — [[constraints]]).

---

## 5. Frozen boundaries (do not cross)

- **No camera/physics/shader changes.** Scans render via the existing fixed-function
  textured path; the off-axis frustum and `enveloping` branch are reused as-is.
- **No grid panning** — scanned rooms are enclosures; the rim stays anchored, look-yaw = 0
  ([[grids-dont-pan]]).
- **No per-frame cost from import** — parse/detect/decimate at import; cache the VBO + the
  transform; the draw loop only sees a ready `Mesh`.
- **`scan_transform` is immutable content** — the importer owns alignment; not a creator
  surface (prevents shearing the room off the bezel).
- Add a guard sim for the importer's math (orientation/scale/anchor) and for
  `mesh:` allowlist + decimation caps — the frozen-invariance tripwire pattern of
  `sim_grid_api.py`.

---

## 6. Phasing & risk

| Step | Deliverable | Complexity | Risk |
|---|---|---|---|
| S1 | Mesh-import core (GLB/GLTF/OBJ → `Mesh`, textures, hash cache, decimation cap) | M | Med — PyInstaller bundling of the loader; perf caps. Shared with text-to-3D. |
| S2 | Object scans → Grid Room `mesh:` placeables (Void variant) | M | Low — rides the unified placeable stack. |
| S3 | USDZ via Model I/O + RoomPlan plane shortcut | M | Med — native parsing, bundle deps. |
| S4 | Room scans → portal worlds (RANSAC orient + bezel anchor) | L | High — robust alignment across messy scans; needs `/verify`. |
| S5 | Premium gating + asset storage/quota | S | Low — reuse `Licensing/entitlement.py`. |

**Order:** S1 → S2 (proves the pipeline cheaply on objects) → S3 (Apple hook) → S4 (the
showcase) → S5 (monetize). Object scans first de-risks the loader before tackling room
alignment.

---

## 7. Why this is a strong premium feature

- **Personal & sticky** — "a window into *my* room / *my* scanned object" beats any stock
  world; high perceived value, natural Pro tier.
- **Ecosystem moat** — leans on iPhone LiDAR / Object Capture that IRIS's category rivals
  can't easily reach.
- **Reuses everything** — the unified coordinate stack, the enclosure renderer, the
  freemium lever, and the very mesh-import core that text-to-3D needs. One investment,
  two flagship features.

## Related
[[TEXT_TO_3D_RESEARCH]] · [[WORLD_SCHEMA]] · [[grid-creator-tool-plan]] · [[IMPLEMENTATION_ROADMAP]] · [[constraints]] · [[design-decisions]] · [[world-system]]
