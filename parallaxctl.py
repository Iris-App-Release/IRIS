#!/usr/bin/env python3
"""
parallaxctl.py — Iris / Parallax Wall command-line control center.

NOTE: This file was REBUILT on 2026-05-30 after the previous copy (which lived in
Build/) was accidentally deleted by build_dmg.sh's clean step — on a
case-insensitive filesystem PyInstaller's ./build work dir collided with the
source Build/ folder. The original was not recoverable, so this is a functional
reconstruction from the engine's flag-file / daemon conventions, not a
byte-for-byte restore. (build_dmg.sh now uses a non-colliding work dir.)

It drives the long-lived wallpaper daemon and engine toggles via the same files
the engine itself polls:
    ~/.parallax_off            master switch — pause (hide wallpaper + release
                               camera) / resume
    ~/.parallax_icons_off      hide the orbital application icons only
    ~/.iris/daemon.pid         PID of the detached wallpaper daemon
    ~/.iris/preferences.json   user preferences (incl. the active "portal")

Commands:
    status                 show daemon / pause / icons / active-world state
    start                  launch the wallpaper daemon (detached)
    stop                   stop the wallpaper daemon
    restart                stop + start
    pause | resume | toggle    master switch (~/.parallax_off)
    icons [on|off]         show / set orbital icon visibility
    world [name]           list worlds / set the active world (live switch)
    log                    tail the daemon log, if present
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT              = Path(__file__).resolve().parent
HOME              = Path.home()
TRACKING_OFF_FLAG = HOME / ".parallax_off"
ICONS_OFF_FLAG    = HOME / ".parallax_icons_off"
CONFIG_DIR        = HOME / ".iris"
PREFS_FILE        = CONFIG_DIR / "preferences.json"
DAEMON_PID_FILE   = CONFIG_DIR / "daemon.pid"
DAEMON_LOG        = CONFIG_DIR / "daemon.log"


# ── helpers ───────────────────────────────────────────────────────────────────
def _read_prefs() -> dict:
    try:
        return json.loads(PREFS_FILE.read_text())
    except Exception:
        return {}


def _write_pref(key: str, value) -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    data = _read_prefs()
    data[key] = value
    PREFS_FILE.write_text(json.dumps(data, indent=2))


def _daemon_pid() -> int | None:
    try:
        pid = int(DAEMON_PID_FILE.read_text().strip())
        os.kill(pid, 0)        # raises if not alive
        return pid
    except Exception:
        return None


def _available_portals() -> list[str]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from Portals.portal_runtime import resolve_portals_dir
        from Portals.portal_loader import PortalLoader
        return WorldLoader(resolve_worlds_dir(ROOT)).list_available_portals() or ["earth"]
    except Exception:
        return ["earth"]


# ── commands ────────────────────────────────────────────────────────────────
def cmd_status(_args) -> int:
    pid = _daemon_pid()
    paused = TRACKING_OFF_FLAG.exists()
    icons = not ICONS_OFF_FLAG.exists()
    world = _read_prefs().get("portal", "earth")
    print(f"daemon : {'running (pid %d)' % pid if pid else 'not running'}")
    print(f"state  : {'paused' if paused else 'active'}")
    print(f"icons  : {'on' if icons else 'off'}")
    print(f"world  : {world}   (available: {', '.join(_available_portals())})")
    return 0


def cmd_start(_args) -> int:
    if _daemon_pid():
        print("daemon already running"); return 0
    TRACKING_OFF_FLAG.unlink(missing_ok=True)
    venv_py = ROOT / ".venv" / "bin" / "python3"
    python = str(venv_py) if venv_py.exists() else sys.executable
    env = {**os.environ, "PARALLAX_MODE": "wallpaper", "PARALLAX_DAEMON": "1"}
    env.pop("SDL_VIDEO_CENTERED", None); env.pop("SDL_VIDEO_WINDOW_POS", None)
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(DAEMON_LOG, "ab") as logf:
        proc = subprocess.Popen([python, str(ROOT / "launcher.py")], env=env,
                                start_new_session=True, stdout=logf, stderr=logf)
    DAEMON_PID_FILE.write_text(str(proc.pid))
    print(f"started wallpaper daemon (pid {proc.pid})")
    return 0


def cmd_stop(_args) -> int:
    pid = _daemon_pid()
    if not pid:
        print("daemon not running"); return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        print(f"could not stop pid {pid}: {e}"); return 1
    DAEMON_PID_FILE.unlink(missing_ok=True)
    print(f"stopped daemon (pid {pid})")
    return 0


def cmd_restart(args) -> int:
    cmd_stop(args)
    return cmd_start(args)


def cmd_pause(_args) -> int:
    TRACKING_OFF_FLAG.touch(); print("paused (wallpaper hidden, camera released)"); return 0


def cmd_resume(_args) -> int:
    TRACKING_OFF_FLAG.unlink(missing_ok=True); print("resumed"); return 0


def cmd_toggle(_args) -> int:
    if TRACKING_OFF_FLAG.exists():
        return cmd_resume(_args)
    return cmd_pause(_args)


def cmd_icons(args) -> int:
    if args:
        want_on = args[0].lower() in ("on", "1", "true", "show")
        if want_on:
            ICONS_OFF_FLAG.unlink(missing_ok=True)
        else:
            ICONS_OFF_FLAG.touch()
    print(f"icons: {'on' if not ICONS_OFF_FLAG.exists() else 'off'}")
    return 0


def cmd_portal(args) -> int:
    worlds = _available_portals()
    if not args:
        active = _read_prefs().get("portal", "earth")
        for w in worlds:
            print(f"  {'* ' if w == active else '  '}{w}")
        return 0
    name = args[0]
    if name not in worlds:
        print(f"unknown world '{name}'. available: {', '.join(worlds)}"); return 1
    _write_pref("portal", name)
    print(f"world set to '{name}' (the running engine picks this up live)")
    return 0


def cmd_log(_args) -> int:
    if not DAEMON_LOG.exists():
        print("no daemon log yet"); return 0
    subprocess.run(["tail", "-n", "60", str(DAEMON_LOG)])
    return 0


COMMANDS = {
    "status": cmd_status, "start": cmd_start, "stop": cmd_stop, "restart": cmd_restart,
    "pause": cmd_pause, "resume": cmd_resume, "toggle": cmd_toggle,
    "icons": cmd_icons, "portal": cmd_world, "log": cmd_log,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    fn = COMMANDS.get(cmd)
    if fn is None:
        print(f"unknown command '{cmd}'. try: {', '.join(COMMANDS)}")
        return 1
    return fn(rest)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
