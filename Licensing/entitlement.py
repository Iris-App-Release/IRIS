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

# ── World paywall (single-unlock model, 2026-06-07) ──────────────────────────────
# Which worlds are free vs. behind the one-time Pro unlock. `earth` is the free
# flagship (the magic moment must land before any payment); `grid_room` is the
# World Builder scratch and is always usable. `gem` + `the_watcher` require Pro.
# Buying Pro flips ONE flag (premium_subscription) and unlocks BOTH at once.
# These are the on-disk world folder slugs (Worlds/<slug>/world.json).
FREE_WORLDS   = ("earth", "grid_room")
LOCKED_WORLDS = ("gem", "the_watcher")

# World Builder is not launched yet: everyone sees "Coming soon" in its tab UNTIL
# either this flips True (official launch) OR the device is in Dev Mode (developer).
WORLD_BUILDER_RELEASED = False

# ── Store wiring (Lemon Squeezy) ─────────────────────────────────────────────────
# LS_STORE_URL: your LS checkout page — opened by the in-app "Unlock Pro" button.
# The License API doesn't need a product ID; the key encodes the product itself.
# Fill this in once your LS product is live:
LS_STORE_URL = "https://portalpro.lemonsqueezy.com/checkout/buy/4e3dcf1d-a221-499a-8f67-56cbbda70e3c"


def _verify_lemon_squeezy(license_key: str):
    """Activate a Lemon Squeezy license key on this device → (ok, instance_id, info).

    Calls POST /v1/licenses/activate with the key + a stable device name.
    Stdlib-only (urllib) — zero new dependencies, PyInstaller-safe, and crash-proof:
    any network / parse / timeout error returns (False, None, {}). This is the ONLY
    function that talks to the store; all other activation logic stays in activate().
    """
    import json as _json
    import urllib.request
    try:
        import platform
        node = platform.node() or "Mac"
        instance_name = f"IRIS on {node}"[:50]
    except Exception:
        instance_name = "IRIS Mac"
    try:
        payload = _json.dumps({
            "license_key": license_key,
            "instance_name": instance_name,
        }).encode()
        req = urllib.request.Request(
            "https://api.lemonsqueezy.com/v1/licenses/activate",
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = _json.loads(resp.read().decode())
        ok  = bool(data.get("activated"))
        iid = (data.get("instance") or {}).get("id")          # stable per-device id
        return ok, iid, (data if isinstance(data, dict) else {})
    except Exception:
        return False, None, {}


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

    # ── world paywall ──────────────────────────────────────────────────────────
    def is_world_unlocked(self, world_name: str) -> bool:
        """True if this world may be USED as the live wallpaper (Desktop Mode).

        Free worlds are always usable; the locked built-ins (gem, the_watcher)
        need Pro. This gates USE, not PREVIEW — the demo always renders every
        world so a buyer can see exactly what they're getting before paying.
        Unknown worlds (a user's own World-Builder/imported world) default to
        UNLOCKED: never lock someone out of a world they made. Total/crash-proof.
        """
        name = (world_name if isinstance(world_name, str) else "").strip()
        if name in LOCKED_WORLDS:
            return self.is_premium() or self.is_dev_mode()
        return True

    def locked_worlds(self) -> tuple:
        """The still-locked world slugs (empty once Pro or Dev Mode is active)."""
        return () if (self.is_premium() or self.is_dev_mode()) else tuple(LOCKED_WORLDS)

    # ── dev mode (developer master switch) ─────────────────────────────────────
    def is_dev_mode(self) -> bool:
        """True if this device is in Dev Mode — the developer's master switch.

        Dev Mode unlocks every world AND reveals in-progress features (the World
        Builder tab) that ship as "Coming soon" for everyone else. It is separate
        from premium: a paying customer gets the worlds but NOT the unfinished
        World Builder, so buying never reveals it before launch.
        """
        return bool(self._load().get("dev_mode", False))

    def set_dev_mode(self, value: bool = True) -> None:
        """Flip Dev Mode directly (the /dev-mode command / tests)."""
        data = self._load()
        data["dev_mode"] = bool(value)
        self._save(data)

    def world_builder_available(self) -> bool:
        """Whether the World Builder tab is live (vs. showing "Coming soon").

        Live only once it officially launches (WORLD_BUILDER_RELEASED) OR on a
        Dev-Mode device. Centralised here so the UI never hardcodes the rule.
        """
        return WORLD_BUILDER_RELEASED or self.is_dev_mode()

    # ── unlock (purchase / dev grant) ──────────────────────────────────────────
    def set_premium(self, value: bool = True) -> None:
        """Flip the Pro switch directly. Used by a successful activate() AND by the
        license CLI / tests to demonstrate lock↔unlock with no store wired yet."""
        data = self._load()
        data["premium_subscription"] = bool(value)
        self._save(data)

    def activate(self, code: str) -> bool:
        """Verify a Lemon Squeezy license key; on success unlock Pro permanently.

        Calls the LS activate endpoint → on success persists premium_subscription,
        the key, and the per-device instance_id (so we can re-validate or deactivate
        later). Crash-proof and total: any failure returns False without writing.
        There is intentionally NO backdoor code — an empty/bad key always returns False.
        """
        code = (code or "").strip().upper()
        if not code:
            return False
        ok, instance_id, _info = _verify_lemon_squeezy(code)
        if ok:
            data = self._load()
            data["premium_subscription"] = True
            data["license_key"] = code
            if instance_id:
                data["ls_instance_id"] = instance_id
            self._save(data)
        return ok

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
