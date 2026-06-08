#!/usr/bin/env python3
"""
sim_entitlement.py — headless validation of the WORLD PAYWALL.

No GL, no camera, no network, and — importantly — NO writes to the real
~/.iris/licensing.json (every checker here points at a throwaway temp file). The
paywall is a single on/off flag (Pro) that gates USE of the locked worlds while
leaving every world previewable. This sim pins that contract so it can't drift:

  1. Free worlds (earth, grid_room) are ALWAYS usable, Pro or not.
  2. Locked worlds (gem, the_watcher) are usable IFF Pro is active.
  3. set_premium() flips the gate; locked_worlds() empties once Pro.
  4. activate() cannot unlock without a wired store (no backdoor code).
  5. Unknown / junk world names default to UNLOCKED and never crash.
  6. Frozen-invariance: the camera/render core never imports Licensing, and the
     app_engine Desktop-Mode path actually consults the gate.

Run:  .venv/bin/python Scripts/validation/sim_entitlement.py   (exit 0 = pass)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

from Licensing.entitlement import (  # noqa: E402
    EntitlementChecker, FREE_WORLDS, LOCKED_WORLDS,
    LS_STORE_URL, WORLD_BUILDER_RELEASED,
)

_fail = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)


def _fresh() -> EntitlementChecker:
    """An EntitlementChecker bound to a unique temp file (never the user's)."""
    tmp = Path(tempfile.mkdtemp()) / "licensing.json"
    return EntitlementChecker(path=tmp)


def main() -> int:
    print("world paywall — entitlement gate (use-gating, preview always free)")
    print(f"  free={list(FREE_WORLDS)}  locked={list(LOCKED_WORLDS)}  "
          f"store_url_set={bool(LS_STORE_URL)}")
    print()

    # ── 1. Free worlds are always usable ────────────────────────────────────────
    print("1. Free worlds are usable with or without Pro")
    ec = _fresh()
    check("a fresh (non-Pro) user can use every FREE world",
          all(ec.is_world_unlocked(w) for w in FREE_WORLDS))

    # ── 2. Locked worlds gate on Pro ────────────────────────────────────────────
    print("\n2. Locked worlds are usable only with Pro")
    ec = _fresh()
    check("a non-Pro user CANNOT use the locked worlds",
          all(not ec.is_world_unlocked(w) for w in LOCKED_WORLDS),
          f"{[w for w in LOCKED_WORLDS if ec.is_world_unlocked(w)]} wrongly unlocked")
    ec.set_premium(True)
    check("after Pro, the user CAN use the locked worlds",
          all(ec.is_world_unlocked(w) for w in LOCKED_WORLDS))

    # ── 3. set_premium flips the gate; locked_worlds reflects it ─────────────────
    print("\n3. The Pro switch toggles cleanly (persisted to its file)")
    ec = _fresh()
    check("non-Pro: locked_worlds() lists exactly the locked set",
          set(ec.locked_worlds()) == set(LOCKED_WORLDS))
    ec.set_premium(True)
    check("Pro: locked_worlds() is empty", ec.locked_worlds() == ())
    check("Pro persists across a re-read of the same file",
          EntitlementChecker(path=ec._path).is_premium())
    ec.set_premium(False)
    check("revoking Pro re-locks the worlds",
          all(not ec.is_world_unlocked(w) for w in LOCKED_WORLDS))

    # ── 4. activate() has no backdoor while the store is unwired ─────────────────
    print("\n4. activate() cannot unlock without a real (wired) store")
    ec = _fresh()
    check("activate('') is False", ec.activate("") is False)
    check("activate('ANY-CODE') without a real LS server returns False "
          "(no backdoor in shipped code)", ec.activate("ANY-CODE-1234") is False)
    check("a failed activation does NOT grant Pro", not ec.is_premium())

    # ── 5. Unknown / junk worlds default unlocked, never crash ───────────────────
    print("\n5. Unknown / junk world names default to UNLOCKED and never raise")
    ec = _fresh()
    ok = True
    for junk in ("my_custom_world", "", "   ", None, 123, ["x"], {"a": 1}):
        try:
            if not ec.is_world_unlocked(junk):       # a world I made must not be locked
                ok = False
        except Exception:
            ok = False
    check("is_world_unlocked is total (any input → bool, unknown → unlocked)", ok)

    # ── 6. Frozen-invariance + the gate is actually wired ────────────────────────
    print("\n6. The frozen core never imports Licensing; app_engine consults the gate")
    cam = (Path(_root) / "Engine" / "camera_math.py").read_text()
    ren = (Path(_root) / "Engine" / "renderer.py").read_text()
    check("Engine/camera_math.py does not import Licensing",
          "Licensing" not in cam and "entitlement" not in cam)
    check("Engine/renderer.py does not import Licensing",
          "Licensing" not in ren and "entitlement" not in ren)
    ae = (Path(_root) / "Launcher" / "app_engine.py").read_text()
    check("app_engine's Desktop-Mode path consults is_world_unlocked (gate is wired)",
          "is_world_unlocked" in ae)
    check("app_engine fails OPEN (a licensing import error must not brick the engine)",
          "_entitlement = None" in ae)

    # ── 7. Dev Mode unlocks everything; the World Builder tab is dev-only ─────────
    print("\n7. Dev Mode (developer master switch) + the World Builder 'Coming soon' gate")
    ec = _fresh()
    check("a fresh device is NOT in Dev Mode", not ec.is_dev_mode())
    check("World Builder defaults to 'Coming soon' (not available) off Dev Mode",
          ec.world_builder_available() == WORLD_BUILDER_RELEASED and not ec.is_dev_mode())
    # Premium alone (a paying customer) unlocks worlds but must NOT reveal World Builder.
    ec.set_premium(True)
    check("a paying (premium) customer can use locked worlds…",
          all(ec.is_world_unlocked(w) for w in LOCKED_WORLDS))
    check("…but premium does NOT reveal World Builder (stays 'Coming soon')",
          ec.world_builder_available() == WORLD_BUILDER_RELEASED)
    # Dev Mode reveals World Builder AND unlocks worlds, independent of premium.
    ec = _fresh()
    ec.set_dev_mode(True)
    check("Dev Mode reveals the World Builder tab", ec.world_builder_available())
    check("Dev Mode also unlocks the locked worlds (developer sees everything)",
          all(ec.is_world_unlocked(w) for w in LOCKED_WORLDS))
    ec.set_dev_mode(False)
    check("turning Dev Mode off re-hides World Builder and re-locks worlds",
          not ec.world_builder_available()
          and all(not ec.is_world_unlocked(w) for w in LOCKED_WORLDS))
    # The UI actually consults the gate and renders the placeholder.
    ov = (Path(_root) / "UI" / "demo_overlay.py").read_text()
    check("demo_overlay gates the World Builder tab on _wb_available() "
          "(world_builder_available)", "_wb_available" in ov)
    check("demo_overlay renders a 'Coming Soon' placeholder for the gated tab",
          "Coming Soon" in ov)

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed — the world paywall holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
