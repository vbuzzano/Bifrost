# Bifrost Wire Protocol

Reference for the binary protocol between the PC server (`server/protocol.py`)
and the Amiga daemon (`src/daemon.c`/`src/daemon.h`). If you're adding a new
packet type, keep both sides' constants in sync - there's no schema
negotiation, just two hand-written implementations of the same layout.

## Architecture

- **PC = TCP server.** Listens on a configurable port (default `7890`) and
  accepts exactly one Amiga connection at a time.
- **Amiga = TCP client.** Discovers the server via UDP broadcast (no IP
  configuration needed), then connects.
- All control/event packets are **fixed 8-byte binary structures**, sent
  over the same TCP connection in both directions.

## Discovery (UDP, before any TCP connection exists)

| Message | Direction | Bytes | Content |
|---|---|---|---|
| `Bifrost_DISCOVER:<port>` | PC → subnet broadcast | 17+ | ASCII literal + `:` + decimal TCP port |
| `Bifrost_HERE` | Amiga → PC | 12 | ASCII literal |

1. The PC broadcasts `Bifrost_DISCOVER:<port>` (its actual TCP listening
   port, e.g. `Bifrost_DISCOVER:7890`) to its subnet's broadcast address
   every 3 seconds, on a **fixed UDP port** (`DISC_PORT` /
   `Bifrost_DISC_PORT`, default `7891`) - independent of the TCP port, so
   discovery stays reachable even if the TCP port changes.
2. The Amiga listens on that fixed UDP port; on receiving a message with
   the `Bifrost_DISCOVER` prefix, it replies `Bifrost_HERE` to the sender,
   parses the port after the first `:`, and opens a TCP connection to the
   PC on that port. If the payload carries no valid port (e.g. an older PC
   build sending the bare literal), it falls back to the Amiga's own
   CLI-configurable `s_port` (default `Bifrost_DEFAULT_PORT`, `7890`) -
   in that case the port must still be matched manually on both sides.
3. Only one Amiga connection is accepted at a time; a new connection
   replaces the previous one (see `tcp_server.py`'s `run()`).

## Packet Format

Every packet is exactly 8 bytes, big-endian:

```
byte:    0      1      2-3      4-5      6      7
field: type   flags   x:int16  y:int16   code   state
```

`struct` format string: `'>BBhhBB'` (uint8, uint8, int16, int16, uint8, uint8).

Not every packet type uses every field - unused fields are sent as `0`.
Which fields are meaningful depends entirely on `type`; there's no generic
interpretation of "x"/"y"/"code" across packet types.

## Packet Types

| Type | Value | Direction | Purpose |
|---|---|---|---|
| `PKT_MOUSE_MOVE` | `0x01` | PC → Amiga | Relative mouse movement |
| `PKT_MOUSE_BTN` | `0x02` | PC → Amiga | Mouse button press/release |
| `PKT_KEY` | `0x03` | PC → Amiga | Keyboard key press/release |
| `PKT_WHEEL` | `0x04` | PC → Amiga | Mouse wheel scroll |
| `PKT_HELLO` | `0x05` | Amiga → PC | Announces the PC-side edge/corner trigger |
| `PKT_EDGE_TRIGGER` | `0x06` | Amiga → PC | Amiga-side edge fired - switch focus to PC |
| `PKT_FOCUS_ENTER` | `0x07` | PC → Amiga | Focus just switched to Amiga via an edge trigger |
| `PKT_CLIENT_STATE` | `0x08` | Amiga → PC | Client enabled/disabled (Exchange/BifrostCX) |
| `PKT_HEARTBEAT` | `0x09` | Amiga → PC | Liveness ping, ~every 1s |

### `PKT_MOUSE_MOVE` (0x01) - PC → Amiga

| Field | Meaning |
|---|---|
| `flags` | Qualifier byte (see below) - held buttons/modifiers at the time of this delta |
| `x` | Delta X, signed, pixels (clamped to -128..127 before send) |
| `y` | Delta Y, signed, pixels (clamped to -128..127 before send) |
| `code`, `state` | Unused (`0`) |

Sent by `capture.py`'s mouse flush timer while focus is on Amiga. These are
**relative deltas**, never absolute coordinates - the Amiga tracks its own
cursor position (`s_curX`/`s_curY` in `daemon.c`) by accumulating them.

### `PKT_MOUSE_BTN` (0x02) - PC → Amiga

| Field | Meaning |
|---|---|
| `flags` | Qualifier byte |
| `code` | Button ID: `BTN_LEFT`=0, `BTN_RIGHT`=1, `BTN_MIDDLE`=2 |
| `state` | `PKT_DOWN`=1 (pressed) or `PKT_UP`=0 (released) |
| `x`, `y` | Unused (`0`) |

### `PKT_KEY` (0x03) - PC → Amiga

| Field | Meaning |
|---|---|
| `flags` | Qualifier byte |
| `code` | Amiga rawkey code (mapped from the PC key on the server - see `keymap.py`) |
| `state` | `PKT_DOWN`=1 or `PKT_UP`=0 |
| `x`, `y` | Unused (`0`) |

Covers normal keys, modifiers (Shift/Ctrl/Alt/Amiga - also update `flags`
for subsequent events), and Capslock (rawkey `0x62`). Capslock's DOWN/UP
state is tracked as a **toggle**, not a normal press/release: `_on_key_press`/
`_on_key_release` flip it directly from the raw key event (works even
while the keyboard listener is suppressed, i.e. focus on Amiga, when
Windows' own `GetKeyState` toggle bit never updates); `_capslock_poller_loop`
only catches up from `GetKeyState` while focus is on PC, where that value
is reliable. See `capture.py`'s comments on both for the full reasoning.

### `PKT_WHEEL` (0x04) - PC → Amiga

| Field | Meaning |
|---|---|
| `flags` | Qualifier byte |
| `code` | Direction: `WHEEL_UP`=0, `WHEEL_DOWN`=1 |
| `x`, `y`, `state` | Unused (`0`) |

Injected on the Amiga side under **both** `IECLASS_RAWKEY` (modern apps)
and `IECLASS_NEWMOUSE` (legacy apps expecting the NewMouse standard).

### `PKT_HELLO` (0x05) - Amiga → PC

| Field | Meaning |
|---|---|
| `code` | PC-side edge/corner bitmask that triggers switching focus to Amiga |
| `flags`, `x`, `y`, `state` | Unused (`0`) |

Sent once right after the Amiga connects, and again whenever the edge
config changes live (e.g. via BifrostCX/`SET_CONFIG`) so an
already-connected server picks up the change without a reconnect. `code`
is a bitmask: `EDGE_TOP`=0x01, `EDGE_BOTTOM`=0x02, `EDGE_LEFT`=0x04,
`EDGE_RIGHT`=0x08 (combine two for a corner, e.g. `TOP|LEFT`); `0` disables
edge switching entirely.

### `PKT_EDGE_TRIGGER` (0x06) - Amiga → PC

| Field | Meaning |
|---|---|
| `code` | Percent (0-255) along the Amiga's exit edge, for cursor placement on the PC side |
| `flags`, `x`, `y`, `state` | Unused (`0`) |

Sent when the Amiga-side edge-resistance state machine fires (cursor
pushed against its screen edge) - tells the PC to switch focus back to PC,
placing the PC cursor at the equivalent position along its own edge.
Ignored (any value) when the configured edge is a corner rather than a
straight edge.

### `PKT_FOCUS_ENTER` (0x07) - PC → Amiga

| Field | Meaning |
|---|---|
| `code` | Percent (0-255) along the Amiga's entry edge, for cursor placement on the Amiga side |
| `flags`, `x`, `y`, `state` | Unused (`0`) |

The mirror of `PKT_EDGE_TRIGGER`: sent when focus switches to Amiga via a
PC-side edge trigger, so the Amiga warps its cursor to line up with where
it left the PC screen.

### `PKT_CLIENT_STATE` (0x08) - Amiga → PC

| Field | Meaning |
|---|---|
| `code` | `1` = enabled, `0` = disabled |
| `flags`, `x`, `y`, `state` | Unused (`0`) |

Driven by the Amiga-side Exchange/BifrostCX enable-disable toggle
(`s_clientEnabled` in `daemon.c`). When disabled, the PC forces focus back
to PC and refuses to switch to Amiga focus until re-enabled (see
`capture.set_amiga_client_state`).

### `PKT_HEARTBEAT` (0x09) - Amiga → PC

| Field | Meaning |
|---|---|
| `x`, `y` | Current Amiga cursor position (signed int16 each) |
| `flags`, `code`, `state` | Unused (`0`) |

Sent roughly every second **regardless of other traffic**, interleaved
with normal event packets - proves the daemon's main loop is alive and
responsive on its own, independent of any PC→Amiga packet backlog. The
server's `tcp_server.py` watchdog treats a heartbeat gap over
`HEARTBEAT_TIMEOUT_S` (2s) as "daemon stopped responding" and soft-disables
the client (same mechanism as `PKT_CLIENT_STATE`) without dropping the TCP
connection - a resumed heartbeat re-enables it automatically.

## Qualifier Byte (`flags`, byte 1)

Bitmask, shared meaning across every packet type that uses it:

| Bit | Constant | Meaning |
|---|---|---|
| `0x01` | `QUAL_LSHIFT` | Left Shift held |
| `0x02` | `QUAL_RSHIFT` | Right Shift held |
| `0x04` | `QUAL_CTRL` | Ctrl held |
| `0x08` | `QUAL_LALT` | Left Alt held |
| `0x10` | `QUAL_RALT` | Right Alt held |
| `0x20` | `QUAL_LBUTTON` | Left mouse button held (drag support) |
| `0x40` | `QUAL_RBUTTON` | Right mouse button held |
| `0x80` | `QUAL_AMIGA` | Left or Right Amiga key held |

On the Amiga side, `daemon.c`'s `qualToAmiga()` translates this byte into
the equivalent `ie_Qualifier` bits for `input.device` (e.g.
`IEQUALIFIER_LSHIFT`, `IEQUALIFIER_LCOMMAND`/`RCOMMAND` - the latter two
tracked locally from the Left/Right Amiga rawkey codes rather than the
combined `QUAL_AMIGA` bit, since the wire can't tell which side was
pressed).

## Connection Lifecycle

```
PC                                    Amiga
--                                    -----
broadcast Bifrost_DISCOVER:<port> -->
                                  <--  reply Bifrost_HERE (UDP)
                                  <--  TCP connect
                                  <--  PKT_HELLO (initial edge config)
--> PKT_FOCUS_ENTER (on PC-edge trigger)
                                  <--  PKT_EDGE_TRIGGER (on Amiga-edge trigger)
                                  <--  PKT_HEARTBEAT (~every 1s, always)
                                  <--  PKT_CLIENT_STATE (on Exchange toggle)
--> PKT_MOUSE_MOVE / PKT_MOUSE_BTN / PKT_KEY / PKT_WHEEL (while focus = Amiga)
```

A dropped TCP connection (clean close or socket error) forces focus back
to PC and returns the server to waiting for a fresh `Bifrost_HERE`/connect
sequence - no manual restart needed on either side.
