"""
Bifrost capture - global mouse/keyboard hooks with focus management.

Focus modes:
  PC    - normal, input goes to PC only
  AMIGA - input captured, forwarded to Amiga, suppressed on PC

Toggle: Scroll Lock key  |  Top-right corner -> Amiga mode

Mouse strategy (Amiga mode):
  suppress=True to swallow clicks.
  Windows WH_MOUSE_LL does NOT prevent cursor movement when suppressed,
  so we warp cursor to center after each delta via ctypes.SetCursorPos.
  SetCursorPos does NOT re-trigger WH_MOUSE_LL (no loop, no _warping flag needed).
  _last is always reset to _center so next delta is from center.

Keyboard:
  suppress=True in Amiga mode (listener restarted on toggle).
"""
import ctypes
import math
import platform
import threading
import time
from pynput import mouse, keyboard
from pynput.keyboard import Key
from protocol import (pack_mouse_move, pack_mouse_btn, pack_key, pack_wheel,
                      pack_focus_enter,
                      BTN_LEFT, BTN_RIGHT, BTN_MIDDLE,
                      QUAL_LBUTTON, QUAL_RBUTTON, WHEEL_UP, WHEEL_DOWN)
from keymap import get_rawcode, QUAL_MAP
from edge_resistance import (EDGE_NONE, EdgeResistance,
                              percent_along_edge, position_from_percent)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TOGGLE_KEY     = Key.scroll_lock
EMERGENCY_KEY  = Key.pause        # force return to PC even if stuck (works with suppress=True)
KILL_KEY       = Key.pause        # + Ctrl held -> kill the server entirely
MOUSE_HZ       = 50               # = PAL VBL rate (1 event/frame = 20ms)
MOUSE_HZ_DRAG  = 15               # every 4th tick @ 20ms = 80ms drag interval (no MCP opaque lag)
                                  # For RTG SAGA 1280x720x32 (~16Hz VBL): use MOUSE_HZ_DRAG=8
                                  # For RTG SAGA 1280x1024x32 (~10Hz VBL): use MOUSE_HZ_DRAG=6
MOUSE_INTERVAL = 1.0 / MOUSE_HZ
MOUSE_SPEED    = 1                # raw input has no Windows acceleration: multiply to compensate
                                  # increase if cursor feels slow, decrease if too fast
DELTA_MAX      = 80      # discard impossible startup deltas
# Amiga screen mode
#AMIGA_W        = 640
#AMIGA_H        = 512
# Mouse curve - piecewise linear:
#   |d| <= CURVE_LINEAR  ->  output = |d|         (1:1, precise)
#   |d| >  CURVE_LINEAR  ->  output = CURVE_LINEAR + (|d|-CURVE_LINEAR)*CURVE_RATIO
# Result: 1->1, 2->2, 3->2.5, 4->3, 5->3.5, 10->6, 20->11
CURVE_LINEAR   = 2.0    # threshold for 1:1 zone
CURVE_RATIO    = 0.5    # slope above threshold (0.5 = compress by half)
DEBUG          = True   # print events to console (set False to silence)

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

_IS_WIN = platform.system() == 'Windows'


def _get_screen_size():
    if _IS_WIN:
        u32 = ctypes.windll.user32
        return u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        w, h = r.winfo_screenwidth(), r.winfo_screenheight()
        r.destroy(); return w, h
    except Exception:
        return 1920, 1080


_screen_w, _screen_h = _get_screen_size()
_center_x = _screen_w // 2
_center_y = _screen_h // 2

# (AMIGA_W/H kept for future screenmode handshake)


def _curve(d):
    """Piecewise linear: 1:1 up to CURVE_LINEAR, CURVE_RATIO slope above.
    1->1  2->2  3->2.5  4->3  5->3.5  10->6  20->11"""
    if d == 0:
        return 0.0
    a = abs(d)
    if a <= CURVE_LINEAR:
        scaled = a
    else:
        scaled = CURVE_LINEAR + (a - CURVE_LINEAR) * CURVE_RATIO
    return math.copysign(scaled, d)

if _IS_WIN:
    _u32 = ctypes.windll.user32

    def _cursor_amiga_enter():
        """Hide cursor. RIDEV_NOLEGACY (Raw Input) freezes it - no ClipCursor needed."""
        _u32.ShowCursor(0)

    def _cursor_amiga_exit():
        _u32.ShowCursor(1)

else:
    _mouse_ctrl_ref = [None]

    def _cursor_amiga_enter():
        pass

    def _cursor_amiga_exit():
        pass


def _set_cursor_pos(x, y):
    if _IS_WIN:
        ctypes.windll.user32.SetCursorPos(x, y)

# ---------------------------------------------------------------------------
# Focus state
# ---------------------------------------------------------------------------

FOCUS_PC    = 0
FOCUS_AMIGA = 1

_focus      = FOCUS_PC
_focus_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_send_fn      = None
_connected_fn = lambda: True
_qualifiers   = 0        # keyboard modifiers
_mouse_btns   = 0        # QUAL_LBUTTON | QUAL_RBUTTON - held mouse buttons

_acc_dx    = 0
_acc_dy    = 0
_acc_qual  = 0
_move_lock = threading.Lock()

# Sub-pixel float remainder - only touched from the flush timer thread
# Keeps fractional part between flushes so dx=+1 * 0.25 accumulates
# over 4 events and eventually sends +1 instead of being discarded.
_flush_rem_x = 0.0
_flush_rem_y = 0.0

_last_x = None
_last_y = None

_ml      = None
_ml_lock = threading.Lock()
_kl      = None
_kl_lock = threading.Lock()
_raw     = None   # RawInputCapture instance (Windows Amiga mode)

# Edge switching (PC -> Amiga), configured by the Amiga client via PKT_HELLO
_pc_edge_mask       = EDGE_NONE
_pc_edge_resistance = EdgeResistance()
_pc_btn_held        = False   # suppress edge trigger while dragging on PC


def set_pc_edge(mask: int) -> None:
    """Called by tcp_server.py when a PKT_HELLO arrives. 0 = disabled."""
    global _pc_edge_mask
    _pc_edge_mask = mask & 0xFF
    if DEBUG:
        print(f'[Bifrost] PC edge trigger set to 0x{_pc_edge_mask:02x}')

# ---------------------------------------------------------------------------
# Mouse flush timer
# ---------------------------------------------------------------------------

def _qual():
    """Current qualifier byte: keyboard modifiers + held mouse buttons."""
    return (_qualifiers | _mouse_btns) & 0xFF


def _flush_mouse():
    global _acc_dx, _acc_dy, _flush_rem_x, _flush_rem_y
    with _move_lock:
        dx, dy, q = _acc_dx, _acc_dy, _acc_qual
        _acc_dx = _acc_dy = 0
    if not (dx or dy):
        return
    # Apply curve + accumulate float remainder (no sub-pixel loss between flushes)
    _flush_rem_x += _curve(dx)
    _flush_rem_y += _curve(dy)
    sdx = int(_flush_rem_x)
    sdy = int(_flush_rem_y)
    _flush_rem_x -= sdx
    _flush_rem_y -= sdy
    if not (sdx or sdy):
        return
    sdx_clamped = max(-128, min(127, sdx))
    sdy_clamped = max(-128, min(127, sdy))
    if DEBUG:
        conn = 'SENT' if _send_fn else 'NO_CLIENT'
        print(f'[mouse] {conn} dx={sdx_clamped:+d} dy={sdy_clamped:+d}  (raw_pc dx={dx:+d} dy={dy:+d}  rem={_flush_rem_x:.2f},{_flush_rem_y:.2f})')
    if _send_fn:
        _send_fn(pack_mouse_move(sdx_clamped, sdy_clamped, q))


def _mouse_timer_loop():
    _drag_skip = MOUSE_HZ // MOUSE_HZ_DRAG   # e.g. 50//25 = skip 1 in 2
    _tick = 0
    while True:
        time.sleep(MOUSE_INTERVAL)
        _tick += 1
        # During drag (LBUTTON held): throttle to MOUSE_HZ_DRAG
        # to give Amiga time to redraw opaque window before next event
        if (_mouse_btns & QUAL_LBUTTON) and (_tick % _drag_skip) != 0:
            continue
        _flush_mouse()

# ---------------------------------------------------------------------------
# Raw Input handlers (Windows Amiga mode - hardware deltas, no position)
# ---------------------------------------------------------------------------

def _on_raw_delta(dx, dy):
    """Called from RawInputCapture thread. True hardware deltas - no clamping."""
    global _acc_dx, _acc_dy, _acc_qual
    # Apply speed factor: raw input has no Windows mouse acceleration
    dx = int(dx * MOUSE_SPEED)
    dy = int(dy * MOUSE_SPEED)
    if DEBUG and (dx or dy):
        print(f'[mouse] raw      dx={dx:+d} dy={dy:+d}')
    if dx or dy:
        with _move_lock:
            _acc_dx  += dx
            _acc_dy  += dy
            _acc_qual = _qual()


def _on_raw_button(bid, pressed):
    """Raw Input: update drag state only. _on_click_amiga (pynput) sends the packet."""
    global _mouse_btns
    if bid == 0:
        if pressed: _mouse_btns |= QUAL_LBUTTON
        else:       _mouse_btns &= ~QUAL_LBUTTON
    elif bid == 1:
        if pressed: _mouse_btns |= QUAL_RBUTTON
        else:       _mouse_btns &= ~QUAL_RBUTTON
    # No pack_mouse_btn here - _on_click_amiga sends the single packet


# ---------------------------------------------------------------------------
# Mouse handlers - PC mode
# ---------------------------------------------------------------------------

def _on_move_pc(x, y):
    global _last_x, _last_y
    dx = 0 if _last_x is None else x - _last_x
    dy = 0 if _last_y is None else y - _last_y
    _last_x, _last_y = x, y
    # Suppress edge trigger while a button is held (dragging) - reuses the
    # resistance machine's own EDGE_NONE handling to force/keep state=NONE.
    effective_mask = EDGE_NONE if _pc_btn_held else _pc_edge_mask
    if _pc_edge_resistance.update(x, y, dx, dy, _screen_w, _screen_h, effective_mask):
        percent = percent_along_edge(x, y, _screen_w, _screen_h, effective_mask)
        _set_focus(FOCUS_AMIGA, entry_percent=percent)


def _on_click_pc(x, y, button, pressed):
    """Track PC-side button state only (no forwarding - not in Amiga focus)."""
    global _pc_btn_held
    _pc_btn_held = pressed

# ---------------------------------------------------------------------------
# Mouse handlers - Amiga mode
#
# suppress=False: cursor moves on PC screen (SetCursorPos is unreliable).
# We simply track the actual cursor position (_last = x, y) so deltas are
# always the true 1:1 physical movement. No warp needed.
# DELTA_MAX filters the one large startup artefact (cursor not at _last yet).
# ---------------------------------------------------------------------------

def _on_move_amiga(x, y):
    global _last_x, _last_y, _acc_dx, _acc_dy, _acc_qual

    if _last_x is None:
        _last_x, _last_y = x, y
        return

    dx = x - _last_x
    dy = y - _last_y
    _last_x, _last_y = x, y          # track actual cursor position - no warp

    # Discard startup artefact: first event after focus switch has large delta
    # because _last was set to center while cursor was elsewhere.
    # After one discard, _last = x and all subsequent deltas are correct.
    if abs(dx) > DELTA_MAX or abs(dy) > DELTA_MAX:
        if DEBUG:
            print(f'[mouse] DISCARD  pos=({x},{y}) dx={dx:+d} dy={dy:+d}  (>{DELTA_MAX})')
        return

    if DEBUG and (dx or dy):
        print(f'[mouse] event    pos=({x},{y}) dx={dx:+d} dy={dy:+d}')

    if dx or dy:
        with _move_lock:
            _acc_dx  += dx
            _acc_dy  += dy
            _acc_qual = _qual()


def _on_click_amiga(x, y, button, pressed):
    global _mouse_btns
    bid = None
    if button == mouse.Button.left:    bid = BTN_LEFT
    elif button == mouse.Button.right: bid = BTN_RIGHT
    elif button == mouse.Button.middle: bid = BTN_MIDDLE
    if bid is not None:
        # Track button state for IEQUALIFIER_LEFTBUTTON in move events (drag)
        if button == mouse.Button.left:
            if pressed: _mouse_btns |= QUAL_LBUTTON
            else:       _mouse_btns &= ~QUAL_LBUTTON
        elif button == mouse.Button.right:
            if pressed: _mouse_btns |= QUAL_RBUTTON
            else:       _mouse_btns &= ~QUAL_RBUTTON
        if _send_fn:
            _send_fn(pack_mouse_btn(bid, pressed, _qual()))

# ---------------------------------------------------------------------------
# Keyboard handlers (shared, suppress flag set per listener instance)
# ---------------------------------------------------------------------------

def _on_key_press(key):
    global _qualifiers

    # Emergency: Pause -> force PC focus via thread (NOT direct call - deadlock risk)
    # Ctrl+Pause -> kill server
    if key == EMERGENCY_KEY:
        if _qualifiers & 0x04:  # QUAL_CTRL
            print('[Bifrost] KILL: Ctrl+Pause - exiting')
            _cursor_amiga_exit()
            import os; os._exit(0)
        else:
            print('[Bifrost] EMERGENCY: Pause - forcing PC focus')
            _cursor_amiga_exit()  # restore cursor immediately (most critical)
            # Use thread - direct _do_set_focus call risks deadlock (stop() waits
            # for callback to finish, but callback is waiting for stop() to finish)
            threading.Thread(target=_do_set_focus, args=(FOCUS_PC,), daemon=True).start()
            return

    if key == TOGGLE_KEY:
        with _focus_lock:
            cur = _focus
        _set_focus(FOCUS_PC if cur == FOCUS_AMIGA else FOCUS_AMIGA)
        return   # do NOT return False - stops listener permanently
    q = QUAL_MAP.get(key)
    if q:
        _qualifiers |= q
    if _focus == FOCUS_AMIGA:
        code = get_rawcode(key)
        if code is not None and _send_fn:
            _send_fn(pack_key(code, True, _qual()))


def _on_key_release(key):
    global _qualifiers
    if key == TOGGLE_KEY:
        return
    q = QUAL_MAP.get(key)
    if q:
        _qualifiers &= ~q
    if _focus == FOCUS_AMIGA:
        code = get_rawcode(key)
        if code is not None and _send_fn:
            _send_fn(pack_key(code, False, _qual()))


def _on_scroll(x, y, dx, dy):
    """Mouse wheel scroll (dy > 0 = up, dy < 0 = down)."""
    if _focus != FOCUS_AMIGA or not _send_fn:
        return
    # Send one wheel event per scroll unit (allow rapid scrolling)
    scroll_count = abs(int(dy))
    direction = WHEEL_UP if dy > 0 else WHEEL_DOWN
    for _ in range(scroll_count):
        if DEBUG:
            print(f'[mouse] wheel {("UP" if dy > 0 else "DOWN")} SENT')
        _send_fn(pack_wheel(direction, _qual()))

# ---------------------------------------------------------------------------
# Focus switch
# ---------------------------------------------------------------------------

def _do_set_focus(new_focus, entry_percent=None):
    global _focus, _ml, _kl, _raw, _last_x, _last_y, _mouse_btns, _pc_btn_held

    with _focus_lock:
        if _focus == new_focus:
            return
        _focus = new_focus

    with _ml_lock:
        old_ml = _ml
    with _kl_lock:
        old_kl = _kl
    old_raw = _raw

    # --- Build new listeners FIRST so user is never left with no listener ---
    if new_focus == FOCUS_AMIGA:
        _cursor_amiga_enter()
        _mouse_btns = 0

        if _IS_WIN:
            from raw_input_win import RawInputCapture
            new_raw = RawInputCapture(on_delta=_on_raw_delta, on_button=_on_raw_button)
            new_raw.start()
            _raw = new_raw
            new_ml = mouse.Listener(
                on_move=None,
                on_click=_on_click_amiga,
                on_scroll=_on_scroll,
                suppress=True,
            )
        else:
            new_ml = mouse.Listener(on_move=_on_move_amiga,
                                     on_click=_on_click_amiga,
                                     on_scroll=_on_scroll,
                                     suppress=False)
        kb_suppress = True
        label = 'AMIGA  (Scroll Lock / Pause to release)'
        if entry_percent is not None and _send_fn:
            _send_fn(pack_focus_enter(entry_percent))
    else:
        _cursor_amiga_exit()
        _mouse_btns = 0
        _last_x = _last_y = None
        _pc_edge_resistance.__init__()
        _pc_btn_held = False
        if entry_percent is not None:
            target_x, target_y = position_from_percent(entry_percent, _screen_w, _screen_h, _pc_edge_mask)
            _set_cursor_pos(target_x, target_y)
        new_ml = mouse.Listener(on_move=_on_move_pc, on_click=_on_click_pc, suppress=False)
        kb_suppress = False
        label = 'PC'

    new_kl = keyboard.Listener(on_press=_on_key_press, on_release=_on_key_release,
                                suppress=kb_suppress)
    new_ml.daemon = True
    new_kl.daemon = True
    new_ml.start()
    new_kl.start()

    # Update globals so watchdog/callbacks use new listeners
    with _ml_lock:
        globals()['_ml'] = new_ml
    with _kl_lock:
        globals()['_kl'] = new_kl

    # --- Stop old AFTER new are running (user never left listener-less) ---
    if old_ml:
        try: old_ml.stop()
        except Exception: pass
    if old_raw:
        try: old_raw.stop()
        except Exception: pass
    if old_kl:
        try: old_kl.stop()
        except Exception: pass

    print(f'[Bifrost] Focus -> {label}')


def _set_focus(new_focus, entry_percent=None):
    if new_focus == FOCUS_AMIGA and not _connected_fn():
        print('[Bifrost] Not connected - cannot switch to Amiga mode')
        return
    threading.Thread(target=_do_set_focus, args=(new_focus, entry_percent), daemon=True).start()


def _watchdog_loop():
    """Every 3s: if in Amiga mode and keyboard listener is dead -> force PC focus."""
    while True:
        time.sleep(3.0)
        if _focus == FOCUS_AMIGA:
            with _kl_lock:
                kl = _kl
            if kl is None or not kl.is_alive():
                print('[Bifrost] WATCHDOG: keyboard listener dead - forcing PC focus')
                _cursor_amiga_exit()
                _set_focus(FOCUS_PC)

# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------

def start(send_fn, connected_fn=None):
    global _send_fn, _connected_fn, _ml, _kl

    _send_fn      = send_fn
    _connected_fn = connected_fn if connected_fn is not None else (lambda: True)

    if not _IS_WIN:
        _mouse_ctrl_ref[0] = mouse.Controller()

    print(f'[Bifrost] Screen: {_screen_w}x{_screen_h}')
    print('[Bifrost] Edge trigger: waiting for Amiga PKT_HELLO | Scroll Lock = toggle')
    print('[Bifrost] Focus: PC')

    threading.Thread(target=_mouse_timer_loop, daemon=True).start()
    threading.Thread(target=_watchdog_loop, daemon=True).start()

    ml = mouse.Listener(on_move=_on_move_pc, on_click=_on_click_pc, on_scroll=_on_scroll, suppress=False)
    kl = keyboard.Listener(on_press=_on_key_press, on_release=_on_key_release,
                            suppress=False)
    ml.daemon = True
    kl.daemon = True
    ml.start()
    kl.start()

    with _ml_lock:
        globals()['_ml'] = ml
    with _kl_lock:
        globals()['_kl'] = kl

    return ml, kl
