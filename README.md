# Bifrost

**Remote Mouse & Keyboard Gateway for Vampire V4 / AmigaOS**

Bifrost enables seamless mouse and keyboard forwarding from a PC to a Vampire V4 Amiga over TCP/IP. Control your Amiga remotely with smooth, low-latency input using a piecewise-linear acceleration curve and sub-pixel precision. Includes toggle switching to alternate between PC and Amiga input control.

## Features

✅ **Remote Input Forwarding** - Real-time mouse and keyboard events from PC to Amiga  
✅ **Smooth Mouse Movement** - Piecewise-linear acceleration curve (sub-pixel accumulation)  
✅ **Low-Latency Streaming** - TCP_NODELAY for immediate packet delivery  
✅ **Keyboard Support** - Full keyboard forwarding with toggle capability  
✅ **Input Toggle** - Scroll Lock or screen edge trigger to switch PC ↔ Amiga control  
✅ **Edge Detection** - Screen edge/corner switching for focus control  
✅ **Auto-Discovery** - UDP broadcast — no IP configuration needed  
✅ **JSON Configuration** - No code edits — configure via `bifrost_config.json`  
✅ **Python Server** - Cross-platform PC side daemon (Windows/Linux/macOS)  

## Quick Start

### 1. PC Side
```bash
pip install -r server/requirements.txt
python server/main.py
```

### 2. Amiga Side
```bash
Bifrost
```

**Done!** Server auto-discovers and connects. Toggle focus with **Scroll Lock**.

## Installation

### PC Requirements
- Python 3.8+
- Network connectivity to Amiga (Ethernet or USB FTDI)

### Amiga Requirements
- Vampire V4 (68080 SAGA)
- AmigaOS 3.2+
- Network connectivity to PC

### Setup

**1. Install Python dependencies:**
```bash
cd server
pip install -r requirements.txt
```

**2. Start server:**
```bash
python server/main.py           # Default port 7890
python server/main.py --port 9999  # Custom port
```

**3. Copy Bifrost to Amiga:**
```bash
Copy Bifrost to SYS:
```

**4. Launch from CLI:**
```bash
Bifrost [port] [edge]
```

**Auto-discovery:** Server is found via UDP broadcast on port 7891 (TCP 7890 + 1). No IP needed.

## Usage

### Command-Line Arguments (Amiga)

```bash
Bifrost                      # Auto-discover, default port (7890)
Bifrost 9999                 # Custom TCP port (PC must also use 9999)
Bifrost 9999 TOPRIGHT        # + Edge trigger (top-right corner)
```

**Edge Options:** `TOP`, `BOTTOM`, `LEFT`, `RIGHT`, `TOPLEFT`, `TOPRIGHT`, `BOTTOMLEFT`, `BOTTOMRIGHT`

**⚠️ Port Limitation:** If you change the port on PC, you must also specify it on Amiga CLI. The UDP discovery protocol doesn't currently transmit the TCP port — it's assumed to be `UDP port - 1`. This will be fixed in Phase 2 (auto-negotiation).

### Configuration (PC)

Edit `server/bifrost_config.json`:

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
    "emergency": "pause"
  },
  "debug": {
    "enabled": true
  }
}
```

**For detailed parameter explanations, profiles, and troubleshooting:** See [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

### Toggle Focus (PC ↔ Amiga)

- **Scroll Lock key** - Toggle between PC and Amiga input
- **Screen corner** - Top-right click also triggers toggle (if enabled via edge config)

## Architecture

### PC Side (Server)
- Python daemon captures mouse/keyboard
- Applies acceleration curve
- Sends 8-byte packets via TCP/IP (50 Hz default)

### Amiga Side (Client)
- Receives packets over TCP
- Injects into `input.device` stream
- Supports edge-triggered focus switching

## Technical Details

### Network Protocol

- **Discovery:** UDP broadcast (port 7891 default)
  - PC broadcasts `Bifrost_DISCOVER`
  - Amiga replies `Bifrost_HERE` and connects via TCP
  - No pre-configured IP needed

- **Data:** TCP/IP with TCP_NODELAY enabled
  - Fixed 8-byte packets with big-endian encoding
  - Packet types: `PKT_MOUSE_MOVE`, `PKT_MOUSE_BTN`, `PKT_KEY`, `PKT_WHEEL`, `PKT_HELLO`, `PKT_EDGE_TRIGGER`, `PKT_FOCUS_ENTER`, `PKT_PING`
  - Default send rate: 50 Hz (~20ms per event)

### Mouse Acceleration (Piecewise-Linear)

```
|d| ≤ CURVE_LINEAR  →  output = |d|       (1:1 precision)
|d| >  CURVE_LINEAR  →  output = CL + (|d|-CL) × CURVE_RATIO
```

**Example (default: linear=2.0, ratio=0.5):**
- 1px → 1px, 2px → 2px, 3px → 2.5px, 4px → 3px, 10px → 6px

### Why MOUSE_HZ_DRAG?

**Only relevant for apps using opaque drag (MCP — Move/Copy/Paste window).**

If an app uses opaque drag (Workbench, file managers), each mouse event forces a full-screen redraw. Lower send rate during drag prevents overwhelming the Amiga.

If an app uses transparent drag or no drag visual, set `hz_drag = hz` — no lag, no benefit to lowering.

## Testing & Validation

**All tests on:**
- Apollo Computer Vampire V4 (A6000, 68080 SAGA)
- Configuration: 50 Hz polling, CURVE_LINEAR=2.0, CURVE_RATIO=0.5

**Validated:**
- ✅ Smooth mouse movement with sub-pixel accumulation
- ✅ Keyboard input forwarding
- ✅ Edge-triggered focus switching
- ✅ Low-latency auto-discovery
- ✅ Acceleration curve responsiveness

**Note:** Other Vampire versions or non-accelerated Amigas may need parameter adjustments. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for hardware-specific profiles.

## Building from Source

```bash
# Build for 68020+ (SAGA-compatible)
make CPU=68020 build

# Release build
make MODE=release build

# Clean
make clean

# Upload to Vampire V4
make upload
```

## Version History

### v0.3 (Current)
- ✅ Piecewise-linear acceleration curve
- ✅ Sub-pixel float accumulation
- ✅ TCP_NODELAY for low-latency delivery
- ✅ Edge detection and boundary handling
- ✅ UDP auto-discovery
- ✅ JSON configuration file

### v0.2
- ✅ Smooth mouse movement
- ✅ Keyboard forwarding
- ✅ Toggle switching

### v0.1
- ✅ Initial client-server architecture
- ✅ TCP/IP mouse forwarding
- ✅ Basic acceleration curve

## Documentation

| Document | Purpose |
|----------|---------|
| [ROADMAP.md](ROADMAP.md) | Development roadmap (Phases 2-6) |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | **Full configuration guide** — parameter details, profiles, troubleshooting |
| [MILESTONES.txt](MILESTONES.txt) | Release history and validation points |

## License

Copyright (c) 2025 Vincent Buzzano (ReddoC)

See LICENSE file for details.

## Credits & Acknowledgments

Bifrost is inspired by:
- **VNC (Virtual Network Computing)** — Remote desktop architecture
- **Synergy** — Cross-machine input forwarding
- **Vampire V4 SAGA Hardware** — Apollo Team
- **AmigaOS input.device** — Standard input event handling
- **Python pynput** — Cross-platform input capture

---

**Status:** Ready for production use on Vampire V4 with validated smooth mouse curve.

**Next:** Per-app profiles, Amiga→PC reverse control, GUI preferences editor — see [ROADMAP.md](ROADMAP.md)
