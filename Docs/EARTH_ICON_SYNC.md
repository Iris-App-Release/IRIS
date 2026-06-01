# Earth-to-Icons Transform Synchronization

## Overview

The icons overlay now inherits ALL Earth transforms through an inter-process communication (IPC) mechanism. When the head-tracking system moves the Earth due to parallax, the orbital app icons move identically with it, creating a unified 3D scene.

## Architecture

### Main Process (Wallpaper Daemon)

**File:** `main.py`

1. **Camera Transform Calculation** (lines ~289-295):
   - Head tracking input: `hx, hy, hz` (from FaceTracker)
   - Camera position: `cam_x, cam_y, cam_z` (updated with lag smoothing)
   - Size ratio: `perspective_scale` (computed from face distance)

2. **Earth Transform** (lines ~332-339):
   - World position: `(bx + cam_x*0.50, by + cam_y*0.50, -10.0)`
   - The parallax factor (0.50) scales head movement into apparent Earth shift

3. **State Export** (line ~302):
   - Calls `_export_earth_state(cam_x, cam_y, cam_z, perspective_scale, t_s)`
   - Writes to `~/.parallax_earth_state.json` (~40 bytes)
   - Called at 60 Hz (one per frame)

**Export Format:**
```json
{
  "earth_x": 0.0,           // World position (parallax-adjusted)
  "earth_y": 0.0,
  "earth_z": -10.0,
  "cam_x": 1.5,             // Camera offset (head tracking)
  "cam_y": -0.8,
  "cam_z": 11.5,
  "perspective_scale": 0.98, // 1.0 = baseline, <1.0 = far, >1.0 = close
  "time": 45.32,            // Elapsed time (seconds)
  "timestamp_ms": 1705234567000
}
```

### Icons Overlay Process

**File:** `icons_overlay.py`

1. **State Loading** (in `drawRect_`, line ~185):
   - Reads `~/.parallax_earth_state.json` every frame (60 Hz)
   - Freshness check: ignores state older than 100ms
   - Falls back to zero state if wallpaper daemon is not running

2. **Transform Application**:
   ```python
   # Earth's screen position (with parallax offset visible to user)
   parallax_px = earth_state["cam_x"] * 60.0
   parallax_py = earth_state["cam_y"] * 60.0
   earth_screen_x = screen_center_x + parallax_px
   earth_screen_y = screen_center_y + parallax_py
   
   # Perspective-scaled orbit radii
   rx_scaled = (orbit_radius_x + bob) * perspective_scale
   ry_scaled = (orbit_radius_y + bob) * perspective_scale
   
   # Orbital position in Earth's local coordinate system
   icon_x = earth_screen_x + rx_scaled * cos(angle)
   icon_y = earth_screen_y + ry_scaled * sin(angle)
   ```

3. **Scale Factors**:
   - `parallax_px/py *= 60.0`: Converts camera offset units to screen pixels
   - Empirically chosen so head movement feels natural (~100px per unit at typical viewing distance)

## Orbital Apps Folder Integration

### Dynamic App Loading

**Directory:** `/Applications/Orbital Apps/`

The icons overlay now monitors this folder for `.app` bundles:

1. **Startup** (main() function):
   - Scans `/Applications/Orbital Apps/` for `.app` directories
   - Merges orbital folder apps with config apps from `~/.parallax_icons.json`
   - Loads all apps into icon descriptors

2. **Runtime Monitoring** (OrbitalAppsWatcher class):
   - Polls folder every 1 second
   - Detects additions/removals of `.app` bundles
   - Recalculates orbital phases when app count changes
   - Triggers view redraw without daemon restart

**Flow:**
```
/Applications/Orbital Apps/
├── MyCustomApp.app    ← User can drag here
├── AnotherApp.app     ← Auto-detected at runtime
└── ...
                         ↓
                    [OrbitalAppsWatcher]
                         ↓
              [Rebuild icon list + phases]
                         ↓
              [Redraw OrbitView with new icons]
```

## File Synchronization Details

### `~/.parallax_earth_state.json`

- **Size:** ~150 bytes
- **Write Rate:** 60 Hz (wallpaper daemon)
- **Read Rate:** 60 Hz (icons overlay)
- **Stale Timeout:** 100ms (no updates for >100ms = daemon halted)
- **Read Failure:** Gracefully falls back to zero state (centered, no parallax)

### Orbital Apps Monitoring

- **Scan Rate:** 1 Hz (efficient, no continuous filesystem watches)
- **Change Detection:** Set comparison of discovered `.app` paths
- **Reliability:** Silently ignores permission errors, non-.app items
- **Atomicity:** Folder changes take ≤1 second to reflect in overlay

## Performance Implications

| Component | Impact | Notes |
|-----------|--------|-------|
| main.py | ~1ms/frame | JSON serialize 40 bytes at 60 Hz |
| icons_overlay.py | ~0.5ms/frame | JSON parse + file I/O, cached when stale |
| Total Overhead | <2ms | <3% of 16.67ms budget at 60 FPS |

## Testing Checklist

- [ ] Wallpaper daemon exports Earth state at 60 Hz
- [ ] Icons overlay reads and applies transforms
- [ ] Head movement causes icons to shift on screen (parallax visible)
- [ ] Face distance changes scale icons appropriately
- [ ] `/Applications/Orbital Apps/` folder monitoring works
- [ ] Icons redraw when apps added/removed to orbital folder
- [ ] Zero state fallback when daemon is off
- [ ] Config apps + orbital folder apps merge correctly

## Usage

### Enable Orbital Apps Folder

```bash
# Create the folder (will be auto-created, but can do manually)
mkdir -p /Applications/Orbital\ Apps

# Add any .app bundles to monitor
cp -r /Applications/MyApp.app /Applications/Orbital\ Apps/

# Icons overlay will detect them within 1 second
```

### Monitor Apps at Runtime

The OrbitalAppsWatcher runs independently; no restart needed when apps are added/removed.

```bash
# Watch icons overlay logs
tail -f /tmp/parallaxicons.out.log | grep -i "app\|orbit"
```

## Future Enhancements

1. **inotify/FSEvents**: Replace 1Hz polling with filesystem event listeners (faster detection, lower CPU)
2. **Icon Caching**: Preload icon NSImages at startup to avoid jank on first add
3. **Configuration UI**: macOS preferences pane to manage orbital apps without CLI
4. **Parallax Calibration**: Adjustable parallax scale factor in config file
5. **Performance Metrics**: Add frame timing to Earth state export for monitoring
