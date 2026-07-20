# Bifrost Development Roadmap

Long-term architecture and feature phases for Bifrost remote input gateway.

## Current Status

**v0.3** (2026-07-20) - Production ready
- ✅ Remote mouse & keyboard forwarding (PC → Amiga)
- ✅ Piecewise-linear acceleration curve
- ✅ Sub-pixel precision (float accumulator)
- ✅ Low-latency TCP/IP (TCP_NODELAY)
- ✅ Input toggle (Scroll Lock, screen corner)
- ✅ Edge detection & boundary handling
- ✅ Configurable polling rate (MOUSE_HZ)

---

## Phase 2: Enhanced Key Mapping 🔜

**Goal:** Fix and extend keyboard support for better Amiga compatibility.

### Phase 2.1: Special Key Remapping
- Map PC Right Window → Amiga Left Amiga key
- Map PC Right Ctrl → Amiga Left Amiga key (alternative)
- Map PC INS → Amiga Help key
- Map PC Left Alt → Amiga Left Alt (with proper ALT key handling)
- **Impact:** Full keyboard compatibility with Amiga layouts

### Phase 2.2: Runtime Arguments & Control Port
- Add `STATUS` argument - query connection status
- Add `STOP` argument - disconnect and quit gracefully
- Add `PORT=<n>` argument - change TCP port at runtime
- Live config updates via PORT protocol (like XMouseD)
- **Impact:** Better process control and scriptability from shell

**Estimated:** Phase 2 complete by v0.4

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

**Estimated:** Phase 3 in v0.5

---

## Phase 4: Advanced Configuration 🔞

**Goal:** Flexible input remapping and profile system.

### Phase 4.1: Keymap Remapping Engine
- Allow arbitrary key-to-key remapping via config file
- Support combo keys (Ctrl+Alt+X → specific Amiga key)
- Per-app keymap profiles
- **Impact:** Support legacy Amiga keyboard layouts, gaming profiles

### Phase 4.2: Per-App/Per-Screen Profiles
- Save acceleration curves per Amiga app/screen
- Auto-detect resolution and apply matching profile
- Persist profiles in Amiga-side config
- **Impact:** Optimized feel for different app types

**Estimated:** Phase 4 in v0.6

---

## Phase 5: User Interface 🔞

**Goal:** GUI configuration without editing files.

### Phase 5.1: MUI Preferences Editor (Amiga-side)
- Graphical curve adjustment
- Toggle key configuration
- Network setup (server IP/port)
- Profile management
- **Impact:** No-code configuration for end users

### Phase 5.2: Python Server GUI (PC-side)
- Real-time latency/packet visualization
- Mouse movement graph
- Input suppression status
- **Impact:** Debugging and performance monitoring

**Estimated:** Phase 5 in v0.7

---

## Phase 6: Security & Advanced Features 🔞

### Phase 6.1: Bidirectional Security
- Optional encryption (TLS/SSL over TCP)
- Authentication token for Amiga↔PC pairing
- Firewall-friendly tunneling options
- **Impact:** Safe operation over untrusted networks

### Phase 6.2: Python Bidirectional Client
- Full Amiga↔PC control (not just PC→Amiga)
- Headless operation (no local input suppression)
- Remote scripting/automation from PC
- **Impact:** Amiga automation platform

**Estimated:** Phase 6 in v0.8

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

### Phase 5+ (Full Stack)
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
- **Phase 3**: Reverse channel deferred pending Phase 2 completion (current suppression model works)
