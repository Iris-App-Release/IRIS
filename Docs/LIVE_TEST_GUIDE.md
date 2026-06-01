# Live Testing Guide: Earth-to-Icons Synchronization

## Quick Start Test (5 minutes)

### Prerequisites
```bash
cd /Users/averychatten/Documents/ParallaxWall

# Ensure folder exists
mkdir -p /Applications/Orbital\ Apps

# Check recent logs are clear
rm -f /tmp/parallaxwall.*.log /tmp/parallaxicons.*.log
```

### Step 1: Start the Wallpaper Daemon
```bash
./launch.command
```

**Expected output:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Parallax Wall
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Python: 3.11.x at /opt/homebrew/bin/python3.11
  Dependencies installed.
  Launching…

[main] window 2880×1800  GL drawable ...
[main] GL_VERSION  = OpenGL 2.1 Metal
[main] Loaded N apps: M from config + 0 from orbital folder
[main] Engine resumed
[icons] Overlay running on 2880×1800
```

Let this run for 5 seconds.

### Step 2: Verify Earth State Export

```bash
# In a new terminal:
cat ~/.parallax_earth_state.json | python3 -m json.tool
```

**Expected output** (updates every 1-2 seconds):
```json
{
  "earth_x": 0.5,
  "earth_y": -0.2,
  "earth_z": -10.0,
  "cam_x": 1.5,
  "cam_y": -0.4,
  "cam_z": 11.2,
  "perspective_scale": 1.02,
  "time": 3.45,
  "timestamp_ms": 1705234567890
}
```

✓ **Check:** File exists and updates in real time

### Step 3: Monitor Icons Overlay Startup

```bash
# In a new terminal (while wallpaper is running):
parallaxctl icons start
```

**Expected output:**
```
  ✓ Icons overlay started (pid 12345)  — logs at /tmp/parallaxicons.out.log
```

Check the log:
```bash
tail -f /tmp/parallaxicons.out.log
```

**Expected output:**
```
[icons] Requesting camera permission…
[icons] Camera permission: granted
[icons] Engine selected: MediaPipe FaceLandmarker
[icons] Loaded 10 apps: 10 from config + 0 from orbital folder
[icons] Overlay running on 2880×1800
[icons] Config file       : ~/.parallax_icons.json
[icons] Toggle flag       : ~/.parallax_icons_off
[icons] Press Ctrl-C to quit.
```

### Step 4: Test Parallax Movement

**Head movement test:**
1. Slowly tilt head to the **right**
2. Watch the orbital icons on wallpaper
3. **Expected:** Icons orbit around a point shifted to the **right**
4. Repeat tilting **left**
5. **Expected:** Icons orbit around a point shifted to the **left**

**Face distance test:**
1. Move face **forward** toward screen
2. **Expected:** Icons orbit expands (larger radius)
3. Move face **backward** away from screen  
4. **Expected:** Icons orbit shrinks (smaller radius)

### Step 5: Test Orbital Apps Folder

```bash
# In a new terminal:
echo "Testing orbital apps folder monitoring..."

# Add an app (copy an existing one for testing)
cp -r /Applications/Safari.app /Applications/Orbital\ Apps/Safari-Test.app

# Wait 1-2 seconds and check logs
tail -f /tmp/parallaxicons.out.log | grep -i "app\|orbit"
```

**Expected output** (within 1 second):
```
[icons] Detected app change — now tracking 11 apps
```

Check that a new icon appeared on the wallpaper. This confirms dynamic app detection.

```bash
# Remove the test app
rm -rf /Applications/Orbital\ Apps/Safari-Test.app

# Wait 1-2 seconds
```

**Expected output:**
```
[icons] Detected app change — now tracking 10 apps
```

## Detailed Test Scenarios

### Scenario A: Parallax Coherence Verification

**Objective:** Verify icons move with Earth due to head tracking

**Steps:**
1. Start both daemon and icons overlay
2. Position face centered, looking at screen
3. Note orbital icon positions (should be centered)
4. Slowly move head to the right (~3 inches)
5. Observe orbital icons shift right
6. Note: icons should stay the same **distance** from each other
7. Measure shift distance (should be ~60-120 pixels at normal head movement)

**Pass Criteria:**
- ✓ Icons shift consistently with head movement
- ✓ Shift stops when head stops moving
- ✓ Shift reverses when moving back
- ✓ No lag (should be <50ms delayed from head position)
- ✓ Icons maintain fixed relative distances

### Scenario B: Perspective Scaling Verification

**Objective:** Verify perspective_scale affects icon orbit size

**Steps:**
1. Position face at normal viewing distance (~24 inches)
2. Measure apparent orbit radius with virtual ruler or grid
3. Move face forward to ~12 inches
4. Observe orbit radius should grow (~10-20%)
5. Move back to ~36 inches
6. Observe orbit radius should shrink

**Pass Criteria:**
- ✓ Orbit visibly larger when face is close
- ✓ Orbit visibly smaller when face is far
- ✓ Scaling is smooth (no jittery jumps)
- ✓ Icons don't disappear off-screen

### Scenario C: Stale State Fallback

**Objective:** Verify icons gracefully handle daemon being offline

**Steps:**
1. Start wallpaper daemon and icons overlay
2. Confirm icons are visible and moving
3. Kill wallpaper daemon: `parallaxctl stop`
4. Observe icons for 2 seconds
5. **Expected:** Icons should snap to center screen and stop moving

**Pass Criteria:**
- ✓ Icons don't crash when Earth state file is not updated
- ✓ Icons snap to zero state (center) without flickering
- ✓ Overlay remains visible and responsive

### Scenario D: Folder Monitoring Under Load

**Objective:** Verify app folder detection works with many apps

**Steps:**
1. Create 10 test apps in orbital folder:
   ```bash
   for i in {1..10}; do
     mkdir -p /Applications/Orbital\ Apps/TestApp$i.app/Contents
   done
   ```
2. Monitor overlay logs: `tail -f /tmp/parallaxicons.out.log | grep "app"`
3. Add one more app
4. Verify detection happens within 1-2 seconds
5. Remove all test apps

**Pass Criteria:**
- ✓ Detects multiple apps at startup
- ✓ Detects additions without restart
- ✓ Correctly counts new app count
- ✓ Redraw happens without lag

### Scenario E: Config + Orbital Merge

**Objective:** Verify config and orbital apps are properly merged

**Steps:**
1. Check default config: `cat ~/.parallax_icons.json`
   - Should have ~10 apps
2. Add 3 apps to `/Applications/Orbital Apps/`
3. Restart icons overlay: `parallaxctl icons restart`
4. Check logs for message
5. **Expected:** Total should be 13 (10 + 3)

**Pass Criteria:**
- ✓ Config apps appear first in orbit
- ✓ Orbital folder apps appear next
- ✓ No duplicates if same app in both
- ✓ Total count is sum (minus duplicates)

## Performance & Latency Tests

### Test F: Frame Rate Impact

**Objective:** Verify <2ms overhead per frame

**Tools needed:**
- Wallpaper logs with timing data

**Steps:**
1. Start daemon with performance monitoring enabled
2. Run for 30 seconds and capture frame times
3. Calculate CPU time for Earth export

**Expected results:**
- Overhead: <2ms per frame
- JSON write: <0.5ms
- No visible frame drops due to I/O

### Test G: File I/O Stress

**Objective:** Verify robust handling of concurrent reads/writes

**Steps:**
1. Create a script that reads Earth state file rapidly:
   ```bash
   while true; do
     cat ~/.parallax_earth_state.json >/dev/null
     usleep 10000  # 10ms
   done
   ```
2. Run this in background
3. Verify no crashes or corruption

**Expected results:**
- ✓ No file corruption
- ✓ Both daemon and icons continue smoothly
- ✓ Partial reads handled gracefully

## Troubleshooting

### Issue: Earth state file not created

**Symptom:** `~/.parallax_earth_state.json` doesn't exist after starting daemon

**Diagnosis:**
```bash
# Check if daemon is running
pgrep -f main.py | head -1

# Check daemon logs
tail -20 /tmp/parallaxwall.out.log
```

**Solution:**
1. Check main.py syntax: `python3 -m py_compile main.py`
2. Verify _export_earth_state is called
3. Check file permissions on home directory

### Issue: Icons not moving with head

**Symptom:** Icons stay in center, don't shift when head moves

**Diagnosis:**
```bash
# Monitor Earth state updates
watch -n 0.1 'cat ~/.parallax_earth_state.json | python3 -m json.tool'

# Check if cam_x and cam_y are changing
```

**Solution:**
1. Verify wallpaper daemon is actually running: `parallaxctl status`
2. Check that head tracking is enabled
3. Verify icons_overlay is reading from correct file path
4. Check parallax_px calculation: should be cam_x * 60.0

### Issue: Orbital apps folder monitoring not working

**Symptom:** Adding apps to /Applications/Orbital Apps/ has no effect

**Diagnosis:**
```bash
# Check folder exists
ls -la /Applications/Orbital\ Apps/

# Monitor watcher logs
tail -f /tmp/parallaxicons.out.log | grep -i "app\|orbit\|change"
```

**Solution:**
1. Verify folder is `/Applications/Orbital Apps/` (exact name)
2. Verify apps are `.app` bundles (not generic directories)
3. Check for permission errors on folder
4. Restart icons overlay: `parallaxctl icons restart`

## Acceptance Criteria

All of the following must pass:

- [ ] Earth state file exports at 60 Hz from wallpaper daemon
- [ ] Icons overlay reads state and applies transforms
- [ ] Head movement causes visible icon shift on screen
- [ ] Shift magnitude is proportional to head tilt angle
- [ ] Face distance changes icon orbit size appropriately
- [ ] Zero state fallback works when daemon stops
- [ ] /Applications/Orbital Apps/ folder monitoring detects additions
- [ ] /Applications/Orbital Apps/ folder monitoring detects removals
- [ ] App count updates within 1-2 seconds of folder change
- [ ] No visual jitter or frame drops during normal use
- [ ] Config + orbital apps merge correctly (no duplicates)
- [ ] All test scenarios A-G pass without errors

## Final Sign-Off

Once all criteria pass, the implementation is complete and ready for production use.

**Test completed by:** ________________
**Date:** ________________
**Notes:** 
```
____________________________________________________________________
____________________________________________________________________
```
