#!/usr/bin/env python3
"""
sim_overlay.py — Headless validation of the demo overlay logic (new state model).

No real display, no GL, no camera. Runs DemoOverlay under SDL's dummy video
driver and exercises the PURE-LOGIC layer (everything except draw_gl). Config
paths are redirected to a temp dir so the sim never touches ~/.iris.

  1. FLOATING DEFAULT — opens not-live, primary CTA "Enable Camera",
     status "Floating preview".
  2. ENABLE CAMERA — instantly flips to live (State B), raises tracking_requested,
     persists onboarded; primary becomes "Set as Desktop Background".
  3. ENABLE DESKTOP — raises desktop_mode_requested WITHOUT clearing live (keeping
     live=True avoids the tracker switching to scripted-idle for the transition frame,
     which was the cause of the freeze-frame bug); on_desktop_enabled() → daemon
     running, primary becomes "Disable Desktop Mode".
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
    ov_mod.CAMERA_OFF_FLAG = tmp / "camera_off"   # keep camera-toggle writes off ~/.iris
    from UI.demo_overlay import DemoOverlay

    W, H, S = 1180, 760, 2.0

    # ── 1. Floating default ────────────────────────────────────────────────────
    print("Floating default:")
    o = DemoOverlay(W, H, scale=S, daemon_running=False, desktop_paused=False)
    check("opens NOT live (floating preview)", o.live is False)
    check("primary CTA is 'Enable Camera for Desktop Mode'",
          o._primary() == ("Enable Camera for Desktop Mode", "enable_camera"),
          repr(o._primary()))
    check("status reads 'Floating preview'", o._status_text() == "Floating preview")

    # ── 2. Enable Camera (routed via Settings; _set_camera_enabled starts tracking) ─
    # Clicking primary navigates to Settings. The user enables camera there.
    # _set_camera_enabled(True) is the single choke-point: it sets live +
    # tracking_requested regardless of which code path calls it.
    print("\nEnable Camera (routed via Settings):")
    # Start from camera-disabled state (simulates first run / camera turned off).
    o._set_camera_enabled(False)   # camera off — no toast in sim, state only
    o._active_tab = "worlds"; o._compute_layout()
    check("with camera off, primary shows 'Enable Camera for Desktop Mode'",
          o._primary() == ("Enable Camera for Desktop Mode", "enable_camera"),
          repr(o._primary()))
    _click(o, o, "primary")
    check("clicking it navigates to Settings tab", o._active_tab == "settings")
    # User enables camera from the Settings toggle (camera was off, so toggle → on).
    o._click("camera_toggle")
    check("_set_camera_enabled(True) sets live=True", o.live is True)
    check("_set_camera_enabled(True) sets tracking_requested=True", o.tracking_requested is True)
    o._active_tab = "worlds"; o._compute_layout()
    check("primary shows 'Starting camera…' while settling",
          o._primary() == ("Starting camera…", "none"), repr(o._primary()))
    o.notify_tracking_active()   # engine: real head data arrived → camera granted
    check("primary becomes 'Set as Desktop Background' once granted",
          o._primary() == ("Set as Desktop Background", "enable_desktop"), repr(o._primary()))

    # ── 3. Enable Desktop → raise request WITHOUT clearing live (freeze-frame fix) ─
    print("\nEnable Desktop Mode:")
    _click(o, o, "primary")
    check("live stays True (no scripted-idle switch = no freeze frame)", o.live is True)
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

    # ── 5. Reopen routing ──────────────────────────────────────────────────────
    print("\nReopen routing:")
    # 5a. Daemon already running — don't auto-start tracking (daemon owns camera).
    o2 = DemoOverlay(W, H, scale=S, daemon_running=True, desktop_paused=False)
    check("daemon running: opens floating (no double tracking)", o2.live is False)
    check("daemon running: primary is Disable",
          o2._primary() == ("Disable Desktop Mode", "disable_desktop"), repr(o2._primary()))
    check("daemon running: never auto-requests camera", o2.tracking_requested is False)
    # 5b. No daemon, previously onboarded (macOS TCC already granted) — auto-start.
    o2b = DemoOverlay(W, H, scale=S, daemon_running=False, desktop_paused=False)
    check("re-open after onboard: auto-starts live tracking (no re-toggle needed)",
          o2b.live is True and o2b.tracking_requested is True)

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

    # ── 9. Camera-disable routing regression ───────────────────────────────────
    # After camera is granted then disabled, the button must revert to
    # "Enable Camera for Desktop Mode" → Settings routing.
    print("\nCamera-disable routing:")
    o5 = DemoOverlay(W, H, scale=S, daemon_running=False, desktop_paused=False)
    # Grant camera via the Settings path (direct state manipulation, as the engine does)
    o5._set_camera_enabled(True); o5.notify_tracking_active()
    check("after grant → 'Set as Desktop Background'",
          o5._primary() == ("Set as Desktop Background", "enable_desktop"), repr(o5._primary()))
    o5._set_camera_enabled(False)                            # disable camera access
    check("after camera disabled → 'Enable Camera for Desktop Mode' → Settings",
          o5._primary() == ("Enable Camera for Desktop Mode", "enable_camera"),
          repr(o5._primary()))
    check("camera-disabled clears tracking_active", o5.tracking_active is False)
    # Clicking it now routes to Settings (not a direct camera request).
    _click(o5, o5, "primary")
    check("clicking routes to Settings tab", o5._active_tab == "settings")
    # Clicking it re-enables access (otherwise the engine ignores the request).
    o5._active_tab = "worlds"; o5._compute_layout()   # return from Settings
    _click(o5, o5, "primary")
    check("clicking after camera-off routes to Settings",
          o5._active_tab == "settings")

    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
