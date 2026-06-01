#!/bin/bash
# Test launcher: Start wallpaper + icons + show real-time status
# Double-click to run

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARALLAXCTL="$SCRIPT_DIR/parallaxctl"

chmod +x "$PARALLAXCTL" 2>/dev/null

clear

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Parallax Wall — Test Mode"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

echo "  Starting wallpaper daemon…"
"$PARALLAXCTL" start > /dev/null 2>&1 || true
sleep 2

echo "  Starting icons overlay…"
"$PARALLAXCTL" icons start > /dev/null 2>&1 || true
sleep 2

echo "  Waiting for initialization…"
sleep 2

clear

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ Systems Started — Live Status Below"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# Function to show status
show_status() {
    echo "  Status:"
    "$PARALLAXCTL" status 2>/dev/null || echo "  [Error reading status]"
    echo
    echo "  Earth State:"
    if [ -f ~/.parallax_earth_state.json ]; then
        python3 << 'PYSCRIPT'
import json
from pathlib import Path
try:
    with open(Path.home() / ".parallax_earth_state.json") as f:
        s = json.load(f)
    print(f"    cam_x: {s['cam_x']:+.2f}  cam_y: {s['cam_y']:+.2f}  perspective: {s['perspective_scale']:.2f}")
except:
    print("    [Reading state...]")
PYSCRIPT
    else
        echo "    [Waiting for first export...]"
    fi
    echo
}

# Show initial status
show_status

echo "  Testing checklist:"
echo "    □ Move head LEFT/RIGHT  → icons orbit should shift"
echo "    □ Move face FORWARD/BACK → orbit size should change"
echo "    □ Add app to /Applications/Orbital Apps/"
echo "    □ Wait 1-2 seconds for detection"
echo "    □ New icon should appear"
echo
echo "  Logs:"
echo "    Wallpaper: tail -f /tmp/parallaxwall.out.log"
echo "    Icons:     tail -f /tmp/parallaxicons.out.log"
echo "    State:     watch -n 0.5 'cat ~/.parallax_earth_state.json | python3 -m json.tool'"
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# Live status update every 3 seconds
while true; do
    sleep 3
    clear
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ✓ Systems Running — Live Status [$(date +%H:%M:%S)]"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo
    show_status
    echo "  Tip: You can open additional terminals and run:"
    echo "    tail -f /tmp/parallaxwall.out.log"
    echo "    tail -f /tmp/parallaxicons.out.log"
    echo
    echo "  To stop: Press Ctrl-C, then run 'parallaxctl stop'"
done
