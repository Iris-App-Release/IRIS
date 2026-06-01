#!/bin/bash
# Toggle the entire Parallax Wall wallpaper system on/off
# Double-click to run, or execute from terminal

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARALLAXCTL="$SCRIPT_DIR/parallaxctl"

# Make sure parallaxctl is executable
chmod +x "$PARALLAXCTL" 2>/dev/null

# Get current state
if [ -f ~/.parallax_off ]; then
    STATE="OFF"
    ACTION="ON"
else
    STATE="ON"
    ACTION="OFF"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Parallax Wall Toggle"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "  Current state: $STATE"
echo "  Toggling to:   $ACTION"
echo

# Execute toggle
"$PARALLAXCTL" toggle

echo
echo "  ✓ Wallpaper is now $ACTION"
echo
read -r -p "  Press ENTER to close…"
