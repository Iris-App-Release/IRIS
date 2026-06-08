#!/usr/bin/env python3
"""
license_cli.py — switch between what YOU see and what a CUSTOMER sees.

  .venv/bin/python Scripts/license_cli.py            # toggle (no args)
  .venv/bin/python Scripts/license_cli.py toggle     # same — swap views
  .venv/bin/python Scripts/license_cli.py status     # show current view

  .venv/bin/python Scripts/license_cli.py activate KEY  # verify a real LS key

Two named views:
  DEVELOPER VIEW  — Dev Mode ON: every world unlocked + World Builder tab live.
                    This is the right state for your machine.
  CUSTOMER VIEW   — Dev Mode OFF, premium OFF: Gem + The Watcher locked,
                    World Builder = "Coming soon". Exactly what a new buyer sees.

A running app picks up the change live (no restart). Never touches the frozen core.
"""
from __future__ import annotations

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[1])
if _root not in sys.path:
    sys.path.insert(0, _root)

from Licensing.entitlement import (  # noqa: E402
    EntitlementChecker, FREE_WORLDS, LOCKED_WORLDS,
    LS_STORE_URL, WORLD_BUILDER_RELEASED,
)

_DEV_VIEW      = "DEVELOPER VIEW  (your machine — everything unlocked)"
_CUSTOMER_VIEW = "CUSTOMER VIEW   (new buyer — 2 worlds locked, World Builder coming soon)"


def _view_name(ec: EntitlementChecker) -> str:
    return _DEV_VIEW if ec.is_dev_mode() else _CUSTOMER_VIEW


def _print_status(ec: EntitlementChecker) -> None:
    print(f"  Current view       : {_view_name(ec)}")
    print(f"  World Builder tab  : {'LIVE' if ec.world_builder_available() else 'Coming soon'}")
    print(f"  Store URL (LS)     : {LS_STORE_URL or '(not set)'}")
    print("  World lock state   :")
    for w in FREE_WORLDS:
        print(f"      {w:14} free  (always)")
    for w in LOCKED_WORLDS:
        print(f"      {w:14} {'UNLOCKED' if ec.is_world_unlocked(w) else 'LOCKED  ← customer sees this'}")


def _set_dev(ec: EntitlementChecker, on: bool) -> None:
    ec.set_dev_mode(on)
    # Customer view also strips any hand-granted premium so it's a clean slate.
    if not on:
        ec.set_premium(False)


def main(argv: list[str]) -> int:
    ec  = EntitlementChecker()
    cmd = (argv[0].lower() if argv else "toggle")

    # ── Toggle (default — no args) ──────────────────────────────────────────────
    if cmd in ("toggle", "switch"):
        was_dev = ec.is_dev_mode()
        _set_dev(ec, not was_dev)
        print(f"Switched  →  {_view_name(ec)}")
        _print_status(ec)
        return 0

    # ── Explicit view selection ──────────────────────────────────────────────────
    if cmd in ("dev", "on", "developer"):
        _set_dev(ec, True)
        print(f"Switched  →  {_view_name(ec)}")
        _print_status(ec)
        return 0

    if cmd in ("customer", "off", "reset"):
        _set_dev(ec, False)
        print(f"Switched  →  {_view_name(ec)}")
        _print_status(ec)
        return 0

    # ── Status ───────────────────────────────────────────────────────────────────
    if cmd == "status":
        print("IRIS — Dev Mode / world paywall")
        _print_status(ec)
        return 0

    # ── Real store activation (production use) ───────────────────────────────────
    if cmd == "activate":
        if len(argv) < 2:
            print("usage: activate <license_key>")
            return 2
        ok = ec.activate(argv[1])
        print("Activation:", "SUCCESS — Pro unlocked." if ok else
              "FAILED (bad key, or network error).")
        return 0 if ok else 1

    print(f"unknown command: {cmd!r}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
