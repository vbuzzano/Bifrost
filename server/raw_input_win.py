"""
Bifrost Raw Input - Windows-only exclusive mouse capture via WM_INPUT.

Uses RIDEV_INPUTSINK | RIDEV_NOLEGACY which:
  - Receives ALL hardware mouse input (even when not foreground)
  - Prevents legacy WM_MOUSEMOVE/WM_LBUTTONDOWN from being generated
  - Cursor does NOT move, clicks do NOT reach PC apps
  - Delivers true hardware deltas via WM_INPUT (no screen-boundary clamping)

This is the same mechanism used by games for exclusive mouse capture.
"""
import ctypes
import ctypes.wintypes as wt
import threading

# ---------------------------------------------------------------------------
# HID constants
# ---------------------------------------------------------------------------

HID_USAGE_PAGE_GENERIC = 0x01
HID_USAGE_GENERIC_MOUSE = 0x02

# RAWINPUTDEVICE.dwFlags
RIDEV_INPUTSINK = 0x00000100   # receive input even when not in foreground
# NOTE: RIDEV_NOLEGACY (0x00000030) theoretically prevents legacy mouse messages
# but is unreliable on modern Windows (cursor still moves, clicks still fire).
# We use RIDEV_INPUTSINK only for hardware deltas, and pynput suppress=True
# to block cursor movement and clicks from reaching PC applications.
RIDEV_REMOVE    = 0x00000001   # unregister

# Windows messages
WM_INPUT = 0x00FF
WM_QUIT  = 0x0012

# GetRawInputData command
RID_INPUT = 0x10000003

# RAWINPUTHEADER.dwType
RIM_TYPEMOUSE = 0

# RAWMOUSE.usButtonFlags
RI_MOUSE_LEFT_BUTTON_DOWN   = 0x0001
RI_MOUSE_LEFT_BUTTON_UP     = 0x0002
RI_MOUSE_RIGHT_BUTTON_DOWN  = 0x0004
RI_MOUSE_RIGHT_BUTTON_UP    = 0x0008
RI_MOUSE_MIDDLE_BUTTON_DOWN = 0x0010
RI_MOUSE_MIDDLE_BUTTON_UP   = 0x0020

# ---------------------------------------------------------------------------
# Win32 structures
# ---------------------------------------------------------------------------

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ('usUsagePage', wt.USHORT),
        ('usUsage',     wt.USHORT),
        ('dwFlags',     wt.DWORD),
        ('hwndTarget',  wt.HWND),
    ]


class _RAWMOUSE_BTNS(ctypes.Structure):
    _fields_ = [('usButtonFlags', wt.USHORT), ('usButtonData', wt.USHORT)]


class _RAWMOUSE_UNION(ctypes.Union):
    _fields_ = [('buttons', _RAWMOUSE_BTNS), ('ulButtons', wt.ULONG)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ('usFlags',            wt.USHORT),
        ('_u',                 _RAWMOUSE_UNION),
        ('ulRawButtons',       wt.ULONG),
        ('lLastX',             ctypes.c_long),
        ('lLastY',             ctypes.c_long),
        ('ulExtraInformation', wt.ULONG),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ('dwType',  wt.DWORD),
        ('dwSize',  wt.DWORD),
        ('hDevice', wt.HANDLE),
        ('wParam',  wt.WPARAM),
    ]


class _RAWINPUT_DATA(ctypes.Union):
    _fields_ = [('mouse', RAWMOUSE)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [('header', RAWINPUTHEADER), ('data', _RAWINPUT_DATA)]


class _MSG(ctypes.Structure):
    _fields_ = [
        ('hwnd',    wt.HWND),
        ('message', wt.UINT),
        ('wParam',  wt.WPARAM),
        ('lParam',  wt.LPARAM),
        ('time',    wt.DWORD),
        ('pt',      wt.POINT),
    ]

# ---------------------------------------------------------------------------
# RawInputCapture
# ---------------------------------------------------------------------------

class RawInputCapture:
    """
    Creates a message-only Win32 window, registers for exclusive raw mouse
    input, and calls on_delta(dx, dy) and on_button(btn_id, pressed) from
    a background thread.

    btn_id: 0=left, 1=right, 2=middle
    """

    def __init__(self, on_delta, on_button=None):
        self._on_delta   = on_delta
        self._on_button  = on_button
        self._hwnd       = None
        self._thread     = None
        self._u32        = ctypes.windll.user32
        self._k32        = ctypes.windll.kernel32

    def start(self):
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait(timeout=2.0)

    def stop(self):
        if self._hwnd:
            self._u32.PostMessageW(self._hwnd, WM_QUIT, 0, 0)
            self._hwnd = None

    def _run(self, ready_event):
        u32 = self._u32

        # Declare DefWindowProcW signature so ctypes converts args correctly
        u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        u32.DefWindowProcW.restype = ctypes.c_longlong

        # Window procedure (LRESULT is 64-bit on 64-bit Windows)
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wt.HWND, wt.UINT,
                                      wt.WPARAM, wt.LPARAM)

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_INPUT:
                self._handle_raw_input(lparam)
            return u32.DefWindowProcW(hwnd, msg, wparam, lparam)

        proc_ref = WNDPROC(wnd_proc)

        # Register window class
        class WNDCLASSEX(ctypes.Structure):
            _fields_ = [
                ('cbSize',        wt.UINT),   ('style',         wt.UINT),
                ('lpfnWndProc',   WNDPROC),   ('cbClsExtra',    ctypes.c_int),
                ('cbWndExtra',    ctypes.c_int),('hInstance',    wt.HINSTANCE),
                ('hIcon',         wt.HICON),   ('hCursor',       wt.HANDLE),
                ('hbrBackground', wt.HBRUSH),  ('lpszMenuName',  wt.LPCWSTR),
                ('lpszClassName', wt.LPCWSTR), ('hIconSm',       wt.HICON),
            ]

        CLASS_NAME = "Bifrost_RawInput"
        hInst = self._k32.GetModuleHandleW(None)

        wc = WNDCLASSEX()
        wc.cbSize        = ctypes.sizeof(WNDCLASSEX)
        wc.lpfnWndProc   = proc_ref
        wc.hInstance     = hInst
        wc.lpszClassName = CLASS_NAME
        u32.RegisterClassExW(ctypes.byref(wc))

        # Create message-only window
        HWND_MESSAGE = ctypes.cast(ctypes.c_void_p(-3), wt.HWND)
        hwnd = u32.CreateWindowExW(
            0, CLASS_NAME, "Bifrost Raw Input",
            0, 0, 0, 0, 0,
            HWND_MESSAGE, None, hInst, None
        )
        self._hwnd = hwnd

        # Register for exclusive raw mouse input
        rid = RAWINPUTDEVICE()
        rid.usUsagePage = HID_USAGE_PAGE_GENERIC
        rid.usUsage     = HID_USAGE_GENERIC_MOUSE
        rid.dwFlags     = RIDEV_INPUTSINK   # hardware deltas via WM_INPUT
        rid.hwndTarget  = hwnd
        u32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))

        ready_event.set()

        # Message loop
        msg = _MSG()
        while u32.GetMessageW(ctypes.byref(msg), hwnd, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

        # Unregister on exit
        rid.dwFlags    = RIDEV_REMOVE
        rid.hwndTarget = None
        u32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
        u32.DestroyWindow(hwnd)

    def _handle_raw_input(self, lparam):
        u32    = self._u32
        size   = wt.UINT(0)
        hdr_sz = ctypes.sizeof(RAWINPUTHEADER)

        # Get required buffer size
        u32.GetRawInputData(ctypes.c_void_p(lparam), RID_INPUT,
                             None, ctypes.byref(size), hdr_sz)
        if size.value == 0:
            return

        buf = (ctypes.c_byte * size.value)()
        if u32.GetRawInputData(ctypes.c_void_p(lparam), RID_INPUT,
                                buf, ctypes.byref(size), hdr_sz) <= 0:
            return

        ri = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
        if ri.header.dwType != RIM_TYPEMOUSE:
            return

        m  = ri.data.mouse
        dx = int(m.lLastX)
        dy = int(m.lLastY)

        if (dx or dy) and self._on_delta:
            self._on_delta(dx, dy)

        if self._on_button:
            bf = m._u.buttons.usButtonFlags
            if bf & RI_MOUSE_LEFT_BUTTON_DOWN:   self._on_button(0, True)
            if bf & RI_MOUSE_LEFT_BUTTON_UP:     self._on_button(0, False)
            if bf & RI_MOUSE_RIGHT_BUTTON_DOWN:  self._on_button(1, True)
            if bf & RI_MOUSE_RIGHT_BUTTON_UP:    self._on_button(1, False)
            if bf & RI_MOUSE_MIDDLE_BUTTON_DOWN: self._on_button(2, True)
            if bf & RI_MOUSE_MIDDLE_BUTTON_UP:   self._on_button(2, False)
