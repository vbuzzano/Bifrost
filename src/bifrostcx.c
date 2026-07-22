/*
 * BifrostCX - Workbench commodity front-end for Bifrost
 *
 * Optional companion to Bifrost (the network daemon). Workbench-only -
 * reads PORT/EDGE tooltypes from its own icon, starts or reconfigures
 * Bifrost via its existing control port (never spawns a child process
 * itself - see design spec for why that matters), and owns all
 * commodities.library/Exchange integration (Enable/Disable/Remove).
 *
 * (c) 2026 Vincent Buzzano - MIT License
 */

// --- Library bases first (VBCC inline pragma requirement) ---
struct ExecBase       *SysBase;
struct DosLibrary     *DOSBase;
struct IntuitionBase  *IntuitionBase;

#include <proto/exec.h>
#include <proto/dos.h>
#include <exec/execbase.h>
#include <exec/types.h>
#include <exec/io.h>
#include <dos/dostags.h>
#include <dos/dosextens.h>
#include <devices/timer.h>
#include <workbench/workbench.h>
#include <workbench/startup.h>
#include <workbench/icon.h>
#include <proto/icon.h>
#include <intuition/intuition.h>
#include <intuition/intuitionbase.h>
#include <proto/intuition.h>

#include "daemon.h"

//===========================================================================
// parsePortToolType - Parse a PORT tooltype's decimal string value.
// Returns 0 on any invalid/out-of-range input (caller keeps its current
// default in that case). Takes UBYTE* (not char*) to match FindToolType()'s
// return type directly, no cast needed at the call site.
//===========================================================================

static ULONG parsePortToolType(const UBYTE *s)
{
    ULONG portNum = 0;
    LONG  i = 0;
    if (!s) return 0;
    while (s[i] >= '0' && s[i] <= '9' && i < 5)
    {
        portNum = portNum * 10 + (ULONG)(s[i] - '0');
        i++;
    }
    return (portNum > 0 && portNum < 65536) ? portNum : 0;
}

//===========================================================================
// parseEdgeToken - Match a tooltype value against the edge keyword table.
// Case-insensitive via the (c|32) bit trick, not stricmp(). Compound
// keywords (TOPLEFT etc.) are listed before their single-word prefixes so
// "TOPLEFT" is never matched as just "TOP".
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
// sendConfigMessage - Send a BMSG_CMD_* carrying a BifrostConfig payload to
// Bifrost's control port and wait for its reply, with a timeout. *cfg is
// sent as input and overwritten with the reply's config on success (the
// daemon's actual answer for GET_CONFIG; an echo of what was sent for
// SET_CONFIG). Returns the reply's `result` field, or 0xFFFFFFFF on
// timeout/error.
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
// launchBifrost - Run "Bifrost <port> <edge>" as an independent, genuinely
// separate loaded program via SystemTagList() (its own LoadSeg(), its own
// seglist - no sharing with BifrostCX, which is what makes launching
// Bifrost safe here where the old in-image CreateNewProcTags daemon spawn
// was not). SYS_Asynch so this doesn't block waiting for Bifrost's own
// detached background process to "finish" (it never does, by design).
//===========================================================================

static BOOL launchBifrost(ULONG port, UBYTE edge)
{
    char        cmdBuf[64];
    LONG        i = 0;
    LONG        j;
    const char *namePart = PROGRAM_NAME " ";
    const char *edgeName;
    LONG        rc;

    for (j = 0; namePart[j]; j++) cmdBuf[i++] = namePart[j];

    {
        UBYTE digits[6];
        LONG  nd = 0;
        ULONG p  = port;
        if (p == 0) { digits[nd++] = '0'; }
        while (p > 0) { digits[nd++] = (UBYTE)('0' + (p % 10)); p /= 10; }
        while (nd > 0) { cmdBuf[i++] = (char)digits[--nd]; }
    }
    cmdBuf[i++] = ' ';

    switch (edge)
    {
        case EDGE_TOP | EDGE_LEFT:     edgeName = "TOPLEFT";     break;
        case EDGE_TOP | EDGE_RIGHT:    edgeName = "TOPRIGHT";    break;
        case EDGE_BOTTOM | EDGE_LEFT:  edgeName = "BOTTOMLEFT";  break;
        case EDGE_BOTTOM | EDGE_RIGHT: edgeName = "BOTTOMRIGHT"; break;
        case EDGE_TOP:                 edgeName = "TOP";         break;
        case EDGE_BOTTOM:              edgeName = "BOTTOM";      break;
        case EDGE_LEFT:                edgeName = "LEFT";        break;
        case EDGE_RIGHT:               edgeName = "RIGHT";       break;
        default:                       edgeName = "";            break;
    }
    for (j = 0; edgeName[j]; j++) cmdBuf[i++] = edgeName[j];
    cmdBuf[i] = '\0';

    rc = SystemTags((CONST_STRPTR)cmdBuf, SYS_Asynch, TRUE, TAG_DONE);
    return (rc != -1);
}

//===========================================================================
// confirmRestart - Yes/No AutoRequest() asking whether to stop and relaunch
// Bifrost on a different port. If intuition.library can't be opened,
// returns TRUE (proceed) rather than silently doing nothing forever.
//===========================================================================

static BOOL confirmRestart(void)
{
    struct IntuiText  bodyText, posText, negText;
    BOOL              result;

    IntuitionBase = (struct IntuitionBase *)OpenLibrary("intuition.library", 36);
    if (!IntuitionBase)
    {
        return TRUE;
    }

    negText.FrontPen  = 1;
    negText.BackPen   = 0;
    negText.DrawMode  = JAM2;
    negText.LeftEdge  = 0;
    negText.TopEdge   = 0;
    negText.ITextFont = NULL;
    negText.IText     = (UBYTE *)"No";
    negText.NextText  = NULL;

    posText        = negText;
    posText.IText  = (UBYTE *)"Yes";

    bodyText       = negText;
    bodyText.IText = (UBYTE *)"Bifrost is running on a different port.\nRestart it with the new port/edge?";

    result = AutoRequest(NULL, &bodyText, &posText, &negText, 0, 0, 320, 80);

    CloseLibrary((struct Library *)IntuitionBase);
    IntuitionBase = NULL;
    return result;
}

//===========================================================================
// ensureBifrostRunning - Find Bifrost's control port, starting or
// reconfiguring it as needed per the three cases in the design spec.
// Returns the (possibly newly-started) control port, or NULL if Bifrost
// couldn't be found/started/reconfigured.
//===========================================================================

static struct MsgPort *ensureBifrostRunning(ULONG port, UBYTE edge, BOOL quiet)
{
    struct MsgPort *existingPort;
    LONG            tries;

    Forbid();
    existingPort = FindPort(Bifrost_PORT_NAME);
    Permit();

    if (!existingPort)
    {
        if (!launchBifrost(port, edge))
        {
            Print(PROGRAM_NAME "CX: ERROR - Bifrost not found in command path");
            return NULL;
        }

        for (tries = 0; tries < 100; tries++)
        {
            Forbid();
            existingPort = FindPort(Bifrost_PORT_NAME);
            Permit();
            if (existingPort) break;
            Delay(5);
        }

        if (!existingPort)
        {
            Print(PROGRAM_NAME "CX: ERROR - Bifrost did not start in time");
            return NULL;
        }

        return existingPort;
    }

    // Already running - compare config
    {
        struct BifrostConfig cfg;
        ULONG                getResult = sendConfigMessage(existingPort, BMSG_CMD_GET_CONFIG, &cfg);

        if (getResult == 0xFFFFFFFF)
        {
            Print(PROGRAM_NAME "CX: ERROR - Bifrost already running but not responding");
            return NULL;
        }

        if (cfg.port == port)
        {
            if (cfg.pcEdge != edge)
            {
                cfg.pcEdge = edge;
                sendConfigMessage(existingPort, BMSG_CMD_SET_CONFIG, &cfg);
            }
            return existingPort;
        }

        // Port differs - confirm before disrupting an active connection
        if (quiet || confirmRestart())
        {
            struct MsgPort       *newPort;
            struct BifrostConfig  dummy;
            BOOL                  wasEnabled = cfg.cxEnabled;
            dummy.port = 0; dummy.pcEdge = 0; dummy.cxEnabled = FALSE;
            sendConfigMessage(existingPort, BMSG_CMD_QUIT, &dummy);

            if (!launchBifrost(port, edge))
            {
                Print(PROGRAM_NAME "CX: ERROR - Bifrost not found in command path");
                return NULL;
            }

            newPort = NULL;
            for (tries = 0; tries < 100; tries++)
            {
                Forbid();
                newPort = FindPort(Bifrost_PORT_NAME);
                Permit();
                if (newPort) break;
                Delay(5);
            }

            // A fresh Bifrost always starts with cxEnabled = TRUE (its
            // compiled-in default) - if the daemon we just replaced was
            // Disabled via Exchange, re-apply that so our broker's
            // Activate state (unaffected by the restart - it's ours, not
            // the daemon's) stays in sync with what Bifrost actually does.
            if (newPort && !wasEnabled)
            {
                struct BifrostConfig newCfg;
                if (sendConfigMessage(newPort, BMSG_CMD_GET_CONFIG, &newCfg) != 0xFFFFFFFF)
                {
                    newCfg.cxEnabled = FALSE;
                    sendConfigMessage(newPort, BMSG_CMD_SET_CONFIG, &newCfg);
                }
            }
            return newPort;
        }

        // Declined - adopt the actual running port as-is, but still push
        // our edge preference live (edge changes never need confirmation).
        if (cfg.pcEdge != edge)
        {
            cfg.pcEdge = edge;
            sendConfigMessage(existingPort, BMSG_CMD_SET_CONFIG, &cfg);
        }
        return existingPort;
    }
}

//===========================================================================
// _start() - Entry point. Workbench-only: reads PORT/EDGE tooltypes from
// its own icon. If launched from a CLI (pr_CLI != NULL), prints a short
// message and exits - not a supported path, just a safety net.
//===========================================================================

LONG _start(void)
{
    struct Process    *proc;
    struct WBStartup  *wbMsg = NULL;
    ULONG              cxPort = Bifrost_DEFAULT_PORT;
    UBYTE              cxEdge = EDGE_NONE;
    BOOL               quiet  = FALSE;
    LONG               exitCode = RETURN_OK;

    SysBase = *(struct ExecBase **)4L;
    DOSBase = (struct DosLibrary *)OpenLibrary("dos.library", 36);
    if (!DOSBase)
    {
        return RETURN_FAIL;
    }

    proc = (struct Process *)FindTask(NULL);

    if (proc->pr_CLI != NULL)
    {
        Print(PROGRAM_NAME "CX must be launched from Workbench");
        CloseLibrary((struct Library *)DOSBase);
        return RETURN_FAIL;
    }

    WaitPort(&proc->pr_MsgPort);
    wbMsg = (struct WBStartup *)GetMsg(&proc->pr_MsgPort);

    {
        struct Library *IconBase = OpenLibrary("icon.library", 33);
        if (IconBase && wbMsg->sm_NumArgs > 0)
        {
            BPTR oldDir = CurrentDir(wbMsg->sm_ArgList[0].wa_Lock);
            struct DiskObject *diskObj = GetDiskObject(wbMsg->sm_ArgList[0].wa_Name);
            CurrentDir(oldDir);

            if (diskObj)
            {
                UBYTE *tt;

                if ((tt = FindToolType(diskObj->do_ToolTypes, "PORT")))
                {
                    ULONG p = parsePortToolType(tt);
                    if (p != 0)
                    {
                        cxPort = p;
                    }
                }

                if ((tt = FindToolType(diskObj->do_ToolTypes, "EDGE")))
                {
                    UBYTE edgeMask;
                    LONG  edgeLen;
                    if (parseEdgeToken(tt, &edgeMask, &edgeLen))
                    {
                        cxEdge = edgeMask;
                    }
                }

                if (FindToolType(diskObj->do_ToolTypes, "QUIET"))
                {
                    quiet = TRUE;
                }

                FreeDiskObject(diskObj);
            }
            CloseLibrary(IconBase);
        }
        else if (IconBase)
        {
            CloseLibrary(IconBase);
        }
    }

    {
        struct MsgPort *bifrostPort = ensureBifrostRunning(cxPort, cxEdge, quiet);
        if (!bifrostPort)
        {
            exitCode = RETURN_FAIL;
        }
        // Task 7 fills in: register the commodity broker using bifrostPort
        // and run the message loop.
    }

    if (wbMsg)
    {
        ReplyMsg((struct Message *)wbMsg);
    }
    CloseLibrary((struct Library *)DOSBase);
    return exitCode;
}
