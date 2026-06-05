---
title: Text-to-3D & Mesh Generation Research
type: research
related: [WORLD_SCHEMA, SCAN_IMPORT_ARCHITECTURE, grid-creator-tool-plan, IMPLEMENTATION_ROADMAP, constraints]
last_updated: 2026-06-05
sources:
  - Engine/renderer.py
  - Worlds/placeable.py
  - obsidian-docs/architecture/constraints.md
---

# Text-to-3D & Mesh Generation Research (Phase 6)

> **Question.** Can a service replace the three built-in primitives with real generated
> meshes — so "a glowing red dragon back-left" produces a *dragon*, not a sphere? What
> are the options, and what does IRIS specifically need to adopt one?
>
> **Verdict up front.** The *generator* is the easy part — several mature cloud APIs do
> fast, cheap, commercially-licensed GLB. The *hard part is on our side*: IRIS is an
> Apple-Silicon, OpenGL-2.1 app, so (a) **local/on-device generation is not viable**
> (every open-source model needs NVIDIA/CUDA) and (b) we first need a **GLB→VBO mesh
> import pipeline** before any generated asset can be shown. Pick the API last; build the
> import path first.

---

## 1. The two IRIS-specific constraints that decide everything

**C-1 — No local generation.** The strongest open models (Microsoft **TRELLIS / TRELLIS.2**,
**TripoSR**, Stability **SF3D**) require a 16–24 GB **NVIDIA** GPU and CUDA/Linux. IRIS
runs on Apple Silicon with OpenGL 2.1 ([[constraints]]). So "minimal local CPU usage" is
satisfied only by **cloud APIs** (the model runs on the vendor's GPU) or a **self-hosted
cloud GPU** we rent. On-device text-to-3D on the user's Mac is out.

**C-2 — We can't render a GLB yet.** Today the renderer draws three fixed-function
primitives (`Engine/renderer.py` `make_cube/sphere/cylinder` → `Mesh` VBOs). A generated
asset is a textured triangle mesh. Showing it needs a **mesh-import pipeline**:

```
GLB/glTF  →  loader (pygltflib / trimesh)  →  (vertices, normals, uv, indices)
          →  Engine.renderer.Mesh(v, n, u, i)          ← class already exists
          →  texture upload (Earth already textures meshes)
          →  allowlist extension:  "mesh:<asset_id>"  (per-world assets dir)
```

This is **additive** — fixed-function textured draw, like Earth and the primitives, so the
frozen `shaders/` are untouched (no live-compile risk; [[constraints]]). It is the real
gating work and it is **shared with [[SCAN_IMPORT_ARCHITECTURE]]** (scans are also imported
meshes). Effort: moderate (loader + asset storage + cache + a guard sim). Build it once;
both features ride on it.

---

## 2. The service landscape (2026)

All figures from vendor/comparison pages dated 2026 (see Sources); **verify pricing at
integration time** — it moves quarterly.

| Service | Speed (text→GLB) | API cost | Local CPU | GLB | USDZ | Commercial (paid) | Notes |
|---|---|---|---|---|---|---|---|
| **Tripo AI** | ~8 s (fastest practical) | API $0.01/credit; 2,000 free credits | none (cloud) | ✅ | — | ✅ | Auto game-ready topology + rigging; dev-friendly REST. |
| **Meshy AI** | ~1 min | Pro $10/mo (1k credits) → Studio $30/mo | none (cloud) | ✅ | ✅ | ✅ | **Best-documented REST API**; 7 export formats (FBX/OBJ/GLB/USDZ/STL/BLEND/3MF). |
| **Rodin (Hyper3D)** | ~60–180 s | Business ~$120/mo | none (cloud) | ✅ | ✅ | ✅ | Premium quality (Gen-2 ~10B params, 4K PBR). Highest fidelity, highest cost. |
| **3D AI Studio** | choose model (20–180 s) | unified credits | none (cloud) | ✅ | ✅ | ✅ | **Aggregator** — one REST API in front of Tripo/Meshy/Rodin; reduces vendor lock-in. |
| **Stability SF3D** | ~0.5 s (albedo only) | OSS / hosted | NVIDIA if self-host | ✅ | — | model license | Image→3D; rapid prototyping, no PBR. |
| **TRELLIS / TRELLIS.2** (MS, OSS) | ~3–60 s on H100 | self-host GPU cost | **16–24 GB NVIDIA** | ✅ (+PBR, gaussians) | — | MIT-ish, check | Top OSS quality; **cloud GPU only** for IRIS (not local). |
| **TripoSR** (OSS) | fast | self-host GPU cost | **CUDA/Linux** | via mesh | — | OSS | Image→3D reconstruction; not local on Mac. |

### Tiered evaluation (against the brief: reasonable cost, fast, minimal local CPU, commercial)

- **BEST — Tripo AI.** Fastest (~8 s), genuinely cheap usage-based API ($0.01/credit +
  2,000 free), clean GLB, commercial rights on paid, game-ready topology. Best fit for an
  interactive "Send → see it" hook where latency is felt.
- **GOOD — Meshy AI** (best docs, **USDZ** export aligns with Apple/scan story, predictable
  subscription) and **3D AI Studio** (one integration, swap models, hedge vendor risk).
- **EXPERIMENTAL —**
  - **Rodin/Hyper3D** for a premium "hero asset" tier (quality, 4K PBR) where the $120/mo
    and longer latency are acceptable.
  - **Stability SF3D** for sub-second rough prototyping (albedo only).
  - **TRELLIS.2 self-hosted on a rented cloud GPU** if we ever want to own the model /
    cap per-asset COGS at scale, and can output **3D Gaussians** — but see §3.

---

## 3. Gaussian-splat pipelines — promising, but a different renderer

TRELLIS-class models can emit **3D Gaussian splats** (and radiance fields), which look
spectacular for organic/scanned content. But splats are **not** triangle meshes: rendering
them needs per-frame depth sorting and custom splat shaders. IRIS's GL 2.1 **fixed-function**
pipeline can't draw them without a dedicated renderer + new shaders — and shaders sit next
to the frozen core ([[constraints]]). **Conclusion:** splats are a *separate, later* render
track (high risk, high reward), explicitly **out of scope** for the first mesh-import phase.
Stick to GLB triangle meshes, which drop straight into the existing `Mesh` VBO path.

---

## 4. COGS — fits the model already in place

Generated meshes have the same economics as the existing Claude call: a per-generation
vendor bill that is **the developer's**, gated by the freemium lever. The channels are
identical to [[grid-creator-tool-plan]] §10.7:

- **Dev-funded proxy** — app → our backend (holds Tripo/Meshy key, meters per device).
  Cleanest UX; needs a server; Pro price must clear COGS.
- **BYOK** — power users paste their own key. Zero COGS, niche appeal.
- **Hybrid** — free tier = primitives only (zero COGS); Pro = N proxied mesh generations.

Meshes cost more per call than the text generation, so they belong **behind the paywall**
from day one — the perfect Pro differentiator (free = primitives, Pro = "describe any
object"). Cache aggressively: identical prompt → reuse the stored GLB; store generated
assets per-world so re-opening a world is free.

---

## 5. Recommendation

1. **Build the GLB→VBO mesh-import pipeline first** (the real gate; shared with scans).
   Extend the `model` allowlist to `mesh:<asset_id>`, store assets under the world's
   `asset_dir`, cache by content hash, add a guard sim. Keep it fixed-function/textured.
2. **Integrate Tripo AI** as the first generator (speed + cost + commercial). Abstract it
   behind a `MeshProvider` interface so Meshy/3D AI Studio/Rodin can slot in.
3. **Gate behind Pro** (free = three primitives; Pro = generated meshes), reusing the
   `Licensing/entitlement.py` lever.
4. **Defer** splats and on-device generation indefinitely (renderer mismatch / Apple-Silicon).

This keeps the reliability bar (primitives always render) while adding generated meshes as
a paid, cached, fixed-function extension that never touches the frozen core.

---

## Sources

- [3D AI Pricing & Credits Comparison (2026): Sloyd vs Meshy vs Tripo vs CSM vs Hyper3D](https://www.sloyd.ai/blog/3d-ai-price-comparison)
- [Best 3D Model Generation APIs in 2026 — 3DAI Studio](https://www.3daistudio.com/blog/best-3d-model-generation-apis-2026)
- [Meshy Official Pricing](https://www.meshy.ai/pricing)
- [Tripo — The Best Text to GLB AI 3D Model Converter (2026)](https://www.tripo3d.ai/content/en/guide/the-best-text-to-glb-ai-3d-model-converter)
- [Best 8 AI 3D Model Generators in 2026 — RapidDirect](https://www.rapiddirect.com/blog/best-8-ai-3d-model-generators/)
- [Microsoft TRELLIS (GitHub)](https://github.com/microsoft/TRELLIS) · [TRELLIS.2 (GitHub)](https://github.com/microsoft/TRELLIS.2)
- [TripoSR (open-source image-to-3D)](https://www.triposrai.com/)
- [Stable Fast 3D (Stability AI)](https://www.stablefast3d.com/)

## Related
[[WORLD_SCHEMA]] · [[SCAN_IMPORT_ARCHITECTURE]] · [[grid-creator-tool-plan]] · [[IMPLEMENTATION_ROADMAP]] · [[constraints]]
