# Bifrost Changelog

All notable changes to Bifrost are documented in this file.

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
