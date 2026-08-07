# Bifrost Development Roadmap

Long-term architecture and feature phases for Bifrost remote input gateway.

## Philosophy

Bifrost targets a niche (real Amiga hardware + a modern PC), but "niche"
isn't an excuse for rough edges - a tool that behaves predictably and needs
zero manual synchronization is what turns one niche user into someone who
recommends it to the next one. Every phase below is judged on that bar, not
just "does it technically work."

## Current Status

**v0.6.0** (2026-08-03) - Phase 2 complete
- ✅ UDP discovery auto-negotiates the PC's TCP port - no manual port
  matching needed on either side, even if the PC's port changes

**v0.5.0** (2026-07-27) - Production ready
- ✅ Remote mouse & keyboard forwarding (PC → Amiga)
- ✅ Piecewise-linear acceleration curve
- ✅ Sub-pixel precision (float accumulator)
- ✅ Low-latency TCP/IP (TCP_NODELAY)
- ✅ Input toggle (Scroll Lock, screen corner)
- ✅ Edge detection & boundary handling
- ✅ Amiga-side CLI-configurable mouse tuning (HZ/HZDRAG/SPEED/DELTAMAX/CURVELINEAR/CURVERATIO), live-pushable to a running daemon
- ✅ PC Capslock sync, NOCAPSLOCK toggle
- ✅ Heartbeat liveness (`PKT_HEARTBEAT`), STATUS/STOP control port

---

## Phase 3: Bidirectional Control 🔜

**Goal:** Enable Amiga→PC reverse channel (alternative to mouse suppression).

### Phase 3.1: Amiga-Side Server
- Add lightweight TCP server on Amiga side
- Allow Amiga to send control events back to PC
- Synchronize input mode state between PC & Amiga
- **Impact:** Cleaner toggle logic, status feedback from Amiga

### Phase 3.2: Python Client Enhancement
- Add reverse channel listener
- Display Amiga state in server UI
- Validate toggle status bidirectionally
- **Impact:** More reliable input switching

**Estimated:** Phase 3 in v0.7

---

## Phase 4: Multi-Client Support 🔜

**Goal:** Several Amigas attached to one PC at once (e.g. an A6000 left, an
A1200 right, a WinUAE instance top), each on its own screen edge, without
quitting/relaunching Bifrost to switch which one is active. Scoped as a
refactor of the existing per-connection logic into a reusable client
module, not a from-scratch redesign - `capture.py`/`tcp_server.py` already
isolate per-connection concerns (reader thread, heartbeat, `PKT_HELLO`
handling), they just live in module-level globals instead of an object per
client today.

### Phase 4.1: Client Abstraction Refactor
- Extract per-connection state (`_pc_edge_mask`, `_pc_edge_resistance`,
  heartbeat/watchdog fields, the active socket) out of `capture.py`'s and
  `tcp_server.py`'s module-level globals into a `client.py` class, one
  instance per connected Amiga
- `tcp_server.py`'s accept loop stops closing/replacing the previous
  connection on every new one (`self._conn.close()`) - keeps a registry of
  active clients instead
- **Impact:** Same connection-handling code reused per Amiga, no duplicated logic

### Phase 4.2: Per-Edge Routing & Conflict Handling
- Each client's `PKT_HELLO`-announced edge registers it as the target for
  that edge; reject/warn on a second client claiming an edge already owned
  by another active one
- Route PC input to whichever client is currently focused (PC edge crossed
  -> that Amiga; that Amiga's own edge trigger -> back to PC) instead of a
  single global focus flag
- **Impact:** Multiple Amigas reachable from distinct physical PC edges, switching between them like a hardware KVM

**Estimated:** Phase 4 in v0.8

---

## Phase 5: Advanced Configuration 🔜

**Goal:** Flexible input remapping and profile system.

### Phase 5.1: Keymap Remapping Engine
- Allow arbitrary key-to-key remapping via config file
- Support combo keys (Ctrl+Alt+X → specific Amiga key)
- Per-app keymap profiles
- **Impact:** Support legacy Amiga keyboard layouts, gaming profiles

### Phase 5.2: Per-App/Per-Screen Profiles
- Save acceleration curves per Amiga app/screen
- Auto-detect resolution and apply matching profile
- Persist profiles in Amiga-side config
- **Impact:** Optimized feel for different app types

**Estimated:** Phase 5 in v0.9

---

## Phase 6: User Interface 🔜

**Goal:** GUI configuration without editing files.

### Phase 6.1: MUI Preferences Editor (Amiga-side)
- Graphical curve adjustment
- Toggle key configuration
- Network setup (server IP/port)
- Profile management
- **Impact:** No-code configuration for end users

### Phase 6.2: Python Server GUI (PC-side)
- Real-time latency/packet visualization
- Mouse movement graph
- Input suppression status
- **Impact:** Debugging and performance monitoring

**Estimated:** Phase 6 in v0.10

---

## Phase 7: Security & Advanced Features 🔜

### Phase 7.1: Bidirectional Security
- Optional encryption (TLS/SSL over TCP)
- Authentication token for Amiga↔PC pairing
- Firewall-friendly tunneling options
- **Impact:** Safe operation over untrusted networks

### Phase 7.2: Python Bidirectional Client
- Full Amiga↔PC control (not just PC→Amiga)
- Headless operation (no local input suppression)
- Remote scripting/automation from PC
- **Impact:** Amiga automation platform

**Estimated:** Phase 7 in v0.11

---

## Phase 8: Platform Portability 🔜

**Goal:** Bring the Amiga-side client to the AmigaOS-lineage OSes that
still matter for this tool, and only those. vbcc alone offers nine target
architectures (m68k-amigaos, m68k-kick13, m68k-atari, cf-atari,
m68k-jaguar, ppc-amigaos, ppc-morphos, ppc-powerup, ppc-warpos) - most
don't fit Bifrost: Kickstart 1.2/1.3 predates any realistic TCP/IP stack;
Atari TOS/MiNT and the Jaguar aren't AmigaOS at all (no `input.device`,
would mean rewriting the daemon from scratch, not porting it); PowerUp and
WarpOS exist purely to accelerate CPU-bound work, and Bifrost is a small
background network daemon with nothing to accelerate. Only the OSes below
are worth pursuing. **No version target** - each is its own toolchain/SDK
effort, scheduled opportunistically rather than tied to a release number.

### Phase 8.1: AmigaOS 4.x (PPC)
- Separate build using the AmigaOS4 SDK (clib2/newlib) instead of vbcc/NDK39
- Audit input.device/rawkey API differences from OS3.x
- **Impact:** Native support on PPC AmigaOne/Sam440/etc. hardware

### Phase 8.2: MorphOS (PPC)
- Separate build using the MorphOS SDK
- Same API-compatibility audit as 8.1, different ABI/toolchain
- **Impact:** Native support on Pegasos/Efika/Mac mini G4 etc.

### Phase 8.3: AROS (x86)
- Not a vbcc target at all - needs AROS' own gcc-based toolchain, not
  vbcc/NDK39, so this is a heavier lift than 8.1/8.2 despite being the
  same general idea
- Verify the exec.library/bsdsocket/input.device compatibility layer covers
  what `daemon.c` needs
- **Impact:** Runs on AROS-based systems (Icaros, etc.) without a 68k CPU or emulation

---

## Backlog / Future Exploration

- Multi-screen support (Workbench + RTG screens)
- Clipboard forwarding (text copy/paste)
- Drag-and-drop file transfer
- Performance profiling mode (measure round-trip latency)
- Alternative transport (UDP for lower latency, with packet recovery)

---

## Architecture Notes

### Current (v0.3)
```
PC (capture.py) --TCP/IP--> Amiga (Bifrost driver) -> input.device
         ↓
   [pynput capture]
         ↓
   [piecewise curve]
         ↓
   [8-byte packets @ 50Hz (20ms)]
```

### Phase 3+ (Bidirectional)
```
PC (capture.py) <--TCP/IP--> Amiga (Bifrost server/client)
         ↑                          ↓
   [pynput capture]          [input.device]
   [suppress control] <------[toggle state]
```

### Phase 4+ (Multi-Client)
```
                        <--TCP/IP--> Amiga #1 (edge: LEFT)
PC (tcp_server.py)      <--TCP/IP--> Amiga #2 (edge: RIGHT)
         ↓              <--TCP/IP--> Amiga #3 (edge: TOP)
   [client registry: edge -> connection]
         ↓
   [focus routed to whichever edge fired,
    back to PC via that client's own PKT_EDGE_TRIGGER]
```

### Phase 6+ (Full Stack)
```
PC GUI (Tkinter)    Amiga MUI Prefs
    ↓                      ↓
capture.py <--TCP/IP--> bifrost (daemon + prefs)
    ↓                      ↓
pynput              input.device + config
```

---

## Decision Log

- **v0.3**: Validated 100Hz polling + TCP_NODELAY as optimal for smooth movement
- **v0.3**: Float accumulator prevents sub-pixel loss (critical for precision)
- **Phase 2**: Special key mapping deferred until Phase 2 (core input works, keys are nice-to-have)
- **Phase 2.2**: UDP discovery port decoupled from the TCP port (now fixed at
  `Bifrost_DISC_PORT`) instead of embedding the negotiated port in the
  Amiga's `Bifrost_HERE` reply as originally planned - the Amiga can't
  parse a port it needs before it even receives a packet, so the PC's
  broadcast (`Bifrost_DISCOVER:<port>`) had to carry it instead
- **Phase 3**: Reverse channel deferred pending Phase 2 completion (current suppression model works)
- **Phase 4**: Multi-client scoped as a refactor of already-isolated
  per-connection logic (`capture.py`/`tcp_server.py`) into a reusable
  `client.py` module, not a ground-up redesign - see Phase 4's goal note
