# Bifrost Configuration Guide

This document explains all configuration parameters in `bifrost_config.json` and their impact on mouse/keyboard behavior.

## Quick Start

Edit `server/bifrost_config.json` to adjust parameters. No code changes needed. Restart server for changes to take effect.

```bash
# Start server with config loaded
python server/main.py
```

---

## Mouse Configuration

### `mouse.hz` (Polling Rate)

**Default:** `50`  
**Unit:** Hz (events per second)  
**Equivalent:** `1000ms / hz` = delay between events

**Examples:**
- `hz=50` → 1 event every 20ms (PAL VBL rate, matches Amiga refresh)
- `hz=100` → 1 event every 10ms (faster, but more CPU load on Amiga)
- `hz=30` → 1 event every 33ms (slower, less responsive)

**Impact on Feel:**
- ⬆️ Higher = smoother movement, more responsive, more CPU load
- ⬇️ Lower = choppier, less responsive, lower CPU load

**When to adjust:**
- Responsive work (creative apps, file managers): increase to 75-100 Hz
- Slow Amiga or network lag: decrease to 30-40 Hz
- Standard use: leave at 50 Hz (validated on A6000)

### `mouse.hz_drag` (Polling Rate During Drag)

**Default:** `15`  
**Unit:** Hz (events per second when mouse button held)

**Why separate from `hz`?**

This is an **optimization for AmigaOS apps that use MCP (Move/Copy/Paste) opaque window** — a full-screen outline that redraws with each mouse event during drag.

**Important:** This only matters if the app draws an **opaque drag outline**. If an app uses:
- Transparent drag (follow cursor without outline)
- No visual drag feedback
- Custom drag mechanism (not MCP opaque)

Then `hz_drag` should match `hz` — lowering it provides **no benefit** and only makes drag feel sluggish.

**For MCP opaque apps (Workbench, file managers):**
On an A6000, full-screen redraws at 50 Hz during drag can cause lag. Lowering `hz_drag` reduces redraw cost while maintaining smooth movement.

**How it works:**
When left or right mouse button is held, send events at `hz_drag` rate instead of normal `hz`. When button released, resume normal rate.

**Impact:**
- `hz_drag=15` (default for MCP): smooth drag without lag on A6000
- `hz_drag=50`: matches `hz` → responsive but MCP apps may lag/flicker
- `hz_drag=5`: minimal Amiga load but sluggish drag

**When to adjust:**
- Using mostly MCP opaque apps (Workbench, file managers): 12-15 (default)
- Mix of transparent & opaque drag: 20-30
- Transparent drag only: set equal to `hz` (e.g., both 50)
- Minimal Amiga resources: 8-12

### `mouse.speed` (Input Multiplier)

**Default:** `1`  
**Range:** 0.5 - 5.0

**What it does:** Multiplies all mouse deltas by this factor.

**Examples:**
- `speed=1.0` → No scaling (1px from PC = 1px to Amiga)
- `speed=2.0` → Double sensitivity (1px from PC = 2px to Amiga)
- `speed=0.5` → Half sensitivity (2px from PC = 1px to Amiga)

**Note:** Windows input is raw (no OS acceleration). This multiplier compensates if movement feels too slow.

**When to adjust:**
- Mouse feels sluggish: increase to 1.5-2.0
- Mouse feels too fast: decrease to 0.5-0.8
- Default works for most: leave at 1.0

### `mouse.delta_max` (Startup Glitch Filter)

**Default:** `80`  
**Unit:** Pixels

**What it does:** Discards any single mouse delta larger than this value.

**Why needed:** Startup glitches or mode switches can produce impossible deltas (e.g., 500px jump). These break immersion.

**When to adjust:**
- VR/trackball users: increase to 150-200
- Normal mouse: leave at 80
- Fast erratic mouse: increase to 120

---

## Acceleration Curve

AmigaOS needs **predictable** mouse acceleration, not Windows' aggressive ramping. Bifrost uses a **piecewise-linear** curve:

```
|d| ≤ CURVE_LINEAR  →  output = |d|
|d| >  CURVE_LINEAR  →  output = CURVE_LINEAR + (|d| - CURVE_LINEAR) × CURVE_RATIO
```

### `curve.linear` (Precision Threshold)

**Default:** `2.0`  
**Unit:** Pixels (input delta)

**What it does:** Deltas up to this size are sent unchanged (1:1). Above this, compression begins.

**Examples:**
- `linear=2.0` (default): 1→1, 2→2, 3→2.5, 4→3, 10→6
- `linear=1.0`: 1→1, 2→1.5, 3→2, 10→5.5 (less precise)
- `linear=4.0`: 1→1, 2→2, 3→3, 4→4, 5→4.5 (more precision, less acceleration)

**Impact:**
- ⬆️ Higher = more precise small movements, less acceleration
- ⬇️ Lower = faster acceleration, less precision in small movements

**When to adjust:**
- Pixel art/precise work: increase to 3.0-4.0
- General use (file browsing, editing): 2.0 (default)
- Quick, coarse movements: 1.0-1.5

### `curve.ratio` (Compression Above Threshold)

**Default:** `0.5`  
**Range:** 0.0 - 1.0

**What it does:** Controls how much to compress deltas above the linear threshold.

**Examples:**
- `ratio=0.5` (default): 50% compression above threshold
- `ratio=1.0`: No compression (linear acceleration)
- `ratio=0.3`: Heavy compression (70% reduction)

**Examples with linear=2.0:**
- `ratio=0.5`: 10px → 6px, 20px → 11px (smooth ramping)
- `ratio=1.0`: 10px → 10px, 20px → 20px (no ramping)
- `ratio=0.2`: 10px → 3.6px, 20px → 5.6px (very compressed)

**Impact:**
- ⬆️ Higher = more linear, less acceleration
- ⬇️ Lower = more aggressive acceleration

**When to adjust:**
- Standard GUI use: 0.5 (default)
- Gaming (faster swing): 0.3-0.4
- Precision work (less acceleration): 0.7-1.0

---

## Keyboard Configuration

### `keys.toggle` (Focus Toggle Key)

**Default:** `"scroll_lock"`  
**Supported:** `scroll_lock`, `pause`, `esc`, `tab`, `backspace`, `enter`

**What it does:** Pressing this key switches focus between PC and Amiga.

**Impact:**
- PC mode → Amiga mode: Input captured, sent to Amiga, suppressed on PC
- Amiga mode → PC mode: Input returns to PC, mouse/keyboard stop forwarding

**When to adjust:**
- Prefer Pause key: `"pause"`
- Prefer Escape: `"esc"`
- Add support for other keys: Edit the `_KEY_MAP` dict in `capture.py`

### `keys.emergency` (Emergency Return Key)

**Default:** `"pause"`

**What it does:** If stuck in Amiga mode, press this to force return to PC.

**Note:** This works even if other input is stuck or suppressed (pynput emergency handler).

**Supported values:** `scroll_lock`, `pause`, `esc`, `tab`, `backspace`, `enter`

**When to adjust:**
- Use different key: `"esc"`

**Note:** Can't be disabled or set equal to `keys.toggle` — an invalid value, or a collision with `keys.toggle`, falls back to a safe default with a console warning.

### `keys.kill_modifier` (Kill-Server Modifier)

**Default:** `"ctrl"`  
**Supported values:** `ctrl`, `shift`, `alt`

**What it does:** Holding this modifier while pressing the emergency key (e.g. Ctrl+Pause) force-quits the server instead of just returning focus to PC.

**When to adjust:**
- Prefer Shift instead of Ctrl: `"shift"`
- An invalid value falls back to `"ctrl"` with a console warning.

---

## Debug Configuration

### `debug.enabled` (Console Output)

**Default:** `true`  
**Options:** `true` or `false`

**What it does:** Print mouse/keyboard events to console as they happen.

**Example output:**
```
Mouse delta: dx=5, dy=-3, qualifiers=0x00
Key press: code=68, qualifier=SHIFT
Wheel: UP
```

**When to adjust:**
- Development/troubleshooting: `true`
- Production/silent mode: `false`

### `debug.print_events` (Event Details)

**Default:** `true`

**What it does:** When `enabled=true`, print detailed event info (currently same as `enabled`).

---

## Network Configuration

**Not set via `bifrost_config.json`.** TCP/UDP ports are set via command-line flags on `server/main.py`, not the JSON config file:

```bash
python server/main.py --port 9999
```

- TCP port defaults to 7890 (`--port`)
- UDP discovery port is always TCP port + 1 (automatic, not separately configurable)
- If you change the port, remember to also pass it to the Amiga client: `Bifrost 9999`

**When to adjust:**
- Network conflicts (another service on 7890): pass `--port 9999`
- Firewall rules: adjust to match your policy
- USB FTDI bridge: may need different ports (untested)

---

## Configuration Profiles

### Standard Production (A6000 Validated)
```json
{
  "mouse": {"hz": 50, "hz_drag": 15, "speed": 1, "delta_max": 80},
  "curve": {"linear": 2.0, "ratio": 0.5},
  "debug": {"enabled": false}
}
```

### Responsive Work (File Managers, Creative Apps)
```json
{
  "mouse": {"hz": 75, "hz_drag": 20, "speed": 1, "delta_max": 80},
  "curve": {"linear": 2.0, "ratio": 0.5},
  "debug": {"enabled": false}
}
```

### Precision Work (Pixel Art, Graphics)
```json
{
  "mouse": {"hz": 75, "hz_drag": 20, "speed": 0.8, "delta_max": 60},
  "curve": {"linear": 4.0, "ratio": 0.8},
  "debug": {"enabled": false}
}
```

### Slow Amiga / High Latency
```json
{
  "mouse": {"hz": 30, "hz_drag": 10, "speed": 1, "delta_max": 60},
  "curve": {"linear": 2.0, "ratio": 0.5},
  "debug": {"enabled": true}
}
```

---

## Troubleshooting via Configuration

| Problem | Adjustment |
|---------|------------|
| Mouse feels sluggish | Increase `hz` or `speed` |
| Mouse feels jerky/choppy | Increase `hz` to smooth transitions |
| Drag operations lag/flicker | Decrease `hz_drag` to 10-12 |
| Can't hit small targets | Increase `curve.linear` to 3.0-4.0 |
| Overshoots too much | Decrease `curve.ratio` to 0.3-0.4 |
| Startup jumps/glitches | Increase `delta_max` to 120-150 |
| Amiga overloaded / CPU max | Decrease `hz` and `hz_drag` by 10-15 each |
| Console too noisy | Set `debug.enabled=false` |

---

## Testing Your Config

1. **Edit** `bifrost_config.json`
2. **Restart** `python server/main.py`
3. **Watch console** for config load message
4. **Test for 2-3 minutes** to feel the change
5. **Adjust if needed** and repeat

Changes take effect immediately after restart (no recompile needed).

---

## Questions?

- Check `README.md` for usage examples
- Review `capture.py` comments for implementation details
- Test profiles above as starting points
