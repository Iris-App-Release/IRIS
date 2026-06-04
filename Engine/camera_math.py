"""
orbital_math.py — Pure geometry + camera math for the orbital icon system.

NO OpenGL, NO pygame, NO Cocoa, NO camera. This module is the single source of
truth for the icon orbital coordinate system so it can be unit-tested headlessly
(see sim_orbit.py) and reused by renderer.IconOrbit without duplication.

Coordinate system (matches main.py exactly):
  • World space. Earth center lives at EARTH_BASE + camera parallax offset.
  • Camera at (cam_x, cam_y, cam_z) looking toward (cam_x*k, cam_y*k, 0), up +Y.
  • Right-handed: +Z points toward the camera, the Earth sits at z = -10.

The icons live in EARTH-LOCAL space (relative to Earth's center). The host code
applies the SAME glTranslatef(earth_world) that positions the Earth, so the icons
inherit Earth's parallax/projection/depth for free — they are one rigid body.
"""

from __future__ import annotations

import math
import numpy as np

# ─── Camera / projection — MUST match main.py's gluPerspective + gluLookAt ──────
FOVY_DEG          = 58.0     # main.py: gluPerspective(58.0, aspect, 0.3, 200.0)
NEAR              = 0.3
FAR               = 200.0
CAM_BASE_Z        = 11.5     # main.py: BASE_Z
CAM_TARGET_FACTOR = 0.02     # main.py: gluLookAt center = (cam*0.02, ., 0)

# ─── Earth — MUST match main.py OBJECTS["earth"] + renderer.Earth ───────────────
EARTH_BASE        = (0.0, 0.0, -10.0)   # base_x, base_y, base_z
# Off-axis window rig: the Earth is FIXED in world space and its on-screen
# parallax is produced entirely by the off-axis frustum (the eye moving relative
# to a stationary object at z=-10). The old rig added an artificial cam*0.50
# follow to fake parallax under a symmetric gluLookAt; that would now double the
# motion, so the follow factor is 0. The icons remain rigidly Earth-locked.
EARTH_PARALLAX    = 0.0
R_SURFACE         = 2.6                 # renderer.Earth.R_SURFACE (writes depth)
R_ATMOSPHERE      = 2.85                # renderer.Earth.R_ATMOSPHERE (glow, no depth)

# ─── Orbital ring defaults (world units) ────────────────────────────────────────
# The ring radius must clear the atmosphere glow; the tilt must be steep enough
# that the far arc passes BEHIND the Earth silhouette (radius R_SURFACE) so the
# depth buffer occludes it. See sim_orbit.py for the assertions that pin these.
ORBIT_RADIUS      = 4.2      # distance of each icon from Earth center
ORBIT_TILT_DEG    = 63.0     # tilt of the orbital plane about the X axis
ICON_WORLD_SIZE   = 0.85     # billboard quad edge length in world units
ORBIT_SPEED       = 0.22     # radians / second around the ring
BOB_AMP           = 0.10     # radial wobble amplitude (world units)
BOB_SPEED         = 0.6      # radial wobble speed (rad/s)


def earth_world_center(cam_x: float, cam_y: float) -> np.ndarray:
    """Earth's world-space center for the current camera offset (parallax)."""
    bx, by, bz = EARTH_BASE
    return np.array([bx + cam_x * EARTH_PARALLAX,
                     by + cam_y * EARTH_PARALLAX,
                     bz], dtype=np.float64)


def orbital_local_pos(angle: float, radius: float = ORBIT_RADIUS,
                      tilt_rad: float = math.radians(ORBIT_TILT_DEG)) -> np.ndarray:
    """
    Position of an icon on the tilted ring, in EARTH-LOCAL coordinates.

    The ring starts in the XY plane (radius `radius`) then tilts about the X
    axis. The scene's camera looks down the -Z axis at a ring tilted so its TOP
    edge recedes AWAY from the viewer and its BOTTOM edge swings toward it — the
    natural "seen from slightly above" orientation. With +Z toward the camera:
      • angle ≈ +90° (top of ring)    → local -Z (away)   → passes BEHIND Earth.
      • angle ≈ -90° (bottom of ring) → local +Z (toward) → passes in FRONT.

    +sin(angle) still maps to +Y (screen-up); only the DEPTH term is negated
    relative to a naive +X-axis rotation. That sign is the actual handedness of
    the tilt the scene uses — a plain +X rotation would (incorrectly) tip the
    top toward the camera, which is the upside-down orientation we are fixing.
    """
    ca, sa = math.cos(angle), math.sin(angle)
    ct, st = math.cos(tilt_rad), math.sin(tilt_rad)
    return np.array([radius * ca,
                     radius * sa * ct,
                     -radius * sa * st], dtype=np.float64)


def icon_angle(phase: float, t_s: float, speed: float = ORBIT_SPEED) -> float:
    """Current ring angle for an icon, given its phase offset and elapsed time."""
    return phase + t_s * speed


def icon_radius(t_s: float, bob_phase: float,
                base_radius: float = ORBIT_RADIUS,
                bob_amp: float = BOB_AMP,
                bob_speed: float = BOB_SPEED) -> float:
    """Per-icon ring radius including the floating 'bob' wobble."""
    return base_radius + bob_amp * math.sin(t_s * bob_speed + bob_phase)


# ══════════════════════════════════════════════════════════════════════════════
#  Camera + projection matrices (numpy replicas of gluLookAt / gluPerspective).
#  Used for headless screen-projection checks and for click hit-testing docs.
# ══════════════════════════════════════════════════════════════════════════════

def look_at(eye, center, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    eye    = np.asarray(eye,    dtype=np.float64)
    center = np.asarray(center, dtype=np.float64)
    up     = np.asarray(up,     dtype=np.float64)
    f = center - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    M = np.identity(4, dtype=np.float64)
    M[0, :3] = s
    M[1, :3] = u
    M[2, :3] = -f
    M[0, 3]  = -s.dot(eye)
    M[1, 3]  = -u.dot(eye)
    M[2, 3]  =  f.dot(eye)
    return M


def perspective(fovy_deg=FOVY_DEG, aspect=1.0, near=NEAR, far=FAR) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fovy_deg) * 0.5)
    M = np.zeros((4, 4), dtype=np.float64)
    M[0, 0] = f / aspect
    M[1, 1] = f
    M[2, 2] = (far + near) / (near - far)
    M[2, 3] = (2.0 * far * near) / (near - far)
    M[3, 2] = -1.0
    return M


# ══════════════════════════════════════════════════════════════════════════════
#  Off-axis "window" projection (Kooima generalized perspective projection).
#
#  Physical model: the monitor is a FIXED rectangle (the window) lying in the
#  world z = 0 plane. The scene lives behind it at z < 0 (Earth at z = -10). The
#  viewer's eye is a tracked point in FRONT of the glass at z = +cam_z. What the
#  eye sees is the scene projected through the window aperture — an asymmetric
#  (sheared) frustum whose apex is the eye and whose base is the window rect.
#
#  Unlike a symmetric gluPerspective + gluLookAt rig, this is geometrically what
#  a real window does: lateral eye translation shears the frustum (true motion
#  parallax), and moving the eye CLOSER widens the subtended angle (reveal grows
#  on approach). No camera rotation is involved — a window reveals scene by where
#  the eye IS, never by where it points. See sim_offaxis.py for the validation.
#
#  Window sizing: the half-height is chosen so that an on-axis eye at the neutral
#  distance CAM_BASE_Z reproduces the original gluPerspective(FOVY_DEG) framing
#  exactly — tan(FOVY/2) = WINDOW_HALF_H / CAM_BASE_Z. So at rest the view is
#  identical to the old rig; only off-centre / near eyes change anything.
# ══════════════════════════════════════════════════════════════════════════════

WINDOW_HALF_H = CAM_BASE_Z * math.tan(math.radians(FOVY_DEG) * 0.5)


def window_half_extents(aspect: float, half_h: float | None = None) -> tuple[float, float]:
    """(half_width, half_height) of the physical window rect at z = 0, world units.

    `half_h` is an OPT-IN override of the frozen WINDOW_HALF_H, used only by the
    per-user metric-calibration path ([[Engine/calibration.py]]). When None (the
    default, and the only value any frozen caller/sim passes) this returns the
    calibrated cinematic framing byte-for-byte — the freeze is preserved.
    """
    h = WINDOW_HALF_H if half_h is None else float(half_h)
    return h * aspect, h


def off_axis_frustum(cam_x: float, cam_y: float, cam_z: float,
                     aspect: float, near: float = NEAR, far: float = FAR,
                     half_h: float | None = None) -> np.ndarray:
    """
    glFrustum-form projection matrix for an eye at (cam_x, cam_y, cam_z) looking
    through the fixed window rect at z = 0. Reduces to perspective(FOVY_DEG) when
    the eye is centred at z = CAM_BASE_Z.

    The window axes are world-aligned (right=+x, up=+y, normal=+z toward eye), so
    Kooima's frame-alignment rotation is identity and the eye→screen distance is
    simply cam_z. The frustum edges at the near plane are the window corners
    scaled by near/cam_z and shifted by the eye offset.

    `half_h` is an OPT-IN window half-height (world units). Default None ⇒ the
    frozen WINDOW_HALF_H, so this is byte-identical to the pre-calibration matrix
    for every existing caller and headless sim. The metric-calibration layer
    passes a custom half_h to match the user's real screen subtense; the matrix
    algebra below is unchanged either way. Backward-compat + the metric path are
    pinned by Scripts/validation/sim_calibration.py.
    """
    half_w, half_h = window_half_extents(aspect, half_h)
    d = max(cam_z, 1e-3)          # eye distance to the glass (guard /0)
    s = near / d
    l = (-half_w - cam_x) * s
    r = ( half_w - cam_x) * s
    b = (-half_h - cam_y) * s
    t = ( half_h - cam_y) * s

    M = np.zeros((4, 4), dtype=np.float64)
    M[0, 0] = 2.0 * near / (r - l)
    M[1, 1] = 2.0 * near / (t - b)
    M[0, 2] = (r + l) / (r - l)
    M[1, 2] = (t + b) / (t - b)
    M[2, 2] = -(far + near) / (far - near)
    M[2, 3] = -(2.0 * far * near) / (far - near)
    M[3, 2] = -1.0
    return M


def view_translate(cam_x: float, cam_y: float, cam_z: float) -> np.ndarray:
    """
    Pure-translation modelview that places the eye at the origin. This is the
    far-field / zero-rotation case of view_matrix() below; kept as its own entry
    point for the headless geometry checks.
    """
    M = np.identity(4, dtype=np.float64)
    M[0, 3] = -cam_x
    M[1, 3] = -cam_y
    M[2, 3] = -cam_z
    return M


# ─── Proximity gate + rotational exploration ────────────────────────────────────
# The third viewing component. A real observer explores a FAR scene by moving
# (translation parallax, already produced by the off-axis frustum) and a NEAR
# scene by turning the head (rotation). These are independent inputs — head
# position (cam_x/y, cam_z) and head ORIENTATION (yaw/pitch) — that we BLEND, not
# substitute. Rotation's influence is gated by how close the viewer is, so it is
# weak far away and dominant up close, with a smooth (smoothstep) transition so
# the user never feels a mode switch.
#
# Sense convention (matches the spec, and is the OPPOSITE of translation):
#   • translation right  → reveal the LEFT  of the scene (window parallax)
#   • turning head right → reveal the RIGHT of the scene (panning a portal)

ROT_PROX_LO   = 0.0    # head-z (proximity) at which rotation begins to matter
ROT_PROX_HI   = 0.8    # head-z at which rotation reaches full influence
ROT_MAX_DEG   = 20.0   # max view pan at full proximity + full head turn


def proximity(hz: float, lo: float = ROT_PROX_LO, hi: float = ROT_PROX_HI) -> float:
    """
    Smooth 0→1 proximity weight from the tracker's head-z. 0 = far (translation
    only), 1 = close (rotation fully enabled). Smoothstep so the blend has zero
    first-derivative discontinuity — no perceptible mode switch.
    """
    t = (hz - lo) / (hi - lo) if hi > lo else 0.0
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def _rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def _rot_y(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def view_matrix(cam_x: float, cam_y: float, cam_z: float,
                yaw: float = 0.0, pitch: float = 0.0) -> np.ndarray:
    """
    Modelview for the full three-component rig: rotate the view about the EYE by
    (yaw, pitch), then place the eye at the origin. M = R · T(-eye), so the eye
    maps to 0 and the rotation pivots around it (panning the portal, not orbiting
    the scene). With yaw = pitch = 0 this is exactly view_translate().

    The rotation is applied as a modelview rotation, so the off-axis frustum's
    window plane pans WITH the gaze — at close range this reads as "peeking
    around inside the world", which is precisely the near-field behaviour wanted.
    """
    R = _rot_y(yaw) @ _rot_x(pitch)
    eye = np.array([cam_x, cam_y, cam_z], dtype=np.float64)
    M = np.identity(4, dtype=np.float64)
    M[:3, :3] = R
    M[:3, 3] = -(R @ eye)
    return M


def camera_eye(cam_x: float, cam_y: float, cam_z: float) -> np.ndarray:
    return np.array([cam_x, cam_y, cam_z], dtype=np.float64)


def camera_center(cam_x: float, cam_y: float) -> np.ndarray:
    return np.array([cam_x * CAM_TARGET_FACTOR,
                     cam_y * CAM_TARGET_FACTOR, 0.0], dtype=np.float64)


def project_point(world, view, proj, vp_w: float, vp_h: float):
    """
    Project a world point to window coords (origin bottom-left, like gluProject).
    Returns (screen_x, screen_y, ndc_z, eye_z). eye_z < 0 is in front of camera.
    """
    p = np.asarray([world[0], world[1], world[2], 1.0], dtype=np.float64)
    eye  = view @ p
    clip = proj @ eye
    if abs(clip[3]) < 1e-12:
        return None
    ndc = clip[:3] / clip[3]
    sx = (ndc[0] * 0.5 + 0.5) * vp_w
    sy = (ndc[1] * 0.5 + 0.5) * vp_h
    return sx, sy, ndc[2], eye[2]


def segment_hits_sphere(eye, target, center, radius: float) -> bool:
    """
    True iff the segment from `eye` to `target` crosses the sphere BEFORE reaching
    `target` — i.e. the sphere occludes the target from the eye. If `target` is
    nearer than the sphere (in front), returns False.
    """
    eye    = np.asarray(eye,    dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    center = np.asarray(center, dtype=np.float64)
    d  = target - eye
    oc = eye - center
    a  = d.dot(d)
    b  = 2.0 * oc.dot(d)
    c  = oc.dot(oc) - radius * radius
    disc = b * b - 4.0 * a * c
    if disc < 0.0 or a < 1e-12:
        return False
    sq = math.sqrt(disc)
    s1 = float((-b - sq) / (2.0 * a))
    s2 = float((-b + sq) / (2.0 * a))
    eps = 1e-6
    # An intersection strictly between eye (s=0) and target (s=1) means occlusion.
    return bool((eps < s1 < 1.0 - eps) or (eps < s2 < 1.0 - eps))
