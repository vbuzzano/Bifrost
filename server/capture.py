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
import json
import math
import os
import platform
import threading
import time
from pynput import mouse, keyboard
from pynput.keyboard import Key
from protocol import (pack_mouse_move, pack_mouse_btn, pack_key, pack_wheel,
                      pack_focus_enter,
                      BTN_LEFT, BTN_RIGHT, BTN_MIDDLE,
                      QUAL_LBUTTON, QUAL_RBUTTON, WHEEL_UP, WHEEL_DOWN,
                      QUAL_CTRL, QUAL_LSHIFT, QUAL_RSHIFT, QUAL_LALT, QUAL_RALT)
from keymap import get_rawcode, QUAL_MAP, set_right_amiga_source
from edge_resistance import (EDGE_NONE, EdgeResistance,
                              percent_along_edge, position_from_percent)

# ---------------------------------------------------------------------------
# Configuration - Load from bifrost_config.json
# ---------------------------------------------------------------------------

def _load_config():
    """Load configuration from bifrost_config.json with sensible defaults."""
    config_file = os.path.join(os.path.dirname(__file__), 'bifrost_config.json')

    # Default values
    defaults = {
        'network': {'port': 7890},
        'mouse': {'hz': 50, 'hz_drag': 15, 'speed': 1, 'delta_max': 80},
        'curve': {'linear': 2.0, 'ratio': 0.5},
        'keys': {'toggle': 'scroll_lock', 'emergency': 'pause', 'kill_modifier': 'ctrl',
                  'right_amiga': 'windows'},
        'debug': {'enabled': True, 'print_events': True}
    }

    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                user_config = json.load(f)
            # Merge user config with defaults
            for section in defaults:
                if section in user_config and isinstance(user_config[section], dict):
                    defaults[section].update(user_config[section])
            print(f"[OK] Loaded config from {config_file}")
        else:
            print(f"[WARN] Config file not found: {config_file}")
            print(f"  Using default configuration")
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON parse error in {config_file}: {e}")
        print(f"  Using default configuration")
    except Exception as e:
        print(f"[ERROR] Error loading config: {e}")
        print(f"  Using default configuration")

    return defaults

_CONFIG = _load_config()

def _validate_positive_number(value, name, default):
    """Ensure value is a positive int/float; fall back to default (with a warning) otherwise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        print(f"[WARN] Invalid {name}={value!r} in bifrost_config.json "
              f"(must be a positive number) - using default {default}")
        return default
    return value

# Parse key names to pynput Key objects
_KEY_MAP = {
    'scroll_lock': Key.scroll_lock,
    'pause': Key.pause,
    'esc': Key.esc,
    'tab': Key.tab,
    'backspace': Key.backspace,
    'enter': Key.enter,
}

def _get_key(key_name, field_name, default_name):
    """Convert key name string to pynput Key object; falls back to default_name
    (with a warning) for any missing, non-string, or unrecognized value."""
    if isinstance(key_name, str):
        key = _KEY_MAP.get(key_name.lower())
        if key is not None:
            return key
    print(f"[WARN] Invalid {field_name}={key_name!r} in bifrost_config.json "
          f"(expected one of {sorted(_KEY_MAP)}) - using default '{default_name}'")
    return _KEY_MAP[default_name]

# keys.kill_modifier name -> qualifier bitmask (see protocol.py QUAL_*)
_MODIFIER_MAP = {
    'ctrl':  QUAL_CTRL,
    'shift': QUAL_LSHIFT | QUAL_RSHIFT,
    'alt':   QUAL_LALT | QUAL_RALT,
}

def _get_modifier_mask(name, default_name):
    if isinstance(name, str) and name.lower() in _MODIFIER_MAP:
        return _MODIFIER_MAP[name.lower()]
    print(f"[WARN] Invalid keys.kill_modifier={name!r} in bifrost_config.json "
          f"(expected one of {sorted(_MODIFIER_MAP)}) - using default '{default_name}'")
    return _MODIFIER_MAP[default_name]

def _get_right_amiga_source(name):
    """'windows' (default) sends Right Amiga via Right Windows/Cmd;
    'ctrl' sends it via Right Ctrl instead."""
    if isinstance(name, str) and name.lower() in ('windows', 'ctrl'):
        return name.lower()
    print(f"[WARN] Invalid keys.right_amiga={name!r} in bifrost_config.json "
          f"(expected 'windows' or 'ctrl') - using default 'windows'")
    return 'windows'

# Load configuration into module-level variables
MOUSE_HZ      = _validate_positive_number(_CONFIG['mouse']['hz'], 'mouse.hz', 50)
MOUSE_HZ_DRAG = _validate_positive_number(_CONFIG['mouse']['hz_drag'], 'mouse.hz_drag', 15)
if MOUSE_HZ_DRAG > MOUSE_HZ:
    print(f"[WARN] mouse.hz_drag ({MOUSE_HZ_DRAG}) cannot exceed mouse.hz ({MOUSE_HZ}) "
          f"- clamping to {MOUSE_HZ}")
    MOUSE_HZ_DRAG = MOUSE_HZ
MOUSE_SPEED   = _CONFIG['mouse']['speed']
DELTA_MAX     = _validate_positive_number(_CONFIG['mouse']['delta_max'], 'mouse.delta_max', 80)
CURVE_LINEAR  = _CONFIG['curve']['linear']
CURVE_RATIO   = _CONFIG['curve']['ratio']
TOGGLE_KEY    = _get_key(_CONFIG['keys']['toggle'], 'keys.toggle', 'scroll_lock')
EMERGENCY_KEY = _get_key(_CONFIG['keys']['emergency'], 'keys.emergency', 'pause')
if EMERGENCY_KEY == TOGGLE_KEY:
    # Pick whichever fallback name doesn't collide with the (already resolved) toggle key
    _fallback_name = 'pause' if TOGGLE_KEY != Key.pause else 'esc'
    print(f"[WARN] keys.toggle and keys.emergency resolve to the same key - "
          f"forcing keys.emergency to '{_fallback_name}' instead")
    EMERGENCY_KEY = _KEY_MAP[_fallback_name]
KILL_MODIFIER_MASK = _get_modifier_mask(_CONFIG['keys']['kill_modifier'], 'ctrl')
RIGHT_AMIGA_SOURCE = _get_right_amiga_source(_CONFIG['keys'].get('right_amiga', 'windows'))
set_right_amiga_source(use_ctrl=(RIGHT_AMIGA_SOURCE == 'ctrl'))
DEBUG = _CONFIG['debug']['enabled']

MOUSE_INTERVAL = 1.0 / MOUSE_HZ

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

_IS_WIN = platform.system() == 'Windows'

if _IS_WIN:
    # Without this, a non-DPI-aware process gets GetSystemMetrics() values
    # virtualized/scaled down by Windows (e.g. 2560x1440 on a 3840x2160
    # monitor at 150% scaling), while the low-level mouse hook still
    # reports true physical pixel coordinates - the two disagree, and edge
    # detection breaks in exactly that scaled-vs-physical gap. Must be set
    # before any GetSystemMetrics() call below.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # fallback (Windows 7/8)
        except Exception:
            pass


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


def _get_virtual_desktop():
    """Bounding box of ALL monitors combined (origin, width, height).
    Mouse coordinates from pynput/the low-level hook span this whole area
    on a multi-monitor setup, not just the primary monitor - PC-side edge
    detection must use these bounds (not _get_screen_size(), which is
    primary-monitor-only) or the trigger zone ends up sitting at the seam
    between monitors instead of the true outer edge of the desktop."""
    if _IS_WIN:
        u32 = ctypes.windll.user32
        x0 = u32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        y0 = u32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        vw = u32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        vh = u32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        return x0, y0, vw, vh
    w, h = _get_screen_size()
    return 0, 0, w, h


_screen_w, _screen_h = _get_screen_size()
_center_x = _screen_w // 2
_center_y = _screen_h // 2

# Virtual desktop bounds (all monitors) - used for PC-side edge detection
# and re-entry cursor placement, so edges are the true outer boundary of
# the whole multi-monitor desktop rather than a single-monitor width.
_vscreen_x0, _vscreen_y0, _vscreen_w, _vscreen_h = _get_virtual_desktop()

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

_RESIST_STATE_NAMES = {0: 'NONE', 1: 'STARTED', 2: 'ACTIVE', 3: 'COOLDOWN'}

def _on_move_pc(x, y):
    global _last_x, _last_y
    dx = 0 if _last_x is None else x - _last_x
    dy = 0 if _last_y is None else y - _last_y
    _last_x, _last_y = x, y
    # Normalize to the virtual desktop's own coordinate space (origin can be
    # negative/nonzero with multiple monitors) so edge detection checks
    # against the true outer boundary of the whole desktop, not just the
    # primary monitor's width/height.
    vx = x - _vscreen_x0
    vy = y - _vscreen_y0
    # Suppress edge trigger while a button is held (dragging) - reuses the
    # resistance machine's own EDGE_NONE handling to force/keep state=NONE.
    effective_mask = EDGE_NONE if _pc_btn_held else _pc_edge_mask
    if DEBUG and effective_mask != EDGE_NONE and _pc_edge_resistance._state != 0:
        state_name = _RESIST_STATE_NAMES.get(_pc_edge_resistance._state, '?')
        print(f'[edge] x={vx} y={vy} dx={dx:+d} dy={dy:+d} vscreen={_vscreen_w}x{_vscreen_h} '
              f'mask=0x{effective_mask:02x} state={state_name}')
    if _pc_edge_resistance.update(vx, vy, dx, dy, _vscreen_w, _vscreen_h, effective_mask):
        percent = percent_along_edge(vx, vy, _vscreen_w, _vscreen_h, effective_mask)
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
        if _qualifiers & KILL_MODIFIER_MASK:
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
            target_x, target_y = position_from_percent(entry_percent, _vscreen_w, _vscreen_h, _pc_edge_mask)
            _set_cursor_pos(target_x + _vscreen_x0, target_y + _vscreen_y0)
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

    print(f'[Bifrost] Screen: {_screen_w}x{_screen_h}  '
          f'(virtual desktop: {_vscreen_w}x{_vscreen_h} at origin {_vscreen_x0},{_vscreen_y0})')
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
