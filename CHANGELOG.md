# Bifrost Changelog

All notable changes to Bifrost are documented in this file.

## [0.5.1] - 2026-07-31

### Fixed
- Documentation-only release: corrected the mouse-tuning/CLI instructions,
  fixed inaccurate OS and CPU requirements, and added the missing PC
  server install steps to the README/guide. No code changes.

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
