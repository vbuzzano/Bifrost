/*
 * Bifrost - Public IPC API for control port messaging
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

#define Bifrost_DEFAULT_PORT 7890
#define Bifrost_DISC_PORT    7891    // UDP discovery port (= TCP port + 1)


#define BMSG_CMD_QUIT        0   // Stop daemon (disconnects from PC first)
#define BMSG_CMD_GET_STATUS  1   // Query connection status
#define BMSG_CMD_GET_CONFIG  2   // Read current port/edge/cx-enabled
#define BMSG_CMD_SET_CONFIG  3   // Apply new edge/cx-enabled (port ignored -
                                 // immutable at runtime, needs a restart)

#define CONTROL_REPLY_TIMEOUT 2  // seconds to wait for daemon reply


// Edge/corner bitmask (matches server/edge_resistance.py EDGE_*)
#define EDGE_NONE       0x00
#define EDGE_TOP        0x01
#define EDGE_BOTTOM     0x02
#define EDGE_LEFT       0x04
#define EDGE_RIGHT      0x08

// Configurable daemon state. GET_CONFIG copies the daemon's current values
// into this; SET_CONFIG's setConfig() (daemon.c) applies every field
// except port. New settings land here, not as new BMSG_CMD_* values or new
// CLI arguments - see design spec for the rationale.
struct BifrostConfig
{
    ULONG port;       // informational on GET_CONFIG; ignored by setConfig()
    UBYTE pcEdge;      // live-updatable
    BOOL  cxEnabled;   // live-updatable
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
