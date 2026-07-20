"""
Bifrost UDP broadcast discovery server.

Broadcasts Bifrost_DISCOVER to the subnet broadcast address every 3 seconds
so the Amiga client can find the server without needing an explicit IP
address configured. The Amiga replies with Bifrost_HERE and then initiates
the TCP connection.
"""
import socket
import threading
import time

_DISC_MSG   = b'Bifrost_DISCOVER'
_DISC_REPLY = b'Bifrost_HERE'
_INTERVAL   = 3.0


def _get_broadcast_addr() -> str:
    """Calculate subnet broadcast address from local IP (assumes /24 netmask)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to a non-routable address to determine local interface
        s.connect(('10.255.255.255', 1))
        local_ip = s.getsockname()[0]
        s.close()
        # Replace last octet with 255 for /24 subnet broadcast
        parts = local_ip.split('.')
        parts[-1] = '255'
        return '.'.join(parts)
    except Exception:
        # Fallback to limited broadcast if calculation fails
        return '255.255.255.255'


def start(disc_port: int = 7891) -> None:
    """Start the UDP broadcast discovery thread (non-blocking)."""
    t = threading.Thread(target=_broadcast_loop, args=(disc_port,), daemon=True)
    t.start()


def _broadcast_loop(disc_port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    broadcast_addr = _get_broadcast_addr()
    print(f'[Bifrost] Broadcasting discovery to {broadcast_addr}:{disc_port}')

    try:
        while True:
            try:
                sock.sendto(_DISC_MSG, (broadcast_addr, disc_port))
            except OSError as e:
                print(f'[Bifrost] Discovery broadcast error: {e}')
            time.sleep(_INTERVAL)
    finally:
        sock.close()
