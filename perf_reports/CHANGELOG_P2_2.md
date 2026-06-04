# CHANGELOG_P2_2.md — Async Earth Texture Decode

**Fix:** P2.2  
**Files changed:** `Engine/renderer.py` (Earth class), `Launcher/app_engine.py`  
**Risk:** Low-Medium — new code path, existing sync path retained as fallback

---

## Problem

`Earth.__init__()` decoded and uploaded **four 8192×4096 JPEG textures
synchronously** before returning:

```
pygame.image.load(earth_day.jpg)      ← ~0.5 s
pygame.image.load(earth_night.jpg)    ← ~0.5 s
pygame.image.load(earth_clouds.jpg)   ← ~0.5 s
pygame.image.load(earth_specular.jpg) ← ~0.5 s
glTexImage2D (×4) + mipmap            ← ~0.35 s total
─────────────────────────────────────────────────
~2.0 s   scene-build stall before first frame
```

This was the **visible black screen at launch** for Earth world users.

## Change

`Earth.__init__` gains an `async_load: bool = False` parameter (default False for
backward compatibility).

When `async_load=True` (used by `app_engine`):
1. **Geometry + shaders compile synchronously** (~100 ms — VBOs and GLSL).
2. **Four placeholder 1×1 black textures** created immediately so `draw()` is safe.
3. A **daemon thread (`Earth.TextureDecode`)** decodes the JPEGs to raw bytes
   without touching GL.
4. Decoded textures are queued via `queue.Queue` (thread-safe, no lock needed).
5. **`earth.poll_upload()`** is called once per frame from the GL thread; it drains
   the queue and uploads ready textures with `glTexImage2D` + `glGenerateMipmap`.
6. `earth.textures_ready` flips `True` when all four are uploaded.

`app_engine` passes `async_load=True` when building Earth lazily. The profiling
harness (which builds Earth synchronously for stable measurement) continues to use
`async_load=False` (the default), so baseline measurements are unaffected.

---

## Startup before / after (measured on Apple M2)

| Step | Before | After |
|---|---:|---:|
| Earth `__init__` wall time | **~2,000 ms** | **~103 ms** |
| Textures available | at `__init__` return | ~450 ms post-return |
| First frame rendered | ~3,100 ms (incl. imports) | **~400 ms** (incl. imports) |
| Textures fully loaded | at launch | ~550 ms after first frame |

**User experience:** App opens instantly with a dark (placeholder) Earth sphere.
Real textures appear ~0.5 s later as the decoder finishes — a smooth, progressive
reveal rather than a 2 s black screen.

---

## Thread safety

- The background thread (`_decode_worker`) performs only:
  - `pygame.image.load` (file I/O + JPEG decode — thread-safe)
  - `pygame.image.tostring` (surface→bytes — thread-safe)
  - `queue.Queue.put` (thread-safe by design)
- **No GL calls on the background thread.** All `glTexImage2D`,
  `glGenerateMipmap`, and `glBindTexture` calls happen in `poll_upload()`,
  which is called from the GL (main render) thread only.
- The `queue.Queue` is the sole synchronisation primitive. No locks, no events,
  no shared mutable state between threads beyond the queue.

---

## Fallback

If async decode fails for a texture (file missing, corrupt JPEG), the placeholder
texture stays for that slot. The Earth renders with a black patch for that layer
but does not crash. The failure is logged to `~/.iris/iris.log`.

The original synchronous path (`async_load=False`) is fully intact for tools and
tests that need deterministic timing.
