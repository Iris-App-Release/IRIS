# ASSET_LOADING_REPORT.md

**Phase 9 — Asset Loading Investigation**
Method: on-disk asset inventory (`ls`/`du`), construction timing from the harness
(`load_texture_2d` cProfile), RSS deltas from `mem_probe.py`. Apple M2.

---

## 1. Asset inventory (on disk vs decoded)

Textures are stored JPEG/PNG-compressed; the runtime cost is the **decoded**
size. "Dim" = pixel dimensions; decoded = W·H·channels·1.33 (mipmaps).

| Asset | On disk | Dim | Decoded (VRAM) | Loaded by | When |
|---|---:|---|---:|---|---|
| `earth/earth_clouds.jpg` | 11.1 MB | 8192×4096 | **134 MB** | `Earth()` | **eager, every world** |
| `earth/earth_day.jpg` | 4.35 MB | 8192×4096 | **134 MB** | `Earth()` | **eager, every world** |
| `earth/earth_night.jpg` | 3.00 MB | 8192×4096 | **134 MB** | `Earth()` | **eager, every world** |
| `earth/earth_specular.jpg` | 1.74 MB | 8192×4096 | **134 MB** | `Earth()` | **eager, every world** |
| `earth/earth_normal.jpg` | 1.79 MB | 8192×4096 | — | **nobody** (see §4) | never |
| `stars/space_background.jpg` | 0.29 MB | 4096×2048 | ~33 MB | `Nebula()` | eager, every world |
| `stars/milky_way_8k.jpg` | 1.82 MB | (fallback) | — | `Nebula()` fallback only | only if space_bg missing |
| `the_watcher/eye_diffuse.png` | 0.77 MB | — | ~small | `Eye()` | lazy (Watcher world) |
| `the_watcher/eye_normal.png` | 0.74 MB | — | — | `Eye()` | lazy |
| `the_watcher/eye_specular.png` | 0.02 MB | — | — | `Eye()` | lazy |
| `the_watcher/source/eye_anterior…jpg` | 1.37 MB | — | — | **nobody** (source art) | never (ship-strip) |
| `icon/earth_icon.png` | 0.28 MB | — | small | app icon | n/a runtime |
| `models/face_landmarker.task` | 3.58 MB | — | (model) | tracker | lazy (on enable) |
| **assets/ total** | **29 MB** | | | | |

---

## 2. Largest / slowest assets (measured)

- **Largest (memory):** the four Earth 8K textures — **~536 MB decoded** combined,
  the dominant allocation in the whole app (MEMORY_ANALYSIS §2).
- **Slowest (load time):** `load_texture_2d` totals **1.94 s** for the 5 startup
  textures (cProfile), broken down:
  - `pygame.image.load` (JPEG decode): **0.59 s**
  - `pygame.image.tostring` (surface→bytes): **0.26 s**
  - `Surface.convert`: **0.15 s**
  - `glTexImage2D` + `glGenerateMipmap` upload: **0.35 s** (15 GL calls)
  - The Earth ctor alone is **~1.9–2.0 s** of the ~2.0–2.6 s scene build.

So **texture decode+upload is ~75 % of cold scene-build time** and the Earth's 8K
JPEGs are essentially all of it.

---

## 3. Assets loaded too early

| Asset | Issue | Evidence |
|---|---|---|
| Earth 4× 8K textures | **Eager at startup regardless of active world** (app_engine:383). A Grid Room / Gem / Watcher session loads + holds 536 MB it never samples. | MEMORY_ANALYSIS §3 |
| `space_background` (Nebula) | Eager even for `void`-background worlds (Grid Room, Watcher). | app_engine:380 |
| Stars VBOs | Eager even when background ≠ "stars". | app_engine:381 |

These three eager builds add **~2.0 s to cold start and ~870 MB RAM** for worlds
that don't use them.

---

## 4. Assets loaded but UNUSED (verified)

- **`earth/earth_normal.jpg` (8192×4096, 1.79 MB on disk)** — present in assets but
  **not loaded by any code path.** `Earth.__init__` binds day/night/clouds/specular
  only; there is no normal-map sampler. Dead art on disk (no runtime cost, but
  ships in the bundle). *Confirm before deleting — it may be staged for a future
  normal-mapped Earth.*
- **`the_watcher/source/eye_anterior_…jpg` (1.37 MB)** — source art for the baked
  eye textures; not loaded at runtime. Strip from the shipped bundle.
- **`milky_way_8k.jpg`** — only a *fallback* if `space_background.jpg` is missing;
  on a normal install it is never loaded but ships in the bundle.

---

## 5. Recommendations (→ ROADMAP)

1. **Lazy-load Earth/Nebula/Stars** gated on the active world's needs (same change
   that saves 870 MB RAM — ASSET + MEMORY agree). Cold start for non-Earth worlds
   drops ~2 s; Earth worlds unchanged. **(P1)**
2. **Async / background texture upload** for Earth worlds: build the GL context and
   show the void/stars immediately, stream the 8K Earth textures on the worker
   thread (or load a low-res mip first, refine). Removes the ~2 s black-screen
   stall at launch. **(P2)**
3. **Right-size textures**: 8192×4096 → 4096×2048 (¼ the decode time *and* memory)
   or ship GPU-compressed `.ktx`. The Earth subtends a small fraction of the
   screen; 8K is over-spec. **(P2, art sign-off)**
4. **Bundle hygiene**: drop unused `earth_normal.jpg`, the Watcher `source/` art,
   and the unused `milky_way_8k.jpg` fallback from the shipped DMG (disk/download
   size only, not runtime). **(P3)**
