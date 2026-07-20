# Bifrost

**Remote Mouse & Keyboard Gateway for Vampire V4 / AmigaOS**

Bifrost enables seamless mouse and keyboard forwarding from a PC to a Vampire V4 Amiga over TCP/IP. Control your Amiga remotely with smooth, low-latency input using a piecewise-linear acceleration curve and sub-pixel precision. Includes toggle switching to alternate between PC and Amiga input control.

## Features

### Core Features ✅

✅ **Remote Input Forwarding** - Real-time mouse and keyboard events from PC to Amiga  
✅ **Smooth Mouse Movement** - Piecewise-linear acceleration curve (sub-pixel accumulation)  
✅ **Low-Latency Streaming** - TCP_NODELAY for immediate packet delivery (~10ms intervals)  
✅ **Keyboard Support** - Full keyboard forwarding with toggle capability  
✅ **Input Toggle** - Scroll Lock or screen corner tap to switch PC ↔ Amiga control  
✅ **Edge Detection** - Optional screen edge wrapping and boundary handling  
✅ **Configurable Acceleration** - Curve linear ratio and mouse polling rate (MOUSE_HZ)  
✅ **Sub-Pixel Precision** - Float accumulator prevents input loss between flushes  
✅ **Multi-CPU Support** - Builds for 68020+ (optimized for SAGA hardware)  
✅ **Python Server** - Cross-platform PC side daemon (Windows/Linux/macOS)  

### Upcoming Features 🔜

Phase 2 (v0.4): Special key mapping, runtime arguments (STATUS/STOP)  
Phase 3 (v0.5): Bidirectional control (Amiga→PC reverse channel)  
Phase 4 (v0.6): Keymap remapping, per-app/screen profiles  
Phase 5 (v0.7): MUI preferences editor (Amiga), Python GUI (PC)  
Phase 6 (v0.8): Security (TLS, authentication), full bidirectional control  

**See [ROADMAP.md](ROADMAP.md) for detailed phases and architecture.**

## Architecture

Bifrost uses a **client-server architecture**:

### PC Side (Server)
- **Python daemon** (`server/capture.py`)
- Captures PC mouse and keyboard input
- Applies acceleration curve
- Sends events via TCP/IP to Amiga

### Amiga Side (Client)
- **Device driver** (Bifrost for AmigaOS)
- Receives mouse/keyboard events
- Injects into Amiga input stream via `input.device`
- Supports toggle for input control switching

## System Requirements

### PC (Server)
- **Python 3.8+**
- Windows, Linux, or macOS
- Network connectivity to Amiga (Ethernet or USB FTDI adapter)

### Amiga (Client)
- **Vampire V4** (with SAGA hardware) — 68080 CPU
- AmigaOS 3.2+
- Network connectivity to PC

## Testing & Validation

**All tests and validation performed on:**
- **Hardware**: Apollo Computer Vampire V4 (68080 SAGA)
- **Model**: A6000 (Amiga 600 accelerator board)
- **Configuration**: 50 Hz polling, CURVE_LINEAR=2.0, CURVE_RATIO=0.5

**Validated features** (v0.3):
- ✅ Smooth mouse movement with sub-pixel accumulation
- ✅ Keyboard input forwarding
- ✅ Edge-triggered focus switching (screen corners)
- ✅ Low-latency TCP/IP with UDP auto-discovery
- ✅ Acceleration curve responsiveness

**Note:** Other Vampire versions (V2, V1) or non-accelerated Amigas may have different performance characteristics. Adjust `MOUSE_HZ` and `MOUSE_HZ_DRAG` based on your hardware's capabilities.

## Installation

### 1. PC Side Setup (First)

Start the server first — Amiga will auto-discover it.

```bash
# Install Python dependencies
pip install -r server/requirements.txt

# Launch server daemon
python server/capture.py
```

The server will listen for UDP discovery broadcasts on port 7891 (TCP 7890 + 1).

### 2. Amiga Side Setup

```bash
# Copy Bifrost to desired location (or SYS:)
Copy Bifrost to SYS:
Copy Bifrost.info to SYS:  # Optional icon

# Launch - server is auto-discovered, no IP needed
Bifrost
```

### 3. Network Configuration

Ensure PC and Amiga are on the same network:
- **Ethernet** ✅ (simplest, auto-discovery works)
- **USB FTDI** ⚠️ (serial→TCP bridge — untested, may require manual port config)

Auto-discovery uses UDP broadcast on port 7891 — requires same subnet or broadcast-enabled network.

## Usage

### On Amiga

**From CLI:**
```bash
Bifrost [port] [edge]
```

The server is discovered automatically via UDP broadcast on the network — no IP configuration needed.

**Examples:**
```bash
# Auto-discover server on default port (7890)
Bifrost

# Use custom TCP port
Bifrost 9999

# Enable edge switching (screen right edge → Amiga)
Bifrost 7890 RIGHT

# Custom port + edge (top-right corner)
Bifrost 9999 TOPRIGHT
```

**Command-Line Arguments:**

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `port` | Number | 7890 | TCP port (discovery uses port+1) |
| `edge` | String | none | PC screen edge/corner for focus switch to Amiga |

**Edge Options (case-insensitive):**
- Single edges: `TOP`, `BOTTOM`, `LEFT`, `RIGHT`
- Corners: `TOPLEFT`, `TOPRIGHT`, `BOTTOMLEFT`, `BOTTOMRIGHT`
- Disabled by default (edge switching off)

### On PC

**Launch server daemon (auto-discovery):**
```bash
python server/capture.py
```

The server automatically:
- Loads `bifrost_config.json` (auto-discovered, or uses defaults)
- Listens for UDP discovery broadcasts on port 7891
- Accepts TCP connections on port 7890
- Prints config status on startup

**Configuration (edit `server/bifrost_config.json`):**

```json
{
  "mouse": {
    "hz": 50,
    "hz_drag": 15,
    "speed": 1,
    "delta_max": 80
  },
  "curve": {
    "linear": 2.0,
    "ratio": 0.5
  },
  "keys": {
    "toggle": "scroll_lock",
    "emergency": "pause",
    "kill_modifier": "ctrl"
  },
  "debug": {
    "enabled": true,
    "print_events": true
  }
}
```

**Configuration Reference:**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `mouse.hz` | Number | 50 | Normal polling rate (Hz, ~20ms) |
| `mouse.hz_drag` | Number | 15 | Drag polling rate (Hz, ~66ms) to reduce MCP lag |
| `mouse.speed` | Number | 1 | Input multiplier (no Windows acceleration) |
| `mouse.delta_max` | Number | 80 | Discard startup glitches > N pixels |
| `curve.linear` | Float | 2.0 | Threshold for 1:1 zone (≤2px = precise) |
| `curve.ratio` | Float | 0.5 | Compression above threshold (0.5 = compress by half) |
| `keys.toggle` | String | scroll_lock | Toggle key (scroll_lock, pause, esc, tab, etc.) |
| `keys.emergency` | String | pause | Force-return to PC if stuck |
| `debug.enabled` | Boolean | true | Print events to console |

**Why MOUSE_HZ_DRAG is lower:** Dragging files in AmigaOS shows a full-screen opaque outline (MCP). Each update forces redraw. Lowering drag rate from 50 Hz to 15 Hz (~66ms) prevents overwhelming the Amiga.

## Input Control Toggle

### Default Hotkeys
- **Scroll Lock** - Toggle between PC and Amiga input
- **Screen corner tap** - Top-right corner click switches to Amiga control

### Behavior
- **PC Control** (default) - Mouse/keyboard control PC apps, forwarded to Amiga display
- **Amiga Control** - Direct Amiga input, PC input suppressed locally

## Configuration Examples

### Default Setup (Auto-Discovery)

**Amiga:**
```bash
# Server auto-discovered on UDP port 7891 (TCP 7890)
Bifrost
```

**PC (server/capture.py):**
```python
MOUSE_HZ = 50             # Default (20ms per event)
CURVE_LINEAR = 2.0
CURVE_RATIO = 0.5
DEBUG = True
```

### With Edge Switching

**Amiga (top-right corner switches to Amiga):**
```bash
Bifrost 7890 TOPRIGHT
```

### Custom Port Setup

**Amiga:**
```bash
# Connect via custom TCP port 9999 (discovery: 9900)
Bifrost 9999
```

**PC (server/capture.py):**
- No port config in Python server (it listens on 0.0.0.0, Amiga initiates connection)

### High-Responsiveness Gaming

**PC (server/capture.py):**
```python
MOUSE_HZ = 100            # ~10ms per event (2× response)
MOUSE_HZ_DRAG = 30        # Faster drags
CURVE_LINEAR = 1.0        # Less initial dead zone
CURVE_RATIO = 0.3         # Compressed acceleration
```

### Validated Production Config (v0.3)

**PC (server/capture.py):**
```python
# smooth-mouse-v1 milestone - tested and smooth
MOUSE_HZ = 50
MOUSE_HZ_DRAG = 15
CURVE_LINEAR = 2.0
CURVE_RATIO = 0.5
TOGGLE_KEY = Key.scroll_lock
```

**Amiga:**
```bash
Bifrost 7890 TOPRIGHT
```

**Result**: Smooth, natural mouse movement with sub-pixel precision and edge-triggered focus switch.

## Technical Details

### Mouse Acceleration Curve

Bifrost uses a **piecewise-linear accumulation** system:

```
Delta 1 → 1px
Delta 2 → 2px
Delta 3 → 2.5px (ratio adjustment)
Delta 4 → 3px
...
```

Benefits:
- ✅ Smooth, predictable acceleration
- ✅ Sub-pixel float accumulation prevents input loss
- ✅ Matches modern OS acceleration curves
- ✅ Tuneable via CURVE_LINEAR and CURVE_RATIO

### Network Protocol

- **Discovery**: UDP broadcast (port = TCP port + 1, default 7891)
  - PC broadcasts `Bifrost_DISCOVER`, Amiga replies `Bifrost_HERE`
  - No pre-configured IP needed — auto-discovery finds server
- **TCP/IP**: TCP_NODELAY enabled for low-latency packet delivery
- **Packets**: Fixed 8-byte size with big-endian encoding
  - Format: `[type][flags][x:i16][y:i16][code][state]`
  - Types: `PKT_MOUSE_MOVE`, `PKT_MOUSE_BTN`, `PKT_KEY`, `PKT_WHEEL`, `PKT_HELLO`, `PKT_EDGE_TRIGGER`, `PKT_FOCUS_ENTER`, `PKT_PING`
- **Send rate**: 50 Hz default (~20ms per event, adjustable via MOUSE_HZ in server/capture.py)

### Input Suppression

- **Amiga mode**: `suppress=False` (mouse) + `suppress=True` (keyboard)
  - Allows seeing PC mouse cursor while Amiga has keyboard control
- **PC mode**: Full local input control

## Troubleshooting

### Connection refused / Cannot connect to PC

**Solution:** 
1. Check PC firewall allows port 9999 (or custom PORT)
2. Verify Amiga can ping PC (`ping <pc-ip>`)
3. Ensure server is running: `python server/capture.py`

### Mouse movement laggy or jumpy

**Solution:**
1. Increase `MOUSE_HZ` (more polling)
2. Reduce `CURVE_LINEAR` for less aggressive acceleration
3. Check network latency: `ping <pc-ip>` from Amiga

### Keyboard not responding

**Solution:**
1. Verify toggle mode - use Scroll Lock to switch to Amiga control
2. Check server logs for input capture errors
3. Restart both Bifrost and server daemon

### Toggle not working

**Solution:**
1. Ensure Scroll Lock is not locked by OS (toggle state)
2. Try screen corner tap (top-right) as alternative
3. Manually restart with STOP argument and reconnect

## Building from Source

### Requirements

- VBCC m68k cross-compiler
- AmigaOS NDK 3.2+
- GNU Make
- Python 3.8+ (server side only)

### Build Commands

```bash
# Build for 68020+ (SAGA-compatible)
make CPU=68020 build

# Build release version
make MODE=release build

# Clean build artifacts
make clean

# Upload to Vampire V4
make upload
```

## Version History

### v0.3 (Current) - Smooth & Edge Ready
- ✅ Piecewise-linear acceleration curve
- ✅ Sub-pixel float accumulation
- ✅ TCP_NODELAY for low-latency packets
- ✅ Edge detection and boundary handling
- ✅ Scroll Lock toggle (PC ↔ Amiga)
- ✅ Configurable MOUSE_HZ (10-200ms polling)

### v0.2
- ✅ Smooth mouse movement
- ✅ Keyboard forwarding
- ✅ Basic toggle switching

### v0.1
- ✅ Initial client-server architecture
- ✅ TCP/IP mouse forwarding
- ✅ Basic acceleration curve

## Documentation

- [ROADMAP.md](ROADMAP.md) - Complete development roadmap (Phases 2-6, architecture notes)
- [MILESTONES.txt](MILESTONES.txt) - Tagged release history and validation points
- [server/requirements.txt](server/requirements.txt) - Python dependencies
- [Makefile](Makefile) - Build configuration (CPU targets, release builds)

## License

Copyright (c) 2025 Vincent Buzzano (ReddoC)

See LICENSE file for details.

## Credits & Acknowledgments

Bifrost is inspired by:

- **VNC (Virtual Network Computing)** - Remote desktop architecture
- **Synergy** - Cross-machine input forwarding
- **Vampire V4 SAGA Hardware** - Apollo Team (low-latency I/O capabilities)
- **AmigaOS input.device** - Standard input event handling
- **Python pynput** - Cross-platform input capture

---

**Status:** Ready for production use on Vampire V4 with validated smooth mouse curve.

**Next:** Per-app profiles, Amiga→PC reverse control, GUI preferences editor.
