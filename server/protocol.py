"""
Bifrost Protocol - 8-byte binary packet encoding.

Packet layout (big-endian):
  [0]   type:  PKT_MOUSE_MOVE | PKT_MOUSE_BTN | PKT_KEY | PKT_WHEEL | PKT_HELLO | PKT_EDGE_TRIGGER | PKT_FOCUS_ENTER | PKT_PING
  [1]   flags: qualifier bitmask (QUAL_*)
  [2-3] x:     int16 mouse delta (big-endian)
  [4-5] y:     int16 mouse delta (big-endian)
  [6]   code:  Amiga rawkey code OR button ID
  [7]   state: PKT_UP (0) or PKT_DOWN (1)
"""
import struct

# Packet types
PKT_MOUSE_MOVE   = 0x01
PKT_MOUSE_BTN    = 0x02
PKT_KEY          = 0x03
PKT_WHEEL        = 0x04
PKT_HELLO        = 0x05   # Amiga -> Server: announces the PC edge/corner
                           # that triggers switching to Amiga (see
                           # server/edge_resistance.py for the bitmask).
                           # Sent once, right after the Amiga connects.
PKT_EDGE_TRIGGER = 0x06   # Amiga -> Server: the Amiga-side edge
                           # resistance state machine fired - switch
                           # focus back to PC. byte[6] = percent (0-255)
                           # position along the Amiga's exit edge.
PKT_FOCUS_ENTER  = 0x07   # Server -> Amiga: focus just switched to Amiga
                           # via an edge trigger. byte[6] = percent (0-255)
                           # position along the Amiga's entry edge; ignored
                           # by the receiver when that edge is a corner.
PKT_PING         = 0xFF

# Button IDs (PKT_MOUSE_BTN code byte)
BTN_LEFT   = 0
BTN_RIGHT  = 1
BTN_MIDDLE = 2

# Wheel direction (PKT_WHEEL code byte)
WHEEL_UP   = 0
WHEEL_DOWN = 1

# State byte
PKT_UP   = 0
PKT_DOWN = 1

# Qualifier flags (must match Bifrost.c QUAL_*)
QUAL_LSHIFT   = 0x01
QUAL_RSHIFT   = 0x02
QUAL_CTRL     = 0x04
QUAL_LALT     = 0x08
QUAL_RALT     = 0x10
QUAL_LBUTTON  = 0x20   # left mouse button held (needed for drag on Amiga windows)
QUAL_RBUTTON  = 0x40   # right mouse button held
QUAL_AMIGA    = 0x80   # Left or Right Amiga key held (see keymap.py right_amiga)

# '>BBhhBB' = big-endian: uint8, uint8, int16, int16, uint8, uint8 = 8 bytes
_FMT = '>BBhhBB'

def pack_mouse_move(dx: int, dy: int, flags: int = 0) -> bytes:
    """Encode a mouse delta movement packet."""
    return struct.pack(_FMT, PKT_MOUSE_MOVE, flags & 0xFF, dx, dy, 0, 0)

def pack_mouse_btn(button: int, pressed: bool, flags: int = 0) -> bytes:
    """Encode a mouse button press/release packet."""
    state = PKT_DOWN if pressed else PKT_UP
    return struct.pack(_FMT, PKT_MOUSE_BTN, flags & 0xFF, 0, 0, button, state)

def pack_key(rawcode: int, pressed: bool, flags: int = 0) -> bytes:
    """Encode a keyboard event packet (rawcode = Amiga rawkey code)."""
    state = PKT_DOWN if pressed else PKT_UP
    return struct.pack(_FMT, PKT_KEY, flags & 0xFF, 0, 0, rawcode & 0xFF, state)

def pack_wheel(direction: int, flags: int = 0) -> bytes:
    """Encode a mouse wheel event (WHEEL_UP=0 or WHEEL_DOWN=1)."""
    return struct.pack(_FMT, PKT_WHEEL, flags & 0xFF, 0, 0, direction & 1, 0)

def pack_hello(pc_edge: int) -> bytes:
    """Encode the Amiga->Server handshake announcing which PC edge/corner
    (bitmask, see edge_resistance.py) switches focus to Amiga.
    0 = edge switching disabled."""
    return struct.pack(_FMT, PKT_HELLO, 0, 0, 0, pc_edge & 0xFF, 0)

def pack_edge_trigger(percent: int = 0) -> bytes:
    """Encode the Amiga->Server request to switch focus back to PC.
    percent (0-255) = position along the Amiga's exit edge; ignored by
    the receiver when that edge is a corner."""
    return struct.pack(_FMT, PKT_EDGE_TRIGGER, 0, 0, 0, percent & 0xFF, 0)

def pack_focus_enter(percent: int) -> bytes:
    """Encode the Server->Amiga notification that focus switched to Amiga
    via an edge trigger. percent (0-255) = position along the Amiga's
    entry edge to place the cursor at; ignored by the receiver when that
    edge is a corner."""
    return struct.pack(_FMT, PKT_FOCUS_ENTER, 0, 0, 0, percent & 0xFF, 0)

def pack_ping() -> bytes:
    """Encode a keepalive packet."""
    return struct.pack(_FMT, PKT_PING, 0, 0, 0, 0, 0)
