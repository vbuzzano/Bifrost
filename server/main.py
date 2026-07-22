#!/usr/bin/env python3
"""
Bifrost Server - entry point with systray icon.

Captures mouse and keyboard on this PC and forwards events over TCP
to the Bifrost daemon running on an Amiga with SAGA chipset.

Usage:
    python main.py [--host HOST] [--port PORT]

    --host  Listen address (default: 0.0.0.0)
    --port  TCP port       (default: network.port from bifrost_config.json,
                             itself defaulting to 7890 - pass --port to
                             override for a one-off run without editing
                             the config)
"""
import sys
import os
import argparse
import threading
import time

# Ensure imports from this directory work regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import capture
from tcp_server import BifrostServer

# Systray support (optional)
try:
    from pystray import Icon, Menu, MenuItem
    from PIL import Image, ImageDraw
    HAS_SYSTRAY = True
except ImportError as e:
    HAS_SYSTRAY = False
    print(f'[WARN] Systray disabled - missing dependency: {e}')
    print('[WARN] Run "pip install -r requirements.txt" to enable the systray icon')

_instance_mutex = None  # keeps the Windows mutex handle alive for the process lifetime


def _acquire_single_instance_lock() -> bool:
    """True if this is the only running instance. False means another
    instance already holds the lock - the caller should exit.

    Needed because tcp_server.py sets SO_REUSEADDR, which on Windows lets
    a second process bind() the same port with no error - so two copies
    of the global mouse/keyboard hook would silently run at once instead
    of the second one failing loudly."""
    global _instance_mutex
    if capture._IS_WIN:
        import ctypes
        ERROR_ALREADY_EXISTS = 183
        _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Bifrost_SingleInstance')
        return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    else:
        import tempfile
        lock_path = os.path.join(tempfile.gettempdir(), 'bifrost.lock')
        if os.path.exists(lock_path):
            try:
                with open(lock_path) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)  # raises if not running
                return False
            except (ValueError, OSError):
                pass  # stale lock file - fall through and take it
        with open(lock_path, 'w') as f:
            f.write(str(os.getpid()))
        return True


_SYSTRAY_COLORS = {
    'connected': (0, 200, 0, 255),
    'disabled': (230, 150, 0, 255),
    'disconnected': (128, 128, 128, 255),
}

_SYSTRAY_LABELS = {
    'connected': 'Amiga Connected',
    'disabled': 'Amiga Disabled',
    'disconnected': 'Amiga Disconnected',
}


def _systray_state(conn_active: bool, cx_disabled: bool) -> str:
    """Pure state computation, kept separate from the polling loop below
    for testability. 'disabled' means connected but CX-disabled on the
    Amiga side (see capture.set_amiga_cx_state)."""
    if not conn_active:
        return 'disconnected'
    return 'disabled' if cx_disabled else 'connected'


def _create_icon(state: str) -> 'Image.Image':
    """Create a 16x16 icon: green=connected, orange=disabled, grey=disconnected."""
    img = Image.new('RGBA', (16, 16), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 14, 14], fill=_SYSTRAY_COLORS[state])
    return img


class _SystrayController:
    def __init__(self, srv: BifrostServer):
        self.srv = srv
        self.icon = None
        self.stop_event = threading.Event()
        self._last_state = None

    def _menu_for(self, state: str) -> 'Menu':
        return Menu(
            MenuItem(_SYSTRAY_LABELS[state], lambda: None, enabled=False),
            MenuItem("Quit", self._quit)
        )

    def _update_loop(self) -> None:
        """Update icon/menu only when state actually changes."""
        while not self.stop_event.is_set():
            with self.srv._lock:
                conn_active = self.srv._conn is not None
            state = _systray_state(conn_active, capture._amiga_cx_disabled)

            if state != self._last_state:
                self._last_state = state
                self.icon.icon = _create_icon(state)
                self.icon.menu = self._menu_for(state)

            time.sleep(0.5)

    def _quit(self) -> None:
        """Quit the application: stop the tray icon and let the server's
        own accept loop notice _running=False and unwind cleanly."""
        self.stop_event.set()
        self.icon.stop()
        self.srv._running = False

    def run(self) -> None:
        """Run the server on the main thread (so Ctrl+C keeps working
        exactly as without the systray) while the tray icon runs detached
        in the background."""
        self.icon = Icon(
            "Bifrost",
            icon=_create_icon('disconnected'),
            menu=self._menu_for('disconnected')
        )
        self.icon.run_detached()

        update_thread = threading.Thread(target=self._update_loop, daemon=True)
        update_thread.start()

        try:
            self.srv.run()
        finally:
            self.stop_event.set()
            self.icon.stop()


def _resolve_port(cli_port: 'int | None') -> int:
    """--port always wins when passed; otherwise fall back to
    network.port from bifrost_config.json (7890 if unset/invalid)."""
    if cli_port is not None:
        return cli_port
    port = capture._CONFIG.get('network', {}).get('port', 7890)
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        print(f"[WARN] Invalid network.port={port!r} in bifrost_config.json "
              f"(must be 1-65535) - using default 7890")
        return 7890
    return port


def main() -> None:
    if not _acquire_single_instance_lock():
        print('[Bifrost] Another instance is already running - exiting.')
        sys.exit(1)

    p = argparse.ArgumentParser(
        description='Bifrost Server - forward mouse/keyboard to Amiga'
    )
    p.add_argument('--host', default='0.0.0.0',
                   help='Listen address (default: 0.0.0.0 = all interfaces)')
    p.add_argument('--port', type=int, default=None,
                   help='TCP port (default: network.port from bifrost_config.json)')
    args = p.parse_args()

    port = _resolve_port(args.port)
    srv = BifrostServer(host=args.host, port=port)

    if HAS_SYSTRAY:
        ctrl = _SystrayController(srv)
        ctrl.run()
    else:
        srv.run()


if __name__ == '__main__':
    main()
