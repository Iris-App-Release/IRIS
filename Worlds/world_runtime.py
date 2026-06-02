"""
world_runtime.py — Active-world selection + live switching for the engine.

Decides WHICH world the engine draws. The active world name is read from
~/.iris/preferences.json ("world" key) and its declarative definition is loaded
from Worlds/<name>/world.json via WorldLoader. The preference file is re-polled
(mtime-cached) every frame, so switching worlds — in the demo UI, or by editing
preferences — takes effect LIVE in both the demo window and the detached
wallpaper daemon, with no restart. This mirrors the existing ~/.parallax_*
flag-file toggles the engine already polls.

This module touches NO camera / physics / parallax code. It only chooses which
assets and background the renderer composes, from declarative fields whose
defaults reproduce the Earth world exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

from Worlds.world_loader import WorldLoader

DEFAULT_WORLD = "earth"


def resolve_worlds_dir(base: Path) -> Path:
    """Return the worlds directory under `base`, tolerating either casing
    (the source tree uses 'Worlds'; PyInstaller bundles it as 'worlds')."""
    for name in ("Worlds", "worlds"):
        cand = base / name
        if cand.exists():
            return cand
    return base / "Worlds"


class WorldRuntime:
    """Tracks the active world definition and re-selects it live from prefs."""

    def __init__(self, worlds_dir: Path | str, prefs_file: Path | str,
                 default: str = DEFAULT_WORLD) -> None:
        self.loader = WorldLoader(Path(worlds_dir))
        self.prefs_file = Path(prefs_file)
        self.default = default
        self.name: str | None = None
        self._def: dict = {}
        self._prefs_mtime = None
        self.select(self._pref_world())

    # ── preference plumbing ────────────────────────────────────────────────────
    def _pref_world(self) -> str:
        try:
            return json.loads(self.prefs_file.read_text()).get("world", self.default)
        except Exception:
            return self.default

    def available(self) -> list[str]:
        try:
            worlds = self.loader.list_available_worlds()
            return worlds or [self.default]
        except Exception:
            return [self.default]

    def display_name(self, world_name: str) -> str:
        try:
            return self.loader.load_world(world_name).get("name", world_name)
        except Exception:
            return world_name

    # ── selection / polling ────────────────────────────────────────────────────
    def select(self, name: str | None) -> str:
        name = name or self.default
        try:
            self._def = self.loader.load_world(name)
            self.name = name
        except Exception as e:
            if self.name is None:                 # first load failed → hard fallback
                try:
                    self._def = self.loader.load_world(self.default)
                except Exception:
                    self._def = {}
                self.name = self.default
            print(f"[world] could not load '{name}': {e}; staying on '{self.name}'")
        return self.name

    def poll(self) -> bool:
        """Re-read the world preference iff the prefs file changed on disk.
        Returns True when the active world actually changed."""
        try:
            m = self.prefs_file.stat().st_mtime
        except OSError:
            m = None
        if m == self._prefs_mtime:
            return False
        self._prefs_mtime = m
        want = self._pref_world()
        if want != self.name:
            self.select(want)
            return True
        return False

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
    # every other world ignores them, so the defaults change nothing.
    @property
    def show_window_frame(self) -> bool:
        """Opt-in faint frame on the glass (world z=0). Default OFF → shipped
        worlds unchanged."""
        return bool(self.rendering.get("show_window_frame", False))

    @property
    def enveloping(self) -> bool:
        """Forward-dolly depth model for ENCLOSURE worlds (Grid Room, Gem box).
        When True the engine holds the eye-to-glass distance at BASE_Z (FOV
        constant — no lens zoom) and instead dollies the scene toward the eye along
        −z as the viewer leans in, so the camera moves INTO the room: the object of
        interest grows with honest perspective and the front rim slides off-screen
        until enveloped. The rotational 'look' is MERGED toward the Earth feel: it
        engages early and wide (blended with the dolly) but its amplitude is capped
        while the front rim is still on screen, ramping to full only once the rim
        clears — so the early look never shears a still-visible grid edge. Default
        OFF → object worlds (Earth, The Watcher) keep telephoto zoom + the frozen
        proximity gate, byte-identical. See [[off-axis-projection]],
        [[what-makes-perspective-optimal]] and the per-world depth-response +
        enclosure-look blocks in app_engine.py."""
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
