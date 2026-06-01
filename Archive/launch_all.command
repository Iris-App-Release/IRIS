#!/bin/bash
# Parallax Wall — startup. Used by the Login Item.
# The orbital app-icons are now rendered INSIDE the OpenGL wallpaper daemon
# (renderer.IconOrbit), so there is a single process to launch — no separate
# overlay. Spawned detached so we return immediately to launchd / the session.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Wallpaper daemon (OpenGL scene + head tracking + orbital icons)
nohup "$SCRIPT_DIR/launch.command"       >> /tmp/parallaxwall.out.log 2>&1 &
disown
