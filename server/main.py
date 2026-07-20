#!/usr/bin/env python3
"""
Bifrost Server - entry point with systray icon.

Captures mouse and keyboard on this PC and forwards events over TCP
to the Bifrost daemon running on an Amiga with SAGA chipset.

Usage:
    python main.py [--host HOST] [--port PORT]

    --host  Listen address (default: 0.0.0.0)
    --port  TCP port       (default: 7890)
"""
import sys
import os
import argparse
import threading
import time

# Ensure imports from this directory work regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcp_server import BifrostServer

# Systray support (optional)
try:
    from pystray import Icon, Menu, MenuItem
    from PIL import Image, ImageDraw
    HAS_SYSTRAY = True
except ImportError:
    HAS_SYSTRAY = False


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

    def _update_loop(self) -> None:
        """Periodically update icon based on connection state."""
        while not self.stop_event.is_set():
            try:
                with self.srv._lock:
                    connected = self.srv._conn is not None

                status_text = "Amiga Connected" if connected else "Amiga Disconnected"
                self.icon.icon = _create_icon(connected)

                menu = Menu(
                    MenuItem(status_text, lambda: None, enabled=False),
                    MenuItem("Quit", self._quit)
                )
                self.icon.menu = menu
            except:
                pass

            time.sleep(0.5)

    def _quit(self) -> None:
        """Quit the application."""
        self.icon.stop()
        self.srv._running = False

    def run(self) -> None:
        """Start server with systray."""
        self.icon = Icon(
            "Bifrost",
            icon=_create_icon(connected=False),
            menu=Menu(
                MenuItem("Amiga Disconnected", lambda: None, enabled=False),
                MenuItem("Quit", self._quit)
            )
        )

        update_thread = threading.Thread(
            target=self._update_loop,
            daemon=True
        )
        update_thread.start()

        srv_thread = threading.Thread(
            target=self.srv.run,
            daemon=False
        )
        srv_thread.start()

        self.icon.run()


def main() -> None:
    p = argparse.ArgumentParser(
        description='Bifrost Server - forward mouse/keyboard to Amiga'
    )
    p.add_argument('--host', default='0.0.0.0',
                   help='Listen address (default: 0.0.0.0 = all interfaces)')
    p.add_argument('--port', type=int, default=7890,
                   help='TCP port (default: 7890)')
    args = p.parse_args()

    srv = BifrostServer(host=args.host, port=args.port)

    if HAS_SYSTRAY:
        ctrl = _SystrayController(srv)
        ctrl.run()
    else:
        srv.run()


if __name__ == '__main__':
    main()
