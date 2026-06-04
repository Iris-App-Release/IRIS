# PHYSICS_REPORT.md

**Phase 7 — Physics Investigation**
Method: source audit of every per-frame state update + per-stage timing from the
harness. Apple M2, 600 frames.

---

## 1. Finding: there is no physics engine

A repository-wide search for a physics/collision/constraint/integration system
returns **nothing** — every hit is a comment explicitly stating the module
*touches no physics*:

```
world_runtime.py:12   "This module touches NO camera / physics / parallax code."
demo_overlay.py:31    "This module touches NO physics."
renderer.py:1109      "No new rendering/camera/physics systems are introduced."
```

There are **no rigid bodies, no collision detection, no constraint solver, no
numerical integrator, no broadphase, no offscreen/inactive-object stepping.** What
the brief calls "physics" is, in IRIS, a small set of **closed-form, O(1)
per-frame updates**. The "physics tuning" referenced in `CLAUDE.md` is the frozen
**camera math** (`Engine/camera_math.py`), i.e. projection geometry — not a
simulation.

---

## 2. The actual per-frame "motion" work (measured)

| "Physics-like" update | Where | Cost/frame | Form |
|---|---|---:|---|
| Camera smoothing (x,y,z,yaw,pitch) | app_engine `head_cam` | **0.009 ms** | exponential lerp `c += α(t−c)`, dt-aware |
| Earth/cloud spin + UV scroll | `Earth.update` | part of **0.009 ms** | `angle = (angle + ω·dt) % 360` |
| Icon orbital position | `IconOrbit.draw` (`om.icon_angle/radius/orbital_local_pos`) | ~0.01 ms | trig: `sin/cos(phase + ωt)` per icon |
| Proximity gate | `om.proximity(hz)` | <0.001 ms | smoothstep clamp |
| World state poll | `world.poll` | **0.047 ms** | 2× `stat()`, mtime-cached |
| **TOTAL "physics"** | | **≈ 0.07 ms/frame** | **~0.2 % of a 33 ms budget** |

(`animate` stage = 0.009 ms, `head_cam` = 0.009 ms, `sun` = 0.007 ms, `world_poll`
= 0.047 ms — summed ≈ 0.07 ms.)

---

## 3. Brief's specific questions, answered

| Question | Answer (evidence) |
|---|---|
| Physics update frequency | Per render frame (30/60 fps), inline. No fixed-timestep accumulator; smoothing is dt-aware so it's framerate-independent (app_engine:118-122). |
| Collision systems | **None.** |
| Constraint systems | **None.** |
| Objects updated while offscreen | N/A — the only animated objects are Earth (1), clouds (1), and ≤10 icons, all on-screen by construction; there is no scene graph of cullable bodies. |
| Objects updated while inactive | Lazy worlds (Eye/Gem/Room) are **not even constructed** until their world is active; once inactive they are not updated (the draw branch isn't taken). Earth/clouds/icons update unconditionally but cost ~0.01 ms. |
| Physics cost per frame | **≈ 0.07 ms (0.2 %).** |

---

## 4. One micro-note (not worth fixing)

`Earth.update` and `IconOrbit.update` are called **every frame even when the active
world doesn't draw them** (e.g. Grid Room still calls `earth.update`/`icons.update`
in the harness/host because they're eagerly built). Cost: ~0.009 ms/frame —
**negligible**. If Earth construction is made lazy (see MEMORY_ANALYSIS /
ASSET_LOADING — the real reason to do it), these updates naturally fall away too.

---

## 5. Conclusion

**Physics is a non-issue for performance.** At ~0.07 ms/frame it is ~0.2 % of the
frame budget and three orders of magnitude below the present/GPU cost. No
optimization is warranted or recommended here. The takeaway is the *opposite* of a
bottleneck: the motion model is admirably cheap (closed-form, no solver).
