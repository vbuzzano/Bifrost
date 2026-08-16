"""
Bifrost UDP broadcast discovery server.
v~ 0.6.1 [PROGRAM_VERSION]~ (~ 16.08.2026 [PROGRAM_DATE]~)

Broadcasts Bifrost_DISCOVER (with the TCP port appended) to the subnet
broadcast address every 3 seconds so the Amiga client can find the server
without needing an explicit IP address or matching port configured. The
UDP discovery port itself is fixed (DISC_PORT) - independent of the TCP
port - so it stays reachable even if the TCP port changes. The Amiga
replies with Bifrost_HERE and then initiates the TCP connection to the
port it parsed from the broadcast payload.
"""
import socket
import threading
import time

DISC_PORT   = 7891  # fixed - must match src/bifrost.h Bifrost_DISC_PORT
_DISC_MSG   = b'Bifrost_DISCOVER'
_DISC_REPLY = b'Bifrost_HERE'
_INTERVAL   = 3.0


def build_discover_message(tcp_port: int) -> bytes:
    """Build the discovery broadcast payload, port embedded after ':'."""
    return _DISC_MSG + b':' + str(tcp_port).encode('ascii')


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


def start(tcp_port: int, disc_port: int = DISC_PORT) -> None:
    """Start the UDP broadcast discovery thread (non-blocking)."""
    t = threading.Thread(target=_broadcast_loop, args=(tcp_port, disc_port), daemon=True)
    t.start()


def _broadcast_loop(tcp_port: int, disc_port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    broadcast_addr = _get_broadcast_addr()
    message = build_discover_message(tcp_port)
    print(f'[Bifrost] Broadcasting discovery to {broadcast_addr}:{disc_port} (TCP port {tcp_port})')

    try:
        while True:
            try:
                sock.sendto(message, (broadcast_addr, disc_port))
            except OSError as e:
                print(f'[Bifrost] Discovery broadcast error: {e}')
            time.sleep(_INTERVAL)
    finally:
        sock.close()
