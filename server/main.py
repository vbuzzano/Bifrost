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


def _create_icon(connected: bool) -> 'Image.Image':
    """Create a 16x16 icon: green if connected, grey if disconnected."""
    img = Image.new('RGBA', (16, 16), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (0, 200, 0, 255) if connected else (128, 128, 128, 255)
    draw.ellipse([2, 2, 14, 14], fill=color)
    return img


class _SystrayController:
    def __init__(self, srv: BifrostServer):
        self.srv = srv
        self.icon = None
        self.stop_event = threading.Event()
        self._last_connected = None

    def _menu_for(self, connected: bool) -> 'Menu':
        status_text = "Amiga Connected" if connected else "Amiga Disconnected"
        return Menu(
            MenuItem(status_text, lambda: None, enabled=False),
            MenuItem("Quit", self._quit)
        )

    def _update_loop(self) -> None:
        """Update icon/menu only when connection state actually changes."""
        while not self.stop_event.is_set():
            with self.srv._lock:
                connected = self.srv._conn is not None

            if connected != self._last_connected:
                self._last_connected = connected
                self.icon.icon = _create_icon(connected)
                self.icon.menu = self._menu_for(connected)

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
            icon=_create_icon(connected=False),
            menu=self._menu_for(connected=False)
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
