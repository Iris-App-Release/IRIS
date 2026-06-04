"""
portal_loader.py — Portal definition loader (JSON-based).

Loads portal environments from JSON definitions (earth, mars, etc).
Currently only Earth is active; others are placeholders.

Classes:
  • Portal: Abstract base class for portals
  • PortalLoader: Loader for JSON portal definitions
"""

from __future__ import annotations

import json
from pathlib import Path
from abc import ABC, abstractmethod


class Portal(ABC):
    """Abstract base class for portal environments."""

    def __init__(self, name: str, metadata: dict):
        self.name = name
        self.metadata = metadata

    @abstractmethod
    def get_primary_mesh(self):
        """Get the primary renderable mesh for this portal."""
        pass


class PortalLoader:
    """Loads portal definitions from JSON."""

    def __init__(self, portals_dir: Path):
        self.portals_dir = portals_dir

    def load_portal(self, portal_name: str) -> dict:
        """Load a portal definition from JSON."""
        portal_path = self.portals_dir / portal_name / "portal.json"
        if not portal_path.exists():
            raise FileNotFoundError(f"Portal definition not found: {portal_path}")

        with open(portal_path) as f:
            return json.load(f)

    def list_available_portals(self) -> list[str]:
        """List all available portal definitions."""
        portals = []
        if self.portals_dir.exists():
            for item in self.portals_dir.iterdir():
                if item.is_dir() and (item / "portal.json").exists():
                    portals.append(item.name)
        return sorted(portals)
