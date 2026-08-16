# Bifrost Changelog

All notable changes to Bifrost are documented in this file.

## [0.6.0] - 2026-08-08

### Added
- Auto-negotiated TCP port: the PC embeds its actual TCP listening port in
  the UDP discovery broadcast (`Bifrost_DISCOVER:<port>`) and the Amiga
  connects to it automatically. No more manually passing a matching port
  on both sides when the PC's port isn't the default. The UDP discovery
  port itself is now fixed (7891), independent of the TCP port, so it
  stays reachable regardless. Completes Phase 2 of the roadmap.
- `systray.enabled` config option to skip the systray icon entirely, e.g.
  on headless Linux/Wayland setups with no tray protocol - `--no-systray`
  is still available for one-off runs and always overrides it.

### Changed
- `HZDRAG` now defaults to the same rate as `HZ` instead of a fixed 15 -
  the lower default only helped apps using opaque drag (MCP-style, e.g.
  Workbench icon dragging), which most software doesn't use, so
  throttling drag by default made things worse for the common case. Pass
  `HZDRAG=n` explicitly to opt into a lower rate for opaque-drag apps.

### Fixed
- Linux: the systray backend failing to start at runtime (e.g. no working
  tray protocol on a bare Wayland compositor) no longer takes the whole
  server down - it logs a warning and continues without the icon.
- Linux: a startup failure in the server run loop (e.g. a permission error
  opening `/dev/uinput`, or the TCP port already in use) no longer exits
  silently with code 0 when running under the systray - the unconditional
  hard exit needed to avoid hanging on pystray's non-daemon backend thread
  was swallowing the exception; it's now logged and the process exits
  non-zero.
- Linux: fixed the mouse cursor becoming visible again unexpectedly during
  Amiga focus - the `Xlib.display.Display()` connection backing the
  XFixes invisible-cursor handle could get silently garbage-collected
  while still in use.
- Linux: the near-edge cursor re-center (keeps a drag from getting stuck
  at a screen edge) only skipped mid-drag while the left button was held -
  a right-button drag near an edge still triggered the warp and stuttered.
- Edge-trigger: the cursor reaching a hard corner/edge boundary with zero
  remaining delta could fail to fire (a real screen edge can't produce a
  delta past itself, so the resistance check waiting for one never saw
  it), and rapid small deltas below the push threshold (e.g. from a
  high-report-rate/VNC mouse) were dropped instead of accumulating
  toward it.

### Removed
- The Amiga-side TCP port CLI argument (`Bifrost <port>`) and the `port`
  field of the `BifrostConfig` IPC struct (`GET_CONFIG`/`SET_CONFIG`) - the
  discovery broadcast's port suffix is mandatory now, not a value with a
  manual fallback. **Breaking change for third-party tools (BifrostCX)**
  that read `port` from `GET_CONFIG` or pass a port to `launchBifrost()` -
  the field no longer exists.

## [0.5.1] - 2026-07-31

### Fixed
- Documentation-only release: corrected the mouse-tuning/CLI instructions,
  fixed inaccurate OS and CPU requirements, added the missing PC server
  install steps, fixed a UTF-8 BOM that broke `more` on real Amigas, and
  noted that both PC and Amiga must be set to a US keyboard layout to
  avoid wrong characters (accents aren't supported at all yet). No code
  changes.

## [0.5.0] - 2026-07-27

### Changed
- Mouse tuning (poll rate, speed, acceleration) is now configured on the
  Amiga side via CLI arguments instead of the PC's JSON config file.
- Relaunching Bifrost while it's already running now updates its live
  settings instead of being refused.

### Fixed
- Fixed a UDP discovery bug that could weaken or break device detection
  on the network.
- Fixed several reliability issues: a rare crash on message timeout, a
  config error that could be silently ignored, an unenforced speed
  limit, and network send failures that went unlogged.

### Improved
- Internal code cleanup (no behavior change).

## [0.4.3] - 2026-07-26

### Added
- `PKT_HEARTBEAT` (replaces `PKT_PING`) - sent by the Amiga daemon ~every 1s
  regardless of other traffic, carries the current Amiga cursor position;
  lets the PC server detect a stalled Amiga main loop independent of any
  PC→Amiga packet backlog
- PC Capslock state sync to Amiga (drives `IEQUALIFIER_CAPSLOCK` so
  keymap.library types uppercase correctly), `NOCAPSLOCK` CLI arg to disable it

### Fixed
- Left/Right Amiga key qualifiers (`LCOMMAND`/`RCOMMAND`) now track per-side
  state from the rawkey code instead of setting both from the wire's single
  combined `QUAL_AMIGA` bit - AmigaOS shortcuts that check one side
  specifically (e.g. Amiga+M) now behave correctly

### Improved
- Logging and connection status reporting (`daemon.c`, `tcp_server.py`)

### Documentation
- Documented the Ctrl+Alt+Del/Windows Secure Attention Sequence limitation
  (cannot be captured from a user-mode hook) in README's Known Limitations

## [0.4.1] - 2026-07-22

### Changed
- **API Refactoring: Eliminated "Commodity" terminology from Bifrost core**
  - Renamed protocol constant `PKT_CX_STATE` → `PKT_CLIENT_STATE` (client enabled/disabled state)
  - Renamed daemon state variable `s_cxEnabled` → `s_clientEnabled`
  - Renamed socket variable `s_cxTcpSock` → `s_clientTcpSock`
  - Renamed server functions `set_amiga_cx_state()` → `set_amiga_client_state()`
  - Renamed server functions `pack_cx_state()` → `pack_client_state()`
  - Removed references to commodities.library from Bifrost daemon documentation
  - **Note:** Commodities support is handled by BifrostCX (separate Workbench commodity), not Bifrost itself
  
### Improved
- **Header file separation (Internal API clarification)**
  - Split `daemon.h` into two focused headers:
    - `daemon.h`: Private API for daemon/CLI (includes TCP protocol details, program constants, shared state)
    - `bifrost.h`: Public IPC API for third-party clients (control port messages, configuration structures)
  - `daemon.h` now includes `bifrost.h` to avoid duplication
  - Clarified public contract vs internal implementation details

## [0.4.0] - 2026-07-21

### Added
- Client-enabled/disabled state tracking (`PKT_CX_STATE` packets)
- Server-side state management in `capture.py`
- Systray state display for "disabled" (client paused via Exchange)

### Changed
- PC server now forces focus to PC when Amiga client is disabled
- Updated test suite for client state tracking

### Fixed
- Edge configuration no longer leaks between separate Bifrost connections

## [0.3] - Earlier

### Features
- Piecewise-linear acceleration curve
- Sub-pixel float accumulation
- TCP_NODELAY for low-latency delivery
- Edge detection and boundary handling
- UDP auto-discovery
- JSON configuration file
- Smooth mouse movement
- Keyboard forwarding
- Toggle switching (Scroll Lock)
- Initial client-server architecture
