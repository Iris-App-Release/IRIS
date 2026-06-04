"""
portal_runtime.py — Active-portal selection + live switching for the engine.

Decides WHICH portal the engine draws. The active portal name is read from
~/.iris/preferences.json ("portal" key) and its declarative definition is loaded
from Portals/<name>/portal.json via PortalLoader. The preference file is re-polled
(mtime-cached) every frame, so switching portals — in the demo UI, or by editing
preferences — takes effect LIVE in both the demo window and the detached
wallpaper daemon, with no restart. This mirrors the existing ~/.parallax_*
flag-file toggles the engine already polls.

This module touches NO camera / physics / parallax code. It only chooses which
assets and background the renderer composes, from declarative fields whose
defaults reproduce the Earth portal exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

from Portals.portal_loader import PortalLoader

DEFAULT_PORTAL = "earth"


def resolve_portals_dir(base: Path) -> Path:
    """Return the portals directory under `base`, tolerating either casing
    (the source tree uses 'Portals'; PyInstaller bundles it as 'portals')."""
    for name in ("Portals", "portals"):
        cand = base / name
        if cand.exists():
            return cand
    return base / "Portals"


class PortalRuntime:
    """Tracks the active portal definition and re-selects it live from prefs."""

    def __init__(self, portals_dir: Path | str, prefs_file: Path | str,
                 default: str = DEFAULT_PORTAL) -> None:
        self.loader = PortalLoader(Path(portals_dir))
        self.prefs_file = Path(prefs_file)
        self.default = default
        self.name: str | None = None
        self._def: dict = {}
        self._prefs_mtime = None
        self._portal_mtime = None      # mtime of the active portal.json (hot-reload)
        self.select(self._pref_portal())

    # ── preference plumbing ────────────────────────────────────────────────────
    def _pref_portal(self) -> str:
        try:
            return json.loads(self.prefs_file.read_text()).get("portal", self.default)
        except Exception:
            return self.default

    def available(self) -> list[str]:
        try:
            portals = self.loader.list_available_portals()
            return portals or [self.default]
        except Exception:
            return [self.default]

    def display_name(self, portal_name: str) -> str:
        try:
            return self.loader.load_portal(portal_name).get("name", portal_name)
        except Exception:
            return portal_name

    # ── selection / polling ────────────────────────────────────────────────────
    def _active_portal_path(self) -> Path:
        return self.loader.portals_dir / (self.name or self.default) / "portal.json"

    @staticmethod
    def _safe_mtime(path: Path):
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    def select(self, name: str | None) -> str:
        name = name or self.default
        try:
            self._def = self.loader.load_portal(name)
            self.name = name
        except Exception as e:
            if self.name is None:                 # first load failed → hard fallback
                try:
                    self._def = self.loader.load_portal(self.default)
                except Exception:
                    self._def = {}
                self.name = self.default
            print(f"[portal] could not load '{name}': {e}; staying on '{self.name}'")
        # Prime the hot-reload watch so the next poll() doesn't redundantly reload.
        self._portal_mtime = self._safe_mtime(self._active_portal_path())
        return self.name

    def poll(self) -> bool:
        """Re-read portal state iff something changed on disk (both checks are
        mtime-cached — only a cheap stat() per frame, no per-frame disk read).
        Returns True when the active portal's definition actually changed.

          1. prefs file mtime → live portal SWITCH (demo UI / preferences edit).
          2. active portal.json mtime → in-place HOT-RELOAD (Portal Builder save),
             so editing placeable_objects updates the scene with no restart.
        """
        changed = False

        # 1. Portal switch via preferences.
        m = self._safe_mtime(self.prefs_file)
        if m != self._prefs_mtime:
            self._prefs_mtime = m
            want = self._pref_portal()
            if want != self.name:
                self.select(want)               # also re-primes _portal_mtime
                return True

        # 2. Hot-reload the active portal.json in place (keep last-good on failure).
        wm = self._safe_mtime(self._active_portal_path())
        if wm != self._portal_mtime:
            self._portal_mtime = wm
            try:
                self._def = self.loader.load_portal(self.name)
                changed = True
            except Exception as e:
                print(f"[portal] hot-reload of '{self.name}' failed: {e}; keeping last good")

        return changed

    # ── declarative scene parameters (Earth-preserving defaults) ───────────────
    @property
    def env(self) -> dict:
        return self._def.get("environment", {})

    @property
    def rendering(self) -> dict:
        return self._def.get("rendering", {})

    @property
    def primary_mesh(self) -> str:
        return self.env.get("primary_mesh", "earth")

    @property
    def background(self) -> str:
        return self.env.get("background", "stars")

    @property
    def show_icons(self) -> bool:
        return bool(self.rendering.get("show_icons", True))

    @property
    def clear_color(self) -> tuple[float, float, float]:
        c = self.rendering.get("clear_color", [0.0, 0.0, 0.012])
        return (float(c[0]), float(c[1]), float(c[2]))

    # ── Grid Room / spatial-reference parameters (Earth-preserving defaults) ───
    # Read only by the "room" primary_mesh and the opt-in window-frame anchor;
    # every other portal ignores them, so the defaults change nothing.
    @property
    def show_window_frame(self) -> bool:
        """Opt-in faint frame on the glass (portal z=0). Default OFF → shipped
        portals unchanged."""
        return bool(self.rendering.get("show_window_frame", False))

    @property
    def enveloping(self) -> bool:
        """Marks a RIM-ANCHORED ENCLOSURE / GRID portal (Grid Room, Gem) that draws a
        front rim on the glass at portal z = 0. Such portals share the object portals'
        telephoto zoom AND parallax window shift — the grid zooms exactly like the
        sphere portals and a body at the Earth anchor (z = −10) subtends the same
        on-screen size Earth would. The ONE difference: enclosure portals DO NOT PAN —
        the rotational look is held at zero (in app_engine.py). The bezel-anchored rim
        is the grid's purpose (it communicates real cm² of digital space, a box behind
        the glass); a rotational look would rotate that still-visible rim and shear it,
        so clean panning is exclusive to the open SPHERE portals. Default OFF → object
        portals (Earth, The Watcher) keep the full proximity-gated look, byte-identical.
        (History: a forward-dolly 'move into the room' model, then a capped look
        (LOOK_ENCLOSURE_AMP), were both tried and removed 2026-06-02 — any non-zero pan
        still shears the anchored rim. See [[off-axis-projection]],
        [[what-makes-perspective-optimal]] and the enclosure block in app_engine.py.)"""
        return bool(self.rendering.get("enveloping", False))

    @property
    def grid_color(self) -> tuple[float, float, float]:
        c = self.rendering.get("grid_color", [0.30, 0.72, 1.0])
        return (float(c[0]), float(c[1]), float(c[2]))

    @property
    def grid_depth(self) -> float:
        return float(self.rendering.get("grid_depth", 18.0))

    @property
    def grid_divisions(self) -> int:
        return int(self.rendering.get("grid_divisions", 8))

    # ── Portal Builder: user-placeable objects (Grid Room creator surface) ──────
    # Default empty, so every existing portal is byte-identical. The renderer
    # allowlists + clamps this list (Portals/placeable.sanitize_objects) before any
    # draw — this accessor is just the raw JSON pass-through.
    @property
    def placeable_objects(self) -> list[dict]:
        return self._def.get("assets", {}).get("placeable_objects", []) or []
