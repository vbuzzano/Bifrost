/*
 * Bifrost - Amiga Mouse and Keyboard Controller (client daemon)
 *
 * UDP auto-discovery: listens for Bifrost_DISCOVER broadcast on port 7891,
 * replies Bifrost_HERE, then TCP-connects to server on port 7890.
 * No IP configuration needed - server is discovered automatically.
 *
 * Usage: Bifrost [port]
 *   port  - TCP port (default: 7890, discovery: port+1 = 7891)
 *
 * (c) 2026 Vincent Buzzano - MIT License
 */

// --- Library bases first (VBCC inline pragma requirement) ---
struct ExecBase       *SysBase;
struct DosLibrary     *DOSBase;
struct Library        *SocketBase;
struct IntuitionBase  *IntuitionBase;

#include <proto/exec.h>
#include <proto/dos.h>

// These types must be defined before proto/bsdsocket.h (used by inline protos)
typedef ULONG  in_addr_t;
typedef LONG   socklen_t;

struct sockaddr
{
    UBYTE sa_len;
    UBYTE sa_family;
    BYTE  sa_data[14];
};

// Forward declaration - gethostbyname returns this; unused but needed by protos
struct hostent;

// bsdsocket inline protos also reference struct timeval via WaitSelect
#include <devices/timer.h>

// Now safe to include bsdsocket protos
#define CLIB_BSDSOCKET_PROTOS_H // skip missing clib/ header, use VBCC inline protos
#include <proto/bsdsocket.h>

#include <exec/execbase.h>
#include <exec/types.h>
#include <exec/io.h>
#include <dos/dostags.h>
#include <dos/dosextens.h>
#include <devices/inputevent.h>
#include <devices/input.h>
#include <newmouse.h>
#include <intuition/screens.h>
#include <intuition/intuitionbase.h>
#include <proto/intuition.h>

//===========================================================================
// Program constants
//===========================================================================

// ---> BEGIN GENERATED PROGRAM_CONSTANTS
#define PROGRAM_NAME "Bifrost"
#define PROGRAM_VERSION "0.3"
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
// Socket types  (not in NDK39 headers - defined before proto/bsdsocket.h above)
//===========================================================================

// in_addr_t, socklen_t, struct sockaddr, struct hostent - defined above

#define AF_INET         2
#define SOCK_STREAM     1
#define SOCK_DGRAM      2
#define IPPROTO_TCP     6
#define IPPROTO_UDP     17
#define SOL_SOCKET      0xFFFF  // AmigaOS/AmiTCP socket-level option
#define SO_REUSEADDR    0x0004  // allow re-bind after disconnect
#define SO_ERROR        0x1007  // BSD socket-level pending-error option

#define FIONBIO         0x8004667EUL  // BSD ioctl: set/clear non-blocking mode
#define EINPROGRESS     36            // BSD errno: connect() in progress (non-blocking)

// Non-blocking connect() timeout - fail fast instead of blocking on the
// TCP stack's default SYN retry timeout (can be ~20s when the server port
// is not yet accepting, e.g. right after a server restart).
#define CONNECT_TIMEOUT_SECS   3

struct in_addr
{
    ULONG s_addr;
};

struct sockaddr_in
{
    UBYTE          sin_len;
    UBYTE          sin_family;
    UWORD          sin_port;
    struct in_addr sin_addr;
    BYTE           sin_zero[8];     // total: 16 bytes
};

// fd_set with 1 ULONG bitmask - supports sockets 0..31
typedef struct
{
    ULONG fds_bits;
} fd_set_t;

#define FD_ZERO(s)      ((s)->fds_bits = 0UL)
#define FD_SET(n, s)    ((s)->fds_bits |= (1UL << (ULONG)(n)))
#define FD_ISSET(n, s)  ((s)->fds_bits & (1UL << (ULONG)(n)))

//===========================================================================
// Global state
//===========================================================================

static struct MsgPort   *s_InputPort = NULL;
static struct IOStdReq  *s_InputReq  = NULL;
static struct InputEvent s_eventBuf;

static struct MsgPort       *s_TimerPort = NULL;
static struct timerequest   *s_TimerReq  = NULL;

// Amiga-side cursor position estimate (updated from every injected delta)
// and the last known screen dimensions, both refreshed by correctPosition()
// (~150ms real elapsed time, checked opportunistically in the recv loop).
static WORD  s_curX    = 0;
static WORD  s_curY    = 0;
static WORD  s_screenW = 640;
static WORD  s_screenH = 512;
static ULONG s_lastCorrectionMs = 0;

// Edge resistance state machine (mirrors server/edge_resistance.py)
#define RESIST_NONE      0
#define RESIST_STARTED   1
#define RESIST_ACTIVE    2
#define RESIST_COOLDOWN  3

#define EDGE_TOLERANCE   12    // px from edge to be "in zone"
#define MIN_PUSH_DELTA   5     // px minimum coherent push to fire
#define PUSH_TIMEOUT_MS  120UL // ms resistance window before a push can fire
#define COOLDOWN_MS      500UL // ms after firing before it can fire again

static UBYTE s_resistState      = RESIST_NONE;
static ULONG s_resistStateSince = 0;

// TCP port - optionally overridden by CLI arg; discovery port = s_port + 1
static ULONG s_port = Bifrost_DEFAULT_PORT;

// Edge switching: s_pcEdge is the PC edge/corner (from the CLI arg) that
// switches focus to Amiga; s_amigaEdge = oppositeEdge(s_pcEdge) is our
// own local trigger edge, computed once after CLI parsing.
// EDGE_NONE (0x00) on both = edge switching disabled.
static UBYTE s_pcEdge    = EDGE_NONE;
static UBYTE s_amigaEdge = EDGE_NONE;

// Version string (read by AmigaOS version command)
const char version[] = VERSION_STRING;

//===========================================================================
// Forward declarations
//===========================================================================

static void daemon(void);
static BOOL daemonInit(void);
static void daemonCleanup(LONG sock);
static inline void injectEvent(struct InputEvent *ev);
static inline UWORD qualToAmiga(UBYTE flags);
static LONG connectWithTimeout(LONG sock, struct sockaddr_in *sa, LONG timeoutSecs);
static inline UBYTE oppositeEdge(UBYTE edge);
static BOOL parseEdgeToken(UBYTE *p, UBYTE *outMask, LONG *outLen);
static ULONG currentTimeMs(void);
static void correctPosition(void);
static UBYTE detectEdgeHits(WORD x, WORD y, WORD w, WORD h, UBYTE edgeMask);
static UBYTE percentAlongEdge(WORD x, WORD y, WORD w, WORD h, UBYTE edgeMask);
static void  positionFromPercent(UBYTE percent, WORD w, WORD h, UBYTE edgeMask,
                                  WORD *outX, WORD *outY);
static LONG pushDelta(UBYTE hits, WORD dx, WORD dy);
static BOOL resistUpdate(WORD x, WORD y, WORD dx, WORD dy, WORD w, WORD h, UBYTE edgeMask);

//===========================================================================
// Print macros
//===========================================================================

#define Print(text)         Printf(text "\n")
#define PrintF(fmt, ...)    Printf(fmt "\n", __VA_ARGS__)

//===========================================================================
// oppositeEdge - Mirror an edge/corner bitmask: TOP<->BOTTOM, LEFT<->RIGHT
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
// parseEdgeToken - Match a CLI token against the edge keyword table
//
// Case-insensitive via the (c|32) bit trick (same style as XMouseD's
// STOP/START/STATUS parsing), not stricmp(). Compound keywords (TOPLEFT
// etc.) are listed before their single-word prefixes so "TOPLEFT" is
// never matched as just "TOP".
//===========================================================================

typedef struct
{
    const char *name;
    UBYTE       mask;
} EdgeKeyword;

static const EdgeKeyword s_edgeKeywords[] =
{
    { "TOPLEFT",     EDGE_TOP    | EDGE_LEFT  },
    { "TOPRIGHT",    EDGE_TOP    | EDGE_RIGHT },
    { "BOTTOMLEFT",  EDGE_BOTTOM | EDGE_LEFT  },
    { "BOTTOMRIGHT", EDGE_BOTTOM | EDGE_RIGHT },
    { "TOP",         EDGE_TOP                 },
    { "BOTTOM",      EDGE_BOTTOM              },
    { "LEFT",        EDGE_LEFT                },
    { "RIGHT",       EDGE_RIGHT               },
};
#define NUM_EDGE_KEYWORDS (sizeof(s_edgeKeywords) / sizeof(s_edgeKeywords[0]))

static BOOL parseEdgeToken(UBYTE *p, UBYTE *outMask, LONG *outLen)
{
    LONG k;
    for (k = 0; k < (LONG)NUM_EDGE_KEYWORDS; k++)
    {
        const char *name  = s_edgeKeywords[k].name;
        LONG        len   = 0;
        BOOL        match = TRUE;

        while (name[len])
        {
            UBYTE pc = p[len];
            UBYTE nc = (UBYTE)name[len];
            if ((pc | 32) != (nc | 32)) { match = FALSE; break; }
            len++;
        }

        if (match)
        {
            UBYTE term = p[len];
            if (term == '\0' || term == ' ' || term == '\t' || term == '\n')
            {
                *outMask = s_edgeKeywords[k].mask;
                *outLen  = len;
                return TRUE;
            }
        }
    }
    return FALSE;
}

//===========================================================================
// _start() - Entry point, parse optional port/edge args, launch daemon process
//===========================================================================

LONG _start(void)
{
    struct Process              *proc;
    struct CommandLineInterface *cli;
    UBYTE                       *args;
    LONG                         i;
    LONG                         portNum;

    SysBase = *(struct ExecBase **)4L;
    DOSBase = (struct DosLibrary *)OpenLibrary("dos.library", 36);
    if (!DOSBase)
    {
        return RETURN_FAIL;
    }

    // Get raw CLI argument string
    args = (UBYTE *)GetArgStr();

    // Skip leading spaces
    while (*args == ' ' || *args == '\t')
    {
        args++;
    }

    // Show usage on '?'
    if (*args == '?')
    {
        Print("Usage: " PROGRAM_NAME " [port] [edge]");
        PrintF("  port - TCP port (default: %ld, discovery: port+1)", (LONG)Bifrost_DEFAULT_PORT);
        Print("  edge - TOP/BOTTOM/LEFT/RIGHT/TOPLEFT/TOPRIGHT/BOTTOMLEFT/BOTTOMRIGHT");
        Print("         PC edge that switches focus to Amiga (default: none = disabled)");
        Print("  Server is discovered automatically via UDP broadcast.");
        CloseLibrary((struct Library *)DOSBase);
        return RETURN_OK;
    }

    // Parse up to 2 whitespace-separated tokens, any order:
    // a numeric port and/or an edge keyword.
    {
        LONG tok;
        for (tok = 0; tok < 2; tok++)
        {
            while (*args == ' ' || *args == '\t')
            {
                args++;
            }
            if (*args == 0 || *args == '\n')
            {
                break;
            }

            if (*args >= '0' && *args <= '9')
            {
                portNum = 0;
                i = 0;
                while (*args >= '0' && *args <= '9' && i < 5)
                {
                    portNum = portNum * 10 + (*args - '0');
                    args++;
                    i++;
                }
                if (portNum > 0 && portNum < 65536)
                {
                    s_port = (ULONG)portNum;
                }
            }
            else
            {
                UBYTE edgeMask;
                LONG  edgeLen;
                if (parseEdgeToken(args, &edgeMask, &edgeLen))
                {
                    s_pcEdge = edgeMask;
                    args += edgeLen;
                }
                else
                {
                    // Unknown token - skip it and keep parsing
                    while (*args && *args != ' ' && *args != '\t' && *args != '\n')
                    {
                        args++;
                    }
                }
            }
        }
    }

    s_amigaEdge = oppositeEdge(s_pcEdge);

    // Launch daemon as background process
    if (!CreateNewProcTags(
        NP_Entry,    (ULONG)daemon,
        NP_Name,     (ULONG)PROGRAM_NAME " [daemon]",
        NP_Priority, 0,
        TAG_DONE))
    {
        Print(PROGRAM_NAME ": failed to start daemon");
        CloseLibrary((struct Library *)DOSBase);
        return RETURN_FAIL;
    }

    // Detach from CLI (WBM pattern) - shell returns immediately
    proc = (struct Process *)FindTask(NULL);
    if (proc->pr_CLI)
    {
        cli = BADDR(proc->pr_CLI);
        cli->cli_Module = 0;
    }

    PrintF(PROGRAM_NAME ": daemon started (listening on UDP port %ld)",
           (LONG)(s_port + 1));
    if (s_pcEdge != EDGE_NONE)
    {
        PrintF(PROGRAM_NAME ": edge switching enabled (PC edge=0x%02lx, Amiga edge=0x%02lx)",
               (LONG)s_pcEdge, (LONG)s_amigaEdge);
    }

    CloseLibrary((struct Library *)DOSBase);
    return RETURN_OK;
}

//===========================================================================
// qualToAmiga - Map protocol flags byte to Amiga qualifier word
//===========================================================================

static inline UWORD qualToAmiga(UBYTE flags)
{
    UWORD q = 0;
    if (flags & QUAL_LSHIFT)  q |= IEQUALIFIER_LSHIFT;
    if (flags & QUAL_RSHIFT)  q |= IEQUALIFIER_RSHIFT;
    if (flags & QUAL_CTRL)    q |= IEQUALIFIER_CONTROL;
    if (flags & QUAL_LALT)    q |= IEQUALIFIER_LALT;
    if (flags & QUAL_RALT)    q |= IEQUALIFIER_RALT;
    if (flags & QUAL_LBUTTON) q |= IEQUALIFIER_LEFTBUTTON;
    if (flags & QUAL_RBUTTON) q |= IEQUALIFIER_RBUTTON;
    // Server sends a single combined bit (doesn't distinguish which Amiga
    // key) - set both qualifiers so shortcuts checking either one fire.
    if (flags & QUAL_AMIGA)   q |= IEQUALIFIER_LCOMMAND | IEQUALIFIER_RCOMMAND;
    return q;
}

//===========================================================================
// injectEvent - Synchronous event injection via input.device
//===========================================================================

static inline void injectEvent(struct InputEvent *ev)
{
    s_InputReq->io_Command = IND_WRITEEVENT;
    s_InputReq->io_Data    = (APTR)ev;
    s_InputReq->io_Length  = sizeof(struct InputEvent);
    DoIO((struct IORequest *)s_InputReq);
}

//===========================================================================
// currentTimeMs - Synchronous timer.device query (TR_GETSYSTIME)
//
// A one-shot DoIO, not a periodic interrupt-driven timer - same cost
// order as the injectEvent() calls already made routinely. Used both for
// the ~150ms periodic correctPosition() cadence and the edge resistance
// state machine's timing.
//===========================================================================

static ULONG currentTimeMs(void)
{
    s_TimerReq->tr_node.io_Command = TR_GETSYSTIME;
    DoIO((struct IORequest *)s_TimerReq);
    return (ULONG)(s_TimerReq->tr_time.tv_secs * 1000UL
                  + s_TimerReq->tr_time.tv_micro / 1000UL);
}

//===========================================================================
// correctPosition - Refresh s_curX/s_curY/s_screenW/s_screenH from
// Intuition ground truth. Corrects any drift in the locally-accumulated
// position and picks up screen-mode changes within one poll interval.
//
// Uses IntuitionBase->ActiveScreen (the frontmost screen), not
// LockPubScreen(NULL) (the *default* public screen, normally Workbench
// regardless of what's actually on top) - so edge detection tracks
// whichever screen the user is really looking at (e.g. an IBrowse screen
// at a different resolution than Workbench), not just Workbench.
//===========================================================================

static void correctPosition(void)
{
    ULONG ibLock = LockIBase(0);
    struct Screen *scr = IntuitionBase->ActiveScreen;
    if (scr)
    {
        s_curX    = scr->MouseX;
        s_curY    = scr->MouseY;
        s_screenW = scr->Width;
        s_screenH = scr->Height;
    }
    UnlockIBase(ibLock);
}

//===========================================================================
// Edge resistance state machine - mirrors server/edge_resistance.py.
// Driven by mouse-move events (called from the PKT_MOUSE_MOVE case), not
// by a timer - a cursor left parked in the zone with no further movement
// never re-evaluates, so it can never re-fire on its own.
//===========================================================================

// A straight-edge mask (only a horizontal OR only a vertical bit) fires
// from anywhere along that single edge. A corner mask (one horizontal
// bit AND one vertical bit, e.g. TOP|LEFT) only fires in the actual
// corner box - both axes must be hit simultaneously - so e.g. TOPLEFT
// does not also fire along the rest of the left edge or the rest of
// the top edge.
static UBYTE detectEdgeHits(WORD x, WORD y, WORD w, WORD h, UBYTE edgeMask)
{
    UBYTE wantH = edgeMask & (EDGE_LEFT | EDGE_RIGHT);
    UBYTE wantV = edgeMask & (EDGE_TOP | EDGE_BOTTOM);
    UBYTE hitH  = 0;
    UBYTE hitV  = 0;

    if ((edgeMask & EDGE_LEFT) && x <= EDGE_TOLERANCE)
        hitH = EDGE_LEFT;
    else if ((edgeMask & EDGE_RIGHT) && x >= w - 1 - EDGE_TOLERANCE)
        hitH = EDGE_RIGHT;

    if ((edgeMask & EDGE_TOP) && y <= EDGE_TOLERANCE)
        hitV = EDGE_TOP;
    else if ((edgeMask & EDGE_BOTTOM) && y >= h - 1 - EDGE_TOLERANCE)
        hitV = EDGE_BOTTOM;

    if (wantH && wantV)
        return (hitH && hitV) ? (hitH | hitV) : 0;
    return hitH | hitV;
}

// percentAlongEdge - mirrors server/edge_resistance.py's percent_along_edge.
// Returns 0 for a corner mask (a corner is a fixed point, not a range -
// the receiver ignores this value in that case).
static UBYTE percentAlongEdge(WORD x, WORD y, WORD w, WORD h, UBYTE edgeMask)
{
    UBYTE wantH = edgeMask & (EDGE_LEFT | EDGE_RIGHT);
    UBYTE wantV = edgeMask & (EDGE_TOP | EDGE_BOTTOM);

    if (wantH && wantV)
        return 0;

    if (wantH)
    {
        /* LEFT/RIGHT are vertical edges - position along them is the Y axis */
        LONG denom = (LONG)h - 1;
        if (denom <= 0) return 0;
        return (UBYTE)(((LONG)y * 255L) / denom);
    }
    if (wantV)
    {
        /* TOP/BOTTOM are horizontal edges - position along them is the X axis */
        LONG denom = (LONG)w - 1;
        if (denom <= 0) return 0;
        return (UBYTE)(((LONG)x * 255L) / denom);
    }
    return 0;
}

// positionFromPercent - mirrors server/edge_resistance.py's
// position_from_percent. For a corner mask, percent is ignored and the
// fixed corner coordinates are returned unconditionally.
static void positionFromPercent(UBYTE percent, WORD w, WORD h, UBYTE edgeMask,
                                 WORD *outX, WORD *outY)
{
    if (edgeMask & EDGE_LEFT)
        *outX = 0;
    else if (edgeMask & EDGE_RIGHT)
        *outX = (WORD)(w - 1);
    else
        *outX = (WORD)(((LONG)percent * ((LONG)w - 1)) / 255L);

    if (edgeMask & EDGE_TOP)
        *outY = 0;
    else if (edgeMask & EDGE_BOTTOM)
        *outY = (WORD)(h - 1);
    else
        *outY = (WORD)(((LONG)percent * ((LONG)h - 1)) / 255L);
}

static LONG pushDelta(UBYTE hits, WORD dx, WORD dy)
{
    BOOL pushH = ((hits & EDGE_LEFT) && dx < 0) || ((hits & EDGE_RIGHT) && dx > 0);
    BOOL pushV = ((hits & EDGE_TOP) && dy < 0) || ((hits & EDGE_BOTTOM) && dy > 0);
    LONG absDx = (dx < 0) ? -dx : dx;
    LONG absDy = (dy < 0) ? -dy : dy;
    BOOL isCorner = (hits & (EDGE_LEFT | EDGE_RIGHT)) && (hits & (EDGE_TOP | EDGE_BOTTOM));

    if (isCorner)
    {
        if (pushH && !pushV) return (absDy == 0) ? absDx : 0;
        if (pushV && !pushH) return (absDx == 0) ? absDy : 0;
        if (pushH || pushV)  return (absDx > absDy) ? absDx : absDy;
        return 0;
    }

    if (pushH) return absDx;
    if (pushV) return absDy;
    return 0;
}

// Returns TRUE exactly once per completed push-through-edge gesture.
static BOOL resistUpdate(WORD x, WORD y, WORD dx, WORD dy, WORD w, WORD h, UBYTE edgeMask)
{
    UBYTE hits;
    ULONG now;

    if (edgeMask == EDGE_NONE)
    {
        s_resistState = RESIST_NONE;
        return FALSE;
    }

    hits = detectEdgeHits(x, y, w, h, edgeMask);
    now  = currentTimeMs();

    if (s_resistState != RESIST_NONE && hits == EDGE_NONE)
    {
        s_resistState = RESIST_NONE;
        return FALSE;
    }

    switch (s_resistState)
    {
        case RESIST_NONE:
            if (hits != EDGE_NONE)
            {
                s_resistState      = RESIST_STARTED;
                s_resistStateSince = now;
            }
            return FALSE;

        case RESIST_STARTED:
            if (now - s_resistStateSince >= PUSH_TIMEOUT_MS)
            {
                s_resistState = RESIST_ACTIVE;
            }
            return FALSE;

        case RESIST_ACTIVE:
            if (hits != EDGE_NONE && pushDelta(hits, dx, dy) >= MIN_PUSH_DELTA)
            {
                s_resistState      = RESIST_COOLDOWN;
                s_resistStateSince = now;
                return TRUE;
            }
            return FALSE;

        case RESIST_COOLDOWN:
            if (now - s_resistStateSince >= COOLDOWN_MS)
            {
                s_resistState = RESIST_ACTIVE;
            }
            return FALSE;
    }

    return FALSE;
}

//===========================================================================
// connectWithTimeout - Non-blocking connect() with bounded wait
//
// A plain blocking connect() relies on the TCP stack's own SYN retry
// timeout (can be ~20s) when the peer doesn't respond, e.g. right after
// the server process restarts and its listen socket isn't up yet. This
// fails fast after timeoutSecs instead, so the outer discovery loop can
// retry on the next broadcast (every ~3s) rather than stalling for ~20s.
//
// Returns: 0 on success, -1 on failure or timeout.
//===========================================================================

static LONG connectWithTimeout(LONG sock, struct sockaddr_in *sa, LONG timeoutSecs)
{
    fd_set_t       writeFds;
    struct timeval tv;
    ULONG          nonblock;
    LONG           rc;
    LONG           sockErr;
    socklen_t      sockErrLen;

    nonblock = 1;
    IoctlSocket(sock, FIONBIO, (APTR)&nonblock);

    rc = connect(sock, (struct sockaddr *)sa, (LONG)sizeof(*sa));
    if (rc == 0)
    {
        nonblock = 0;
        IoctlSocket(sock, FIONBIO, (APTR)&nonblock);
        return 0;   // connected immediately (rare, e.g. localhost)
    }

    if (Errno() != EINPROGRESS)
    {
        nonblock = 0;
        IoctlSocket(sock, FIONBIO, (APTR)&nonblock);
        return -1;  // real failure (e.g. ECONNREFUSED) - no need to wait
    }

    FD_ZERO(&writeFds);
    FD_SET((ULONG)sock, &writeFds);
    tv.tv_secs = (ULONG)timeoutSecs;
    tv.tv_micro = 0;

    rc = WaitSelect(sock + 1, NULL, (APTR)&writeFds, NULL, &tv, NULL);

    nonblock = 0;
    IoctlSocket(sock, FIONBIO, (APTR)&nonblock);

    if (rc <= 0 || !FD_ISSET((ULONG)sock, &writeFds))
    {
        return -1;  // timeout - server not accepting yet
    }

    // Writable now - check if the connection actually succeeded
    sockErr    = 0;
    sockErrLen = (socklen_t)sizeof(sockErr);
    getsockopt(sock, SOL_SOCKET, SO_ERROR, (APTR)&sockErr, &sockErrLen);

    return (sockErr == 0) ? 0 : -1;
}

//===========================================================================
// daemonInit - Open bsdsocket.library + input.device
//===========================================================================

static BOOL daemonInit(void)
{
    LONG i;

    SysBase = *(struct ExecBase **)4L;
    DOSBase = (struct DosLibrary *)OpenLibrary("dos.library", 36);
    if (!DOSBase)
    {
        return FALSE;
    }

    // Open TCP/IP stack (AmiTCP, Roadshow, ApolloOS)
    SocketBase = OpenLibrary("bsdsocket.library", 4);
    if (!SocketBase)
    {
        Print(PROGRAM_NAME ": bsdsocket.library not found (TCP/IP stack required)");
        return FALSE;
    }

    // Open intuition.library for cursor position / screen dimensions
    IntuitionBase = (struct IntuitionBase *)OpenLibrary("intuition.library", 36);
    if (!IntuitionBase)
    {
        Print(PROGRAM_NAME ": intuition.library not found");
        return FALSE;
    }

    // Open timer.device for the periodic correction / resistance clock
    s_TimerPort = CreateMsgPort();
    if (!s_TimerPort)
    {
        return FALSE;
    }
    s_TimerReq = (struct timerequest *)CreateIORequest(s_TimerPort, sizeof(struct timerequest));
    if (!s_TimerReq)
    {
        DeleteMsgPort(s_TimerPort);
        s_TimerPort = NULL;
        return FALSE;
    }
    if (OpenDevice("timer.device", UNIT_MICROHZ, (struct IORequest *)s_TimerReq, 0))
    {
        DeleteIORequest((struct IORequest *)s_TimerReq);
        DeleteMsgPort(s_TimerPort);
        s_TimerPort = NULL;
        s_TimerReq  = NULL;
        return FALSE;
    }

    // Open input.device for event injection
    s_InputPort = CreateMsgPort();
    if (!s_InputPort)
    {
        return FALSE;
    }
    s_InputReq = (struct IOStdReq *)CreateIORequest(s_InputPort, sizeof(struct IOStdReq));
    if (!s_InputReq)
    {
        DeleteMsgPort(s_InputPort);
        s_InputPort = NULL;
        return FALSE;
    }
    if (OpenDevice("input.device", 0, (struct IORequest *)s_InputReq, 0))
    {
        DeleteIORequest((struct IORequest *)s_InputReq);
        DeleteMsgPort(s_InputPort);
        s_InputPort = NULL;
        s_InputReq  = NULL;
        return FALSE;
    }

    // Zero reusable event buffer
    for (i = 0; i < (LONG)sizeof(s_eventBuf); i++)
    {
        ((UBYTE *)&s_eventBuf)[i] = 0;
    }

    return TRUE;
}

//===========================================================================
// daemonCleanup - Release all resources
//===========================================================================

static void daemonCleanup(LONG sock)
{
    if (sock >= 0 && SocketBase)
    {
        CloseSocket(sock);
    }
    if (s_InputReq)
    {
        CloseDevice((struct IORequest *)s_InputReq);
        DeleteIORequest((struct IORequest *)s_InputReq);
        s_InputReq = NULL;
    }
    if (s_InputPort)
    {
        DeleteMsgPort(s_InputPort);
        s_InputPort = NULL;
    }
    if (s_TimerReq)
    {
        CloseDevice((struct IORequest *)s_TimerReq);
        DeleteIORequest((struct IORequest *)s_TimerReq);
        s_TimerReq = NULL;
    }
    if (s_TimerPort)
    {
        DeleteMsgPort(s_TimerPort);
        s_TimerPort = NULL;
    }
    if (IntuitionBase)
    {
        CloseLibrary((struct Library *)IntuitionBase);
        IntuitionBase = NULL;
    }
    if (SocketBase)
    {
        CloseLibrary(SocketBase);
        SocketBase = NULL;
    }
    if (DOSBase)
    {
        CloseLibrary((struct Library *)DOSBase);
        DOSBase = NULL;
    }
}

//===========================================================================
// daemon() - Background: UDP discovery loop -> TCP connect -> event recv loop
//
// Outer loop: wait for Bifrost_DISCOVER broadcast on UDP port (s_port+1),
//   reply Bifrost_HERE, then TCP connect to sender on s_port.
// Inner loop: recv 8-byte packets and inject events.
//   On disconnect: close TCP, go back to outer UDP discovery loop.
//   CTRL+C: exit both loops cleanly.
//===========================================================================

static void daemon(void)
{
    struct sockaddr_in  discSa;         // UDP bind address
    struct sockaddr_in  fromSa;         // UDP sender (= server IP)
    socklen_t           fromLen;
    struct sockaddr_in  tcpSa;          // TCP connect address
    fd_set_t            readFds;
    ULONG               sigMask;
    UBYTE               pkt[PKT_SIZE];
    UBYTE               buf[32];
    LONG                udpSock    = -1;
    LONG                tcpSock    = -1;
    LONG                rc;
    LONG                i;
    LONG                recvd;
    LONG                reuseVal;
    LONG                discPort;
    BOOL                quit       = FALSE;
    BOOL                disconnected;

    if (!daemonInit())
    {
        goto done;
    }

    discPort = (LONG)(s_port + 1);

    // Create UDP socket for receiving discovery broadcasts
    udpSock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (udpSock < 0)
    {
        Print(PROGRAM_NAME ": UDP socket() failed");
        goto done;
    }

    reuseVal = 1;
    setsockopt(udpSock, SOL_SOCKET, SO_REUSEADDR,
               (char *)&reuseVal, (LONG)sizeof(reuseVal));

    for (i = 0; i < (LONG)sizeof(discSa); i++) ((UBYTE *)&discSa)[i] = 0;
    discSa.sin_len         = (UBYTE)sizeof(discSa);
    discSa.sin_family      = (UBYTE)AF_INET;
    discSa.sin_port        = (UWORD)discPort;
    discSa.sin_addr.s_addr = 0UL;      // INADDR_ANY

    if (bind(udpSock, (struct sockaddr *)&discSa, (LONG)sizeof(discSa)) != 0)
    {
        PrintF(PROGRAM_NAME ": bind UDP port %ld failed (err=%ld)",
               discPort, (LONG)Errno());
        goto done;
    }

    Print(PROGRAM_NAME ": waiting for server... (CTRL+C to quit)");

    // =========================================================
    // Outer loop: discovery
    // =========================================================
    while (!quit)
    {
        FD_ZERO(&readFds);
        FD_SET((ULONG)udpSock, &readFds);
        sigMask = SIGBREAKF_CTRL_C;

        rc = WaitSelect(udpSock + 1, (APTR)&readFds, NULL, NULL, NULL, &sigMask);

        if (sigMask & SIGBREAKF_CTRL_C)
        {
            quit = TRUE;
            break;
        }

        if (rc <= 0 || !FD_ISSET((ULONG)udpSock, &readFds))
        {
            continue;
        }

        // Receive UDP packet and record sender address (= server)
        for (i = 0; i < (LONG)sizeof(fromSa); i++) ((UBYTE *)&fromSa)[i] = 0;
        fromLen = (socklen_t)sizeof(fromSa);
        rc = recvfrom(udpSock, (APTR)buf, (LONG)(sizeof(buf) - 1), 0,
                      (struct sockaddr *)&fromSa, &fromLen);
        if (rc <= 0)
        {
            continue;
        }
        buf[rc] = 0;

        // Validate message == "Bifrost_DISCOVER"
        {
            BOOL ok = TRUE;
            if (rc < DISC_MSG_LEN) ok = FALSE;
            if (ok)
            {
                for (i = 0; i < DISC_MSG_LEN; i++)
                {
                    if (buf[i] != (UBYTE)DISC_MSG[i]) { ok = FALSE; break; }
                }
            }
            if (!ok)
            {
                PrintF(PROGRAM_NAME ": ignoring invalid UDP: %ld bytes", rc);
                continue;
            }
        }

        // Reply Bifrost_HERE to the server
        sendto(udpSock, (APTR)DISC_REPLY, DISC_REPLY_LEN, 0,
               (struct sockaddr *)&fromSa, (LONG)sizeof(fromSa));

        // TCP connect to server (same IP, TCP port s_port)
        tcpSock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (tcpSock < 0)
        {
            Print(PROGRAM_NAME ": socket() failed");
            continue;
        }

        for (i = 0; i < (LONG)sizeof(tcpSa); i++) ((UBYTE *)&tcpSa)[i] = 0;
        tcpSa.sin_len         = (UBYTE)sizeof(tcpSa);
        tcpSa.sin_family      = (UBYTE)AF_INET;
        tcpSa.sin_port        = (UWORD)s_port;
        tcpSa.sin_addr.s_addr = fromSa.sin_addr.s_addr;  // server IP from UDP sender

        PrintF(PROGRAM_NAME ": discovered server, connecting to %ld.%ld.%ld.%ld:%ld",
               (LONG)(fromSa.sin_addr.s_addr >> 24) & 0xFF,
               (LONG)(fromSa.sin_addr.s_addr >> 16) & 0xFF,
               (LONG)(fromSa.sin_addr.s_addr >> 8) & 0xFF,
               (LONG)fromSa.sin_addr.s_addr & 0xFF,
               (LONG)s_port);

        if (connectWithTimeout(tcpSock, &tcpSa, CONNECT_TIMEOUT_SECS) != 0)
        {
            PrintF(PROGRAM_NAME ": connect failed/timeout (err=%ld)", (LONG)Errno());
            CloseSocket(tcpSock);
            tcpSock = -1;
            continue;
        }

        Print(PROGRAM_NAME ": connected - CTRL+C to quit");

        // Fresh per-connection state: resistance machine, position/screen
        // ground truth, and the correction clock.
        s_resistState = RESIST_NONE;
        correctPosition();
        s_lastCorrectionMs = currentTimeMs();

        // Announce our PC edge configuration to the server (0 = disabled)
        {
            UBYTE helloPkt[PKT_SIZE];
            for (i = 0; i < PKT_SIZE; i++) helloPkt[i] = 0;
            helloPkt[0] = PKT_HELLO;
            helloPkt[6] = s_pcEdge;
            send(tcpSock, (APTR)helloPkt, PKT_SIZE, 0);
        }

        // =====================================================
        // Inner loop: receive events and inject into Amiga
        // =====================================================
        disconnected = FALSE;
        while (!quit && !disconnected)
        {
            FD_ZERO(&readFds);
            FD_SET((ULONG)tcpSock, &readFds);
            sigMask = SIGBREAKF_CTRL_C;

            rc = WaitSelect(tcpSock + 1, (APTR)&readFds, NULL, NULL, NULL, &sigMask);

            if (sigMask & SIGBREAKF_CTRL_C)
            {
                quit = TRUE;
                break;
            }

            if (rc < 0)
            {
                Print(PROGRAM_NAME ": WaitSelect error");
                disconnected = TRUE;
                break;
            }

            if (rc > 0 && FD_ISSET((ULONG)tcpSock, &readFds))
            {
                // Receive exactly PKT_SIZE bytes (handle partial recv)
                recvd = 0;
                while (recvd < PKT_SIZE)
                {
                    rc = recv(tcpSock, (APTR)(pkt + recvd), PKT_SIZE - recvd, 0);
                    if (rc <= 0)
                    {
                        Print(PROGRAM_NAME ": server disconnected");
                        disconnected = TRUE;
                        break;
                    }
                    recvd += rc;
                }

                if (disconnected) break;

                // Dispatch packet by type
                switch (pkt[0])
                {
                    case PKT_MOUSE_MOVE:
                    {
                        // bytes 2-3 and 4-5 are big-endian INT16 deltas
                        WORD dx = (WORD)(((UWORD)pkt[2] << 8) | (UWORD)pkt[3]);
                        WORD dy = (WORD)(((UWORD)pkt[4] << 8) | (UWORD)pkt[5]);
                        ULONG nowMs;

                        s_eventBuf.ie_Class     = IECLASS_RAWMOUSE;
                        s_eventBuf.ie_Code      = IECODE_NOBUTTON;
                        s_eventBuf.ie_Qualifier = IEQUALIFIER_RELATIVEMOUSE | qualToAmiga(pkt[1]);
                        s_eventBuf.ie_X         = dx;
                        s_eventBuf.ie_Y         = dy;
                        injectEvent(&s_eventBuf);

                        // Update local position estimate, clamped to the
                        // last known screen dimensions.
                        s_curX = (WORD)(s_curX + dx);
                        s_curY = (WORD)(s_curY + dy);
                        if (s_curX < 0) s_curX = 0;
                        if (s_curX >= s_screenW) s_curX = s_screenW - 1;
                        if (s_curY < 0) s_curY = 0;
                        if (s_curY >= s_screenH) s_curY = s_screenH - 1;

                        // Periodic drift/screen-dimension correction
                        // (~150ms of real elapsed time)
                        nowMs = currentTimeMs();
                        if (nowMs - s_lastCorrectionMs >= 150UL)
                        {
                            correctPosition();
                            s_lastCorrectionMs = nowMs;
                        }

                        // Edge resistance: request switch back to PC.
                        // Suppress while dragging (button held) - reuses
                        // resistUpdate's own EDGE_NONE handling to force/
                        // keep the state machine at RESIST_NONE.
                        if (resistUpdate(s_curX, s_curY, dx, dy, s_screenW, s_screenH,
                                          (pkt[1] & (QUAL_LBUTTON | QUAL_RBUTTON)) ? EDGE_NONE : s_amigaEdge))
                        {
                            UBYTE trigPkt[PKT_SIZE];
                            LONG  ti;
                            for (ti = 0; ti < PKT_SIZE; ti++) trigPkt[ti] = 0;
                            trigPkt[0] = PKT_EDGE_TRIGGER;
                            trigPkt[6] = percentAlongEdge(s_curX, s_curY, s_screenW, s_screenH, s_amigaEdge);
                            send(tcpSock, (APTR)trigPkt, PKT_SIZE, 0);
                            Print(PROGRAM_NAME ": edge trigger fired -> switching to PC");
                        }
                        break;
                    }

                    case PKT_MOUSE_BTN:
                    {
                        UWORD code;

                        switch (pkt[6])
                        {
                            case BTN_LEFT:   code = IECODE_LBUTTON; break;
                            case BTN_RIGHT:  code = IECODE_RBUTTON; break;
                            case BTN_MIDDLE: code = IECODE_MBUTTON; break;
                            default:         code = IECODE_LBUTTON; break;
                        }
                        if (pkt[7] == PKT_UP)
                        {
                            code |= IECODE_UP_PREFIX;
                        }
                        s_eventBuf.ie_Class     = IECLASS_RAWMOUSE;
                        s_eventBuf.ie_Code      = code;
                        s_eventBuf.ie_Qualifier = qualToAmiga(pkt[1]);
                        s_eventBuf.ie_X         = 0;
                        s_eventBuf.ie_Y         = 0;
                        injectEvent(&s_eventBuf);
                        break;
                    }

                    case PKT_KEY:
                    {
                        // pkt[6] = Amiga rawkey code (mapped on server side)
                        UWORD code = (UWORD)pkt[6];
                        if (pkt[7] == PKT_UP)
                        {
                            code |= IECODE_UP_PREFIX;
                        }
                        s_eventBuf.ie_Class     = IECLASS_RAWKEY;
                        s_eventBuf.ie_Code      = code;
                        s_eventBuf.ie_Qualifier = qualToAmiga(pkt[1]);
                        s_eventBuf.ie_X         = 0;
                        s_eventBuf.ie_Y         = 0;
                        injectEvent(&s_eventBuf);
                        break;
                    }

                    case PKT_WHEEL:
                    {
                        // pkt[6] = WHEEL_UP (0) or WHEEL_DOWN (1)
                        // NewMouse standard: issue under BOTH IECLASS_RAWKEY
                        // (modern apps) and IECLASS_NEWMOUSE (legacy apps).
                        UWORD code = (pkt[6] == WHEEL_UP) ? NM_WHEEL_UP : NM_WHEEL_DOWN;
                        s_eventBuf.ie_Code      = code;
                        s_eventBuf.ie_Qualifier = qualToAmiga(pkt[1]);
                        s_eventBuf.ie_X         = 0;
                        s_eventBuf.ie_Y         = 0;

                        s_eventBuf.ie_Class = IECLASS_RAWKEY;
                        injectEvent(&s_eventBuf);

                        s_eventBuf.ie_Class = IECLASS_NEWMOUSE;
                        injectEvent(&s_eventBuf);
                        break;
                    }

                    case PKT_FOCUS_ENTER:
                    {
                        UBYTE percent = pkt[6];
                        WORD  targetX, targetY;
                        WORD  warpDx, warpDy;

                        // s_curX/s_curY are only refreshed opportunistically
                        // inside the PKT_MOUSE_MOVE case, which never runs
                        // while focus is on PC - if the Amiga's own physical
                        // mouse moved independently during that time, the
                        // tracked position is stale. Force a fresh read now,
                        // right before computing the warp delta, so the
                        // relative move lands on the true target regardless.
                        correctPosition();

                        positionFromPercent(percent, s_screenW, s_screenH, s_amigaEdge,
                                            &targetX, &targetY);
                        warpDx = (WORD)(targetX - s_curX);
                        warpDy = (WORD)(targetY - s_curY);

                        s_eventBuf.ie_Class     = IECLASS_RAWMOUSE;
                        s_eventBuf.ie_Code      = IECODE_NOBUTTON;
                        s_eventBuf.ie_Qualifier = IEQUALIFIER_RELATIVEMOUSE;
                        s_eventBuf.ie_X         = warpDx;
                        s_eventBuf.ie_Y         = warpDy;
                        injectEvent(&s_eventBuf);

                        s_curX = targetX;
                        s_curY = targetY;
                        break;
                    }

                    case PKT_PING:
                        break;

                    default:
                        break;
                }
            }
        }

        // TCP session ended - close socket, loop back to discovery
        CloseSocket(tcpSock);
        tcpSock = -1;
        if (!quit)
        {
            Print(PROGRAM_NAME ": reconnecting - waiting for server...");
        }
    }

done:
    if (tcpSock >= 0 && SocketBase) CloseSocket(tcpSock);
    daemonCleanup(udpSock);
}
