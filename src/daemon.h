/*
 * Bifrost - shared declarations between main.c (CLI entry point) and
 * daemon.c (background daemon: discovery, TCP connection, event
 * injection). See daemon.c's file header for the daemon architecture.
 *
 * (c) 2026 Vincent Buzzano - MIT License
 */

#ifndef Bifrost_DAEMON_H
#define Bifrost_DAEMON_H

#include "bifrost.h"

//===========================================================================
// Program constants
//===========================================================================

// ---> BEGIN GENERATED PROGRAM_CONSTANTS
#define PROGRAM_NAME "Bifrost"
#define PROGRAM_VERSION "0.4.1"
#define PROGRAM_DATE "22.07.2026"
#define PROGRAM_AUTHOR "Vincent Buzzano"
#define PROGRAM_DESC_SHORT "Amiga Mouse & Keyboard Controller"
// <--- END GENERATED PROGRAM CONSTANTS

#define VERSION_STRING "$VER: " PROGRAM_NAME " " PROGRAM_VERSION \
    " (" PROGRAM_DATE ") " PROGRAM_DESC_SHORT ", (c) " PROGRAM_AUTHOR

//===========================================================================
// Protocol constants  (must match server/protocol.py)
//===========================================================================

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
                                 // byte[6] = percent (0-255) along 
                                 // s_amigaEdge.
#define PKT_FOCUS_ENTER  0x07    // Server -> Amiga: focus just switched to
                                 // Amiga via an edge trigger. byte[6] =
                                 // percent (0-255) along s_amigaEdge to
                                 // place the cursor at; ignored for corners.
#define PKT_CLIENT_STATE 0x08    // Amiga -> Server: client enabled/
                                 // disabled state. byte[6] = 1 (enabled)
                                 // Sent by daemon.c;
                                 // s_clientEnabled is driven by the 
                                 // application port via BMSG_CMD_SET_CONFIG
                                 // directly.
#define PKT_PING         0xFF    // keepalive

// Button IDs (byte 6 in PKT_MOUSE_BTN)
#define BTN_LEFT        0
#define BTN_RIGHT       1
#define BTN_MIDDLE      2

// Wheel direction (byte 6 in PKT_WHEEL)
#define WHEEL_UP        0
#define WHEEL_DOWN      1

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
// oppositeEdge - Mirror an edge/corner bitmask: TOP<->BOTTOM, LEFT<->RIGHT.
// Shared between main.c (initial CLI parse) and daemon.c (setConfig(),
// which must recompute s_amigaEdge whenever pcEdge changes live).
//===========================================================================

static inline UBYTE oppositeEdge(UBYTE edge)
{
    UBYTE result = 0;
    if (edge & EDGE_TOP)    result |= EDGE_BOTTOM;
    if (edge & EDGE_BOTTOM) result |= EDGE_TOP;
    if (edge & EDGE_LEFT)   result |= EDGE_RIGHT;
    if (edge & EDGE_RIGHT)  result |= EDGE_LEFT;
    return result;
}

//===========================================================================
// daemon() - defined in daemon.c, launched by main.c via CreateNewProcTags
//===========================================================================

void daemon(void);

#endif // Bifrost_DAEMON_H
