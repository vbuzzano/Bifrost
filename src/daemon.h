/*
 * Bifrost - shared declarations between main.c (CLI entry point) and
 * daemon.c (background daemon: discovery, TCP connection, event
 * injection). See daemon.c's file header for the daemon architecture.
 *
 * (c) 2026 Vincent Buzzano - MIT License
 */

#ifndef Bifrost_DAEMON_H
#define Bifrost_DAEMON_H

//===========================================================================
// Program constants
//===========================================================================

// ---> BEGIN GENERATED PROGRAM_CONSTANTS
#define PROGRAM_NAME "Bifrost"
#define PROGRAM_VERSION "0.4.0"
#define PROGRAM_DATE "21.07.2026"
#define PROGRAM_AUTHOR "Vincent Buzzano"
#define PROGRAM_DESC_SHORT "Amiga Mouse & Keyboard Controller"
// <--- END GENERATED PROGRAM CONSTANTS

#define VERSION_STRING "$VER: " PROGRAM_NAME " " PROGRAM_VERSION \
    " (" PROGRAM_DATE ") " PROGRAM_DESC_SHORT ", (c) " PROGRAM_AUTHOR

//===========================================================================
// Protocol constants  (must match server/protocol.py)
//===========================================================================

#define Bifrost_DEFAULT_PORT 7890
#define Bifrost_DISC_PORT    7891    // UDP discovery port (= TCP port + 1)

// Discovery messages
#define DISC_MSG            "Bifrost_DISCOVER"
#define DISC_MSG_LEN        15
#define DISC_REPLY          "Bifrost_HERE"
#define DISC_REPLY_LEN      11

// Packet types (byte 0)
#define PKT_MOUSE_MOVE   0x01    // delta mouse movement
#define PKT_MOUSE_BTN    0x02    // mouse button press/release
#define PKT_KEY          0x03    // keyboard key press/release
#define PKT_WHEEL        0x04    // mouse wheel scroll
#define PKT_HELLO        0x05    // Amiga -> Server: announces s_pcEdge
#define PKT_EDGE_TRIGGER 0x06    // Amiga -> Server: switch focus to PC.
                                 // byte[6] = percent (0-255) along s_amigaEdge.
#define PKT_FOCUS_ENTER  0x07    // Server -> Amiga: focus just switched to
                                 // Amiga via an edge trigger. byte[6] =
                                 // percent (0-255) along s_amigaEdge to
                                 // place the cursor at; ignored for corners.
#define PKT_PING         0xFF    // keepalive

// Button IDs (byte 6 in PKT_MOUSE_BTN)
#define BTN_LEFT        0
#define BTN_RIGHT       1
#define BTN_MIDDLE      2

// Wheel direction (byte 6 in PKT_WHEEL)
#define WHEEL_UP        0
#define WHEEL_DOWN      1

// Edge/corner bitmask (matches server/edge_resistance.py EDGE_*)
#define EDGE_NONE       0x00
#define EDGE_TOP        0x01
#define EDGE_BOTTOM     0x02
#define EDGE_LEFT       0x04
#define EDGE_RIGHT      0x08

// State byte (byte 7)
#define PKT_UP          0
#define PKT_DOWN        1

// Qualifier flags (byte 1) - matches server/protocol.py QUAL_*
#define QUAL_LSHIFT     0x01
#define QUAL_RSHIFT     0x02
#define QUAL_CTRL       0x04
#define QUAL_LALT       0x08
#define QUAL_RALT       0x10
#define QUAL_LBUTTON    0x20    // left mouse button held (drag support)
#define QUAL_RBUTTON    0x40    // right mouse button held
#define QUAL_AMIGA      0x80    // Left or Right Amiga key held

// Packet size - 8 bytes, big-endian
// Layout: [type][flags][x:int16][y:int16][code][state]
#define PKT_SIZE        8

//===========================================================================
// Control port - lets a second "Bifrost STATUS"/"Bifrost STOP" invocation
// talk to the already-running daemon instead of launching a duplicate.
//===========================================================================

// Changing port name breaks compatibility with third-party tools/scripts.
#define Bifrost_PORT_NAME   "Bifrost_Port" // WARNING: Modify with caution!

#define BMSG_CMD_QUIT        0   // Stop daemon (disconnects from PC first)
#define BMSG_CMD_GET_STATUS  1   // Query connection status

#define CONTROL_REPLY_TIMEOUT 2  // seconds to wait for daemon reply

struct BifrostMsg
{
    struct Message msg;
    UBYTE          command;  // BMSG_CMD_*
    ULONG          value;    // command parameter (unused for now)
    ULONG          result;   // 0xFFFFFFFF = error; else command-specific
};

//===========================================================================
// Print macros
//===========================================================================

#define Print(text)         Printf(text "\n")
#define PrintF(fmt, ...)    Printf(fmt "\n", __VA_ARGS__)

//===========================================================================
// Shared state - set by main.c's _start() after CLI parsing, read by
// daemon.c's daemon(). Both run in the same program image; daemon() is a
// separate Process/Task (via CreateNewProcTags) but shares the same
// global data segment, so this is a plain shared variable, not IPC.
//===========================================================================

extern ULONG s_port;       // TCP port; discovery = s_port + 1
extern UBYTE s_pcEdge;     // PC-side edge/corner that switches focus to Amiga
extern UBYTE s_amigaEdge;  // Amiga-side mirror of s_pcEdge (switches back to PC)

//===========================================================================
// daemon() - defined in daemon.c, launched by main.c via CreateNewProcTags
//===========================================================================

void daemon(void);

#endif // Bifrost_DAEMON_H
