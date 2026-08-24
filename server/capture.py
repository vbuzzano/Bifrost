"""
Bifrost capture - global mouse/keyboard hooks with focus management.
v~ 0.6.2 [PROGRAM_VERSION]~ (~ 24.08.2026 [PROGRAM_DATE]~)

Focus modes:
  PC    - normal, input goes to PC only
  AMIGA - input captured, forwarded to Amiga, suppressed on PC

Toggle: Scroll Lock key  |  Top-right corner -> Amiga mode

Mouse strategy (Amiga mode):
  suppress=True to swallow clicks. Movement source differs by platform:
  - Windows: raw hardware deltas via Raw Input (RawInputCapture), not
    cursor position at all - see _on_raw_delta. Cursor is hidden
    (ShowCursor(0)); it isn't read, so it doesn't matter where it sits.
  - Linux: no raw-input equivalent, so cursor position deltas are used
    instead (_on_move_amiga) - re-centered whenever near a real screen
    edge so it never runs out of room to keep reporting movement (see
    _RECENTER_MARGIN), and hidden via the XFixes extension
    (_cursor_amiga_enter) since, unlike Windows, nothing else keeps it
    off-screen/invisible on its own.

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
                      pack_focus_enter, unpack_hello,
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
        'keys': {'toggle': 'scroll_lock', 'emergency': 'pause', 'kill_modifier': 'ctrl',
                  'right_amiga': 'windows'},
        'debug': {'enabled': False, 'log_mouse': False, 'log_keys': False},
        'systray': {'enabled': True}
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
DEBUG     = _CONFIG['debug']['enabled']
# Sub-levels under DEBUG - both off by default; turn on individually when
# diagnosing mouse acceleration/edge-trigger or keymap/qualifier issues.
LOG_MOUSE = DEBUG and bool(_CONFIG['debug'].get('log_mouse', False))
LOG_KEYS  = DEBUG and bool(_CONFIG['debug'].get('log_keys', False))

# Mouse-tuning values - owned by the Amiga daemon, received via PKT_HELLO.
# None until the first PKT_HELLO arrives; capture.py must not act on Amiga
# focus/mouse timing before that - mirrors _set_focus() already refusing
# FOCUS_AMIGA while not connected, so these are simply never exercised
# without a connection anyway.
MOUSE_HZ       = None
MOUSE_HZ_DRAG  = None
MOUSE_SPEED    = None
DELTA_MAX      = None
CURVE_LINEAR   = None
CURVE_RATIO    = None
MOUSE_INTERVAL = None
_mouse_timer_started = False

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
    # Query Xlib directly rather than tkinter: this is the exact same X
    # screen/coordinate space that the XRecord motion events and the
    # XTEST-based recenter warp (_recenter_cursor_fast) already operate in,
    # so it can't disagree with them the way tkinter did - tkinter's
    # winfo_screenwidth() silently fell through to the except branch on at
    # least one real multi-monitor Linux box (likely python3-tk missing -
    # it's an OS package, not something requirements.txt can pull in),
    # landing on the hardcoded 1920x1080 fallback below even though the
    # real combined screen was 3840 wide. That mismatch made the near-edge
    # recenter threshold (_RECENTER_MARGIN) fire across roughly half the
    # real desktop instead of only near the true edge - the root cause of
    # both the periodic stutter and the drag getting stuck at the real
    # (3840-wide) edge that _screen_w=1920 never accounted for.
    try:
        from Xlib import display
        d = display.Display()
        scr = d.screen()
        w, h = scr.width_in_pixels, scr.height_in_pixels
        d.close()
        return w, h
    except Exception as e:
        print(f'[WARN] Could not query X11 screen size ({e}) - falling back '
              f'to 1920x1080. Edge detection and the near-edge recenter will '
              f'be wrong if this is not your actual resolution.')
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

    # No separate hide/show calls on this platform - see
    # _make_amiga_mouse_listener. A prior attempt used the XFixes
    # extension's hide_cursor/show_cursor here; it genuinely hides the
    # cursor at the X11 protocol level, confirmed by testing it in
    # isolation, but reappears the instant the pointer moves - some
    # compositors (this one included, almost certainly GNOME/mutter over
    # XWayland) render their own cursor overlay on motion that doesn't
    # consult XFixes' hidden bit, which is exactly the case that matters
    # here (a KVM-style tool needs it hidden *while moving*, not just at
    # rest). The grab's own cursor override, set below, changes what the
    # compositor considers "the current cursor shape" - the same core
    # mechanism every app relies on for cursor shape changes (I-beam over
    # text, resize handles, etc.), which compositors can't afford to get
    # wrong the way they can an optional legacy extension bit.
    def _cursor_amiga_enter():
        pass

    def _cursor_amiga_exit():
        pass

    # Lazily-built fully-transparent 1x1 cursor, or False once confirmed
    # unavailable (so we only try/warn once, not per focus switch). Keeps
    # its OWN Xlib connection alive for the rest of the process (stored in
    # _cursor_display[0]) - a previous attempt let this connection get
    # garbage-collected right after creating the cursor, which silently
    # closes the connection and makes the X server free every resource
    # that client owned, including the cursor itself; pynput's (separate)
    # connection then grabbed with a cursor ID that no longer existed,
    # which failed the grab entirely - no exception, just a grab that
    # never actually engaged, silencing mouse forwarding altogether.
    _cursor_display = [None]
    _invisible_cursor = [None]

    def _get_invisible_cursor():
        if _invisible_cursor[0] is None:
            try:
                from Xlib import display
                d = display.Display()
                root = d.screen().root
                # Standard X11 "invisible cursor" recipe: a cursor's visible
                # pixels are whatever the *mask* bitmap marks as set, so an
                # all-zero 1x1 mask is see-through regardless of source
                # content/colors - nothing to actually render.
                pixmap = root.create_pixmap(1, 1, 1)
                gc = pixmap.create_gc(foreground=0, background=0)
                pixmap.fill_rectangle(gc, 0, 0, 1, 1)
                cursor = pixmap.create_cursor(pixmap, (0, 0, 0), (0, 0, 0), 0, 0)
                gc.free()
                pixmap.free()
                d.flush()
                _cursor_display[0] = d   # keep alive - see docstring above
                _invisible_cursor[0] = cursor
            except Exception as e:
                print(f'[WARN] Cursor hiding unavailable ({e}) - cursor stays '
                      f'visible during Amiga focus')
                _invisible_cursor[0] = False
        return _invisible_cursor[0] or None

    def _make_amiga_mouse_listener(on_move, on_click, on_scroll):
        """pynput's own X11 grab (suppress=True) only requests
        ButtonPress/ButtonReleaseMask for the grab, with cursor=0 (leave the
        cursor image alone) - see _suppress_start in pynput/mouse/_xorg.py.
        Motion isn't in that mask, so while clicks get redirected away from
        the real desktop, mouse movement (hover, focus-follows-mouse, the
        cursor itself) still reaches/shows on it completely normally.

        Subclass to (1) widen the grabbed mask so motion is captured by the
        same grab too, and (2) pass an invisible cursor for the grab's
        duration - the override applies for as long as the grab is active
        and reverts automatically on ungrab. The grab's status is checked
        explicitly and logged if it fails, rather than trusting the absence
        of a raised exception - GrabPointer always returns a reply even on
        failure (e.g. a stale cursor ID), it doesn't raise. XRecord (the
        separate mechanism that delivers move events to on_move) is
        untouched by any of this."""
        import Xlib.X
        from pynput.mouse._xorg import Listener as _XorgMouseListener

        cursor = _get_invisible_cursor()
        cursor_id = cursor.id if cursor is not None else 0

        class _SuppressingMouseListener(_XorgMouseListener):
            @property
            def _event_mask(self):
                return super()._event_mask | Xlib.X.PointerMotionMask

            def _suppress_start(self, display):
                status = display.screen().root.grab_pointer(
                    True,
                    self._event_mask,
                    Xlib.X.GrabModeAsync,
                    Xlib.X.GrabModeAsync,
                    0,
                    cursor_id,
                    Xlib.X.CurrentTime,
                )
                if status != Xlib.X.GrabSuccess:
                    print(f'[WARN] Pointer grab failed (status={status}) - '
                          f'clicks/movement may leak to the PC during Amiga focus')

        return _SuppressingMouseListener(on_move=on_move, on_click=on_click,
                                          on_scroll=on_scroll, suppress=True)


def _set_cursor_pos(x, y):
    if _IS_WIN:
        ctypes.windll.user32.SetCursorPos(x, y)
    elif _mouse_ctrl_ref[0] is not None:
        _mouse_ctrl_ref[0].position = (x, y)


if not _IS_WIN:
    # Own persistent Xlib connection for the near-edge recenter warp in
    # _on_move_amiga - kept alive for the same reason _cursor_display[0]
    # above is (a connection garbage-collected mid-use silently closes and
    # breaks the next call). Deliberately NOT routed through
    # _set_cursor_pos()/pynput's Controller.position setter: that setter
    # wraps XTEST fake_input in pynput._util.xorg.display_manager, which
    # calls display.sync() on context exit - a blocking round trip to the
    # X server. _on_move_amiga calls this directly from the XRecord
    # handler thread that's also dispatching every subsequent motion
    # event, so that sync() stalled the thread on every recenter; queued
    # real motion events piled up behind it and landed in a burst right
    # after - that burst is what showed up as periodic cursor jitter on
    # the Amiga side. flush() (send, don't wait for a reply) keeps the
    # warp but drops the wait, so recentering no longer blocks event
    # dispatch - which also makes it safe to do mid-drag instead of
    # skipping it (see _on_move_amiga), fixing the stuck-at-edge drag too.
    _recenter_display = [None]

    def _recenter_cursor_fast(x, y):
        import Xlib.X
        import Xlib.ext.xtest
        if _recenter_display[0] is None:
            from Xlib import display
            _recenter_display[0] = display.Display()
        d = _recenter_display[0]
        Xlib.ext.xtest.fake_input(d, Xlib.X.MotionNotify, x=x, y=y)
        d.flush()
else:
    # _on_move_amiga is never wired up as the Amiga-focus mouse callback on
    # Windows (raw_input_win's RawInputCapture is used instead - see
    # set_focus's _IS_WIN branch), so this is never actually called in
    # production here. Defined anyway so the name exists to call/patch.
    def _recenter_cursor_fast(x, y):
        _set_cursor_pos(x, y)


def _get_pc_capslock_state() -> bool:
    """Return True if PC Capslock is ON. Windows only."""
    if _IS_WIN:
        # GetKeyState(0x14) returns int; bit 0 indicates toggle state
        # (different from GetAsyncKeyState which returns press state)
        state = ctypes.windll.user32.GetKeyState(0x14)  # VK_CAPITAL = 0x14
        return bool(state & 1)
    else:
        # Non-Windows: return False (will add keyboard event detection later if needed)
        return False

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
# Set only by the near-edge recenter in _on_move_amiga - marks that _last_x/_last_y
# was just forced to _center_x/_center_y ahead of the real cursor actually getting
# there, so the very next raw delta is a reference-mismatch artefact (not a real
# movement) and must be discarded rather than clamped - see _on_move_amiga.
_just_reset = False

_ml      = None
_ml_lock = threading.Lock()
_kl      = None
_kl_lock = threading.Lock()
_raw     = None   # RawInputCapture instance (Windows Amiga mode)

# Edge switching (PC -> Amiga), configured by the Amiga client via PKT_HELLO
_pc_edge_mask       = EDGE_NONE
_pc_edge_resistance = EdgeResistance()
_pc_btn_held        = False   # suppress edge trigger while dragging on PC

# Capslock state synchronization
_last_pc_capslock_state = False  # last known state of PC Capslock (False=off, True=on)
_capslock_lock = threading.Lock()
# Guards against OS key-repeat re-toggling on every repeated DOWN while the
# physical key is held (see _on_key_press) - only the first DOWN since the
# last UP should flip _last_pc_capslock_state.
_capslock_key_held = False


def apply_amiga_config(data: bytes) -> None:
    """Called by tcp_server.py on every PKT_HELLO (first connect, or a live
    re-send after an Amiga-side config change via SET_CONFIG). Applies all
    7 fields (edge + 6 mouse-tuning values) and lazily starts the mouse
    timer thread on first arrival - it never runs before the Amiga has told
    the PC what tuning to use."""
    global _pc_edge_mask, MOUSE_HZ, MOUSE_HZ_DRAG, MOUSE_SPEED, DELTA_MAX
    global CURVE_LINEAR, CURVE_RATIO, MOUSE_INTERVAL, _mouse_timer_started

    cfg = unpack_hello(data)
    _pc_edge_mask  = cfg['pc_edge'] & 0xFF
    MOUSE_HZ       = cfg['hz']
    MOUSE_HZ_DRAG  = cfg['hz_drag']
    MOUSE_SPEED    = cfg['speed']
    DELTA_MAX      = cfg['delta_max']
    CURVE_LINEAR   = cfg['curve_linear']
    CURVE_RATIO    = cfg['curve_ratio']
    MOUSE_INTERVAL = 1.0 / MOUSE_HZ

    if DEBUG:
        print(f'[Bifrost] Amiga config: edge=0x{_pc_edge_mask:02x} hz={MOUSE_HZ} '
              f'hz_drag={MOUSE_HZ_DRAG} speed={MOUSE_SPEED} delta_max={DELTA_MAX} '
              f'curve_linear={CURVE_LINEAR} curve_ratio={CURVE_RATIO}')

    if not _mouse_timer_started:
        _mouse_timer_started = True
        threading.Thread(target=_mouse_timer_loop, daemon=True).start()


def reset_amiga_config() -> None:
    """Called by tcp_server.py right after accepting a new connection,
    before the fresh PKT_HELLO arrives - avoids a stale edge config leaking
    from a previous connection. Does NOT touch the mouse-tuning globals:
    once the timer thread is running it reads them every iteration (see
    _mouse_timer_loop), and nulling them here would crash that
    already-running thread on its next time.sleep(MOUSE_INTERVAL). The
    incoming connection's own PKT_HELLO overwrites them within milliseconds
    regardless, and Amiga focus can't be entered without a completed
    handshake anyway (_set_focus already refuses FOCUS_AMIGA while not
    connected) - so there's no real window where a previous connection's
    stale tuning values matter."""
    global _pc_edge_mask
    _pc_edge_mask = EDGE_NONE
    if DEBUG:
        print('[Bifrost] PC edge trigger reset (awaiting new PKT_HELLO)')


_amiga_client_disabled = False  # True once a PKT_CLIENT_STATE(disabled) arrives


def set_amiga_client_state(enabled: bool) -> None:
    """Called by tcp_server.py when a PKT_CLIENT_STATE arrives (Exchange
    enable/disable), or by its heartbeat watchdog when PKT_HEARTBEAT goes
    quiet/resumes."""
    global _amiga_client_disabled
    _amiga_client_disabled = not enabled
    if enabled:
        print('[Bifrost] Amiga client enabled')
        return
    print('[Bifrost] Amiga client disabled - forcing PC focus')
    with _focus_lock:
        cur = _focus
    if cur == FOCUS_AMIGA:
        threading.Thread(target=_do_set_focus, args=(FOCUS_PC,), daemon=True).start()


def _reset_amiga_client_state() -> None:
    """Called on each new Amiga connection - avoids a stale disabled state
    leaking from a previous connection (same reasoning as set_pc_edge(0))."""
    global _amiga_client_disabled
    _amiga_client_disabled = False

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
    if LOG_MOUSE:
        conn = 'SENT' if _send_fn else 'NO_CLIENT'
        print(f'[mouse] {conn} dx={sdx_clamped:+d} dy={sdy_clamped:+d}  (raw_pc dx={dx:+d} dy={dy:+d}  rem={_flush_rem_x:.2f},{_flush_rem_y:.2f})')
    if _send_fn:
        _send_fn(pack_mouse_move(sdx_clamped, sdy_clamped, q))


def _mouse_timer_loop():
    _tick = 0
    while True:
        time.sleep(MOUSE_INTERVAL)
        _tick += 1
        # Re-read MOUSE_HZ/MOUSE_HZ_DRAG fresh every tick (not captured once
        # before the loop) so a live config change via apply_amiga_config()
        # takes effect on this already-running thread without a restart.
        _drag_skip = MOUSE_HZ // MOUSE_HZ_DRAG   # e.g. 50//25 = skip 1 in 2
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
    # Discard impossible/glitch deltas (startup artefact, mode switch) BEFORE
    # applying the speed multiplier - filtering after multiplying would let
    # a high SPEED turn a borderline-legitimate raw delta into a false
    # rejection, or a huge raw glitch slip through once scaled down by a low
    # SPEED. Mirrors _on_move_amiga's DELTA_MAX check (the non-Windows path) -
    # this was the Windows path's equivalent gap, harmless at the old fixed
    # ~1x speed but a real risk now that SPEED can push deltas much larger.
    if abs(dx) > DELTA_MAX or abs(dy) > DELTA_MAX:
        if LOG_MOUSE:
            print(f'[mouse] DISCARD raw dx={dx:+d} dy={dy:+d}  (>{DELTA_MAX})')
        return
    # Apply speed factor: raw input has no Windows mouse acceleration
    dx = int(dx * MOUSE_SPEED)
    dy = int(dy * MOUSE_SPEED)
    if LOG_MOUSE and (dx or dy):
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
# Mouse handlers - Amiga mode (non-Windows only - Windows uses raw hardware
# deltas via RawInputCapture instead, on_move=None, see _do_set_focus)
#
# suppress=True moves/confines the real cursor on the real screen (there is
# no non-Windows equivalent of Windows' Raw Input hardware deltas), which
# means it's subject to the real screen's edges - a push that entered Amiga
# focus at the left edge (x=0) has nowhere further left to go, silently
# zeroing every subsequent leftward delta for as long as the gesture
# continues. So: warp back to screen center whenever the real cursor gets
# close to an edge, same idea as the Windows docstring's warp-to-center note
# above, just ported here since this path actually reads cursor position
# (Windows' raw-delta path doesn't and never needed it). Only warping near
# an edge - not after every single delta - matters, to keep the number of
# warps down. _last is set to center BEFORE the warp so the synthetic
# on_move event the warp itself generates resolves to a 0,0 delta instead
# of corrupting the next real one. The warp itself goes through
# _recenter_cursor_fast(), not _set_cursor_pos() - see that function's
# docstring for why (blocking vs non-blocking X11 round trip); this also
# means the warp no longer needs to be skipped while a button is held.
# DELTA_MAX either discards a reference-mismatch artefact (see _just_reset) or
# clamps a genuinely large delta - see the check below for which and why.
# ---------------------------------------------------------------------------

_RECENTER_MARGIN = 100  # px from any screen edge - re-center before the real cursor could clamp there

def _on_move_amiga(x, y):
    global _last_x, _last_y, _acc_dx, _acc_dy, _acc_qual, _just_reset

    if _last_x is None:
        _last_x, _last_y = x, y
        return

    dx = x - _last_x
    dy = y - _last_y

    near_edge = (x <= _RECENTER_MARGIN or x >= _screen_w - 1 - _RECENTER_MARGIN or
                 y <= _RECENTER_MARGIN or y >= _screen_h - 1 - _RECENTER_MARGIN)
    # No longer skipped while a button is held (dragging) - _recenter_cursor_fast()
    # doesn't block the event thread, so there's no jank tradeoff to avoid here
    # anymore (see its docstring). Previously skipping this mid-drag is what let a
    # drag that ran all the way into a real screen edge get stuck at dx=0 until
    # release.
    if near_edge:
        _last_x, _last_y = _center_x, _center_y   # re-center before the warp - see docstring above
        _recenter_cursor_fast(_center_x, _center_y)
        _just_reset = True
    else:
        _last_x, _last_y = x, y

    if abs(dx) > DELTA_MAX or abs(dy) > DELTA_MAX:
        if _just_reset:
            # First raw delta after a recenter reset _last_x/_last_y ahead of the
            # real (async) warp landing - dx/dy reflects that reference mismatch,
            # not real movement, so it must be thrown away entirely rather than
            # clamped (clamping would send one real-looking hop in a bogus
            # direction every time the cursor recenters).
            _just_reset = False
            if LOG_MOUSE:
                print(f'[mouse] DISCARD  pos=({x},{y}) dx={dx:+d} dy={dy:+d}  (>{DELTA_MAX}, reset)')
            return
        # Genuinely large delta from a fast real gesture (common on Linux, where
        # this path tracks cursor *position* - already run through the desktop's
        # own pointer-acceleration curve - rather than raw hardware deltas like
        # the Windows path does, so a single sample can legitimately be much
        # bigger here for the same physical hand movement). Clamp instead of
        # dropping: DELTA_MAX only needs to guard against genuine teleports
        # (the reset case above, ~1000+px) - discarding a merely-fast real
        # gesture entirely made a fast drag visibly stutter/freeze instead of
        # just moving at a capped top speed.
        clamped_dx = max(-DELTA_MAX, min(DELTA_MAX, dx))
        clamped_dy = max(-DELTA_MAX, min(DELTA_MAX, dy))
        if LOG_MOUSE:
            print(f'[mouse] CLAMP    pos=({x},{y}) dx={dx:+d}->{clamped_dx:+d} '
                  f'dy={dy:+d}->{clamped_dy:+d}  (>{DELTA_MAX})')
        dx, dy = clamped_dx, clamped_dy
    else:
        _just_reset = False

    if LOG_MOUSE and (dx or dy):
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

    if key == Key.caps_lock:
        # Toggle interactively from the raw press itself rather than relying
        # solely on _capslock_poller_loop's GetKeyState polling: while in
        # Amiga focus the keyboard listener runs with suppress=True, which
        # blocks the event before Windows updates its own toggle-state bit -
        # GetKeyState would never see the change, so the poller alone can't
        # detect a Capslock press made while already focused on Amiga.
        global _capslock_key_held, _last_pc_capslock_state
        if not _capslock_key_held:
            _capslock_key_held = True
            with _capslock_lock:
                _last_pc_capslock_state = not _last_pc_capslock_state
                if _focus == FOCUS_AMIGA:
                    _send_capslock_event(_last_pc_capslock_state)
                if DEBUG:
                    print(f'[capslock] Interactive toggle -> '
                          f'{"ON" if _last_pc_capslock_state else "OFF"}')
        return

    q = QUAL_MAP.get(key)
    if q:
        _qualifiers |= q
    if _focus == FOCUS_AMIGA:
        code = get_rawcode(key)
        if code is not None and _send_fn:
            if LOG_KEYS:
                print(f'[key] DOWN  key={key!r:<20} code=0x{code:02X} qual=0x{_qual():02X}')
            _send_fn(pack_key(code, True, _qual()))


def _on_key_release(key):
    global _qualifiers
    if key == TOGGLE_KEY:
        return
    if key == Key.caps_lock:
        global _capslock_key_held
        _capslock_key_held = False
        return
    q = QUAL_MAP.get(key)
    if q:
        _qualifiers &= ~q
    if _focus == FOCUS_AMIGA:
        code = get_rawcode(key)
        if code is not None and _send_fn:
            if LOG_KEYS:
                print(f'[key] UP    key={key!r:<20} code=0x{code:02X} qual=0x{_qual():02X}')
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


def _send_capslock_event(pressed):
    """Send a synthetic Capslock key event (0x62) to the Amiga."""
    if _send_fn:
        code = 0x62  # Amiga Capslock rawkey
        if LOG_KEYS:
            print(f'[key] CAPSLOCK {"DOWN" if pressed else "UP":6s} code=0x{code:02X}')
        _send_fn(pack_key(code, pressed, _qual()))


def _resync_capslock_to_amiga():
    """Resend the current PC Capslock state to the Amiga.

    The poller (_capslock_poller_loop) only fires on state *changes*, so if
    Capslock was already on/off before switching focus to Amiga, the Amiga
    would never learn the current state without this explicit resend. Called
    from _do_set_focus every time focus enters Amiga mode."""
    with _capslock_lock:
        _send_capslock_event(_last_pc_capslock_state)

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
            new_ml = _make_amiga_mouse_listener(_on_move_amiga, _on_click_amiga, _on_scroll)
        kb_suppress = True
        label = 'AMIGA  (Scroll Lock / Pause to release)'
        if entry_percent is not None and _send_fn:
            _send_fn(pack_focus_enter(entry_percent))
        _resync_capslock_to_amiga()
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
    if new_focus == FOCUS_AMIGA and _amiga_client_disabled:
        print('[Bifrost] Amiga client disabled via Exchange - cannot switch to Amiga mode')
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


def _capslock_poller_loop():
    """Poll PC Capslock state every 200ms while in PC focus, to catch up
    _last_pc_capslock_state with reality for cases the interactive
    _on_key_press/_on_key_release toggle can't see (e.g. Capslock already ON
    when Bifrost started).

    Must stay a no-op while focus is on Amiga: the keyboard listener runs
    suppressed there (see _do_set_focus), which blocks Windows from ever
    updating GetKeyState's toggle bit - so during Amiga focus GetKeyState is
    stale/unreliable, and "correcting" _last_pc_capslock_state against it
    would just clobber the interactive handler's correct value (that's
    exactly the bug this guard fixes: a Capslock press while already in
    Amiga focus got silently undone ~200ms later by this poller)."""
    global _last_pc_capslock_state
    while True:
        time.sleep(0.2)  # Poll every 200ms
        if _focus == FOCUS_AMIGA:
            continue
        current_state = _get_pc_capslock_state()
        with _capslock_lock:
            if current_state != _last_pc_capslock_state:
                _last_pc_capslock_state = current_state
                if DEBUG:
                    print(f'[capslock] PC state changed to {"ON" if current_state else "OFF"}')

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

    threading.Thread(target=_watchdog_loop, daemon=True).start()
    threading.Thread(target=_capslock_poller_loop, daemon=True).start()

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
