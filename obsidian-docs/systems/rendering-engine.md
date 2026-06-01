---
title: Rendering Engine
type: system
related: [off-axis-projection, world-system, orbital-icons, asset-pipeline, engine-loop-and-daemon, earth, the-watcher, constraints]
last_updated: 2026-05-31
fixed: [retina-best-res-surface]
sources: [Engine/renderer.py, Engine/shader_loader.py, Engine/bloom_postfx.py, shaders/]
---

# Rendering Engine

## Purpose

The rendering engine turns world *content* into pixels. Given the projection and
view matrices from [[off-axis-projection]] and a description of what to draw from
[[world-system]], it composes the scene (sphere, clouds, stars, nebula, eye,
icons) and draws it straight to the screen. (A bloom post-process used to run
here for a cinematic finish; it was **removed 2026-06-01** — see below.)

It targets **OpenGL 2.1 / GLSL 120** on purpose. That legacy compatibility
profile is the common ground between decade-old Macs and Apple-Silicon machines
running GL translated to Metal. GLSL 120 still exposes the fixed-function matrix
uniforms (`gl_ModelViewProjectionMatrix`, `gl_NormalMatrix`, …), so the shaders
layer *on top of* the existing camera math instead of replacing the projection
system — the parallax rig and the shaders stay decoupled.

## Three parts

The engine spans three files:

- `Engine/renderer.py` — the scene objects (meshes, textures, per-object shaders
  and animation).
- `Engine/shader_loader.py` — GLSL compile/link helpers, a cached uniform setter,
  and texture loading.
- `Engine/bloom_postfx.py` — the (now-unused) bloom post-processing pipeline.
  Retained in the tree but no longer imported or run since bloom was removed.

## Scene objects (`renderer.py`)

Geometry helpers: `make_sphere` (UV-sphere, pole-clamped UVs) and `make_gem`
(flat-shaded brilliant-cut facets). A small `Mesh` wrapper holds per-attribute
numpy arrays and uploads them **once to GL buffer objects (VBOs/EBO)** at
construction; the static geometry is then reused every frame instead of being
re-streamed from the CPU (a transparent client-array fallback remains if buffer
creation fails). `Stars` uploads its four attribute arrays the same way. The
render classes:

- **`Earth`** — three concentric spheres: surface (`R = 2.6`), an independently
  spinning cloud shell (`R = 2.625`, just above the surface to avoid z-fighting),
  and an atmospheric-scattering halo (`R = 2.85`). Day/night blend, specular
  oceans, and a normal map drive the surface; the halo is drawn additively from
  the sphere's *back* faces so the glow sits behind the silhouette. Real 23.5°
  axial tilt; surface spins ~6°/s, clouds ~7.5°/s. Powers the [[earth]] world.
- **`Eye`** — "The Watcher": a single textured sphere the same radius as Earth
  (so it fills the same footprint), with wrap-lit diffuse, a tangent-space normal
  map, and a wet cornea specular + Fresnel highlight. It does not spin — only a
  near-imperceptible gaze *drift* (≤1.6°) suggests life. Powers the
  [[the-watcher]] world.
- **`Stars`** — a multi-layer parallax starfield (near/mid/far shells: 900 / 1500
  / 2200 point sprites). Stars carry a stellar-temperature tint table and ~8%
  brighter "feature" stars earn diffraction spikes; drawn additively.
- **`Nebula`** — an inside-rendered background sphere (`R = 95`) that encloses the
  whole scene; prefers the generated `space_background.jpg`, falling back to
  `milky_way_8k.jpg`.
- **`IconOrbit`** — the in-scene orbital app-icon ring, drawn in Earth-local
  space so it inherits Earth's parallax and depth for free. See [[orbital-icons]]
  (which also covers the separate standalone Cocoa launcher).
- **`Gem`** — a 64-triangle flat-shaded brilliant-cut crystal (`n=16`, r=2.2,
  Fresnel + emissive core + two-light specular + soft drop shadow). Exposed as
  [[gem]] world via `Worlds/gem/world.json`. Y-axis spins at 22°/s; X-axis
  tilt oscillates sinusoidally ±25° (never sideways). Drop shadow is a fixed
  horizontal disk drawn before the gem's rotation push. Fully procedural — no
  textures. See [[gem]].

## Anti-bloom alpha convention (now inert)

Historically the **alpha channel doubled as an anti-bloom mask**: objects that
should stay crisp rather than glow — the orbital icons and the eyeball — write
`alpha = 0`, and the bloom bright-pass skipped those pixels. With bloom removed
(2026-06-01) nothing reads that alpha any more, so the convention is **inert** —
the icon/eye shaders still write `alpha = 0` (harmless), but it no longer affects
the image. Everything now renders crisp by default.

## Shaders (`shaders/`, GLSL 120)

| Shader pair | Role |
|---|---|
| `earth` | Day/night blend, specular, normal mapping |
| `clouds` | Cloud shell with alpha + UV drift |
| `atmosphere` | Rayleigh-style atmospheric glow |
| `stars` | Point-sprite starfield with twinkle + spikes |
| `nebula` | Inside-rendered Milky-Way background |
| `eye` | The Watcher's bloodshot sclera + wet cornea |
| `gem` | Faceted crystal (Fresnel + emissive) |
| `icon` | Orbital icon billboards (alpha-discard) |
| `post_bright` | Bright-extract for bloom *(unused — bloom removed)* |
| `post_blur` | Separable Gaussian blur *(unused — bloom removed)* |
| `post_composite` | Final composite + tonemap + vignette *(unused — bloom removed)* |

(`post_quad.vert` is the shared full-screen-quad vertex shader the post passes
reuse. The three `post_*` pairs remain in `shaders/` but are no longer loaded.)

## Shader loader (`shader_loader.py`)

`load_program(name, dir)` compiles `shaders/<name>.vert` + `.frag` and links them,
raising with the full GLSL log on error. `Uniforms` caches uniform locations so
they aren't looked up per frame, with typed setters (`i`, `f`, `v2`, `v3`, `v4`,
`mat3`, `mat4`). `load_texture_2d` loads PNG/JPG via pygame with mipmaps and a
`flip_v` option — equirectangular maps are uploaded *un-flipped* so the north
pole lands at the top UV row. See [[asset-pipeline]].

## Bloom pipeline (`bloom_postfx.py`) — REMOVED 2026-06-01

Bloom was removed. The scene now renders **straight to the default
(multisampled) framebuffer** with no off-screen FBO and no post-process passes.
`BloomPipeline` still exists in `bloom_postfx.py` for reference but is no longer
imported or run.

What it used to do (for context): a scene FBO + ping/pong blur buffers at
`BLOOM_DOWNSCALE = 2`, then bright-extract → 2× separable blur → composite with
Reinhard tonemap (`EXPOSURE = 1.22`, `VIGNETTE = 0.42`, `ABERRATION = 0.0025`,
`BLOOM_STRENGTH = 1.10`). Why it went: the glow was purely cosmetic and the
composite's tonemap/exposure/vignette **veiled the scene** (the "faded" look) —
removing it made every world visibly crisper, dropped three full-screen passes,
and — because the old scene FBO was *not* multisampled — let MSAA actually take
effect for the first time. The accepted trade is that Earth is a little dimmer/
flatter without the exposure+vignette grade. Full rationale in [[log]]
(2026-06-01 "Bloom post-processing removed" entry).

## Data flow

| Consumes | Produces | Destination | Purpose |
|----------|----------|-------------|---------|
| Projection matrix from [[off-axis-projection]] | Framebuffer | [[engine-loop-and-daemon]] | final image to screen |
| Modelview matrix from [[off-axis-projection]] | (same) | (same) | (same) |
| World description from [[world-system]] | (same) | (same) | (same) |
| Textures from [[asset-pipeline]] | (same) | (same) | (same) |
| Sun direction (world space) | Per-object shade + specular | (framebuffer) | lighting |
| Time (`t_s`) | Rotation, animation | (framebuffer) | Earth spin, star twinkle, etc. |
| Head position from [[head-tracking]] (for Eye tracking) | Eye iris rotation | (framebuffer) | gaze follows viewer |

## Constraints

- GL 2.1 / GLSL 120 only. Static meshes (Earth/Nebula/Eye/Gem via `Mesh`, plus
  `Stars`) now use **VBOs**, uploaded once; the floor/shadow/icon/HUD quads remain
  small client-side arrays.
- Renders at the native Retina **drawable** size (not window size) for crisp
  output; render capped at 30 fps in wallpaper/fullscreen, 60 fps in the demo, on
  M1/M2 (see [[constraints]] — the wallpaper cap matches the ~30 Hz head input).
- **A native-Retina GL surface must be forced via Cocoa**, not the pygame flag.
  `_enable_retina_surface()` in `Launcher/app_engine.py` sets
  `wantsBestResolutionOpenGLSurface` on the SDL content view and calls
  `NSOpenGLContext.currentContext().update()`, taking the GL drawable from 1× to
  2× on Retina. It runs after every `set_mode` (startup + the desktop-mode
  resize). **The `ALLOW_HIGHDPI` window flag is a no-op in pygame 2.6 on macOS**
  (verified live — the drawable stayed 1×). Without the Cocoa call,
  `_gl_drawable_size()` returns the logical window size and the entire GL output
  is macOS-upscaled 2×, blurring the scene and the UI overlay. This affects all
  display modes (demo, fullscreen, wallpaper), not just the overlay. See
  [[ui-overlay]] for the companion font + anti-aliased-corner fixes.

## Dependencies

- **Consumes:** matrices from [[off-axis-projection]]; the scene description and
  per-world flags from [[world-system]]; textures from [[asset-pipeline]].
- **Feeds:** the final framebuffer, presented by [[engine-loop-and-daemon]].
- **Related content:** [[earth]], [[the-watcher]], [[orbital-icons]].
