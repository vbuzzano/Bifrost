#!/usr/bin/env python3
"""
Bifrost Server - entry point.

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

# Ensure imports from this directory work regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcp_server import BifrostServer


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
    srv.run()


if __name__ == '__main__':
    main()
