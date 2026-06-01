#!/bin/bash
# Iris — launch from source (no rebuild needed).
# Double-click this file to run the latest code directly.

PROJECT="/Users/averychatten/Documents/IRIS APP"

cd "$PROJECT"

# Pre-select The Watcher so it opens straight to the eye.
mkdir -p ~/.iris
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.iris' / 'preferences.json'
prefs = json.loads(p.read_text()) if p.exists() else {}
prefs['world'] = 'the_watcher'
p.write_text(json.dumps(prefs))
" 2>/dev/null

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " 👁  Iris — dev launch"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Source:  $PROJECT"
echo " Note:    camera not available in source mode"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

PARALLAX_MODE=demo "$PROJECT/.venv/bin/python3" "$PROJECT/launcher.py"
