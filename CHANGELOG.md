# Bifrost Changelog

All notable changes to Bifrost are documented in this file.

## [0.5.1] - 2026-07-31

### Fixed
- Documentation-only release: README.md and Bifrost.guide still described
  mouse tuning as PC-side `bifrost_config.json` fields and were missing the
  `NOCAPSLOCK`/`KEY=VALUE` CLI syntax introduced in 0.5.0; both now match
  `docs/CONFIGURATION.md` and `main.c`'s actual usage. No code changes.

## [0.5.0] - 2026-07-27

### Changed
- **Mouse-tuning config ownership moved from PC to Amiga daemon** - `HZ`,
  `HZDRAG`, `SPEED`, `DELTAMAX`, `CURVELINEAR`, `CURVERATIO` are now
  Amiga-side CLI arguments (`Bifrost HZ=60 SPEED=1.5 ...`) instead of
  PC-side `bifrost_config.json` fields; `docs/CONFIGURATION.md` trimmed to
  match (PC-side mouse-tuning section removed)
- Running `Bifrost` again while an instance is already running now live-pushes
  any edge/mouse-tuning `KEY=VALUE` args this invocation specified to the
  running daemon via `GET_CONFIG`/`SET_CONFIG`, instead of only the edge

### Fixed
- **UDP discovery protocol string lengths** - `DISC_MSG_LEN`/`DISC_REPLY_LEN` were
  one byte short (15/11 instead of 16/12), truncating the last character of
  `Bifrost_DISCOVER`/`Bifrost_HERE` on the wire and weakening/breaking discovery
  matching depending on the server's comparison strictness
- **Use-after-free on control message timeout** - `sendBifrostMessage()`/
  `sendConfigMessage()` (main.c) freed the message and reply port on timeout
  even though the daemon could still write into and reply to them later;
  they're now deliberately leaked (bounded, rare) instead
- **Silently-ignored `SET_CONFIG` result** on the "already running" live-update
  path in `_start()` - a daemon that failed to apply the pushed config was
  reported as "config updated" and exited `RETURN_OK` regardless
- **`HZDRAG` could exceed `HZ` via `SET_CONFIG`** - the CLI already clamped
  this, but a direct `SET_CONFIG` (e.g. from BifrostCX) bypassed it; the
  invariant is now enforced in `daemon.c`'s `setConfig()` itself
- **Failed `send()` calls were silently swallowed** (heartbeat, hello,
  client-state, edge-trigger) - now logged with `Errno()` instead of
  disappearing without a trace
- Several CLI live-update bugs around merging a second invocation's args into
  the running daemon's config (previously only `s_pcEdge` was live-updatable)

### Improved
- Extracted `classifyStopStatus()` in `main.c`, mirroring XMouseD's
  parse/act separation (internal refactor, no behavior change)

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
