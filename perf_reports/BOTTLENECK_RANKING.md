# BOTTLENECK_RANKING.md

**Phase 11 — Master Bottleneck Ranking**
Every entry is backed by a measured number from Phases 1–10 (file cross-refs in
brackets). Ranked by **Impact** (user-visible / resource), with **Complexity** and
**Risk** for sequencing. Apple M2 baseline.

---

## The one-paragraph truth

IRIS is **not bottlenecked at runtime on this hardware.** The render loop sustains
**230–460 fps against a 30 fps cap** [FRAME_TIMING], physics is **0.07 ms/frame**
[PHYSICS], and tracking runs **off-thread at ~0 % of the frame** [TRACKING]. The
real costs are all **at startup and in memory**: **~1.05 GB resident** (727 MB of
it Earth textures loaded for *every* world) [MEMORY], a **~3.1 s cold start**
(1.09 s imports + 2.0 s texture decode) [IMPORT/ASSET], and **continuous background
I/O while idle** [BACKGROUND]. The perceived "lag when opening other apps" is the
**WindowServer recompositing a full-screen Retina wallpaper that keeps drawing even
when covered** — a compositor/visibility problem, not an app compute problem.

---

## Master ranking

| # | Bottleneck | Category | Impact | Complexity | Risk | Evidence |
|--:|---|---|---|---|---|---|
| **1** | **Earth 4× 8K textures loaded eagerly for every world (727 MB)** | Memory | **CRITICAL** — 68 % of RSS; 870 MB wasted on non-Earth worlds | Low | Low | MEMORY §3, ASSET §3 |
| **2** | **Cold-start texture decode/upload (~2.0 s) + eager Nebula/Stars** | Startup | **HIGH** — 2 s black screen at launch | Low–Med | Low | ASSET §2, CPU §2 |
| **3** | **mediapipe over-imports matplotlib+sounddevice (~550 ms)** | Startup | **HIGH** — half the 1.09 s import time, all dead weight | Low | Low | IMPORT §3, RUNTIME_MAP §1 |
| **4** | **Wallpaper renders at 30 fps while occluded / camera-off** | Rendering / Power | **HIGH** — the "stutter when other apps open" + idle GPU/battery | Medium | Medium | BACKGROUND §3 |
| **5** | **30 Hz state-file disk write, continuous (often no consumer)** | Background I/O | **MEDIUM** — 30 SSD writes/s forever; wasted if icons app absent | Low | Low | BACKGROUND §2 |
| **6** | **PyOpenGL auto error-checking (224 glGetError/frame)** | CPU | **MEDIUM** — 10–28 % of per-stage draw CPU; main-thread contention | Low | Low | CPU §3, RENDER_AUDIT #1 |
| **7** | **IconOrbit `glGetFloatv(MODELVIEW)` readback/frame (stall)** | Rendering | **MEDIUM** — 1 GPU→CPU sync/frame; host already has the matrix | Low | Low | RENDER_AUDIT #2 |
| **8** | **8K textures over-spec for on-screen size** | Memory / GPU | **MEDIUM** — 4× memory + decode vs 4K; sampling cost | Low | Med (art) | ASSET §5, MEMORY §6 |
| **9** | **Nebula full-screen fillrate (14.5 % of Earth frame)** | GPU | **LOW–MED** — matters on weak GPUs, not M2 | Medium | Med (art) | FRAME_TIMING §2, RENDER_AUDIT #4 |
| **10** | **Duplicate libSDL2 (cv2 + pygame) resident** | Memory | **LOW** — few MB + symbol collision | Medium | Med | MEMORY §5, IMPORT §3.4 |
| **11** | **1 Hz Orbital-Apps folder rescan** | Background | **LOW** — 1 fs scan/s | Low | Low | BACKGROUND §2 |
| **12** | **Per-icon numpy allocs (~35/frame), static uniform re-uploads** | CPU | **LOW** — sub-0.05 ms/frame | Low | Low | RENDER_AUDIT #3,#6 |
| — | Physics / collision / constraints | Physics | **NONE** — no engine exists; 0.07 ms/frame | — | — | PHYSICS |
| — | Per-frame render compute | CPU/GPU | **NONE on M2** — 7–15× headroom | — | — | FRAME_TIMING §1 |

---

## By category — where the cost actually lives

| Category | State | Top item |
|---|---|---|
| **Memory** | ⚠️ **Worst area** — 1.05 GB, mostly avoidable | #1 eager Earth textures (727 MB) |
| **Startup** | ⚠️ **~3.1 s cold start** | #2 texture decode + #3 mediapipe imports |
| **Rendering** | ✅ Healthy on M2; visibility is the gap | #4 draws-while-occluded |
| **CPU (per frame)** | ✅ Huge headroom | #6 PyOpenGL overhead (free to fix) |
| **GPU (per frame)** | ✅ ~3 ms/frame at 5.6 MPix | #9 Nebula fillrate |
| **Tracking** | ✅ Off-thread, tuned | none — already optimal |
| **Physics** | ✅ Non-existent / closed-form | none |
| **Background/Power** | ⚠️ Always-on I/O + render | #4, #5 |

---

## Sequencing guidance

- **Do first (high impact, low risk, low effort):** #1, #3, #5, #6 — all
  "Low/Low" and together reclaim **~700 MB + ~0.6 s startup + idle I/O** with
  isolated, reversible changes.
- **Do next (high impact, moderate effort):** #2 (async/lazy texture load), #4
  (occlusion-aware pause).
- **Validate with art before touching:** #8, #9 (texture resolution, Nebula).
- **Explicitly do NOT spend time on:** physics, per-frame render micro-opts beyond
  #6/#7, or chasing the 370 k "lines" — the runtime surface is 8.3 k lines and the
  hot path is already well-built [RUNTIME_MAP §0].
