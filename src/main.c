/*
 * Bifrost - Amiga Mouse and Keyboard Controller (CLI entry point)
 * v~ 0.6.0 [PROGRAM_VERSION]~ (~ 08.08.2026 [PROGRAM_DATE]~)
 *
 * Parses CLI args (edge, or STATUS/STOP to control an already-running
 * instance), then launches daemon.c's daemon() as a detached background
 * process. See daemon.c for the actual UDP discovery / TCP connection /
 * event injection loop.
 *
 * Usage: Bifrost [edge] | STATUS | STOP
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
UBYTE s_pcEdge      = EDGE_NONE;
UBYTE s_amigaEdge   = EDGE_NONE;
BOOL  s_capslockEnabled = TRUE;  // FALSE via CLI "NOCAPSLOCK"
UBYTE s_mouseHz         = 50;
UBYTE s_mouseHzDrag     = 15;
UBYTE s_mouseSpeed      = 10;   // x10 fixed-point: 1.0
UBYTE s_mouseDeltaMax   = 80;
UBYTE s_curveLinear     = 20;   // x10 fixed-point: 2.0
UBYTE s_curveRatio      = 5;    // x10 fixed-point: 0.5

// Tracks which of the 7 live-updatable BifrostConfig fields this
// invocation's CLI actually specified. Needed by the "already running"
// push in _start(): pushing s_pcEdge/s_mouseHz/etc unconditionally would
// overwrite the daemon's current live value with this process's
// compile-time default for anything NOT retyped this time (e.g.
// "Bifrost SPEED=2" alone must not reset a previously-set LEFT edge back
// to none) - each flag gates whether its field gets pushed at all, or
// left as whatever GET_CONFIG just fetched. Set by parseArguments().
static BOOL s_gotEdge         = FALSE;
static BOOL s_gotNoCapslock   = FALSE;
static BOOL s_gotHz           = FALSE;
static BOOL s_gotHzDrag       = FALSE;
static BOOL s_gotSpeed        = FALSE;
static BOOL s_gotDeltaMax     = FALSE;
static BOOL s_gotCurveLinear  = FALSE;
static BOOL s_gotCurveRatio   = FALSE;

// Version string (read by AmigaOS version command)
const char version[] = VERSION_STRING;

//===========================================================================
// Forward declarations
//===========================================================================

static BOOL parseEdgeToken(UBYTE *p, UBYTE *outMask, LONG *outLen);
static void classifyStopStatus(UBYTE *args, BOOL *outIsStop, BOOL *outIsStatus);
static BOOL matchKeyword(UBYTE *p, const char *kw, LONG *outLen);
static BOOL matchKeyValue(UBYTE *p, const char *key, ULONG *outValue, LONG *outLen);
static BOOL matchDecimalKeyValue(UBYTE *p, const char *key, UBYTE *outValue, LONG *outLen);
static BOOL keywordNameMatches(UBYTE *p, const char *key);
static void parseArguments(UBYTE *args);
static void printConfigSummary(const struct BifrostConfig *cfg, const char *label);
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
// classifyStopStatus - Pure classification only (mirrors XMouseD's
// parseArguments(): recognize the mode, don't act on it). Whether it's
// STOP/STATUS and what to actually DO about it (Forbid/FindPort/
// sendBifrostMessage/printing) stays in _start() - same split XMouseD
// keeps between its parseArguments() and the if-chain that follows it.
// Case-insensitive via the (c|32) bit trick, must be the whole (only)
// token - "STOPX" or "STATUSFOO" don't match.
//===========================================================================

static void classifyStopStatus(UBYTE *args, BOOL *outIsStop, BOOL *outIsStatus)
{
    UBYTE *p = args;
    *outIsStop   = (p[0]|32)=='s' && (p[1]|32)=='t' && (p[2]|32)=='o' && (p[3]|32)=='p' &&
                   (p[4]=='\0' || p[4]==' ' || p[4]=='\t' || p[4]=='\n');
    *outIsStatus = (p[0]|32)=='s' && (p[1]|32)=='t' && (p[2]|32)=='a' && (p[3]|32)=='t' &&
                   (p[4]|32)=='u' && (p[5]|32)=='s' &&
                   (p[6]=='\0' || p[6]==' ' || p[6]=='\t' || p[6]=='\n');
}

//===========================================================================
// matchKeyword - Case-insensitive whole-token match against a fixed
// keyword, same (c|32) bit-trick style as parseEdgeToken()/classifyStopStatus()
// above. Used for the standalone "NOCAPSLOCK" CLI token.
//===========================================================================

static BOOL matchKeyword(UBYTE *p, const char *kw, LONG *outLen)
{
    LONG len = 0;
    while (kw[len])
    {
        UBYTE pc = p[len];
        UBYTE kc = (UBYTE)kw[len];
        if ((pc | 32) != (kc | 32)) { return FALSE; }
        len++;
    }
    {
        UBYTE term = p[len];
        if (term == '\0' || term == ' ' || term == '\t' || term == '\n')
        {
            *outLen = len;
            return TRUE;
        }
    }
    return FALSE;
}

//===========================================================================
// matchKeyValue - Case-insensitive match of "KEY=digits" at this position.
// Returns FALSE (token untouched, *outValue/*outLen unset) if `key` doesn't
// match, if it isn't followed by '=', or if there are no digits after '='.
// Used for the 6 mouse-tuning CLI tokens (HZ=, SPEED=, etc).
//===========================================================================

static BOOL matchKeyValue(UBYTE *p, const char *key, ULONG *outValue, LONG *outLen)
{
    LONG len = 0;
    while (key[len])
    {
        UBYTE pc = p[len];
        UBYTE kc = (UBYTE)key[len];
        if ((pc | 32) != (kc | 32)) { return FALSE; }
        len++;
    }
    // Accept "KEY=value" or "KEY value" (one or more spaces/tabs) - if
    // neither separator follows, this isn't a match at all (leaves *args
    // untouched so the caller's unknown-token fallback handles it).
    if (p[len] == '=')
    {
        len++;
    }
    else if (p[len] == ' ' || p[len] == '\t')
    {
        while (p[len] == ' ' || p[len] == '\t') { len++; }
    }
    else
    {
        return FALSE;
    }
    {
        ULONG value  = 0;
        LONG  digits = 0;
        while (p[len] >= '0' && p[len] <= '9' && digits < 5)
        {
            value = value * 10 + (ULONG)(p[len] - '0');
            len++;
            digits++;
        }
        if (digits == 0)
        {
            return FALSE; // "KEY=" with no digits - not a match
        }
        {
            UBYTE term = p[len];
            if (term == '\0' || term == ' ' || term == '\t' || term == '\n')
            {
                *outValue = value;
                *outLen   = len;
                return TRUE;
            }
        }
    }
    return FALSE;
}

//===========================================================================
// matchDecimalKeyValue - Like matchKeyValue, but for "KEY=digits[.digit]"
// where the human decimal number is converted directly to the x10
// fixed-point UBYTE used on the wire (e.g. "SPEED=1.5" -> 15, "SPEED=3" ->
// 30, "CURVERATIO=0.5" -> 5). No float type or atof()/strtod() involved -
// this is plain digit parsing, same style as matchKeyValue above, just
// with an optional single fractional digit. Only the first digit after
// '.' is used (matches the wire's 0.1 precision) - any further fractional
// digits are consumed but ignored, not rounded. Used for SPEED/
// CURVELINEAR/CURVERATIO; HZ/HZDRAG/DELTAMAX stay integer-only via
// matchKeyValue since they have no fractional meaning on the wire.
//===========================================================================

static BOOL matchDecimalKeyValue(UBYTE *p, const char *key, UBYTE *outValue, LONG *outLen)
{
    LONG len = 0;
    while (key[len])
    {
        UBYTE pc = p[len];
        UBYTE kc = (UBYTE)key[len];
        if ((pc | 32) != (kc | 32)) { return FALSE; }
        len++;
    }
    // Accept "KEY=value" or "KEY value" (one or more spaces/tabs).
    if (p[len] == '=')
    {
        len++;
    }
    else if (p[len] == ' ' || p[len] == '\t')
    {
        while (p[len] == ' ' || p[len] == '\t') { len++; }
    }
    else
    {
        return FALSE;
    }
    {
        ULONG intPart = 0;
        ULONG tenths  = 0;
        LONG  digits  = 0;
        while (p[len] >= '0' && p[len] <= '9' && digits < 3)
        {
            intPart = intPart * 10 + (ULONG)(p[len] - '0');
            len++;
            digits++;
        }
        if (digits == 0 && p[len] != '.')
        {
            return FALSE; // "KEY=" with nothing usable - not a match
        }
        if (p[len] == '.')
        {
            len++;
            if (p[len] >= '0' && p[len] <= '9')
            {
                tenths = (ULONG)(p[len] - '0');
                len++;
                // Only 1 decimal is meaningful on the wire - consume (don't
                // round) any further fractional digits so "1.53" behaves
                // like "1.5", not a parse failure.
                while (p[len] >= '0' && p[len] <= '9') { len++; }
            }
        }
        {
            UBYTE  term  = p[len];
            ULONG  value = intPart * 10 + tenths;
            if ((term == '\0' || term == ' ' || term == '\t' || term == '\n') &&
                value <= 255)
            {
                *outValue = (UBYTE)value;
                *outLen   = len;
                return TRUE;
            }
        }
    }
    return FALSE;
}

//===========================================================================
// keywordNameMatches - TRUE if `key` matches at this position AND is
// immediately followed by a real token boundary ('=', space/tab, or
// end-of-token) - i.e. the keyword *name* itself is recognized, regardless
// of whether a valid value follows it. Used only to tell "SPEED" (known
// keyword, value missing/invalid) apart from a genuinely unknown token, so
// parseArguments()'s fallback can report a specific "missing value" error
// instead of a generic "unknown argument" for typos like "SPEED" alone,
// "SPEED=", or "SPEED=abc". Deliberately separate from matchKeyValue/
// matchDecimalKeyValue (which already returned FALSE for all of these
// cases without distinguishing why).
//===========================================================================

static BOOL keywordNameMatches(UBYTE *p, const char *key)
{
    LONG len = 0;
    while (key[len])
    {
        UBYTE pc = p[len];
        UBYTE kc = (UBYTE)key[len];
        if ((pc | 32) != (kc | 32)) { return FALSE; }
        len++;
    }
    {
        UBYTE term = p[len];
        return term == '=' || term == ' ' || term == '\t' ||
               term == '\0' || term == '\n';
    }
}

//===========================================================================
// printConfigSummary - One consistent config line, shared by every place
// that needs to report the current mouse-tuning state (fresh-launch
// startup and the "already running" live-update push both call this with
// their own effective BifrostConfig) - previously each had its own
// hand-written PrintF with a different field subset, which had already
// drifted out of sync (the live-update line was missing 4 of the 6
// mouse-tuning fields the startup line showed).
//===========================================================================

static void printConfigSummary(const struct BifrostConfig *cfg, const char *label)
{
    PrintF(PROGRAM_NAME ": %s - edge=0x%02lx capslock=%s hz=%ld hzdrag=%ld "
           "speed=%ld.%ld deltamax=%ld curvelinear=%ld.%ld curveratio=%ld.%ld",
           label,
           (LONG)cfg->pcEdge, cfg->capslockEnabled ? "on" : "off",
           (LONG)cfg->mouseHz, (LONG)cfg->mouseHzDrag,
           (LONG)(cfg->mouseSpeed / 10), (LONG)(cfg->mouseSpeed % 10),
           (LONG)cfg->mouseDeltaMax,
           (LONG)(cfg->curveLinear / 10), (LONG)(cfg->curveLinear % 10),
           (LONG)(cfg->curveRatio / 10), (LONG)(cfg->curveRatio % 10));
}

//===========================================================================
// parseArguments - Parse whitespace-separated CLI tokens (an edge keyword,
// NOCAPSLOCK, and/or KEY=VALUE / KEY VALUE mouse-tuning tokens), any order
// and any count. Sets s_pcEdge/s_capslockEnabled/s_mouseHz/etc directly and
// the matching s_got* flag for each one actually specified (see their
// declaration comment), then validates HZDRAG<=HZ once all tokens are in.
//
// Mirrors XMouseD's parseArguments() naming/shape (see saga-xmouse/src/
// xmoused.c), adapted for Bifrost's much larger argument set - XMouseD's
// version returns a single BYTE mode, which isn't enough output here,
// hence the s_got* globals instead of a return value.
//===========================================================================

static void parseArguments(UBYTE *args)
{
    while (TRUE)
    {
        while (*args == ' ' || *args == '\t')
        {
            args++;
        }
        if (*args == 0 || *args == '\n')
        {
            break;
        }

        {
            UBYTE edgeMask;
            LONG  edgeLen;
            LONG  kwLen;
            ULONG kvValue;
            LONG  kvLen;
            UBYTE kvDecValue;
            LONG  kvDecLen;

            if (parseEdgeToken(args, &edgeMask, &edgeLen))
            {
                s_pcEdge  = edgeMask;
                s_gotEdge = TRUE;
                args += edgeLen;
            }
            else if (matchKeyword(args, "NOCAPSLOCK", &kwLen))
            {
                s_capslockEnabled = FALSE;
                s_gotNoCapslock   = TRUE;
                args += kwLen;
            }
            else if (matchKeyValue(args, "HZ", &kvValue, &kvLen))
            {
                if (kvValue > 0 && kvValue < 256) { s_mouseHz = (UBYTE)kvValue; s_gotHz = TRUE; }
                args += kvLen;
            }
            else if (matchKeyValue(args, "HZDRAG", &kvValue, &kvLen))
            {
                if (kvValue > 0 && kvValue < 256) { s_mouseHzDrag = (UBYTE)kvValue; s_gotHzDrag = TRUE; }
                args += kvLen;
            }
            else if (matchDecimalKeyValue(args, "SPEED", &kvDecValue, &kvDecLen))
            {
                // Clamped to 0.2-3.0: a very high speed sends packets
                // that are already clamped to the max per-event delta
                // almost every time, which can make the cursor overshoot
                // the edge-trigger tolerance zone in a single jump - seen
                // live as a broken edge-switch after using SPEED=10.
                if (kvDecValue < 2)
                {
                    PrintF(PROGRAM_NAME ": WARNING - SPEED (%ld.%ld) below minimum 0.2 - clamping",
                           (LONG)(kvDecValue / 10), (LONG)(kvDecValue % 10));
                    kvDecValue = 2;
                }
                else if (kvDecValue > 30)
                {
                    PrintF(PROGRAM_NAME ": WARNING - SPEED (%ld.%ld) above maximum 3.0 - clamping",
                           (LONG)(kvDecValue / 10), (LONG)(kvDecValue % 10));
                    kvDecValue = 30;
                }
                s_mouseSpeed = kvDecValue;
                s_gotSpeed   = TRUE;
                args += kvDecLen;
            }
            else if (matchKeyValue(args, "DELTAMAX", &kvValue, &kvLen))
            {
                if (kvValue > 0 && kvValue < 256) { s_mouseDeltaMax = (UBYTE)kvValue; s_gotDeltaMax = TRUE; }
                args += kvLen;
            }
            else if (matchDecimalKeyValue(args, "CURVELINEAR", &kvDecValue, &kvDecLen))
            {
                s_curveLinear    = kvDecValue;
                s_gotCurveLinear = TRUE;
                args += kvDecLen;
            }
            else if (matchDecimalKeyValue(args, "CURVERATIO", &kvDecValue, &kvDecLen))
            {
                s_curveRatio    = kvDecValue;
                s_gotCurveRatio = TRUE;
                args += kvDecLen;
            }
            else if (keywordNameMatches(args, "HZ") || keywordNameMatches(args, "HZDRAG") ||
                     keywordNameMatches(args, "SPEED") || keywordNameMatches(args, "DELTAMAX") ||
                     keywordNameMatches(args, "CURVELINEAR") || keywordNameMatches(args, "CURVERATIO"))
            {
                // The keyword itself is recognized but matchKeyValue/
                // matchDecimalKeyValue above already failed for it - the
                // value part is missing or invalid (e.g. "SPEED" alone,
                // "SPEED=", "SPEED=abc"). More specific than the generic
                // unknown-argument warning below.
                PrintF(PROGRAM_NAME ": WARNING - missing/invalid value for %s "
                       "(expected KEY=n or KEY n)", args);
                while (*args && *args != ' ' && *args != '\t' && *args != '\n')
                {
                    args++;
                }
            }
            else
            {
                // Unknown token - warn (style borrowed from XMouseD's
                // "unknown argument: %s") then skip just this one token
                // and keep parsing whatever follows.
                PrintF(PROGRAM_NAME ": WARNING - unknown argument: %s", args);
                while (*args && *args != ' ' && *args != '\t' && *args != '\n')
                {
                    args++;
                }
            }
        }
    }

    // HZDRAG must not exceed HZ - clamp after all tokens are parsed so the
    // check is independent of argument order (HZDRAG=30 HZ=20 must clamp
    // the same as HZ=20 HZDRAG=30).
    if (s_mouseHzDrag > s_mouseHz)
    {
        PrintF(PROGRAM_NAME ": WARNING - HZDRAG (%ld) cannot exceed HZ (%ld) - clamping",
               (LONG)s_mouseHzDrag, (LONG)s_mouseHz);
        s_mouseHzDrag = s_mouseHz;
    }
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
    BOOL                  timedOut  = FALSE;

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
        result   = 0xFFFFFFFF;
        timedOut = TRUE;
        // Message is still pending in the daemon's port - the daemon may
        // GetMsg()/ReplyMsg() it after we've moved on. msg/replyPort are
        // deliberately leaked below (not freed/deleted) rather than risk
        // the daemon writing into freed memory and ReplyMsg()-ing to a
        // deleted port - a bounded, rare leak beats a use-after-free.
    }

    if (!timedOut)
    {
        FreeMem(msg, sizeof(struct BifrostMsg));
    }
    CloseDevice((struct IORequest *)timerReq);
    DeleteIORequest((struct IORequest *)timerReq);
    DeleteMsgPort(timerPort);
    if (!timedOut)
    {
        DeleteMsgPort(replyPort);
    }

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
    BOOL                 timedOut  = FALSE;

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
        result   = 0xFFFFFFFF;
        timedOut = TRUE;
        // See sendBifrostMessage()'s timeout branch: msg/replyPort are
        // deliberately leaked here, not freed, in case the daemon replies
        // late into what would otherwise be freed/deleted memory.
    }

    if (!timedOut)
    {
        FreeMem(msg, sizeof(struct BifrostMsg));
    }
    CloseDevice((struct IORequest *)timerReq);
    DeleteIORequest((struct IORequest *)timerReq);
    DeleteMsgPort(timerPort);
    if (!timedOut)
    {
        DeleteMsgPort(replyPort);
    }

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
        Print("Usage: " PROGRAM_NAME " [edge] [NOCAPSLOCK] [KEY=VALUE...] | STATUS | STOP");
        Print("  edge       - TOP/BOTTOM/LEFT/RIGHT/TOPLEFT/TOPRIGHT/BOTTOMLEFT/BOTTOMRIGHT");
        Print("               PC edge that switches focus to Amiga (default: none = disabled)");
        Print("  NOCAPSLOCK - disable PC Capslock -> Amiga synchronization (default: enabled)");
        Print("  HZ=n          - mouse poll rate, Hz (default: 50)");
        Print("  HZDRAG=n      - mouse poll rate while dragging, Hz (default: 15, clamped <= HZ)");
        Print("  SPEED=n       - mouse speed multiplier, decimal, 0.2-3.0 (default: 1.0, e.g. SPEED=2 or SPEED=1.5)");
        Print("  DELTAMAX=n    - startup glitch filter, pixels (default: 80)");
        Print("  CURVELINEAR=n - acceleration curve linear threshold, decimal (default: 2.0)");
        Print("  CURVERATIO=n  - acceleration curve compression ratio, decimal (default: 0.5)");
        Print("                  (any KEY may be written as KEY=value or KEY value)");
        Print("  STATUS - query the running daemon's connection status");
        Print("  STOP   - disconnect and quit the running daemon");
        Print("  Server is discovered automatically via UDP broadcast.");
        Print("  Running Bifrost again while already running updates its edge live");

        CloseLibrary((struct Library *)DOSBase);
        return RETURN_OK;
    }

    // STOP / STATUS: talk to an already-running daemon instead of parsing
    // port/edge args or launching a new one. classifyStopStatus() only
    // recognizes the mode (mirrors XMouseD's parseArguments()) - acting on
    // it (Forbid/FindPort/sendBifrostMessage/printing) stays here.
    {
        BOOL isStop, isStatus;
        classifyStopStatus(args, &isStop, &isStatus);

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

    // Parse edge/NOCAPSLOCK/KEY=VALUE tokens - see parseArguments()
    // for the full token grammar and the s_got* flags it sets.
    parseArguments(args);

    // A second invocation while Bifrost is already running doesn't launch
    // a duplicate (they'd both bind the same UDP/TCP ports and fight over
    // input.device) - instead it pushes this invocation's config to the
    // running daemon live. Must run AFTER the token-parsing loop above -
    // s_pcEdge/s_mouseHz/etc. only reflect this invocation's actual CLI
    // args once that loop has run; sending them any earlier would push
    // stale compile-time defaults and silently wipe out whatever the
    // daemon was already running with. GET_CONFIG first (rather than
    // blindly SET_CONFIG-ing) so the daemon's current clientEnabled is
    // preserved (it has no CLI representation).
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

        Print(PROGRAM_NAME ": already running - updating live settings");

        // Only overwrite fields this invocation's CLI actually specified -
        // cfg already holds the daemon's current live values from
        // GET_CONFIG above, so anything not retyped this time stays
        // exactly as it was (e.g. "Bifrost SPEED=2" alone must not reset a
        // previously-set LEFT edge back to none).
        if (s_gotEdge)        { cfg.pcEdge          = s_pcEdge; }
        if (s_gotNoCapslock)  { cfg.capslockEnabled = s_capslockEnabled; }
        if (s_gotHz)          { cfg.mouseHz         = s_mouseHz; }
        if (s_gotHzDrag)      { cfg.mouseHzDrag     = s_mouseHzDrag; }
        if (s_gotSpeed)       { cfg.mouseSpeed      = s_mouseSpeed; }
        if (s_gotDeltaMax)    { cfg.mouseDeltaMax   = s_mouseDeltaMax; }
        if (s_gotCurveLinear) { cfg.curveLinear     = s_curveLinear; }
        if (s_gotCurveRatio)  { cfg.curveRatio      = s_curveRatio; }

        // Re-validate HZDRAG<=HZ on the merged result, not the pre-merge
        // s_mouseHz/s_mouseHzDrag locals above: those default to this
        // process's compile-time defaults for anything not retyped this
        // invocation, which is meaningless to compare against here. E.g.
        // "Bifrost HZDRAG=95" alone, against a daemon already running
        // HZ=100, must clamp against the live 100 - not this process's
        // default HZ=50, which would wrongly clamp HZDRAG down to 50.
        if (cfg.mouseHzDrag > cfg.mouseHz)
        {
            PrintF(PROGRAM_NAME ": WARNING - HZDRAG (%ld) cannot exceed HZ (%ld) - clamping",
                   (LONG)cfg.mouseHzDrag, (LONG)cfg.mouseHz);
            cfg.mouseHzDrag = cfg.mouseHz;
        }

        {
            ULONG setResult = sendConfigMessage(existingPort, BMSG_CMD_SET_CONFIG, &cfg);
            if (setResult == 0xFFFFFFFF)
            {
                Print(PROGRAM_NAME ": ERROR - failed to update running daemon");
                CloseLibrary((struct Library *)DOSBase);
                return RETURN_FAIL;
            }
        }
        printConfigSummary(&cfg, "config updated");
        CloseLibrary((struct Library *)DOSBase);
        return RETURN_OK;
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
           (LONG)Bifrost_DISC_PORT);
    {
        // Same printConfigSummary() the "already running" live-update push
        // uses (see above) - one consistent, always-shown line, replacing
        // what used to be 3 separately-worded, separately-conditional
        // PrintF calls that had already drifted out of sync with the
        // live-update message. clientEnabled has no CLI representation
        // (only ever set live via BifrostCX) - TRUE here just matches
        // daemon.c's own compile-time default for a fresh daemon.
        struct BifrostConfig startCfg;
        startCfg.pcEdge           = s_pcEdge;
        startCfg.clientEnabled    = TRUE;
        startCfg.capslockEnabled  = s_capslockEnabled;
        startCfg.mouseHz          = s_mouseHz;
        startCfg.mouseHzDrag      = s_mouseHzDrag;
        startCfg.mouseSpeed       = s_mouseSpeed;
        startCfg.mouseDeltaMax    = s_mouseDeltaMax;
        startCfg.curveLinear      = s_curveLinear;
        startCfg.curveRatio       = s_curveRatio;
        printConfigSummary(&startCfg, "config");
    }

    CloseLibrary((struct Library *)DOSBase);
    return RETURN_OK;
}
