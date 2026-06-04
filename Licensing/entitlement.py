"""
entitlement.py — Freemium entitlement + free-use counter for World Builder.

Additive by design and deliberately far from the frozen physics/camera/render
core (see obsidian-docs/architecture/grid-creator-tool-plan.md §10.3). It tracks
how many free world customizations a device has used and whether a premium
subscription is active, persisting to ``~/.iris/licensing.json``. No network, no
encryption — local-device trust, mirroring the rest of the ``~/.iris`` flag/pref
files. Nothing here is ever imported by the engine/render/camera paths.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

CONFIG_DIR     = Path.home() / ".iris"
LICENSING_FILE = CONFIG_DIR / "licensing.json"

# Unlimited for now (2026-06-03 UX revision): the freemium gate is intentionally
# disabled so World Builder never blocks a save. With an infinite limit,
# `can_save_customization()` is always True and `should_show_upsell()` always False
# — yet all the scaffolding below stays intact, so monetization can be switched back
# on later by changing this single constant to a finite count (e.g. 1). See
# obsidian-docs/architecture/grid-creator-tool-plan.md §10.
FREE_CUSTOMIZATION_LIMIT = math.inf


class EntitlementChecker:
    """Local, per-device entitlement gate for World Builder saves.

    Total and crash-proof: a missing/corrupt licensing file simply reads as a
    fresh free user (0 used, not premium). Writes are best-effort — a failed
    write never raises into the HUD.
    """

    def __init__(self, path: Path = LICENSING_FILE) -> None:
        self._path = path

    # ── persistence ──────────────────────────────────────────────────────────
    def _load(self) -> dict:
        try:
            data = json.loads(self._path.read_text())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        try:
            CONFIG_DIR.mkdir(exist_ok=True)
            self._path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    # ── queries ──────────────────────────────────────────────────────────────
    @property
    def free_limit(self) -> int:
        return FREE_CUSTOMIZATION_LIMIT

    def is_premium(self) -> bool:
        return bool(self._load().get("premium_subscription", False))

    def get_free_usage_count(self) -> int:
        try:
            return int(self._load().get("free_customizations_used", 0))
        except (TypeError, ValueError):
            return 0

    def can_save_customization(self) -> bool:
        """True if the user may save another customization right now."""
        if self.is_premium():
            return True
        return self.get_free_usage_count() < FREE_CUSTOMIZATION_LIMIT

    def should_show_upsell(self) -> bool:
        """True if the next save attempt should surface the premium upsell."""
        if self.is_premium():
            return False
        return self.get_free_usage_count() >= FREE_CUSTOMIZATION_LIMIT

    # ── mutation ─────────────────────────────────────────────────────────────
    def record_customization_saved(self) -> None:
        """Increment the free-usage counter (no-op semantics for premium users —
        the count is harmless once unlimited, and keeps a usage signal for §10
        analytics)."""
        data = self._load()
        try:
            used = int(data.get("free_customizations_used", 0))
        except (TypeError, ValueError):
            used = 0
        data["free_customizations_used"] = used + 1
        data.setdefault("premium_subscription", False)
        self._save(data)
