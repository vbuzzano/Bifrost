# Bifrost

![alt text](assets/bifrost.png)


**Remote Mouse & Keyboard Gateway for AmigaOS 3.x**

Bifrost enables seamless mouse and keyboard forwarding from a PC to a AmigaOs 3.x over TCP/IP. Control your Amiga remotely with smooth, low-latency input using a piecewise-linear acceleration curve and sub-pixel precision. Includes toggle switching to alternate between PC and Amiga input control.

## Features

✅ **Remote Input Forwarding** - Real-time mouse and keyboard events from PC to Amiga  
✅ **Smooth Mouse Movement** - Piecewise-linear acceleration curve (sub-pixel accumulation)  
✅ **Low-Latency Streaming** - TCP_NODELAY for immediate packet delivery  
✅ **Keyboard Support** - Full keyboard forwarding with toggle capability  
✅ **Input Toggle** - Scroll Lock or screen edge trigger to switch PC ↔ Amiga control  
✅ **Edge Detection** - Screen edge/corner switching for focus control  
✅ **Auto-Discovery** - UDP broadcast — no IP or port configuration needed, even if the PC's port isn't the default  
✅ **Configurable** - Mouse tuning via Amiga CLI args, everything else via `bifrost_config.json` — no code edits  
✅ **Systray Status Icon** - Green icon when Amiga connected, grey when disconnected  
✅ **Python Server** - Cross-platform PC side daemon (Windows/Linux/macOS)  

## Quick Start

### 1. PC Side
```bash
cd server
./setup_venv.sh          # Windows: pwsh .\setup_venv.ps1
python main.py            # Windows: .venv\Scripts\python main.py
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
- AmigaOS 2.0 or later — only tested on AmigaOS 3.x hardware so far (see Testing & Validation below)
- 68020 or better CPU (stock or accelerated)
- A TCP/IP stack (AmiTCP, Roadshow, or ApolloOS networking)
- Network connectivity to PC

### Setup

**1. Set up the Python environment (creates `.venv`, installs dependencies):**
```bash
cd server
./setup_venv.sh          # Windows: pwsh .\setup_venv.ps1
```

**2. Start server:**
```bash
python main.py                    # Default port 7890 (Windows: .venv\Scripts\python main.py)
python main.py --port 9999        # Custom port (Amiga auto-detects it, no CLI change needed there)
```

**2b. (optional) Auto-start at login:**

- **Windows:**
  ```powershell
  cd server
  pwsh .\install_startup.ps1
  ```
  Adds a shortcut to your Startup folder so Bifrost launches automatically at every login, with no console window (status is shown in the systray). Logs go to `server\bifrost.log`. Run `uninstall_startup.ps1` to remove it.

  (macOS/Linux: the zip doesn't preserve the executable bit - run `chmod +x server/start_bifrost.sh` once after extracting.)

- **macOS:** `start_bifrost.sh` is a plain launch script - it doesn't register itself anywhere. Open **System Settings → General → Login Items**, click **+**, and add `server/start_bifrost.sh`.

- **Linux:** Same idea - most desktop environments have their own "Startup Applications" setting (e.g. GNOME: *Settings → Apps → Startup Applications*; KDE: *System Settings → Autostart*). Point it at `server/start_bifrost.sh`.

**3. Copy Bifrost to Amiga:**
```bash
Copy Bifrost to SYS:
```

**4. Launch from CLI:**
```bash
Bifrost [edge]
```

**Auto-discovery:** Server is found via UDP broadcast on a fixed port (7891). No IP needed, and the TCP port (7890 by default, or whatever `--port` you passed) is negotiated automatically too.

## Usage

### Command-Line Arguments (Amiga)

```bash
Bifrost                      # Auto-discover PC and its TCP port, whatever it is
Bifrost TOPRIGHT             # + Edge trigger (top-right corner)
Bifrost NOCAPSLOCK            # Disable PC Capslock -> Amiga sync (default: enabled)
Bifrost HZ=75 SPEED=1.5       # Mouse tuning args (see below), any order
Bifrost STATUS                # Query the running daemon's connection status
Bifrost STOP                  # Disconnect and quit the running daemon
Bifrost ?                     # Print full usage/help
```

**Edge Options:** `TOP`, `BOTTOM`, `LEFT`, `RIGHT`, `TOPLEFT`, `TOPRIGHT`, `BOTTOMLEFT`, `BOTTOMRIGHT`

**Mouse Tuning (`KEY=VALUE`):** `HZ=n` poll rate (default 50) · `HZDRAG=n` poll rate while dragging (default 15) · `SPEED=n` speed, 0.2-3.0 (default 1.0) · `DELTAMAX=n` startup glitch filter (default 80) · `CURVELINEAR=n`/`CURVERATIO=n` acceleration curve shape (defaults 2.0/0.5).

**STATUS / STOP:** Talk to the already-running daemon instead of launching a new one - useful for scripts. Running `Bifrost` again while already active updates its settings live instead of starting a duplicate. Use `STOP` first to actually stop it, or `STATUS` to check.

### Configuration

**Mouse tuning is Amiga-side** (see `HZ=`/`SPEED=`/etc. above) - it's sent to the PC automatically over the wire, no PC-side setup needed.

**PC-side config** is everything else: edit `server/bifrost_config.json` (copy it from `bifrost_config.default.json` first if it doesn't exist yet - it's entirely optional, the server runs fine with just the built-in defaults):

```json
{
  "network": {
    "port": 7890
  },
  "keys": {
    "toggle": "scroll_lock",
    "emergency": "pause",
    "kill_modifier": "ctrl"
  },
  "debug": {
    "enabled": false
  }
}
```

**For detailed parameter explanations, profiles, and troubleshooting:** See [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

### Toggle Focus (PC ↔ Amiga)

- **Scroll Lock key** - Toggle between PC and Amiga input
- **Screen corner** - Top-right click also triggers toggle (if enabled via edge config)

### Systray Status Icon (PC)

When the server runs, a systray icon shows the Amiga connection state:

- 🟢 **Green circle** - Amiga is connected and ready to receive input
- ⚫ **Grey circle** - Amiga is disconnected (waiting for Amiga to connect)

The systray menu displays:
- Current connection status: "Amiga Connected" or "Amiga Disconnected"
- **Quit** button to exit the server gracefully

Updates every 0.5 seconds to reflect connection state changes in real-time.

**Note:** Systray support requires `pystray` (installed via `pip install -r requirements.txt`). If not installed, the server runs normally without systray.

## Known Limitations

**Ctrl+Alt+Del cannot be captured.** While in Amiga focus mode, pressing Ctrl+Alt+Del on the PC still brings up Windows' secure screen (lock/task manager/sign out). This is a Windows security feature no application can override, so there's no fix on Bifrost's side.

**Both PC and Amiga must be set to a US keyboard layout.** Bifrost's key mapping is hardcoded for US - it doesn't help to set the PC and Amiga to the same non-US layout (e.g. both to Swiss-French), since keys like Y/Z will still come out swapped. Set the PC to a US layout and the Amiga to `SetMap usa1`. Accented characters (é, è, ü, etc.) aren't supported at all yet - they're silently dropped.

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

- **Discovery:** UDP broadcast (fixed port 7891, independent of the TCP port)
  - PC broadcasts `Bifrost_DISCOVER:<port>` (its actual TCP port)
  - Amiga replies `Bifrost_HERE` and connects via TCP to the negotiated port
  - No pre-configured IP or port needed

- **Data:** TCP/IP with TCP_NODELAY enabled
  - Fixed 8-byte packets with big-endian encoding
  - Packet types: `PKT_MOUSE_MOVE`, `PKT_MOUSE_BTN`, `PKT_KEY`, `PKT_WHEEL`, `PKT_HELLO`, `PKT_EDGE_TRIGGER`, `PKT_FOCUS_ENTER`, `PKT_CLIENT_STATE`, `PKT_HEARTBEAT`
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
- A1200 Pistorm
- UAE A1200 
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

## Documentation

| Document | Purpose |
|----------|---------|
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [ROADMAP.md](ROADMAP.md) | Development roadmap (Phases 3-8) |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | **Full configuration guide** — parameter details, profiles, troubleshooting |
| [MILESTONES.txt](MILESTONES.txt) | Author's dev-log of internal checkpoints (not a changelog) |

## License

Copyright (c) 2025 Vincent Buzzano (ReddoC)

See LICENSE file for details.

---

**Status:** Ready for production.

**Next:** Amiga→PC reverse control, multi-client support (several Amigas on one PC) — see [ROADMAP.md](ROADMAP.md)
