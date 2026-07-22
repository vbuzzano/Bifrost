"""
Bifrost TCP server - waits for Amiga client connection, forwards captured events.
One client at a time. Reconnect is automatic when Amiga re-runs Bifrost.
"""
import socket
import threading
import time
import capture
import discovery
from protocol import pack_ping, PKT_HELLO, PKT_EDGE_TRIGGER, PKT_CX_STATE


class BifrostServer:
    def __init__(self, host: str = '0.0.0.0', port: int = 7890) -> None:
        self._host = host
        self._port = port
        self._conn = None           # Active Amiga connection socket
        self._lock = threading.Lock()
        self._running = False

    def _send(self, data: bytes) -> None:
        """Thread-safe send to the connected Amiga client."""
        with self._lock:
            if self._conn:
                try:
                    self._conn.sendall(data)
                except OSError:
                    print('[Bifrost] Amiga disconnected - returning focus to PC')
                    try:
                        self._conn.close()
                    except OSError:
                        pass
                    self._conn = None
                    # Auto-switch back to PC so user is never stuck
                    capture._set_focus(capture.FOCUS_PC)

    def _ping_loop(self) -> None:
        """Send keepalive every 5 seconds to detect dead connections early."""
        while self._running:
            time.sleep(5)
            self._send(pack_ping())

    def _recv_exact(self, conn, n):
        buf = b''
        while len(buf) < n:
            try:
                chunk = conn.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf += chunk
        return buf

    def _reader_loop(self, conn) -> None:
        """Reads Amiga -> Server control packets (PKT_HELLO, PKT_EDGE_TRIGGER,
        PKT_CX_STATE) on the same TCP connection used for the forwarded events."""
        while True:
            data = self._recv_exact(conn, 8)
            if data is None:
                return
            ptype = data[0]
            if ptype == PKT_HELLO:
                capture.set_pc_edge(data[6])
            elif ptype == PKT_EDGE_TRIGGER:
                capture._set_focus(capture.FOCUS_PC, entry_percent=data[6])
            elif ptype == PKT_CX_STATE:
                capture.set_amiga_cx_state(data[6] == 1)

    def run(self) -> None:
        self._running = True

        # Start global input capture - events call self._send
        # connected_fn: capture blocks Amiga-mode toggle when not connected
        capture.start(self._send, connected_fn=lambda: self._conn is not None)

        # Keepalive thread
        ping_t = threading.Thread(target=self._ping_loop, daemon=True)
        ping_t.start()

        # UDP broadcast so Amiga discovers server without IP config
        disc_port = self._port + 1
        discovery.start(disc_port)

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self._host, self._port))
        srv.listen(1)

        print(f'[Bifrost] TCP listening on port {self._port}')
        print(f'[Bifrost] Broadcasting discovery on UDP port {disc_port}')
        print('[Bifrost] Run "Bifrost" on your Amiga (no IP needed)')
        print('[Bifrost] Press Ctrl+C to stop\n')

        try:
            while self._running:
                srv.settimeout(1.0)
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                print(f'[Bifrost] Amiga connected from {addr[0]}:{addr[1]}')
                # TCP_NODELAY: disable Nagle's algorithm.
                # Without this, the OS batches multiple 8-byte packets into one
                # TCP segment. The Amiga receives them in a burst and processes
                # several DoIO calls back-to-back -> cursor jumps -> jerkiness.
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                # Reset until the fresh PKT_HELLO arrives - avoids a stale
                # edge config leaking from a previous connection.
                capture.set_pc_edge(0)
                capture._reset_amiga_cx_state()
                with self._lock:
                    if self._conn:
                        try:
                            self._conn.close()
                        except OSError:
                            pass
                    self._conn = conn
                threading.Thread(target=self._reader_loop, args=(conn,), daemon=True).start()
        except KeyboardInterrupt:
            print('\n[Bifrost] Stopping...')
        finally:
            self._running = False
            srv.close()
            with self._lock:
                if self._conn:
                    try:
                        self._conn.close()
                    except OSError:
                        pass
