#!/usr/bin/env python3
"""
Headless GL profiling harness for IRIS.

Drives the REAL render path of Launcher/app_engine.main() against a HIDDEN
OpenGL context (real Apple M2 GPU, GL 2.1 Metal), with a SYNTHETIC head-input
path instead of the webcam/mediapipe. This isolates render + camera-math + world
cost with no fullscreen takeover and no camera permission.

Usage:
  python Scripts/perf/harness.py --world earth   --frames 600 --timing
  python Scripts/perf/harness.py --world grid_room --frames 600 --timing
  (run under cProfile externally, see profile_cpu.py)

Per-frame sequence mirrors app_engine.py lines ~484-899 for the chosen world.
"""
from __future__ import annotations
import os, sys, math, time, argparse, json
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")

import numpy as np
import pygame
from pygame.locals import DOUBLEBUF, OPENGL, HIDDEN
from OpenGL.GL import *

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Engine.renderer import (
    Earth, Stars, Nebula, IconOrbit, Gem, GridRoom, PlaceableObjects,
    draw_window_frame,
)
from Engine import camera_math as om
from Worlds.world_runtime import WorldRuntime, resolve_worlds_dir

PREFS_FILE = Path.home() / ".iris" / "preferences.json"

# Real default backing res on this machine: 1470x956 logical * 2 Retina.
DEFAULT_W, DEFAULT_H = 2940, 1912

# Constants copied from app_engine
BASE_Z = 11.5
MAX_SHIFT = 4.5
ZOOM_K = 0.95
CAM_Z_MIN, CAM_Z_MAX = 5.0, 34.0
ROT_MAX_RAD = math.radians(om.ROT_MAX_DEG)
CAM_LAG, CAM_LAG_REF_FPS = 0.55, 60.0
CAM_LAG_TAU = -(1.0 / CAM_LAG_REF_FPS) / math.log(1.0 - CAM_LAG)
CAM_LAG_DT_MAX = 0.10


def synthetic_head(t: float):
    """Deterministic head path: lateral sweep + slow lean + small pitch/yaw.
    Mimics a moving viewer so smoothing/parallax/zoom all stay live (not a
    static frame that would let the driver cache)."""
    hx = 0.6 * math.sin(t * 0.9)
    hy = 0.3 * math.sin(t * 0.6 + 1.0)
    hz = 0.4 * math.sin(t * 0.4)
    yaw = 0.5 * math.sin(t * 0.7)
    pitch = 0.3 * math.sin(t * 0.5 + 0.5)
    return hx, hy, hz, yaw, pitch


def make_context(w, h):
    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 2)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 1)
    try:
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 2)
    except pygame.error:
        pass
    pygame.display.set_mode((w, h), DOUBLEBUF | OPENGL | HIDDEN)
    glViewport(0, 0, w, h)
    glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LEQUAL)
    glHint(GL_PERSPECTIVE_CORRECTION_HINT, GL_NICEST)
    glClearColor(0.0, 0.0, 0.012, 1.0)
    try:
        glEnable(GL_MULTISAMPLE)
    except Exception:
        pass


def build_scene(world_name):
    """Construct exactly what the engine builds for this world (eager parts +
    the lazy parts this world needs). Returns dict of objects + ctor timings."""
    timings = {}
    def timed(name, fn):
        s = time.perf_counter(); o = fn(); timings[name] = (time.perf_counter()-s)*1000; return o

    # Isolate from the user's real prefs: write a temp prefs file pinned to the
    # requested world so poll() stays consistent (and we measure poll's real
    # mtime-stat cost without it switching worlds underneath us).
    import tempfile
    tmp_prefs = Path(tempfile.gettempdir()) / "iris_harness_prefs.json"
    tmp_prefs.write_text(json.dumps({"world": world_name}))

    nebula = timed("Nebula", Nebula)
    stars  = timed("Stars",  Stars)
    earth  = timed("Earth",  Earth)
    icons  = timed("IconOrbit", lambda: IconOrbit(debug=False))
    world  = timed("WorldRuntime", lambda: WorldRuntime(resolve_worlds_dir(ROOT), tmp_prefs))
    world.select(world_name)

    gem = room = placeables = None
    if world.primary_mesh == "gem":
        gem = timed("Gem", Gem)
    if world.primary_mesh == "room":
        room = timed("GridRoom", GridRoom)
        placeables = timed("PlaceableObjects", PlaceableObjects)
    return dict(nebula=nebula, stars=stars, earth=earth, icons=icons,
                world=world, gem=gem, room=room, placeables=placeables), timings


def run(world_name, frames, timing, fps_cap):
    make_context(DEFAULT_W, DEFAULT_H)
    print(f"[harness] GL_RENDERER={glGetString(GL_RENDERER).decode()}  "
          f"res={DEFAULT_W}x{DEFAULT_H}  world={world_name}")
    t_build = time.perf_counter()
    S, ctor = build_scene(world_name)
    build_ms = (time.perf_counter()-t_build)*1000
    print(f"[harness] scene built in {build_ms:.1f} ms  "
          + "  ".join(f"{k}={v:.1f}" for k, v in ctor.items()))

    world = S["world"]
    aspect = DEFAULT_W / DEFAULT_H
    W_logical = 1470
    dpi_scale = max(1.0, DEFAULT_W / W_logical)
    sun_world = np.array([0.55, 0.42, 0.72], dtype=np.float32); sun_world /= np.linalg.norm(sun_world)
    fill_world = np.array([-0.72, -0.30, 0.65], dtype=np.float32); fill_world /= np.linalg.norm(fill_world)

    cam_x = cam_y = 0.0; cam_z = BASE_Z; cam_yaw = cam_pitch = 0.0
    OBJECTS_earth = (0.0, 0.0, -10.0, 0.0)

    # Per-stage accumulators (seconds)
    acc = {k: 0.0 for k in
           ("head_cam", "world_poll", "animate", "proj_view", "sun",
            "bg_nebula", "bg_stars", "primary", "icons", "flip", "frame_total")}
    frame_times = []

    clock = pygame.time.Clock()
    t0 = time.perf_counter(); last = t0
    for i in range(frames):
        fstart = time.perf_counter()
        if fps_cap:
            clock.tick(fps_cap)
        now = time.perf_counter(); dt = now - last; last = now; t_s = now - t0

        # --- head + camera smoothing (mirrors app_engine) ---
        s = time.perf_counter()
        hx, hy, hz, yaw, pitch = synthetic_head(t_s)
        cam_alpha = 1.0 - math.exp(-min(dt, CAM_LAG_DT_MAX) / CAM_LAG_TAU)
        shift = MAX_SHIFT
        cam_x += cam_alpha * (-hx * shift - cam_x)
        cam_y += cam_alpha * (hy * shift * 0.55 - cam_y)
        cam_z_t = max(CAM_Z_MIN, min(CAM_Z_MAX, BASE_Z * math.exp(ZOOM_K * hz)))
        cam_z += cam_alpha * (cam_z_t - cam_z)
        prox = om.proximity(hz)
        yaw_t = yaw * ROT_MAX_RAD * prox
        pitch_t = pitch * math.radians(40.0) * prox
        if world.enveloping:
            yaw_t = pitch_t = 0.0
        cam_yaw += cam_alpha * (yaw_t - cam_yaw)
        cam_pitch += cam_alpha * (pitch_t - cam_pitch)
        acc["head_cam"] += time.perf_counter() - s

        # --- animate ---
        s = time.perf_counter()
        S["earth"].update(dt); S["icons"].update(dt)
        if S["gem"] is not None: S["gem"].update(dt)
        acc["animate"] += time.perf_counter() - s

        # --- world poll ---
        s = time.perf_counter(); world.poll(); acc["world_poll"] += time.perf_counter() - s

        # --- clear + projection/view ---
        s = time.perf_counter()
        cc = world.clear_color
        glClearColor(cc[0], cc[1], cc[2], 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        proj = om.off_axis_frustum(cam_x, cam_y, cam_z, aspect, half_h=None)
        glMatrixMode(GL_PROJECTION); glLoadMatrixf(np.ascontiguousarray(proj.T, dtype=np.float32))
        glMatrixMode(GL_MODELVIEW)
        mv = om.view_matrix(cam_x, cam_y, cam_z, cam_yaw, cam_pitch)
        glLoadMatrixf(np.ascontiguousarray(mv.T, dtype=np.float32))
        acc["proj_view"] += time.perf_counter() - s

        s = time.perf_counter()
        view_rot = mv[:3, :3]
        sun_eye = (view_rot @ sun_world).tolist()
        fill_eye = (view_rot @ fill_world).tolist()
        acc["sun"] += time.perf_counter() - s

        # --- background ---
        if world.background == "stars":
            s = time.perf_counter()
            glPushMatrix(); glTranslatef(cam_x, cam_y, cam_z)
            S["nebula"].draw(t_s, brightness=0.85); glPopMatrix()
            acc["bg_nebula"] += time.perf_counter() - s
            s = time.perf_counter()
            S["stars"].draw(t_s, dpi_scale=dpi_scale)
            acc["bg_stars"] += time.perf_counter() - s

        hw, hh = om.window_half_extents(aspect, None)

        # --- primary mesh ---
        s = time.perf_counter()
        if world.primary_mesh == "room":
            S["room"].draw(hw, hh, world.grid_depth, world.grid_divisions,
                           world.grid_color, t_s, dpi_scale)
            objs = world.placeable_objects
            if objs and S["placeables"] is not None:
                S["placeables"].draw(objs, hw, hh, world.grid_depth, world.grid_divisions)
        elif world.primary_mesh == "gem":
            S["gem"].draw_box(hw, hh, world.grid_depth, world.grid_divisions)
            glPushMatrix(); glTranslatef(0.0, 0.0, OBJECTS_earth[2])
            S["gem"].draw(sun_eye, fill_eye, t_s); glPopMatrix()
        else:
            glPushMatrix(); glTranslatef(0.0, 0.0, OBJECTS_earth[2])
            S["earth"].draw(sun_eye, t_s)
            acc["primary"] += time.perf_counter() - s
            s2 = time.perf_counter()
            if world.show_icons:
                S["icons"].draw(dpi_scale)
            glPopMatrix()
            acc["icons"] += time.perf_counter() - s2
            s = None
        if s is not None:
            acc["primary"] += time.perf_counter() - s

        s = time.perf_counter()
        pygame.display.flip()
        if timing:
            glFinish()  # force GPU completion so frame time reflects real GPU cost
        acc["flip"] += time.perf_counter() - s

        ft = time.perf_counter() - fstart
        acc["frame_total"] += ft
        frame_times.append(ft * 1000.0)

    pygame.quit()
    return acc, frame_times, build_ms, ctor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default="earth")
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--timing", action="store_true", help="glFinish each frame + per-stage stats")
    ap.add_argument("--fps", type=int, default=0, help="cap fps (0=uncapped, measure max throughput)")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    acc, fts, build_ms, ctor = run(args.world, args.frames, args.timing, args.fps)
    n = len(fts)
    fts_sorted = sorted(fts)
    def pct(p): return fts_sorted[min(n-1, int(p/100*n))]
    mean = sum(fts)/n
    print(f"\n=== FRAME TIMING ({n} frames, {args.world}, glFinish={'on' if args.timing else 'off'}) ===")
    print(f"mean   {mean:7.3f} ms   ({1000/mean:6.1f} fps sustained)")
    print(f"median {pct(50):7.3f} ms")
    print(f"p95    {pct(95):7.3f} ms")
    print(f"p99    {pct(99):7.3f} ms")
    print(f"min    {fts_sorted[0]:7.3f} ms    max {fts_sorted[-1]:7.3f} ms")

    print(f"\n=== PER-STAGE (mean ms/frame, % of frame) ===")
    total = acc["frame_total"]
    rows = [(k, v) for k, v in acc.items() if k != "frame_total"]
    rows.sort(key=lambda x: -x[1])
    for k, v in rows:
        print(f"{k:12s} {v/n*1000:8.4f} ms  {v/total*100:6.2f}%")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "world": args.world, "frames": n, "mean_ms": mean,
            "median_ms": pct(50), "p95_ms": pct(95), "p99_ms": pct(99),
            "build_ms": build_ms, "ctor_ms": ctor,
            "stage_ms": {k: acc[k]/n*1000 for k in acc},
        }, indent=2))


if __name__ == "__main__":
    main()
