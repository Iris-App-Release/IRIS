---
title: Daemon Control (parallaxctl)
type: system
related: [engine-loop-and-daemon, world-system, dmg-build-process, distribution-checklist]
last_updated: 2026-05-31
sources: [parallaxctl.py, parallaxctl]
---

# Daemon Control (parallaxctl)

## Purpose

`parallaxctl` is the command-line control center for IRIS — the way to drive the
long-lived wallpaper daemon and the engine's toggles from a terminal, outside the
demo UI. It is intentionally thin: it does not talk to the running engine over a
socket, it just **reads and writes the same flag files the engine already polls**
(see [[engine-loop-and-daemon]]). That shared-file contract is why every command
takes effect live, with no restart.

## Two pieces

- `parallaxctl` — a small bash wrapper that finds the project's `.venv` Python
  (or falls back to `python3.11`/`python3`) and execs `parallaxctl.py`.
- `parallaxctl.py` — the actual CLI (lives at the project root).

## Commands

| Command | Action |
|---|---|
| `status` | Print daemon PID, paused/active, icons on/off, and the active world (+ available worlds) |
| `start` | Launch the wallpaper daemon **detached** (`PARALLAX_MODE=wallpaper PARALLAX_DAEMON=1`), record its PID |
| `stop` | `SIGTERM` the daemon and clear the PID file |
| `restart` | `stop` then `start` |
| `pause` / `resume` / `toggle` | Master switch — create/remove `~/.parallax_off` (hide wallpaper + release camera) |
| `icons [on\|off]` | Show/hide the orbital icons (`~/.parallax_icons_off`) |
| `world [name]` | List worlds, or set the active world (live switch via prefs) |
| `log` | Tail the last 60 lines of the daemon log |

## How it works

- **Daemon lifecycle.** `start` spawns `launcher.py` as a detached process
  (`start_new_session=True`) with the wallpaper env vars, redirecting output to
  `~/.iris/daemon.log` and writing the child PID to `~/.iris/daemon.pid`. `stop`
  reads that PID, checks it is alive (`os.kill(pid, 0)`), and sends `SIGTERM`.
  `status` uses the same liveness probe.
- **Toggles.** `pause`/`resume`/`toggle` create or delete `~/.parallax_off`;
  `icons` does the same with `~/.parallax_icons_off`. The engine's per-frame poll
  picks these up immediately.
- **World selection.** `world <name>` validates the name against the installed
  worlds (via [[world-system]]'s `WorldLoader`) and writes the `"world"` key into
  `~/.iris/preferences.json` (created if needed). The running engine's
  `world.poll()` switches live.

## Files it touches

`~/.parallax_off`, `~/.parallax_icons_off`, `~/.iris/preferences.json`,
`~/.iris/daemon.pid`, `~/.iris/daemon.log` — the same set documented in
[[engine-loop-and-daemon]].

## Notes & constraints

- macOS-oriented; prefers the project `.venv` interpreter, so it expects to run
  from the source tree (with `launcher.py` at the root).
- The detached-daemon path here is distinct from the demo's *in-process* Desktop
  Mode (see [[engine-loop-and-daemon]]). Both end up as a desktop-level
  wallpaper; only this one is a separate, PID-tracked process.
- The current `parallaxctl.py` is a functional reconstruction (rebuilt
  2026-05-30) of an earlier copy that lived under `Build/`; this is why it now
  sits at the project root. Relevant background for [[dmg-build-process]].

## Dependencies

Drives [[engine-loop-and-daemon]] through the shared flag files; sets the active
world for [[world-system]]; the daemon it launches is the packaged engine from
[[dmg-build-process]].
