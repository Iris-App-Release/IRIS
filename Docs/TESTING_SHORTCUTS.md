# Testing Shortcuts Reference

All shortcuts are `.command` files that can be **double-clicked** from Finder for easy access.

## Desktop Shortcuts (Double-Click to Run)

### 1. **Toggle Wallpaper.command** ⚡
**What it does:** Toggle the entire wallpaper system on/off

**When to use:** 
- Quick on/off during testing
- See the real wallpaper by toggling off
- Toggle back on to test the parallax effect

**Output:**
```
Wallpaper is now ON/OFF
```

---

### 2. **Test Everything.command** 🚀
**What it does:** Start wallpaper + icons + show live status

**When to use:**
- Full system test
- Monitor real-time Earth state values
- Watch cam_x/cam_y/perspective changes as you move

**What you'll see:**
```
✓ Systems Running — Live Status [14:32:45]

Status:
  Wallpaper engine : ON    (live)
  Wallpaper proc   : RUNNING (pid 12345)
  Icons overlay    : ON    (orbital launchers visible)
  Icons proc       : RUNNING (pid 12346)

Earth State:
  cam_x: +0.35  cam_y: -0.12  perspective: 0.98
```

**Instructions:**
- Move head LEFT/RIGHT → watch cam_x change
- Move face FORWARD/BACK → watch perspective_scale change
- Open `/Applications/Orbital Apps/` and add an app
- Wait 1-2 seconds for detection

---

### 3. **Check Status.command** 📊
**What it does:** Show current system state without starting anything

**When to use:**
- Check if systems are already running
- View real-time head tracking values
- Verify app folder contents
- Get quick diagnostics

**Output includes:**
- Process IDs of running daemons
- Head position (cam_x, cam_y, cam_z)
- Earth position (world coordinates)
- Perspective scale value
- Apps in `/Applications/Orbital Apps/`
- Data freshness (is daemon alive?)

---

## Command-Line Tools

### Via Terminal

```bash
cd /Users/averychatten/Documents/ParallaxWall

# Start everything
./launch.command

# Toggle wallpaper on/off
parallaxctl toggle

# Start just icons overlay
parallaxctl icons start

# Stop everything
parallaxctl stop
parallaxctl icons stop

# View status
parallaxctl status

# Check logs
tail -f /tmp/parallaxwall.out.log      # Wallpaper daemon
tail -f /tmp/parallaxicons.out.log     # Icons overlay
```

---

## Real-Time Monitoring

### Watch Head Position (Live)
```bash
watch -n 0.5 'cat ~/.parallax_earth_state.json | python3 -m json.tool'
```
Updates every 0.5 seconds. Shows:
- `cam_x`: Head left/right tilt
- `cam_y`: Head up/down tilt
- `perspective_scale`: Face distance
- Freshness timestamp

### Watch Wallpaper Logs (Live)
```bash
tail -f /tmp/parallaxwall.out.log
```

### Watch Icons Overlay Logs (Live)
```bash
tail -f /tmp/parallaxicons.out.log | grep -E "app|orbit|app change"
```

---

## Testing Workflow

### Quick 5-Minute Test
1. Double-click **Test Everything.command**
2. Move head left/right (watch icons shift)
3. Move face forward/back (watch icons resize)
4. Press Ctrl-C to exit

### Full Feature Test
1. Double-click **Test Everything.command**
2. **Parallax Test:**
   - Move head right → icons should orbit around rightward point
   - Move head left → icons should orbit around leftward point
3. **Perspective Test:**
   - Move face forward → orbit expands
   - Move face backward → orbit shrinks
4. **App Folder Test:**
   - Open Finder → `/Applications/Orbital Apps/`
   - Drag an app into the folder
   - Wait 1-2 seconds
   - New icon should appear on wallpaper
   - Remove the app → icon disappears
5. **Toggle Test:**
   - Double-click **Toggle Wallpaper.command**
   - Wallpaper should turn off (real desktop shows)
   - Double-click again → wallpaper should return

### Live Monitoring During Test
Keep these open in separate terminal windows:

**Terminal 1:** Status updates
```bash
watch -n 1 'parallaxctl status'
```

**Terminal 2:** Head tracking values
```bash
watch -n 0.5 'cat ~/.parallax_earth_state.json | python3 -m json.tool'
```

**Terminal 3:** Icons log
```bash
tail -f /tmp/parallaxicons.out.log | grep -i "app\|orbit"
```

---

## Test Checklist

Run through these and mark complete:

### Startup
- [ ] Double-click **Test Everything.command**
- [ ] See "Systems Running" message
- [ ] Check status shows both daemon AND icons running
- [ ] Earth state file has values (not empty)

### Parallax Movement
- [ ] Tilt head RIGHT → icons shift RIGHT
- [ ] Tilt head LEFT → icons shift LEFT
- [ ] cam_x value changes in real-time JSON
- [ ] Shift is smooth (no jitter)
- [ ] Shift stops when head stops

### Perspective Scaling
- [ ] Move face FORWARD → orbit radius grows
- [ ] Move face BACKWARD → orbit radius shrinks
- [ ] perspective_scale value changes 0.7–1.3 range
- [ ] Scaling is smooth
- [ ] Icons don't go off-screen

### Orbital Apps Folder
- [ ] Folder `/Applications/Orbital Apps/` exists
- [ ] Add a test app (copy Safari to folder)
- [ ] Within 1-2 seconds, new icon appears
- [ ] Icon is clickable (launches app if clicked)
- [ ] Remove app from folder
- [ ] Icon disappears within 1-2 seconds

### Toggle Functionality
- [ ] Double-click **Toggle Wallpaper.command**
- [ ] Wallpaper turns OFF (real desktop visible)
- [ ] Icons overlay hidden
- [ ] Double-click again
- [ ] Wallpaper returns ON
- [ ] Icons reappear

### Graceful Degradation
- [ ] Double-click **Test Everything.command**
- [ ] Kill wallpaper: `parallaxctl stop`
- [ ] Icons should snap to center
- [ ] No crash or error
- [ ] Earth state file stops updating
- [ ] Restart wallpaper: `parallaxctl start`
- [ ] Icons resume parallax movement

---

## Troubleshooting from Shortcuts

### If Test Everything.command Hangs
```bash
# Kill all processes
parallaxctl stop
parallaxctl icons stop
pkill -f "main.py"

# Check what's running
pgrep -af "main.py\|icons_overlay"
```

### If Check Status Shows Offline
```bash
# Make sure daemon is actually running
./launch.command &

# Wait 3 seconds, then check status again
sleep 3 && ./Check\ Status.command
```

### If Parallax Movement Not Working
1. Run **Check Status.command**
2. Look at `cam_x` and `cam_y` values
3. Move your head slowly
4. If values don't change → head tracking may need permission grant
5. If values DO change → icons overlay might not be reading state properly

### If Folder Monitoring Not Working
```bash
# Check folder exists with correct name
ls -la /Applications/Orbital\ Apps/

# Check icons overlay is actually running
parallaxctl status | grep "Icons proc"

# Watch logs for detection messages
tail -f /tmp/parallaxicons.out.log | grep -i "app\|change"
```

---

## Pro Tips

**Keep Check Status open while testing:**
```bash
# In one terminal, keep refreshing status every 3 seconds
while true; do clear && ./Check\ Status.command 2>/dev/null | head -30 && sleep 3; done
```

**Monitor both logs simultaneously:**
```bash
# Split terminal and tail both logs
tail -f /tmp/parallaxwall.out.log &
tail -f /tmp/parallaxicons.out.log
```

**Create a live dashboard in a separate window:**
```bash
# macOS notification on app folder changes
while true; do
  count=$(find /Applications/Orbital\ Apps -maxdepth 1 -name "*.app" 2>/dev/null | wc -l)
  osascript -e "display notification \"$count apps in Orbital Apps folder\" with title \"Parallax Wall\""
  sleep 5
done
```

---

## Testing Complete! ✅

Once all checks pass:
1. Parallax movement works smoothly
2. Perspective scaling works
3. App folder monitoring works
4. Toggle functionality works
5. Graceful fallback works

**The implementation is production-ready!** 🚀
