#!/usr/bin/env python3
"""
sim_overlay.py — Headless validation of the demo overlay logic (new state model).

No real display, no GL, no camera. Runs DemoOverlay under SDL's dummy video
driver and exercises the PURE-LOGIC layer (everything except draw_gl). Config
paths are redirected to a temp dir so the sim never touches ~/.iris.

  1. FLOATING DEFAULT — opens not-live, primary CTA "Enable Camera",
     status "Floating preview".
  2. ENABLE CAMERA — instantly flips to live (State B), raises tracking_requested,
     persists onboarded; primary becomes "Enable Desktop Mode".
  3. ENABLE DESKTOP — reverts demo to floating (live False), raises
     desktop_mode_requested; on_desktop_enabled() → daemon running, primary
     becomes "Disable Desktop Mode".
  4. PAUSE / RESUME — Disable writes the master-off flag and flips to a resume
     CTA; Resume clears it.
  5. REOPEN ROUTING — constructed with a running daemon opens straight into the
     main interface (floating), Disable CTA, and never auto-requests the camera
     (no landing/onboarding reset).
  6. SCRIPTED IDLE — floating motion stays small/bounded; no rotation.
  7. HIT-TESTING + RETINA RENDER — buttons hit at centre (scaled), render_surface
     returns a physical-resolution RGBA surface with content, and is cached when
     nothing changes.

Run:  .venv/bin/python sim_overlay.py
Exit 0 = all checks pass, 1 = a check failed.
"""
from __future__ import annotations

# --- reorg path shim (validation harness) ---
import sys as _s
from pathlib import Path as _P
_root = str(_P(__file__).resolve().parents[2])
if _root not in _s.path:
    _s.path.insert(0, _root)

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

_fail = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)


def _click(ov, key_rect_owner, key: str) -> None:
    rect = key_rect_owner._buttons[key]
    # rect is in physical px; handle_event expects WINDOW px → divide by scale.
    pos = (rect.centerx / ov.s, rect.centery / ov.s)
    ov.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos), pos)


def _has_content(surf) -> bool:
    return len(pygame.mask.from_surface(surf, threshold=0).get_bounding_rects()) > 0


def main() -> int:
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    pygame.font.init()

    import UI.demo_overlay as ov_mod
    # Redirect all config writes to a temp dir.
    tmp = Path(tempfile.mkdtemp(prefix="iris_sim_"))
    ov_mod.CONFIG_DIR = tmp
    ov_mod.PREFS_FILE = tmp / "preferences.json"
    ov_mod.DAEMON_PID_FILE = tmp / "daemon.pid"
    ov_mod.TRACKING_OFF_FLAG = tmp / "parallax_off"
    from UI.demo_overlay import DemoOverlay

    W, H, S = 1180, 760, 2.0

    # ── 1. Floating default ────────────────────────────────────────────────────
    print("Floating default:")
    o = DemoOverlay(W, H, scale=S, daemon_running=False, desktop_paused=False)
    check("opens NOT live (floating preview)", o.live is False)
    check("primary CTA is 'Enable Camera'", o._primary() == ("Enable Camera", "enable_camera"),
          repr(o._primary()))
    check("status reads 'Floating preview'", o._status_text() == "Floating preview")

    # ── 2. Enable Camera → live, but Desktop Mode only AFTER camera is granted ──
    print("\nEnable Camera:")
    _click(o, o, "primary")
    check("flips to live (State B)", o.live is True)
    check("raised tracking_requested", o.tracking_requested is True)
    check("persisted onboarded", bool(o._pref("onboarded", False)) is True)
    # The bottom action button OWNS one slot: while the camera is settling it
    # reports the in-flight state and is a no-op — it does NOT yet offer Desktop
    # Mode (the swap waits for the grant, per the new bottom-action spec).
    check("primary shows 'Starting camera…' while settling",
          o._primary() == ("Starting camera…", "none"), repr(o._primary()))
    o.notify_tracking_active()   # engine: real head data arrived → camera granted
    check("primary becomes 'Enable Desktop Mode' once granted",
          o._primary() == ("Enable Desktop Mode", "enable_desktop"), repr(o._primary()))

    # ── 3. Enable Desktop → revert to floating + daemon ────────────────────────
    print("\nEnable Desktop Mode:")
    _click(o, o, "primary")
    check("reverted to floating (live False)", o.live is False)
    check("raised desktop_mode_requested", o.desktop_mode_requested is True)
    o.on_desktop_enabled()
    check("daemon_running after handoff", o.daemon_running is True)
    check("primary now 'Disable Desktop Mode'",
          o._primary() == ("Disable Desktop Mode", "disable_desktop"), repr(o._primary()))

    # ── 4. Pause / resume ──────────────────────────────────────────────────────
    print("\nPause / resume:")
    _click(o, o, "primary")  # disable → pause
    check("master-off flag written on Disable", ov_mod.TRACKING_OFF_FLAG.exists())
    check("primary now 'Enable Desktop Mode' (resume)",
          o._primary() == ("Enable Desktop Mode", "resume_desktop"), repr(o._primary()))
    _click(o, o, "primary")  # resume
    check("master-off flag cleared on Resume", not ov_mod.TRACKING_OFF_FLAG.exists())

    # ── 5. Reopen routing (daemon already running) ─────────────────────────────
    print("\nReopen routing (daemon running):")
    o2 = DemoOverlay(W, H, scale=S, daemon_running=True, desktop_paused=False)
    check("opens into main interface, floating", o2.live is False)
    check("primary is Disable (not a landing page)",
          o2._primary() == ("Disable Desktop Mode", "disable_desktop"), repr(o2._primary()))
    check("never auto-requests the camera", o2.tracking_requested is False)

    # ── 6. Scripted idle bounded ───────────────────────────────────────────────
    print("\nScripted idle motion:")
    mx = my = mz = 0.0
    yaw = pitch = 0.0
    for i in range(4000):
        hx, hy, hz, yaw, pitch = o2.scripted_head(i * 0.05)
        mx, my, mz = max(mx, abs(hx)), max(my, abs(hy)), max(mz, abs(hz))
    check("|hx| bounded (<0.2)", mx < 0.2, f"max {mx:.3f}")
    check("|hy|,|hz| bounded (<0.1)", my < 0.1 and mz < 0.1, f"{my:.3f},{mz:.3f}")
    check("idle yaw/pitch zero", yaw == 0.0 and pitch == 0.0)

    # ── 7. Hit-testing + Retina render + caching ───────────────────────────────
    print("\nHit-testing + render:")
    o3 = DemoOverlay(W, H, scale=S, daemon_running=False, desktop_paused=False)
    pr = o3._buttons["primary"]
    check("primary centre (physical) hits 'primary'", o3._hit(pr.center) == "primary")
    check("outside hits nothing", o3._hit((2, 2)) is None)
    surf = o3.render_surface()
    check(f"surface is physical {int(W*S)}×{int(H*S)}",
          surf.get_size() == (int(W * S), int(H * S)), str(surf.get_size()))
    check("surface has drawn content", _has_content(surf))
    o3.render_surface()  # no change
    check("re-render is cached (not dirty)", o3._dirty is False)

    # ── 8. Tabs, world-nav arrows, preview-suspend signal ──────────────────────
    print("\nTabs / arrows / preview suspend:")
    o4 = DemoOverlay(W, H, scale=S, daemon_running=False, desktop_paused=False)
    check("opens on Worlds tab", o4._active_tab == "worlds")
    check("Worlds tab → preview_active True (engine renders scene)",
          o4.preview_active is True)
    # World-nav arrows cycle the active world instantly (no carousel/animation).
    keys = o4._world_keys
    start = o4.active_world
    _click(o4, o4, "world_next")
    check("right arrow advances world",
          o4.active_world == keys[(keys.index(start) + 1) % len(keys)],
          f"{start} → {o4.active_world}")
    _click(o4, o4, "world_prev")
    check("left arrow returns to start", o4.active_world == start, o4.active_world)
    check("arrow selection persisted to prefs",
          str(o4._pref("world", None)) == start)
    # Switching to Settings/Community suspends the preview and exposes the page.
    _click(o4, o4, "tab:settings")
    check("Settings tab active", o4._active_tab == "settings")
    check("Settings tab → preview_active False (engine skips scene)",
          o4.preview_active is False)
    check("Settings exposes camera_toggle", "camera_toggle" in o4._buttons)
    check("Settings hides world-nav arrows", "world_prev" not in o4._buttons)
    check("Settings renders a content card", _has_content(o4.render_surface()))
    _click(o4, o4, "tab:community")
    check("Community tab → preview_active False", o4.preview_active is False)
    check("Community renders a content card", _has_content(o4.render_surface()))
    _click(o4, o4, "tab:worlds")
    check("returning to Worlds restores preview_active True",
          o4.preview_active is True)
    check("Worlds restores world-nav arrows", "world_prev" in o4._buttons)

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
