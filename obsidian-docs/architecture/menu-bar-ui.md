---
title: Menu Bar UI — Desktop Mode Exit & Control
type: design-decision
related: [productification, demo-overlay, system-interactions, constraints, grid-api-customization]
last_updated: 2026-06-02
sources: [UI/demo_overlay.py, Launcher/app_engine.py, obsidian-docs/worlds/grid_room.md]
---

# Menu Bar UI — Desktop Mode Exit & Control

## Problem

When IRIS enters desktop/wallpaper mode, the demo window closes and the app runs as a click-through daemon. Users have **no visible way to exit back to the menu, toggle camera, or access settings** — they're "trapped" in the wallpaper experience.

## Solution: Menu Bar Icon + Quick Toggle Menu

**Approach:** A lightweight, always-visible macOS menu bar icon that provides:
- **Quick toggles:** Camera On/Off, Exit Desktop Mode, Disable Daemon
- **Full settings:** Link to a separate settings window (window-based, not modal)
- **State indication:** Icon appearance reflects current mode (demo vs. wallpaper)

### Why This Works for IRIS

1. **Native macOS pattern.** Familiar to users (Bartender, Dropzone, 1Blocker, etc.). Discoverable without documentation.
2. **Leverages existing IPC.** The daemon already polls `~/.iris/preferences.json` and flag files each frame. The menu bar app just *writes* those same files — no new communication layer.
3. **Non-intrusive.** Doesn't clutter the wallpaper or steal screen real estate.
4. **Always accessible.** Menu bar is persistent across all Spaces/desktops; doesn't break the immersion of the wallpaper.

## Architecture

### Multi-Process Pattern (Established)

IRIS already uses separate processes:
- `app_engine.py` — main render + wallpaper daemon
- `orbital_icons.py` — separate Cocoa app for icon launcher overlay

The menu bar app follows the same pattern:
- Lightweight Cocoa/PyObjC menu bar service
- Runs continuously in background
- Communicates via existing file-based IPC (`~/.iris/preferences.json`, `~/.parallax_off`, `~/.iris/camera_off`)

### File-Based IPC Contract

Menu bar app writes these files; daemon polls them:

| File | Effect | Menu Bar Action |
|---|---|---|
| `~/.parallax_off` | Pauses daemon, releases camera | "Exit Desktop Mode" |
| `~/.iris/camera_off` | Disables camera without pausing | "Camera Off" toggle |
| `~/.iris/preferences.json` | World selection, UI state | Full settings window |

No new socket/network layer — uses the stable, proven message bus.

## Menu Bar Contents (MVP)

```
┌─────────────────────────┐
│ 🌀 IRIS                 │
├─────────────────────────┤
│ 📷 Camera: On        [✓] │  ← toggle
│ 🖥️  Desktop Mode: On   [✓] │  ← toggle
│ ─────────────────────────│
│ ⚙️  Full Settings...      │  ← opens settings window
│ 📖 Help                   │
│ ⊗  Quit IRIS              │
└─────────────────────────┘
```

- **State indicators:** Checkmarks or colored dots show current state
- **One-click toggle:** No confirmation dialogs; changes take effect ~60ms (next frame poll)
- **Settings → separate window:** Not a menu; gives room for world selection, graphics tuning, etc.

## Exit Flow (Desktop Mode → Demo)

```
User clicks "Exit Desktop Mode" in menu bar
    ↓
Menu bar writes ~/.parallax_off
    ↓
Daemon detects flag (next frame ≤30ms)
    ↓
Engine shuts down camera, halts rendering loop
    ↓
[Option A] Auto-launch demo window
[Option B] Just close daemon; user reopens app
    ↓
Demo window opens with HUD → user can select new world, etc.
```

**Preference:** Option A (auto-relaunch demo) is more seamless, but requires a relaunch path. Option B requires explicit re-open.

## Icon Design

The menu bar icon should be **immediately recognizable** as IRIS:
- Minimal iris/eye glyph (matches app branding)
- Clear, scalable to ~16×16px (menu bar standard)
- Color/grayscale variants for light/dark mode
- State variant: dimmed when camera is off

**Example:** A simplified iris ring or parallax-grid glyph, not a generic gear.

## Relationship to Productification

This UI is **critical for shipping:**

| Milestone | Relevance |
|---|---|
| **Polished UX** ([[productification#user-experience]]) | Menu bar is the entry/exit path; removes "trapped" feeling. |
| **Robust permission flow** | Camera toggle in menu gives users explicit control visible in System Settings feedback. |
| **Developer ID signing** | Menu bar icon is per-bundle; must re-bundle menu bar app if BUNDLE_ID changes. |
| **Multi-world support** | Settings window in menu bar is where world selection lives; grid worlds can be customized here. |
| **Distribution checklist** | Menu bar must be signed with same Developer ID + re-signed post-plist edits, same as main app. |

## Implementation Notes

- **Cocoa or PyObjC?** PyObjC is lighter (reuse Python stack); Cocoa is more native. Either works.
- **Bundling:** Menu bar should ship as part of `Iris.dmg`, auto-installed alongside main app.
- **Permissions:** Menu bar needs macOS permissions for menu bar access (usually auto-granted).
- **Testing:** Must verify exit flow doesn't crash daemon; menu bar survives daemon restart.

## Next Steps

1. Design the icon (iris glyph, light/dark variants)
2. Prototype menu bar app (PyObjC or Cocoa)
3. Verify file-based IPC communication (write flags, watch daemon response)
4. Add auto-relaunch path to demo window post-exit
5. Test on a clean Mac (permission prompts, TCC persistence)
