#!/usr/bin/env python3
"""
sim_wb_preview_parity.py — Headless proof that the World Builder's TWO previews agree.

No OpenGL, no camera context, no display. The World Builder shows the same world two
ways at once:

  • the 30° oblique "Canvas Cube" (UI.canvas_mesh_renderer + demo_overlay), a PARALLEL
    cabinet drawing — a technical sketch where squares stay square, and
  • the live 3-D parallax (Engine.renderer.PlaceableObjects), a PERSPECTIVE off-axis
    frustum (Engine.camera_math).

These are different projection FAMILIES, so they can never be pixel-identical. "The
two previews are accurate and equal" means they agree on every ORDINAL spatial fact —
left/right, up/down, near/far ordering — and on WHICH FACE of each primitive points at
the viewer. This sim pins exactly that contract, at the neutral/centred reference pose
(hx=hy=0, head-z=0, enclosure zero-pan) — the viewpoint the fixed canvas represents.

sim_grid_api §6 already checks the CELL transform pair (grid_to_world ↔
grid_to_canvas_cell). This sim is the layer below it: it pushes cells through the ACTUAL
screen projections and through the per-primitive FACE geometry, which is where the
"inside-out cube" lived (a flipped depth sign nothing was guarding).

Checks:
  A. Axis parity — sweeping one grid axis moves BOTH previews the same way (no flip /
     swapped axis): +gx → screen-right, +gy → screen-up, +gz → deeper in both.
  B. Oblique occlusion order — the canvas paints in depth along its OWN view direction
     (front-right-above), so a nearer opaque sprite overdraws the ones hidden behind it
     (a dot on the left/back of a sphere disappears). The canvas and the front-on
     parallax legitimately occlude differently — this is canvas self-consistency.
  C. Front-face invariant (the inside-out guard) — for cube & cylinder, every drawn
     face is front-facing, the drawn set == the full visible set, and the +Z
     (toward-glass) face is the brightest/last-drawn AND the parallax camera's nearest
     face. The historical bug drew the −Z face as "front" → this FAILS on it.
  D. Single source of truth — the oblique constants the sprite renderer and the canvas
     stage use ARE Worlds.oblique's (no second copy to drift).

Run (invariant gate, joins the sim suite):
    .venv/bin/python Scripts/validation/sim_wb_preview_parity.py
Run (scene gate — check the exact objects about to be previewed/saved):
    .venv/bin/python Scripts/validation/sim_wb_preview_parity.py --scene [path/to/world.json]
Exit code 0 = previews agree, 1 = a parity check failed.
"""

from __future__ import annotations

# --- reorg path shim (validation harness) ---
import sys as _s
from pathlib import Path as _P
_root = str(_P(__file__).resolve().parents[2])
if _root not in _s.path:
    _s.path.insert(0, _root)

import json
import math
import sys

from Engine import camera_math as om
from Worlds import oblique
from Worlds.oblique import (
    project as oproj, toward_viewer_score, face_visible, visible_axis_normals,
    view_depth, AXIS_NORMALS, FRONT_NORMAL, CUBE_FACES, CYLINDER_FACES,
)
from Worlds.placeable import grid_to_world, grid_to_canvas_cell, sanitize_objects

VP_W, VP_H = 2560.0, 1600.0
ASPECT     = VP_W / VP_H
DEPTH      = 18.0      # grid_room default grid_depth
D          = 8         # grid_room default grid_divisions

_fail = 0
def check(name: str, ok: bool, detail: str = "") -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)


# ── Projections at the neutral reference pose ───────────────────────────────────
def parallax_cam():
    """The frozen off-axis camera at the neutral enclosure pose (hz=0, zero pan)."""
    cz   = max(5.0, min(34.0, om.CAM_BASE_Z * math.exp(0.95 * 0.0)))   # cam_z_for(0)
    view = om.view_matrix(0.0, 0.0, cz, 0.0, 0.0)                      # enclosure: no pan
    proj = om.off_axis_frustum(0.0, 0.0, cz, ASPECT, om.NEAR, om.FAR)
    return view, proj


def par_screen(wx, wy, wz, view, proj):
    """3-D preview: (screen_x, screen_y up-positive, eye_z). Nearer ⇒ larger eye_z."""
    sx, sy, _ndcz, eyez = om.project_point([wx, wy, wz], view, proj, VP_W, VP_H)
    return sx, sy, eyez


def can_screen(gx, gy, gz, divisions, u=100.0):
    """Canvas preview: (screen_x, screen_y DOWN-positive, painter key cgz). Nearer the
    glass ⇒ larger cgz (painted later). Absolute offset is irrelevant to ordering."""
    cgx, cgy, cgz = grid_to_canvas_cell(gx, gy, gz, divisions)
    sx, sy = oproj(cgx, cgy, cgz, u)
    return sx, sy, cgz


def _mono_inc(xs):  return all(xs[i] < xs[i + 1] for i in range(len(xs) - 1))
def _mono_dec(xs):  return all(xs[i] > xs[i + 1] for i in range(len(xs) - 1))


def front_face_checks(label: str, faces) -> None:
    """Check C, on one primitive's face table (canvas side)."""
    normals  = [tuple(float(c) for c in f["normal"]) for f in faces]
    scores   = {n: toward_viewer_score(n) for n in normals}
    listed   = set(normals)
    vis_set  = {tuple(n) for n in visible_axis_normals()}
    top      = max(scores, key=scores.get)
    front_ok = (top == FRONT_NORMAL and face_visible(FRONT_NORMAL)
                and all(scores[FRONT_NORMAL] > scores[n] for n in scores if n != FRONT_NORMAL))
    check(f"C·{label}: every drawn face is front-facing (no hidden face painted)",
          all(face_visible(n) for n in normals),
          ", ".join(f"{n}:{scores[n]:+.2f}" for n in normals))
    check(f"C·{label}: drawn faces == the full visible set (none missing / extra)",
          listed == vis_set, f"{sorted(listed)} vs {sorted(vis_set)}")
    check(f"C·{label}: the +Z toward-glass face is the front (brightest, drawn last)",
          front_ok, f"max-score face = {top}")


# ── Invariant mode — the spanning gate ──────────────────────────────────────────
def invariant_main() -> int:
    hw, hh = om.window_half_extents(ASPECT)
    view, proj = parallax_cam()
    px, py, pz = oblique.projector()
    print("world builder — oblique canvas ↔ 3-D parallax preview parity")
    print(f"  aperture={hw:.2f}×{hh:.2f}  D={D}  grid_depth={DEPTH}  "
          f"oblique∠=30°  projector=({px:.3f},{py:.3f},{pz:.3f})  ref pose hz=0, zero pan")
    print()

    # ── A. Axis parity — one axis at a time, no flip / swapped axis ──────────────
    print("A. Axis parity — sweeping one grid axis moves BOTH previews the same way")
    half = D // 2
    xs_par = [par_screen(*grid_to_world(gx, 0, half, hw, hh, DEPTH, D), view, proj)[0]
              for gx in range(-half, half + 1)]
    xs_can = [can_screen(gx, 0, half, D)[0] for gx in range(-half, half + 1)]
    check("X: +gx moves screen-right in BOTH the 3-D preview and the canvas",
          _mono_inc(xs_par) and _mono_inc(xs_can))
    up_par = [par_screen(*grid_to_world(0, gy, half, hw, hh, DEPTH, D), view, proj)[1]
              for gy in range(-half, half + 1)]                       # y-up
    up_can = [-can_screen(0, gy, half, D)[1] for gy in range(-half, half + 1)]  # flip y-down
    check("Y: +gy moves screen-up in BOTH previews",
          _mono_inc(up_par) and _mono_inc(up_can))
    eye_par = [par_screen(*grid_to_world(0, 0, gz, hw, hh, DEPTH, D), view, proj)[2]
               for gz in range(0, D + 1)]                              # nearer⇒larger
    key_can = [can_screen(0, 0, gz, D)[2] for gz in range(0, D + 1)]   # nearer⇒larger
    check("Z: +gz goes DEEPER (away from glass) in BOTH previews — no depth inversion",
          _mono_dec(eye_par) and _mono_dec(key_can),
          f"eye_z {eye_par[0]:.1f}→{eye_par[-1]:.1f}, cgz {key_can[0]:.1f}→{key_can[-1]:.1f}")

    # ── B. Oblique occlusion order — the canvas hides what the 30° view hides ────
    # The Canvas Cube's viewpoint is front-RIGHT-ABOVE (the projector p), so it must
    # paint in ascending view_depth: a nearer opaque sprite overdraws anything behind
    # it. That is what makes a dot on the hidden (left/back) side of a sphere vanish.
    # NB the canvas (3/4 view) and the front-on parallax legitimately occlude
    # DIFFERENTLY — different viewpoints — so this is a canvas self-consistency check,
    # not a vs-parallax one (placement parity is Check A).
    print("\nB. Oblique occlusion order — the canvas paints nearer-in-the-30°-view last")
    def vd(gx, gy, gz):
        return view_depth(*grid_to_canvas_cell(gx, gy, gz, D))
    check("right (+gx) paints over left (−gx) — a left-side dot is hidden",
          vd(half, 0, half) > vd(-half, 0, half),
          f"vd(right)={vd(half,0,half):.2f} > vd(left)={vd(-half,0,half):.2f}")
    check("top (+gy) paints over bottom (−gy)",
          vd(0, half, half) > vd(0, -half, half))
    check("toward-glass (small gz) paints over the back (large gz)",
          vd(0, 0, 0) > vd(0, 0, D),
          f"vd(glass)={vd(0,0,0):.2f} > vd(back)={vd(0,0,D):.2f}")
    ray = [vd(t - half, t - half, D - t) for t in range(0, D + 1)]   # back-left → front-right
    check("view_depth increases strictly from the hidden back-left to the near front-right",
          all(ray[i] < ray[i + 1] for i in range(len(ray) - 1)))

    # ── C. Front-face invariant (the inside-out guard) ──────────────────────────
    print("\nC. Front-face invariant — both previews show the +Z (toward-glass) face")
    front_face_checks("cube", CUBE_FACES)
    front_face_checks("cylinder", CYLINDER_FACES)
    # Parallax side: the cube's nearest face to the reference camera must be +Z, so it
    # matches the canvas front. (Ties the two previews to the SAME physical face.)
    wc = grid_to_world(0, 0, D // 2, hw, hh, DEPTH, D)
    hs = 0.5
    best, bestz = None, -1e18
    for n in AXIS_NORMALS:
        eyez = par_screen(wc[0] + n[0] * hs, wc[1] + n[1] * hs, wc[2] + n[2] * hs, view, proj)[2]
        if eyez > bestz:
            bestz, best = eyez, tuple(float(c) for c in n)
    check("C·parallax: the cube's nearest face to the camera is +Z (== the canvas front)",
          best == FRONT_NORMAL, f"nearest face normal = {best}")

    # ── D. Single source of truth — no second copy of the oblique math ──────────
    print("\nD. Single source of truth — the canvas + sprites use Worlds.oblique, not a copy")
    try:
        import UI.canvas_mesh_renderer as cmr
        same = (cmr._CA is oblique.CA and cmr._SA is oblique.SA and cmr._DR is oblique.DR)
        check("canvas_mesh_renderer imports the shared oblique constants (same objects)", same)
    except Exception as e:                                            # pragma: no cover
        src = (_P(_root) / "UI" / "canvas_mesh_renderer.py").read_text()
        check("canvas_mesh_renderer imports the shared oblique constants (source check)",
              "from Worlds.oblique import" in src, f"(import unavailable: {e})")
    ov = (_P(_root) / "UI" / "demo_overlay.py").read_text()
    check("demo_overlay's Canvas Cube imports Worlds.oblique (no inline 30° constants)",
          "from Worlds.oblique import" in ov and "math.cos(ANG)" not in ov)
    check("demo_overlay paints the canvas in oblique view_depth order (correct occlusion)",
          "view_depth(" in ov)

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED — the two previews DISAGREE")
        return 1
    print("RESULT: all checks passed — the oblique canvas and the 3-D preview agree")
    return 0


# ── Scene mode — gate the exact objects about to be previewed / saved ────────────
def scene_main(path: str) -> int:
    p = _P(path)
    if not p.is_absolute():
        p = _P(_root) / path
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        print(f"  [FAIL] could not read scene {p}: {e}")
        return 1
    rendering = data.get("rendering", {}) or {}
    divisions = int(rendering.get("grid_divisions", 8) or 8)
    depth     = float(rendering.get("grid_depth", 18.0) or 18.0)
    raw       = (data.get("assets", {}) or {}).get("placeable_objects", []) or []
    hw, hh    = om.window_half_extents(ASPECT)
    view, proj = parallax_cam()
    half = divisions / 2.0

    print(f"world builder — scene parity:  {p}")
    print(f"  grid_divisions={divisions}  grid_depth={depth}  objects={len(raw)}")
    print()

    # Out-of-range advisory — the objective signal behind "items spawn randomly":
    # an object Claude placed outside the box gets clamped to a wall/floor.
    clamped = []
    for i, o in enumerate(raw):
        if not isinstance(o, dict):
            continue
        pos = o.get("grid_position")
        try:
            gx, gy, gz = float(pos[0]), float(pos[1]), float(pos[2])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        cx = min(max(gx, -half), half)
        cy = min(max(gy, -half), half)
        cz = min(max(gz, 0.0), float(divisions))
        if abs(cx - gx) > 1e-6 or abs(cy - gy) > 1e-6 or abs(cz - gz) > 1e-6:
            clamped.append((o.get("id", f"#{i}"), (gx, gy, gz), (cx, cy, cz)))

    san = sanitize_objects(raw, divisions)

    # Canvas-space geometry per object: oblique screen pos, view-depth, sprite radius.
    # Used to show the canvas now HIDES what the 30° view hides (the painter pass sorts
    # by view_depth, so a nearer opaque sprite covers any object behind it).
    U = 100.0
    geo = []
    for o in san:
        gx, gy, gz = o["grid_position"]
        cgx, cgy, cgz = grid_to_canvas_cell(gx, gy, gz, divisions)
        sxp, syp = oproj(cgx, cgy, cgz, U)
        rad = max(1.0, float(o.get("scale", 1.0)) * 0.5 * U * 1.1)    # ≈ sprite radius
        geo.append({"o": o, "cell": (gx, gy, gz), "sp": (sxp, syp),
                    "vd": view_depth(cgx, cgy, cgz), "r": rad})
    for g in geo:                                                     # nearer disc covers centre?
        g["hidden"] = any(
            h is not g and h["vd"] > g["vd"]
            and ((g["sp"][0] - h["sp"][0]) ** 2 + (g["sp"][1] - h["sp"][1]) ** 2) ** 0.5 < h["r"] * 0.85
            for h in geo)

    print("  per-object placement + oblique visibility (the SAME cell, both previews):")
    print(f"    {'id':16} {'model':8} {'cell':>16}  {'world':>18}  par  vis")
    for g in geo:
        o = g["o"]; gx, gy, gz = g["cell"]
        wx, wy, wz = grid_to_world(gx, gy, gz, hw, hh, depth, divisions)
        sx, sy, _ez = par_screen(wx, wy, wz, view, proj)
        lr = "L" if sx < VP_W / 2 - 1 else "R" if sx > VP_W / 2 + 1 else "C"
        ud = "T" if sy > VP_H / 2 + 1 else "B" if sy < VP_H / 2 - 1 else "C"
        print(f"    {str(o.get('id'))[:16]:16} {o['model'][8:]:8} "
              f"({gx:+.1f},{gy:+.1f},{gz:+.1f})  ({wx:+.1f},{wy:+.1f},{wz:+.1f})  "
              f"{lr}{ud}  {'HIDDEN' if g['hidden'] else 'shown'}")
    nhidden = sum(1 for g in geo if g["hidden"])
    print(f"    → {nhidden} of {len(geo)} object(s) occluded in the 30° oblique view "
          f"(painted behind a nearer one)")
    print()

    # Hard gate on the actual scene: the renderer face contract for the models present.
    models = {o["model"] for o in san}
    if "builtin:cube" in models:
        front_face_checks("cube", CUBE_FACES)
    if "builtin:cylinder" in models:
        front_face_checks("cylinder", CYLINDER_FACES)
    if not (models & {"builtin:cube", "builtin:cylinder"}):
        print("  (only spheres present — no orientable face contract to check)")

    if clamped:
        print()
        print(f"  ⚠ {len(clamped)} object(s) were OUT OF RANGE and got clamped to the box "
              f"— the likely reason placement felt 'random'. Nudge the prompt / regenerate:")
        for oid, req, got in clamped:
            print(f"      {oid}: requested {tuple(round(v,1) for v in req)} "
                  f"→ clamped to {tuple(round(v,1) for v in got)}")

    print()
    if _fail:
        print(f"RESULT: {_fail} parity check(s) FAILED — do NOT report this scene as correct")
        return 1
    tail = "  (see clamp advisory above)" if clamped else ""
    print(f"RESULT: previews agree — scene is safe to report{tail}")
    return 0


def main(argv) -> int:
    if "--scene" in argv:
        i = argv.index("--scene")
        path = argv[i + 1] if i + 1 < len(argv) else "Worlds/grid_room/world.json"
        return scene_main(path)
    return invariant_main()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
