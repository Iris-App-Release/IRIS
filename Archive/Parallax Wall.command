#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
#  Parallax Wall — single control center.
#
#  Double-click this ONE icon to start Parallax Wall and control everything from
#  one place: the wallpaper, the orbital app icons, auto-start, status and logs.
#
#  • On launch it starts the wallpaper (detached, so closing this window does NOT
#    stop the wallpaper) and then shows a simple menu.
#  • Every action just calls `parallaxctl`, the single command-line controller —
#    so nothing here duplicates logic; it is one friendly front door to it.
# ──────────────────────────────────────────────────────────────────────────────
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTL="$SCRIPT_DIR/parallaxctl"
chmod +x "$CTL" 2>/dev/null

OFF_FLAG="$HOME/.parallax_off"
ICONS_OFF_FLAG="$HOME/.parallax_icons_off"

is_running() { pgrep -f "$SCRIPT_DIR/main.py" >/dev/null 2>&1; }

# ── Auto-start the experience on launch (detached) ────────────────────────────
# Only when nothing is running yet: bring the engine up AND un-pause it, so a
# fresh double-click actually shows the wallpaper. If it is already running we
# leave its on/off state alone — you may be opening this menu precisely to pause
# or stop it.
if ! is_running; then
    echo "Starting Parallax Wall…"
    "$CTL" on    >/dev/null 2>&1   # clear ~/.parallax_off so it becomes visible
    "$CTL" start >/dev/null 2>&1   # launch the detached wallpaper daemon
    sleep 1
fi

state () {  # echoes "ON"/"OFF" for a flag-file (absent = ON)
    [ -f "$1" ] && echo "OFF" || echo "ON "
}

menu () {
    clear
    local run wp ic auto
    if is_running; then run="RUNNING"; else run="not running"; fi
    wp="$(state "$OFF_FLAG")"
    ic="$(state "$ICONS_OFF_FLAG")"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "   P A R A L L A X   W A L L"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo
    echo "   Engine     : $run"
    echo "   Wallpaper  : $wp"
    echo "   App Orbit  : $ic"
    echo
    echo "   ───────────────  Controls  ───────────────"
    echo "   1)  Wallpaper  on / off   (toggle)"
    echo "   2)  App Orbit  on / off   (toggle)"
    echo "   3)  Restart the engine"
    echo "   4)  Stop the engine"
    echo "   5)  Configure App Orbit   (choose which apps orbit)"
    echo "   6)  Auto-start at login   (install / remove)"
    echo "   7)  Full status & logs"
    echo
    echo "   Q)  Quit this menu   (Parallax Wall keeps running)"
    echo
    printf "   Choose: "
}

while true; do
    menu
    read -r choice
    echo
    case "${choice:-}" in
        1) "$CTL" toggle ;;
        2) "$CTL" icons toggle ;;
        3) "$CTL" restart ;;
        4) "$CTL" stop ;;
        5) "$CTL" icons config ;;
        6)
            if "$CTL" status 2>/dev/null | grep -q "INSTALLED"; then
                printf "   Auto-start is ON — remove it? [y/N] "; read -r yn
                [ "${yn:-}" = "y" ] || [ "${yn:-}" = "Y" ] && "$CTL" uninstall
            else
                "$CTL" install
            fi
            ;;
        7) "$CTL" status; echo; echo "   (last log lines — Ctrl-C to return)"; sleep 1; "$CTL" log ;;
        q|Q) echo "   Parallax Wall keeps running. Bye!"; echo; exit 0 ;;
        *) echo "   (unrecognised choice)" ;;
    esac
    echo
    printf "   — press ENTER to continue —"; read -r _
done
