# Bifrost Configuration Guide

This document explains all configuration parameters in `bifrost_config.json` and their impact on mouse/keyboard behavior.

## Quick Start

Copy `server/bifrost_config.default.json` to `server/bifrost_config.json` (gitignored - your personal copy, never committed) and edit it to adjust parameters. No code changes needed. Restart server for changes to take effect. The file is entirely optional - without it, the server runs with the same built-in defaults shown below.

```bash
# Start server with config loaded
python server/main.py
```

---

## Mouse Configuration

Mouse tuning (`hz`, `hz_drag`, `speed`, `delta_max`, acceleration curve
`linear`/`ratio`) is owned by the Amiga daemon, not `bifrost_config.json` -
set it on the Amiga side via CLI arguments (`Bifrost HZ=75 SPEED=15`) and
it's transmitted to the PC automatically over the wire. Run `Bifrost ?` on
the Amiga for the full list of arguments and their defaults. See
`docs/PROTOCOL.md`'s `PKT_HELLO` section for the wire format.

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

### `keys.right_amiga` (Right Amiga Key Source)

**Default:** `"windows"`  
**Supported values:** `windows`, `ctrl`

**What it does:** Chooses which PC key sends the Amiga's Right Amiga key.

- `"windows"` (default): Right Windows key (Right Cmd on Mac/Linux)
- `"ctrl"`: Right Ctrl key instead

**Note:** Left Amiga is fixed to Left Windows (Left Cmd) and isn't configurable. Right Amiga has no consistent PC/Mac equivalent, hence the option. An invalid value falls back to `"windows"` with a console warning.

**Known limitation:** Holding Left/Right Amiga as a modifier for AmigaOS shortcuts (e.g. Amiga+M) isn't wired up yet — only the key press/release itself is forwarded, not the qualifier bit AmigaOS shortcuts check for. See [ROADMAP.md](../ROADMAP.md) Phase 2.1.

---

## Debug Configuration

### `debug.enabled` (Console Output)

**Default:** `true`  
**Options:** `true` or `false`

**What it does:** Master switch for console logging. When `false`, `log_mouse`/`log_keys` below have no effect - nothing is printed.

**When to adjust:**
- Development/troubleshooting: `true`
- Production/silent mode: `false`

### `debug.log_mouse` (Mouse Motion)

**Default:** `false`

**What it does:** Print every mouse delta/discard event (`[mouse] ...` lines). High-frequency - one line per flush tick while the mouse is moving. Off by default so it doesn't drown out other console output; turn on only when debugging mouse acceleration/edge-trigger issues.

**Example output:**
```
[mouse] SENT dx=+5 dy=-3  (raw_pc dx=5 dy=-3  rem=0.20,-0.10)
```

### `debug.log_keys` (Key Sends)

**Default:** `true`

**What it does:** Print every key event actually sent to the Amiga (`[key] ...` lines) - key, Amiga rawkey code, and qualifier byte. Low-frequency; left on by default since it's the primary tool for diagnosing keymap/qualifier issues.

**Example output:**
```
[key] DOWN  key=<65: 'a'>          code=0x20 qual=0x00
[key] UP    key=Key.cmd_r          code=0x67 qual=0x00
```

---

## Network Configuration

### `network.port` (TCP Port)

**Default:** `7890`

**What it does:** Sets the TCP port the server listens on. This is the persistent way to change the port — useful since the server is normally launched automatically at PC boot, where passing a CLI flag each time isn't practical.

```json
{
  "network": {
    "port": 9999
  }
}
```

- `--port` on the command line always overrides `network.port`, for one-off runs without touching the config
- Invalid values (not an integer, or outside 1-65535) fall back to 7890 with a console warning
- UDP discovery port is fixed (7891), independent of the TCP port - it stays reachable no matter what TCP port you pick
- The Amiga auto-detects whatever TCP port you set here via discovery - no need to pass it on the Amiga CLI too (see `docs/PROTOCOL.md`'s Discovery section)

**When to adjust:**
- Network conflicts (another service on 7890): pass `--port 9999`
- Firewall rules: adjust to match your policy
- USB FTDI bridge: may need different ports (untested)

---

## Troubleshooting via Configuration

| Problem | Adjustment |
|---------|------------|
| Mouse feels sluggish | Increase Amiga's `HZ=`/`SPEED=` CLI args |
| Mouse feels jerky/choppy | Increase Amiga's `HZ=` CLI arg to smooth transitions |
| Drag operations lag/flicker | Decrease Amiga's `HZDRAG=` CLI arg to 10-12 |
| Can't hit small targets | Increase Amiga's `CURVELINEAR=` CLI arg to 30-40 (3.0-4.0) |
| Overshoots too much | Decrease Amiga's `CURVERATIO=` CLI arg to 3-4 (0.3-0.4) |
| Startup jumps/glitches | Increase Amiga's `DELTAMAX=` CLI arg to 120-150 |
| Amiga overloaded / CPU max | Decrease Amiga's `HZ=`/`HZDRAG=` CLI args by 10-15 each |
| Console too noisy from mouse spam | Set `debug.log_mouse=false` (default) |
| Console too noisy entirely | Set `debug.enabled=false` |

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
- Run `Bifrost ?` on the Amiga for mouse-tuning CLI arguments and defaults
