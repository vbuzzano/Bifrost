"""
Bifrost edge resistance state machine.

Ported conceptually from MouseMaster's mod_edgewarp.c (EdgeWarp module):
NONE -> STARTED -> ACTIVE -> COOLDOWN, requiring a short resistance
window plus a minimum coherent push before firing, so a cursor that
merely grazes a screen edge does not trigger an action. Unlike
mod_edgewarp.c, this does not warp the cursor - it just reports when the
gesture completes, once per gesture, for the caller to act on (e.g.
switch focus).

Driven by mouse-move events (call update() on every move), not by a
background timer - a cursor left parked in the trigger zone with no
further movement simply never re-evaluates, so it can never re-fire on
its own.
"""
import time

EDGE_NONE   = 0x00
EDGE_TOP    = 0x01
EDGE_BOTTOM = 0x02
EDGE_LEFT   = 0x04
EDGE_RIGHT  = 0x08

EDGE_TOLERANCE = 12     # px from the edge to be considered "in zone"
MIN_PUSH_DELTA = 5      # px minimum coherent push (in the edge direction) to fire
PUSH_TIMEOUT_S = 0.12   # seconds of resistance before a push can fire
COOLDOWN_S     = 0.5    # seconds after firing before it can fire again

_STATE_NONE     = 0
_STATE_STARTED  = 1
_STATE_ACTIVE   = 2
_STATE_COOLDOWN = 3


def opposite(edge: int) -> int:
    """Mirror an edge/corner bitmask: TOP<->BOTTOM, LEFT<->RIGHT."""
    result = 0
    if edge & EDGE_TOP:    result |= EDGE_BOTTOM
    if edge & EDGE_BOTTOM: result |= EDGE_TOP
    if edge & EDGE_LEFT:   result |= EDGE_RIGHT
    if edge & EDGE_RIGHT:  result |= EDGE_LEFT
    return result


def percent_along_edge(x, y, w, h, edge_mask):
    """0-255 position along the edge/corner represented by edge_mask, for
    the caller's own screen dimensions. For a corner mask, always returns
    0 (a corner is a fixed point, not a range - the receiver ignores this
    value in that case). For a straight edge, LEFT/RIGHT map to the Y
    axis and TOP/BOTTOM map to the X axis; 0 = top/left, 255 = bottom/right."""
    want_h = edge_mask & (EDGE_LEFT | EDGE_RIGHT)
    want_v = edge_mask & (EDGE_TOP | EDGE_BOTTOM)

    if want_h and want_v:
        return 0

    if want_h:
        # LEFT/RIGHT are vertical edges - position along them is the Y axis
        denom = h - 1
        return int(round((y / denom) * 255)) if denom > 0 else 0
    if want_v:
        # TOP/BOTTOM are horizontal edges - position along them is the X axis
        denom = w - 1
        return int(round((x / denom) * 255)) if denom > 0 else 0
    return 0


def position_from_percent(percent, w, h, edge_mask):
    """Target (x, y) on this screen for the given edge_mask and percent
    (0-255). For a corner mask, percent is ignored and the fixed corner
    coordinates are returned unconditionally."""
    if edge_mask & EDGE_LEFT:
        x = 0
    elif edge_mask & EDGE_RIGHT:
        x = w - 1
    else:
        x = int(round((percent / 255) * (w - 1)))

    if edge_mask & EDGE_TOP:
        y = 0
    elif edge_mask & EDGE_BOTTOM:
        y = h - 1
    else:
        y = int(round((percent / 255) * (h - 1)))

    return x, y


def _detect_edge_hits(x, y, w, h, edge_mask):
    """Which of the watched edges (edge_mask) the position is currently
    within EDGE_TOLERANCE of.

    A straight-edge mask (only a horizontal OR only a vertical bit) fires
    from anywhere along that single edge. A corner mask (one horizontal
    bit AND one vertical bit, e.g. TOP|LEFT) only fires in the actual
    corner box - both axes must be hit simultaneously - so e.g. TOPLEFT
    does not also fire along the rest of the left edge or the rest of
    the top edge (which would make it behave like a straight-edge mask
    covering two full edges instead of one corner)."""
    want_h = edge_mask & (EDGE_LEFT | EDGE_RIGHT)
    want_v = edge_mask & (EDGE_TOP | EDGE_BOTTOM)

    hit_h = 0
    if edge_mask & EDGE_LEFT and x <= EDGE_TOLERANCE:
        hit_h = EDGE_LEFT
    elif edge_mask & EDGE_RIGHT and x >= w - 1 - EDGE_TOLERANCE:
        hit_h = EDGE_RIGHT

    hit_v = 0
    if edge_mask & EDGE_TOP and y <= EDGE_TOLERANCE:
        hit_v = EDGE_TOP
    elif edge_mask & EDGE_BOTTOM and y >= h - 1 - EDGE_TOLERANCE:
        hit_v = EDGE_BOTTOM

    if want_h and want_v:
        return (hit_h | hit_v) if (hit_h and hit_v) else 0
    return hit_h | hit_v


def _push_delta(hits, dx, dy):
    """Coherent push magnitude in the direction of `hits`, or 0 if the
    push direction doesn't match (or, at a corner, is ambiguous)."""
    push_h = bool((hits & EDGE_LEFT and dx < 0) or (hits & EDGE_RIGHT and dx > 0))
    push_v = bool((hits & EDGE_TOP and dy < 0) or (hits & EDGE_BOTTOM and dy > 0))
    abs_dx, abs_dy = abs(dx), abs(dy)
    is_corner = bool((hits & (EDGE_LEFT | EDGE_RIGHT)) and (hits & (EDGE_TOP | EDGE_BOTTOM)))

    if is_corner:
        if push_h and not push_v:
            return abs_dx if abs_dy == 0 else 0
        if push_v and not push_h:
            return abs_dy if abs_dx == 0 else 0
        if push_h or push_v:
            return max(abs_dx, abs_dy)
        return 0

    if push_h:
        return abs_dx
    if push_v:
        return abs_dy
    return 0


class EdgeResistance:
    """One instance per edge-triggered action. Call update() on every
    mouse move; returns True exactly once per completed push-through-edge
    gesture."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._state = _STATE_NONE
        self._state_since = 0.0

    def update(self, x, y, dx, dy, w, h, edge_mask):
        if edge_mask == EDGE_NONE:
            self._state = _STATE_NONE
            return False

        hits = _detect_edge_hits(x, y, w, h, edge_mask)
        now = self._clock()

        if self._state != _STATE_NONE and hits == EDGE_NONE:
            self._state = _STATE_NONE
            return False

        if self._state == _STATE_NONE:
            if hits != EDGE_NONE:
                self._state = _STATE_STARTED
                self._state_since = now
            return False

        if self._state == _STATE_STARTED:
            if now - self._state_since >= PUSH_TIMEOUT_S:
                self._state = _STATE_ACTIVE
            return False

        if self._state == _STATE_ACTIVE:
            if hits != EDGE_NONE and _push_delta(hits, dx, dy) >= MIN_PUSH_DELTA:
                self._state = _STATE_COOLDOWN
                self._state_since = now
                return True
            return False

        if self._state == _STATE_COOLDOWN:
            if now - self._state_since >= COOLDOWN_S:
                self._state = _STATE_ACTIVE
            return False

        return False
