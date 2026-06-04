# RENDER_LOOP_AUDIT.md

**Phase 5 — Render Loop Investigation**
Per-frame operation trace of `app_engine.main()` + the renderer draw methods,
cross-checked against cProfile GL-call counts (19,900 PyOpenGL wrapper calls /
600 frames = **33 GL calls/frame** Earth world). Impact figures are measured or
derived from the §FRAME_TIMING per-stage data. Apple M2, 2940×1912.

> Context: the app already does most things right (VBOs, cached uniform
> locations, mtime-cached polling, one modelview readback instead of N,
> CPU-side sun vector instead of GPU readback). The findings below are the
> *remaining* inefficiencies, ranked by measured impact.

---

## Findings (ranked by impact)

### #1 — PyOpenGL automatic error checking — **HIGH, trivial fix**
`glCheckError` runs after **every** GL call: **134,198 calls / 600 frames =
224×/frame**. Measured impact: disabling `OpenGL.ERROR_CHECKING` (+`ERROR_LOGGING`)
cut per-stage draw CPU **10–28 %** (`primary` 0.153→0.110 ms, `bg_nebula`
0.114→0.085 ms, `icons` 0.244→0.210 ms).
- **Est. saving:** ~0.1–0.25 ms/frame CPU (more under contention/uncapped).
- **Fix:** set `OpenGL.ERROR_CHECKING = False` before `import OpenGL.GL` in the
  frozen/release build (keep ON in dev). 2 lines. Risk: silent GL errors in dev
  only → gate on a debug env var.

### #2 — IconOrbit modelview read-back — **HIGH, low risk**
`renderer.py:1030` does `glGetFloatv(GL_MODELVIEW_MATRIX)` **once per frame** —
a GPU→CPU sync point. The host **already computed `mv` on the CPU**
(`app_engine.py:767`) and the icons are drawn inside
`glPushMatrix();glTranslatef(0,0,-10)`. The Earth-origin modelview is therefore
`mv · translate(0,0,-10)` — derivable on the CPU with zero GL readback.
- **Est. saving:** removes 1 pipeline stall/frame (Earth world only). The
  `icons` stage is 6 % of frame; the readback is the bulk of its *sync* cost.
- **Fix:** pass the CPU `mv` (or the composed matrix) into `IconOrbit.draw()`
  instead of reading it back. Mirrors the sun-vector fix already done in the host.

### #3 — Per-icon numpy allocation — **MEDIUM**
The icon loop allocates **2 `np.array` per icon per frame** (`p` and the 4×4
billboard `m`) → ~20–35 `np.array`/frame (cProfile: 21,080 calls / 600 = 35/frame).
- **Est. saving:** small CPU + GC pressure; ~0.03 ms/frame.
- **Fix:** preallocate one reusable `(4,4)` float32 buffer and write columns in
  place; reuse a scratch vec4. Geometry of the billboard is constant except the
  translation column.

### #4 — Nebula full-screen fillrate — **MEDIUM (GPU), design-level**
`bg_nebula` is **14.5 % of the Earth frame** (0.63 ms GPU). It draws a 64×64
inside-facing sphere (radius 95) that covers the entire 5.6 MPix Retina viewport
with a textured+animated fragment shader, **every frame**, behind everything.
- **Est. saving:** up to ~0.5 ms/frame GPU if replaced with a cheaper background
  (a single full-screen quad with the same texture, or a static cubemap — no
  per-fragment sphere math). Most impactful on weaker GPUs than the M2.
- **Risk:** visual change; needs art sign-off. Lower priority on M2 (headroom).

### #5 — Redundant per-frame GL state toggling — **LOW**
Each draw method re-sets blend/depth/cull state it could assume. e.g. `Earth.draw`
sets `glEnable(GL_DEPTH_TEST)`/`glDisable(GL_BLEND)` that are already the standing
state; `Stars`/`Nebula`/`icons` each enable+disable blend around their draw. With
only ~5 draw groups/frame this is **~33 GL calls/frame total** — already low.
- **Est. saving:** negligible on M2 (a few µs); not worth the readability cost of
  a state-tracker. **Do not change** — flagged only for completeness.

### #6 — Static uniform re-uploads — **LOW**
`Earth.draw` re-uploads sampler uniforms `u_day/u_night/u_specular` (constant
texture-unit ints) every frame; `Nebula` re-uploads `u_nebula`. These never
change after first set.
- **Est. saving:** ~3–6 `glUniform1i`/frame removed; sub-µs. Cosmetic.
- **Fix:** set sampler uniforms once at program init.

### #7 — `try/except` around point-sprite enables — **LOW**
`Stars.draw` wraps `glEnable(GL_PROGRAM_POINT_SIZE)`/`GL_POINT_SPRITE` in
`try/except` **every frame**. The capability never changes after frame 1.
- **Fix:** probe once at construction, store a bool. Sub-µs.

---

## What is already optimal (verified, do not touch)

- **Geometry is in VBOs/EBO**, uploaded once (`Mesh.__init__`); no per-frame
  vertex streaming. (renderer.py:218-240)
- **Uniform locations are cached** in a dict (`shader_loader.Uniforms._loc`); no
  `glGetUniformLocation` per frame.
- **World switching is mtime-cached** (`world.poll` = 2 `stat()`); no per-frame
  disk reads or JSON parsing unless a file changed.
- **Sun/fill light vectors are computed on the CPU** from the known modelview
  (`app_engine.py:774`) instead of `glGetFloatv` read-back — a stall already
  removed by the authors.
- **Lazy world meshes** (Eye/Gem/Room/Placeables built on first use).

---

## Net assessment

The render loop is **already well-optimized**. The only *measurable* wins are
**#1 (error-checking, free)** and **#2 (icon readback, low-risk)** — together a
few tenths of a ms/frame. The largest drawable cost (#4 Nebula fillrate) is a
design trade-off, not a bug. None of these change the conclusion that the app has
large frame headroom on M2; they matter most on **weaker GPUs** and for reducing
**main-thread CPU that competes with the macOS compositor** when other apps open.
