# CHANGELOG_P1_1.md — Lazy Earth / Nebula / Stars + GPU Unload on World Switch

**Fix:** P1.1  
**Files changed:** `Engine/renderer.py`, `Launcher/app_engine.py`  
**Risk:** Low — mirrors the existing lazy pattern already used for Eye/Gem/Room/Placeables

---

## Problem

`Nebula()`, `Stars()`, and `Earth()` were constructed **unconditionally at startup**
before the active world was consulted:

```python
# Before — always runs regardless of active world
nebula = Nebula()   # +134 MB RSS (incl. driver heap)
stars  = Stars()    #  −18 MB (freed temp)
earth  = Earth()    # +817 MB RSS  ← 4× 8192×4096 JPEG textures
```

A user running **Grid Room** (background=void, primary_mesh=room) held **≈950 MB
of assets that were never sampled**.

## Changes

### 1. `Engine/renderer.py` — `destroy()` on Earth, Nebula, Stars

Added `destroy()` methods to each class that release GL textures, VBOs, and shader
programs. Called when the world switches away so VRAM and RSS are freed promptly.

```python
# Earth.destroy() releases:
glDeleteTextures([tex_day, tex_night, tex_clouds, tex_specular])
glDeleteBuffers(…)   # surface, clouds, atmo VBOs/EBOs
glDeleteProgram(…)   # earth, clouds, atmosphere shader programs
```

### 2. `Launcher/app_engine.py` — lazy construction

Changed eager init to:
```python
nebula = None        # built on first "stars"-background frame
stars  = None        # built on first "stars"-background frame
earth  = None        # built on first Earth-mesh frame (async load)
_earth_failed = False
```

Lazy guards (same pattern as Eye/Gem/Room) wrap every reference in the draw loop.
`earth.update(dt)` is guarded with `if earth is not None`.

### 3. `Launcher/app_engine.py` — release on world switch

`world_changed = world.poll()` result captured. On a world change:
- Nebula/Stars destroyed when switching to a `void` background world.
- Earth destroyed when switching to room/gem/eye **and that world's mesh was
  successfully built** (guards against destroying Earth before knowing the fallback
  won't be needed).

---

## Memory savings (measured on Apple M2)

| Scenario | Before | After | Saving |
|---|---:|---:|---:|
| Grid Room world | 1,133 MB | **143 MB** | **−990 MB** |
| Earth world (at launch) | 1,133 MB | ~1,133 MB | 0 |
| Earth → Grid Room switch | 1,133 MB stays | ~143 MB after switch | −990 MB |

---

## Regression

- Earth world: frame timing identical (sync build via harness, async in app).
- Grid Room world: frame timing identical (281→391 fps range, well above 30 fps cap).
- `destroy()` tested: `glDeleteTextures`, `glDeleteProgram`, `glDeleteBuffers`
  all execute without error.
- Fallback paths (Eye/Gem/Room ctor failure → Earth) still work: Earth is built
  lazily on the first fallback frame.
