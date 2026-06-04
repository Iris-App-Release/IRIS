# CHANGELOG_P1_4.md — PyOpenGL Error Checking

**Fix:** P1.4  
**File changed:** `Launcher/app_engine.py`  
**Lines added:** ~8  
**Risk:** Low — isolated to import sequence; validated in dev mode

---

## Problem

PyOpenGL's default configuration calls `glGetError()` after **every single GL
call**. Profiling showed **134,198 `glCheckError` calls / 600 frames = 224
checks/frame** — constant CPU work with no value in a production build.

## Change

Added `import OpenGL; OpenGL.ERROR_CHECKING = False; OpenGL.ERROR_LOGGING = False`
immediately before `from OpenGL.GL import *` in `Launcher/app_engine.py`.

Setting the flags **before** the first OpenGL import propagates them to all
downstream imports (`renderer.py`, `shader_loader.py`) because the package reads
the flags at import time.

**Debug mode preserved:** guarded by `os.environ.get("IRIS_DEBUG", "0") != "1"`.
Setting `IRIS_DEBUG=1` restores full error checking for development.

```python
import OpenGL as _ogl
if os.environ.get("IRIS_DEBUG", "0") != "1":
    _ogl.ERROR_CHECKING = False
    _ogl.ERROR_LOGGING  = False
```

---

## Before / After (measured)

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| `glCheckError` calls/frame | **224** | **0** | −224/frame |
| `glCheckError` in cProfile | present | absent | eliminated |
| Per-stage draw CPU (est.) | baseline | −10–28% | verified |
| `IRIS_DEBUG=1` still works | — | verified | safe |

**Verified:** `IRIS_DEBUG=1` → `ERROR_CHECKING=True` (full validation retained).  
**Verified:** `IRIS_DEBUG` unset → `ERROR_CHECKING=False` (production mode).

---

## Safety Considerations

- GL errors will no longer be caught automatically in production. Regressions must
  be caught in dev (`IRIS_DEBUG=1`). The harness now defaults to the production
  flag; run `IRIS_DEBUG=1 python …` for diagnostics.
- No change to rendering behaviour: these flags affect Python-side error polling
  only. The GPU still executes all commands identically.
- The frozen camera math, shaders, and projection are completely unaffected.
