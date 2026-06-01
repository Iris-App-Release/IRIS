#!/bin/bash
# Quick status check for Parallax Wall system
# Double-click to see current system state

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARALLAXCTL="$SCRIPT_DIR/parallaxctl"

chmod +x "$PARALLAXCTL" 2>/dev/null

clear

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Parallax Wall — System Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

"$PARALLAXCTL" status

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Earth State (current parallax values):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

if [ -f ~/.parallax_earth_state.json ]; then
    python3 << 'PYSCRIPT'
import json
from pathlib import Path
from datetime import datetime

try:
    with open(Path.home() / ".parallax_earth_state.json") as f:
        s = json.load(f)

    age_ms = int((datetime.now().timestamp() * 1000)) - s.get('timestamp_ms', 0)

    print(f"  Head Position (camera offset):")
    print(f"    cam_x (left/right):  {s['cam_x']:+.3f}")
    print(f"    cam_y (up/down):     {s['cam_y']:+.3f}")
    print(f"    cam_z (forward):     {s['cam_z']:.2f}")
    print()
    print(f"  Earth Position (world coordinates):")
    print(f"    earth_x:             {s['earth_x']:+.3f}")
    print(f"    earth_y:             {s['earth_y']:+.3f}")
    print(f"    earth_z:             {s['earth_z']:.2f}")
    print()
    print(f"  Perspective:")
    print(f"    scale:               {s['perspective_scale']:.3f} (1.0 = baseline, <1.0 = far, >1.0 = close)")
    print()
    print(f"  Freshness:")
    print(f"    age:                 {age_ms}ms")
    print(f"    status:              {'✓ current' if age_ms < 100 else '⚠ stale (>100ms)' if age_ms < 1000 else '✗ offline'}")

except Exception as e:
    print(f"  ✗ Error reading state: {e}")
    print(f"  File may not exist yet (daemon needs to be running)")

PYSCRIPT
else
    echo "  ✗ Earth state file not found"
    echo "  Start daemon with: ./launch.command"
fi

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Orbital Apps Folder:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

if [ -d "/Applications/Orbital Apps" ]; then
    COUNT=$(find "/Applications/Orbital Apps" -maxdepth 1 -name "*.app" -type d | wc -l)
    echo "  ✓ Folder exists with $COUNT apps"
    find "/Applications/Orbital Apps" -maxdepth 1 -name "*.app" -type d | while read app; do
        echo "    - $(basename "$app")"
    done
else
    echo "  ⚠ Folder does not exist (will be auto-created)"
    echo "  Path: /Applications/Orbital Apps/"
fi

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Quick Actions:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

echo "  Start everything:"
echo "    ./launch.command          (wallpaper + icons)"
echo
echo "  Toggle wallpaper:"
echo "    ./Toggle Wallpaper.command"
echo
echo "  View live logs:"
echo "    tail -f /tmp/parallaxwall.out.log    (wallpaper)"
echo "    tail -f /tmp/parallaxicons.out.log   (icons)"
echo
echo "  Stop everything:"
echo "    parallaxctl stop"
echo "    parallaxctl icons stop"
echo

read -r -p "  Press ENTER to close…"
