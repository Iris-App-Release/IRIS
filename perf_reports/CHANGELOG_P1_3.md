# CHANGELOG_P1_3.md — State-File Write Guard

**Fix:** P1.3  
**File changed:** `Launcher/app_engine.py`  
**Lines added:** ~35 (consumer-check state + helper + conditional wrapper)  
**Risk:** Low — orbital_icons.py consumer unaffected when present

---

## Problem

`EARTH_STATE_FILE.write_text(json.dumps(state_data))` ran **30 times/second,
continuously, for the entire session**, serialising camera state for the separate
`orbital_icons.py` desktop-icon overlay process. Three problems:

1. **Written for ALL worlds**: Grid Room, Gem, and Watcher sessions never show
   the icons overlay, yet the write ran unconditionally.
2. **Written even when the overlay is absent**: Users without the decorative icon
   overlay installed paid 30 SSD writes/s for nothing.
3. **No consumer check**: The app had no way to know if anyone was reading the file.

## Change

The write is now gated by three conditions, all of which must be true:

```
world.show_icons                     — active world actually uses orbital icons
AND NOT ICONS_OFF_FLAG.exists()      — icons not explicitly disabled
AND _icons_consumer_present          — overlay process detected running (pgrep, 5s TTL)
```

A `_check_icons_consumer()` helper runs `pgrep -f orbital_icons` with a 5-second
cache interval so the process check costs negligible CPU.

```python
if world.show_icons and not ICONS_OFF_FLAG.exists():
    if now - _icons_consumer_last_check >= _ICONS_CONSUMER_CHECK_INTERVAL:
        _icons_consumer_present    = _check_icons_consumer()
        _icons_consumer_last_check = now
    if _icons_consumer_present and now - last_state_write >= (1.0 / 30.0):
        # … write …
```

---

## Before / After

| Scenario | Before | After |
|---|---|---|
| Grid Room / Gem / Watcher world | 30 writes/s | **0 writes/s** (`show_icons=False`) |
| Earth world, overlay absent | 30 writes/s | **0 writes/s** (pgrep → not found) |
| Earth world, overlay present | 30 writes/s | 30 writes/s (unchanged) |
| Icons disabled via flag | 30 writes/s | **0 writes/s** |

**Verified `show_icons` per world:**
- `earth`: `True` (may write if overlay present)
- `grid_room`: `False` (never writes)
- All non-Earth worlds: `False`

---

## Consumer compatibility

When the overlay IS running (Earth world, icons enabled, overlay process detected):
- Write cadence unchanged: ≤ 30 Hz, throttled as before.
- JSON schema unchanged: consumer reads the same keys (`hx`, `hy`, `hz`, `cam_*`,
  `t_s`, `win_half_h`, `timestamp_ms`).
- The 5-second consumer-check window means if the overlay starts mid-session it is
  detected within 5 s and writes begin.
- If the overlay stops, writes also stop within 5 s (next cache refresh).

No change to `orbital_icons.py` required.
