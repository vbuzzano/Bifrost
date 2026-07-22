/*
 * Bifrost - Amiga Mouse and Keyboard Controller (CLI entry point)
 *
 * Parses CLI args (port/edge, or STATUS/STOP to control an already-running
 * instance), then launches main.c's daemon() as a detached background
 * process. See main.c for the actual UDP discovery / TCP connection /
 * event injection loop.
 *
 * Usage: Bifrost [port] [edge] | STATUS | STOP
 *
 * (c) 2026 Vincent Buzzano - MIT License
 */

// --- Library bases first (VBCC inline pragma requirement) ---
struct ExecBase   *SysBase;
struct DosLibrary *DOSBase;

#include <proto/exec.h>
#include <proto/dos.h>
#include <exec/execbase.h>
#include <exec/types.h>
#include <exec/io.h>
#include <dos/dostags.h>
#include <dos/dosextens.h>
#include <devices/timer.h>

#include "bifrost.h"
#include "daemon.h"

//===========================================================================
// Global state
//===========================================================================

// Shared with main.c (see bifrost.h's "extern" declarations) - set here
// from CLI args, read by daemon() once launched via CreateNewProcTags.
ULONG s_port       = Bifrost_DEFAULT_PORT;
UBYTE s_pcEdge      = EDGE_NONE;
UBYTE s_amigaEdge   = EDGE_NONE;

// Version string (read by AmigaOS version command)
const char version[] = VERSION_STRING;

//===========================================================================
// Forward declarations
//===========================================================================

static BOOL parseEdgeToken(UBYTE *p, UBYTE *outMask, LONG *outLen);
static ULONG sendBifrostMessage(struct MsgPort *port, UBYTE cmd, ULONG value);
static ULONG sendConfigMessage(struct MsgPort *port, UBYTE cmd, struct BifrostConfig *cfg);

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
// sendBifrostMessage - Send a control message to the running daemon's
// public port and wait for its reply, with a timeout in case the daemon
// is wedged or the message is somehow never processed.
//===========================================================================

static ULONG sendBifrostMessage(struct MsgPort *port, UBYTE cmd, ULONG value)
{
    struct MsgPort      *replyPort = NULL;
    struct BifrostMsg    *msg       = NULL;
    struct MsgPort       *timerPort = NULL;
    struct timerequest   *timerReq  = NULL;
    ULONG                 result    = 0xFFFFFFFF;  // error by default
    ULONG                 replySig, timerSig, signals;

    replyPort = CreateMsgPort();
    if (!replyPort)
    {
        return result;
    }

    timerPort = CreateMsgPort();
    if (!timerPort)
    {
        DeleteMsgPort(replyPort);
        return result;
    }

    timerReq = (struct timerequest *)CreateIORequest(timerPort, sizeof(struct timerequest));
    if (!timerReq)
    {
        DeleteMsgPort(timerPort);
        DeleteMsgPort(replyPort);
        return result;
    }

    if (OpenDevice("timer.device", UNIT_VBLANK, (struct IORequest *)timerReq, 0))
    {
        DeleteIORequest((struct IORequest *)timerReq);
        DeleteMsgPort(timerPort);
        DeleteMsgPort(replyPort);
        return result;
    }

    msg = (struct BifrostMsg *)AllocMem(sizeof(struct BifrostMsg), MEMF_PUBLIC | MEMF_CLEAR);
    if (!msg)
    {
        CloseDevice((struct IORequest *)timerReq);
        DeleteIORequest((struct IORequest *)timerReq);
        DeleteMsgPort(timerPort);
        DeleteMsgPort(replyPort);
        return result;
    }

    msg->msg.mn_Node.ln_Type = NT_MESSAGE;
    msg->msg.mn_Length       = sizeof(struct BifrostMsg);
    msg->msg.mn_ReplyPort    = replyPort;
    msg->command             = cmd;
    msg->value               = value;

    PutMsg(port, (struct Message *)msg);

    timerReq->tr_node.io_Command = TR_ADDREQUEST;
    timerReq->tr_time.tv_secs    = CONTROL_REPLY_TIMEOUT;
    timerReq->tr_time.tv_micro   = 0;
    SendIO((struct IORequest *)timerReq);

    replySig = 1L << replyPort->mp_SigBit;
    timerSig = 1L << timerPort->mp_SigBit;
    signals  = Wait(replySig | timerSig);

    if (signals & replySig)
    {
        GetMsg(replyPort);
        result = msg->result;
        AbortIO((struct IORequest *)timerReq);
        WaitIO((struct IORequest *)timerReq);
    }
    else if (signals & timerSig)
    {
        GetMsg(timerPort);
        Print(PROGRAM_NAME ": ERROR - daemon not responding (timeout)");
        result = 0xFFFFFFFF;
        // Message is still pending in the daemon's port - nothing more we
        // can do from here; the daemon will process/reply to it eventually
        // and this (now-abandoned) reply port simply never sees it.
    }

    FreeMem(msg, sizeof(struct BifrostMsg));
    CloseDevice((struct IORequest *)timerReq);
    DeleteIORequest((struct IORequest *)timerReq);
    DeleteMsgPort(timerPort);
    DeleteMsgPort(replyPort);

    return result;
}

//===========================================================================
// sendConfigMessage - Like sendBifrostMessage(), but for BMSG_CMD_GET_CONFIG/
// BMSG_CMD_SET_CONFIG: *cfg is sent as input (SET_CONFIG's payload; ignored
// by the daemon for GET_CONFIG) and overwritten with the daemon's reply
// config on success (GET_CONFIG's actual answer; SET_CONFIG just echoes
// back what was sent). Returns the message's `result` field, or
// 0xFFFFFFFF on timeout/error - same convention as sendBifrostMessage().
//===========================================================================

static ULONG sendConfigMessage(struct MsgPort *port, UBYTE cmd, struct BifrostConfig *cfg)
{
    struct MsgPort      *replyPort = NULL;
    struct BifrostMsg   *msg       = NULL;
    struct MsgPort      *timerPort = NULL;
    struct timerequest  *timerReq  = NULL;
    ULONG                result    = 0xFFFFFFFF;
    ULONG                replySig, timerSig, signals;

    replyPort = CreateMsgPort();
    if (!replyPort)
    {
        return result;
    }

    timerPort = CreateMsgPort();
    if (!timerPort)
    {
        DeleteMsgPort(replyPort);
        return result;
    }

    timerReq = (struct timerequest *)CreateIORequest(timerPort, sizeof(struct timerequest));
    if (!timerReq)
    {
        DeleteMsgPort(timerPort);
        DeleteMsgPort(replyPort);
        return result;
    }

    if (OpenDevice("timer.device", UNIT_VBLANK, (struct IORequest *)timerReq, 0))
    {
        DeleteIORequest((struct IORequest *)timerReq);
        DeleteMsgPort(timerPort);
        DeleteMsgPort(replyPort);
        return result;
    }

    msg = (struct BifrostMsg *)AllocMem(sizeof(struct BifrostMsg), MEMF_PUBLIC | MEMF_CLEAR);
    if (!msg)
    {
        CloseDevice((struct IORequest *)timerReq);
        DeleteIORequest((struct IORequest *)timerReq);
        DeleteMsgPort(timerPort);
        DeleteMsgPort(replyPort);
        return result;
    }

    msg->msg.mn_Node.ln_Type = NT_MESSAGE;
    msg->msg.mn_Length       = sizeof(struct BifrostMsg);
    msg->msg.mn_ReplyPort    = replyPort;
    msg->command             = cmd;
    msg->value               = 0;
    msg->config              = *cfg;

    PutMsg(port, (struct Message *)msg);

    timerReq->tr_node.io_Command = TR_ADDREQUEST;
    timerReq->tr_time.tv_secs    = CONTROL_REPLY_TIMEOUT;
    timerReq->tr_time.tv_micro   = 0;
    SendIO((struct IORequest *)timerReq);

    replySig = 1L << replyPort->mp_SigBit;
    timerSig = 1L << timerPort->mp_SigBit;
    signals  = Wait(replySig | timerSig);

    if (signals & replySig)
    {
        GetMsg(replyPort);
        result = msg->result;
        *cfg   = msg->config;
        AbortIO((struct IORequest *)timerReq);
        WaitIO((struct IORequest *)timerReq);
    }
    else if (signals & timerSig)
    {
        GetMsg(timerPort);
        Print(PROGRAM_NAME ": ERROR - daemon not responding (timeout)");
        result = 0xFFFFFFFF;
    }

    FreeMem(msg, sizeof(struct BifrostMsg));
    CloseDevice((struct IORequest *)timerReq);
    DeleteIORequest((struct IORequest *)timerReq);
    DeleteMsgPort(timerPort);
    DeleteMsgPort(replyPort);

    return result;
}

//===========================================================================
// _start() - Entry point, parse optional port/edge args, launch daemon process
//===========================================================================

LONG _start(void)
{
    struct Process              *proc;
    struct CommandLineInterface *cli;
    struct MsgPort               *existingPort;
    UBYTE                        *args;
    LONG                          i;
    LONG                          portNum;

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
        Print("Usage: " PROGRAM_NAME " [port] [edge] | STATUS | STOP");
        PrintF("  port   - TCP port (default: %ld, discovery: port+1)", (LONG)Bifrost_DEFAULT_PORT);
        Print("  edge   - TOP/BOTTOM/LEFT/RIGHT/TOPLEFT/TOPRIGHT/BOTTOMLEFT/BOTTOMRIGHT");
        Print("           PC edge that switches focus to Amiga (default: none = disabled)");
        Print("  STATUS - query the running daemon's connection status");
        Print("  STOP   - disconnect and quit the running daemon");
        Print("  Server is discovered automatically via UDP broadcast.");
        Print("  Running Bifrost again while already running updates its edge live");

        CloseLibrary((struct Library *)DOSBase);
        return RETURN_OK;
    }

    // STOP / STATUS: talk to an already-running daemon instead of parsing
    // port/edge args or launching a new one. Case-insensitive, must be the
    // whole (only) token - "STOPX" or "STATUSFOO" don't match.
    {
        UBYTE *p = args;
        BOOL isStop   = (p[0]|32)=='s' && (p[1]|32)=='t' && (p[2]|32)=='o' && (p[3]|32)=='p' &&
                        (p[4]=='\0' || p[4]==' ' || p[4]=='\t' || p[4]=='\n');
        BOOL isStatus = (p[0]|32)=='s' && (p[1]|32)=='t' && (p[2]|32)=='a' && (p[3]|32)=='t' &&
                        (p[4]|32)=='u' && (p[5]|32)=='s' &&
                        (p[6]=='\0' || p[6]==' ' || p[6]=='\t' || p[6]=='\n');

        if (isStop || isStatus)
        {
            LONG exitCode = RETURN_OK;

            Forbid();
            existingPort = FindPort(Bifrost_PORT_NAME);
            Permit();

            if (!existingPort)
            {
                Print(PROGRAM_NAME ": not running");
                CloseLibrary((struct Library *)DOSBase);
                return RETURN_WARN;
            }

            if (isStatus)
            {
                ULONG status = sendBifrostMessage(existingPort, BMSG_CMD_GET_STATUS, 0);
                if (status == 0xFFFFFFFF)
                {
                    Print(PROGRAM_NAME ": ERROR - failed to get status");
                    exitCode = RETURN_FAIL;
                }
                else
                {
                    PrintF(PROGRAM_NAME ": %s", status ? "connected" : "waiting for connection");
                }
            }
            else // isStop
            {
                ULONG result = sendBifrostMessage(existingPort, BMSG_CMD_QUIT, 0);
                if (result != 0)
                {
                    Print(PROGRAM_NAME ": ERROR - failed to stop daemon");
                    exitCode = RETURN_FAIL;
                }
                else
                {
                    Print(PROGRAM_NAME ": stopped");
                }
            }

            CloseLibrary((struct Library *)DOSBase);
            return exitCode;
        }
    }

    // A second invocation while Bifrost is already running doesn't launch
    // a duplicate (they'd both bind the same UDP/TCP ports and fight over
    // input.device) - instead it pushes this invocation's edge to the
    // running daemon live. GET_CONFIG first (rather than blindly
    // SET_CONFIG-ing) so the daemon's current clientEnabled is preserved.
    Forbid();
    existingPort = FindPort(Bifrost_PORT_NAME);
    Permit();
    if (existingPort)
    {
        struct BifrostConfig cfg;
        ULONG                getResult;

        getResult = sendConfigMessage(existingPort, BMSG_CMD_GET_CONFIG, &cfg);
        if (getResult == 0xFFFFFFFF)
        {
            Print(PROGRAM_NAME ": ERROR - already running but not responding");
            CloseLibrary((struct Library *)DOSBase);
            return RETURN_FAIL;
        }

        if (cfg.port != s_port)
        {
            Print(PROGRAM_NAME ": already running on a different port - STOP it first, then relaunch");
            CloseLibrary((struct Library *)DOSBase);
            return RETURN_WARN;
        }

        cfg.pcEdge = s_pcEdge;
        sendConfigMessage(existingPort, BMSG_CMD_SET_CONFIG, &cfg);
        PrintF(PROGRAM_NAME ": config updated (edge=0x%02lx)", (LONG)s_pcEdge);
        CloseLibrary((struct Library *)DOSBase);
        return RETURN_OK;
    }

    // Parse up to 2 whitespace-separated tokens, any order: a numeric
    // port and/or an edge keyword.
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
        NP_Name,     (ULONG)PROGRAM_NAME,
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
