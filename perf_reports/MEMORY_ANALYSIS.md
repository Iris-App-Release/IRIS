# MEMORY_ANALYSIS.md

**Phase 8 — Memory Analysis**
Method: live process **RSS** sampling (psutil) around each import + scene-build
step (`Scripts/perf/mem_probe.py`), Apple M2, GL context @2940×1912. Every number
is a measured RSS delta on this machine.

---

## 1. Headline: ~1.05 GB resident, and most of it is Earth textures

| Step | RSS delta | Cumulative RSS | Subsystem |
|---|---:|---:|---|
| baseline (interpreter) | — | 13.9 MB | Python |
| `import numpy` | +11.1 | 25.0 | dep |
| `import pygame` | +11.3 | 36.3 | dep |
| `import OpenGL` | +9.6 | 45.9 | dep |
| `import cv2` | +18.0 | 64.0 | dep (+ duplicate SDL2) |
| `import mediapipe` | **+36.7** | 100.7 | dep (+matplotlib+sounddevice) |
| GL context @2940×1912 | +56.5 | 157.2 | driver/framebuffers |
| `import Engine.renderer` | +0.2 | 157.4 | first-party |
| `Nebula()` | +146.5¹ | 303.9 | **assets** (bg tex + 1st-upload driver heap) |
| `Stars()` | −1.8 | 302.1 | assets (freed temp) |
| **`Earth()`** | **+727.2** | **1029.3** | **assets — 4× 8192×4096** |
| `IconOrbit()` | +39.1 | 1068.4 | assets + AppKit |
| `Gem()` | +4.8 | 1073.2 | assets |
| `GridRoom()` | +0.0 | 1073.2 | geometry only |
| **TOTAL RESIDENT (Earth world)** | | **1073.2 MB** | |

¹ Nebula's +146 MB is inflated by **one-time GL-driver heap allocation** on the
first real texture upload (the Metal-GL backend lazily allocates staging/heap on
first use). The background texture itself (4096×2048 RGB) is ~25 MB + mipmaps. The
driver warmup would land on whichever object uploaded first.

---

## 2. RAM by subsystem (measured)

| Subsystem | RSS | % of total | Notes |
|---|---:|---:|---|
| **Earth textures** | **~727 MB** | **68 %** | 4× 8192×4096 (day/night/clouds/specular) decoded+mipmapped in VRAM/driver |
| GL driver + framebuffers + 1st-upload heap | ~200 MB | 19 % | context (56) + Nebula's driver warmup (~120) |
| Python deps (numpy/pygame/OpenGL/cv2/mediapipe) | ~87 MB | 8 % | of which mediapipe +36.7 (incl. matplotlib+sounddevice) |
| IconOrbit (AppKit raster + 10 icon tex) | ~39 MB | 4 % | AppKit/Foundation framework + NSImage buffers |
| Nebula texture proper | ~25 MB | 2 % | 4096×2048 + mipmaps |
| Gem / GridRoom / Stars geometry | ~10 MB | 1 % | small VBOs |
| First-party Python code | ~0.2 MB | <1 % | 8.3 k lines |

### Texture memory math (decoded, the real VRAM cost)
- 8192×4096×3 bytes = **100.7 MB** per RGB texture, ×**1.33** mipmaps = **134 MB**.
- Earth loads **four** of them → **~536 MB** minimum decoded, before driver
  staging/alignment. Measured +727 MB includes pygame decode intermediates +
  driver copies. **This is the single dominant allocation in the app.**

---

## 3. The big finding: Earth (727 MB) is loaded eagerly for *every* world

`app_engine.py:380-383` constructs `Nebula()`, `Stars()`, and **`Earth()`
unconditionally at startup**, before the active world is consulted. The other
heavy meshes (Eye, Gem, GridRoom, Placeables) are lazy (built on first draw), but
**Earth is not**.

Consequence (measured): a user running the **Grid Room** wallpaper — a wireframe
box with a `void` (black) background that draws **neither Earth nor Nebula** —
still pays:
- **+727 MB** for Earth's four 8K textures (never sampled), and
- **+147 MB** for Nebula (never drawn; background is void).

≈ **870 MB of resident assets that the active world never renders.**

---

## 4. Persistent vs transient

- **Persistent (never freed during a session):** all textures (uploaded once,
  resident for the process lifetime), all VBOs, the GL context, mediapipe graph.
- **Transient (freed):** pygame decode surfaces (`Stars()` step even showed a
  −1.8 MB net as a temp was released). No per-frame allocation of note (the only
  per-frame `np.array` churn is the ~35 small icon matrices/frame — KB-scale, GC'd).
- **No leak observed:** RSS is flat across 600 render frames (textures static,
  geometry static). The cost is **construction-time and permanent**, not growing.

---

## 5. Secondary finding: duplicate SDL2 in memory

`cv2` and `pygame` each load their own `libSDL2-2.0.0.dylib` (objc duplicate-class
warnings at import). cv2 only needs SDL for `cv2.imshow`/HighGUI, which IRIS never
calls. This is a redundant native library resident in the process (a few MB +
symbol-table collision). Low priority; flagged for the trim pass.

---

## 6. Recommendations (→ PERFORMANCE_ROADMAP)

1. **Make `Earth()` lazy** like Eye/Gem/Room — build it on first draw of an
   Earth-bearing world. **Saves up to 727 MB** for users on Grid Room / Gem / The
   Watcher worlds. Highest-value memory change in the app. (P1)
2. **Make `Nebula()`/`Stars()` lazy** too, gated on `world.background == "stars"`.
   Saves ~147 MB for `void`-background worlds. (P1)
3. **Downscale or compress Earth textures.** 8192×4096 is extreme for a sphere
   ~2.6 units across on a 5.6 MPix screen; 4096×2048 would quarter the memory
   (~180 MB) with little perceptible loss, or use a GPU-compressed format (e.g.
   BC/ETC via a `.ktx`) to cut VRAM ~4–6×. (P2 — needs art validation)
4. **Drop cv2's SDL2** / consider AVFoundation capture to remove the duplicate
   native lib. (P3)
