"""
world_loader.py — World definition loader (JSON-based).

Loads world environments from JSON definitions (earth, mars, etc).
Currently only Earth is active; others are placeholders.

Classes:
  • World: Abstract base class for worlds
  • WorldLoader: Loader for JSON world definitions
"""

from __future__ import annotations

import json
from pathlib import Path
from abc import ABC, abstractmethod


class World(ABC):
    """Abstract base class for world environments."""

    def __init__(self, name: str, metadata: dict):
        self.name = name
        self.metadata = metadata

    @abstractmethod
    def get_primary_mesh(self):
        """Get the primary renderable mesh for this world."""
        pass


class WorldLoader:
    """Loads world definitions from JSON."""

    def __init__(self, worlds_dir: Path):
        self.worlds_dir = worlds_dir

    def load_world(self, world_name: str) -> dict:
        """Load a world definition from JSON."""
        world_path = self.worlds_dir / world_name / "world.json"
        if not world_path.exists():
            raise FileNotFoundError(f"World definition not found: {world_path}")

        with open(world_path) as f:
            return json.load(f)

    def list_available_worlds(self) -> list[str]:
        """List all available world definitions."""
        worlds = []
        if self.worlds_dir.exists():
            for item in self.worlds_dir.iterdir():
                if item.is_dir() and (item / "world.json").exists():
                    worlds.append(item.name)
        return sorted(worlds)
