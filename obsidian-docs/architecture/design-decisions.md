---
title: Design Decisions
type: architecture
related: [off-axis-projection, head-tracking, world-system, rendering-engine, orbital-icons, engine-loop-and-daemon, ui-overlay, daemon-control, headless-simulation, constraints, system-interactions, productification, the-gem]
last_updated: 2026-05-31
sources: [Docs/IRIS_OVERVIEW.txt, Docs/FIRST_LAUNCH_AND_DMG_DESIGN.md, Docs/ICON_GL_MERGE_PLAN.md, Engine/camera_math.py, Worlds/world_runtime.py]
---

# Design Decisions

The *why* behind IRIS — the choices that shaped the architecture, gathered from
the project's design docs and the rationale embedded in the code. Pair this with
[[constraints]] (the limits) and [[system-interactions]] (the wiring).

## Product shape

**Head-coupled parallax instead of a VR headset.** Headsets are clunky, tiring,
and antisocial. A desktop illusion is always-on, ambient, needs no setup, and
works with the monitor you already have — and the same motion-parallax cue can
read as real depth at monitor distance. The trade-off (one calibrated viewing
distance) is accepted because users learn the sweet spot quickly. See
[[constraints]].

**"The illusion is the product."** There is no landing page and no loading
screen — the live world renders from frame 0 and the onboarding UI floats over it
as translucent glass that fades when idle ([[ui-overlay]]). Anything that
interrupts or hides the illusion was rejected.

## The camera math

**Off-axis "window" projection over a normal camera.** A symmetric
`gluPerspective` + `gluLookAt` rig has to *fake* parallax by translating the
scene; that isn't what a window does. The Kooima off-axis frustum is
geometrically correct: lateral eye motion shears the frustum (true parallax) and
moving closer widens the reveal — with **no camera rotation**. The window
half-height is sized so a centred eye at the neutral distance reproduces the old
`gluPerspective(58°)` framing exactly, so nothing about the resting view changed.
Consequently `EARTH_PARALLAX = 0`: the scene is fixed in world space and the
frustum produces *all* the parallax (an old per-object follow would now double
it). See [[off-axis-projection]].

**Three independent, blended viewing channels.** Translation, distance scaling,
and rotation are separate inputs, not substitutes. A far scene is explored by
moving (parallax); a near scene by turning the head (rotation) — so rotation is
**proximity-gated** with a smoothstep ramp (weak far, dominant close, no felt
mode switch), and rotation's sense is deliberately *opposite* to translation.
Vertical exploration gets a larger gain than yaw so the viewer can peer past the
planet up close.

**Latency over accuracy.** All the smoothing complexity in [[head-tracking]]
(1€-filter velocity-adaptive boost, near-field and edge damping, VIDEO-mode
tracking) exists because a smooth 60 fps with low lag sells the illusion far
better than high precision with jitter. The boost is provably zero at rest, so it
can never *add* jitter — only cut motion lag.

**Freeze the physics, then iterate.** Parallax calibration took months; once
right, every later experiment risks breaking it. So the camera math, tracking,
renderer math, and shaders are declared frozen, and new work happens in UI,
worlds, and packaging. The freeze is *enforced* by [[headless-simulation]], which
re-checks the invariants on the real modules.

## Content & worlds

**Worlds are JSON, not code.** Mars, abstract scenes, The Watcher — all use the
same physics, so a world is *content*: a declarative `world.json` listing mesh,
background, and flags. This lets the catalog grow without recompiling and without
touching the engine. See [[world-system]].

**Live switching via polled files.** The active world is read from
`~/.iris/preferences.json` and re-checked each frame (mtime-cached), mirroring the
existing `~/.parallax_*` flag-file toggles — so switching is instant in both the
demo and the daemon. This is the same philosophy as the toggles: **the files are
the IPC.** No sockets, they survive restarts, and the engine's existing per-frame
poll is the only machinery needed. See [[system-interactions]].

**The Watcher as a pure reskin.** The second world reuses the exact
sphere→mesh→shader→texture pipeline with a different texture and a few flags (bloom
off, no icons, black void). It deliberately adds no new rendering or animation
systems — proving the world system works as a content layer. See [[the-watcher]].

**The Gem as a distinct renderer class.** The third world ([[gem]]) uses the
pre-existing `Gem` renderer class with `make_gem(n=16)` (64 flat-shaded triangles).
Unlike The Watcher, it is NOT a reskin of an existing mesh — it is a distinct
geometry/shader pair (`gem.vert/frag`) that exposes flat shading, two-light specular
(key + fill), Fresnel rim, emissive core, and iridescence. Bloom is disabled because
the vignette post-effect conflicts with a pure-white background. The gem rotates
continuously via `Gem.update(dt)` / model-space `glRotatef` — the first world with
autonomous model-space rotation independent of the camera rig. It uses minimal
procedural geometry with one texture asset (floor_checkered.png) for the shadow disk.

## Rendering

**OpenGL 2.1 / GLSL 120 for maximum reach.** The legacy compatibility profile is
the common ground between decade-old Macs and Apple-Silicon Metal-translated GL,
and its fixed-function matrix uniforms let shaders layer on top of the existing
camera math without rewriting the projection system. See [[rendering-engine]].

**Alpha as an anti-bloom mask.** Rather than a separate masking pass, objects that
should stay crisp (icons, the eye) write `alpha = 0` and the bloom bright-pass
skips them. One convention keeps icons readable and the eye biological while the
Earth and stars still glow.

## Orbital icons: from two processes to one scene

The orbital icons have a documented evolution worth understanding:

- **The original two-process design** ran a separate Cocoa overlay that read the
  engine's exported camera state from `~/.parallax_earth_state.json` and drew 2-D
  icons in a window *above* the GL scene. It could never get occlusion or a rigid
  lock right: GL-Retina pixels vs Cocoa points diverged, the scale factor was
  re-invented, a cross-window depth test is impossible, and atomic-write races
  snapped the ring to centre. (Documented in `EARTH_ICON_SYNC.md` and the
  `IMPLEMENTATION_*`/`LIVE_TEST_GUIDE` docs.)
- **The GL merge** (`ICON_GL_MERGE_PLAN.md`) folded the icons into the scene as
  real depth-tested billboards in Earth-local space — the scene FBO already had a
  depth attachment, so icons occlude against the globe *for free* and inherit its
  parallax as one rigid body. This is the current `renderer.IconOrbit`.
- **The standalone Cocoa app is retained** for one thing the in-scene icons
  deliberately don't do: clickable launching, aligned via the same exported
  camera state. The in-scene icons are non-interactive on purpose (hit-testing a
  click-through layer hurt latency for no benefit). See [[orbital-icons]].

## Desktop mode & packaging

**In-process Desktop Mode.** Because you cannot composite a UI over *another*
process's GL window, the onboarding window is a windowed instance of the engine
itself with the HUD drawn into the same GL context; enabling Desktop Mode
reconfigures that same window into the wallpaper, keeping the camera grant. The
detached-daemon path is kept for [[daemon-control]]. See [[engine-loop-and-daemon]].

**"Iris" surface, "parallax" internals.** The product name is Iris, but the
engine's identifiers and flag files keep the original "Parallax Wall" working
title (`~/.parallax_off`, etc.). Renaming internal flags/paths is risky for no
user benefit, so only the product surface was reskinned.

**Procedural assets + careful packaging.** Large textures are generated from code
(and one CC-licensed photo) to keep the bundle small on a memory-constrained
machine; lowercase bundled dirs satisfy PyInstaller path resolution; a
non-colliding work dir avoids the case-insensitive `Build/` clash; a stable
bundle id preserves the camera grant. See [[asset-pipeline]], [[dmg-build-process]],
[[constraints]].

## Related

[[constraints]] · [[system-interactions]] · [[off-axis-projection]] ·
[[world-system]] · [[productification]]
