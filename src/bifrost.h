/*
 * Bifrost - Public IPC API for control port messaging
 * v~ 0.6.0 [PROGRAM_VERSION]~ (~ 08.08.2026 [PROGRAM_DATE]~)
 *
 * Third-party tools (BifrostCX, scripts) use this to communicate with
 * the Bifrost daemon via the Amiga message port.
 *
 * (c) 2026 Vincent Buzzano - MIT License
 */

#ifndef Bifrost_H
#define Bifrost_H

#include <exec/types.h>
#include <exec/ports.h>

//===========================================================================
// Control port - lets a second "Bifrost STATUS"/"Bifrost STOP" invocation
// talk to the already-running daemon instead of launching a duplicate.
//===========================================================================

// Changing port name breaks compatibility with third-party tools/scripts.
#define Bifrost_PORT_NAME   "Bifrost_Port" // WARNING: Modify with caution!

#define Bifrost_DISC_PORT    7891    // UDP discovery port - fixed. The TCP
                                      // port is negotiated via the discovery
                                      // payload every connection; Bifrost has
                                      // no CLI/config notion of "the" TCP
                                      // port anymore, so there's no default
                                      // to name here


#define BMSG_CMD_QUIT        0   // Stop daemon (disconnects from PC first)
#define BMSG_CMD_GET_STATUS  1   // Query connection status
#define BMSG_CMD_GET_CONFIG  2   // Read current edge/client-enabled/mouse-tuning
#define BMSG_CMD_SET_CONFIG  3   // Apply new edge/client-enabled/mouse-tuning

#define CONTROL_REPLY_TIMEOUT 2  // seconds to wait for daemon reply


// Edge/corner bitmask (matches server/edge_resistance.py EDGE_*)
#define EDGE_NONE       0x00
#define EDGE_TOP        0x01
#define EDGE_BOTTOM     0x02
#define EDGE_LEFT       0x04
#define EDGE_RIGHT      0x08

// Configurable daemon state. GET_CONFIG copies the daemon's current values
// into this; SET_CONFIG's setConfig() (daemon.c) applies every field. New
// settings land here, not as new BMSG_CMD_* values or new CLI arguments -
// see design spec for the rationale.
struct BifrostConfig
{
    UBYTE pcEdge;      // live-updatable
    BOOL  clientEnabled;   // live-updatable
    BOOL  capslockEnabled; // live-updatable; also settable via CLI NOCAPSLOCK
                           // (see main.c) - default TRUE
    UBYTE mouseHz;         // live-updatable; also settable via CLI HZ=n - default 50
    UBYTE mouseHzDrag;     // live-updatable; also settable via CLI HZDRAG=n - default 15, clamped <= mouseHz
    UBYTE mouseSpeed;      // live-updatable; x10 fixed-point; CLI SPEED=n - default 10 (1.0)
                           // clamped to 2-30 (0.2-3.0) by setConfig() - see daemon.c
    UBYTE mouseDeltaMax;   // live-updatable; also settable via CLI DELTAMAX=n - default 80
    UBYTE curveLinear;     // live-updatable; x10 fixed-point; CLI CURVELINEAR=n - default 20 (2.0)
    UBYTE curveRatio;      // live-updatable; x10 fixed-point; CLI CURVERATIO=n - default 5 (0.5)
};

struct BifrostMsg
{
    struct Message        msg;
    UBYTE                 command;  // BMSG_CMD_*
    ULONG                 value;    // command parameter (unused for now)
    ULONG                 result;   // 0xFFFFFFFF = error; else command-specific
    struct BifrostConfig  config;   // used by GET_CONFIG/SET_CONFIG only
};

#endif // Bifrost_H
