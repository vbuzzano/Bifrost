"""
Bifrost TCP server - waits for Amiga client connection, forwards captured events.
One client at a time. Reconnect is automatic when Amiga re-runs Bifrost.
"""
import socket
import threading
import time
import capture
import discovery
from protocol import PKT_HELLO, PKT_EDGE_TRIGGER, PKT_CLIENT_STATE, PKT_HEARTBEAT, unpack_heartbeat


# daemon.c sends PKT_HEARTBEAT roughly every 1s, interleaved with normal
# traffic regardless of how busy its main loop is (see sendHeartbeatIfDue()
# in daemon.c) - so unlike a request/reply ping, it isn't subject to
# head-of-line blocking behind a backlog of mouse/key packets. A short
# timeout is safe here for that reason.
HEARTBEAT_TIMEOUT_S = 2.0


class BifrostServer:
    def __init__(self, host: str = '0.0.0.0', port: int = 7890) -> None:
        self._host = host
        self._port = port
        self._conn = None           # Active Amiga connection socket
        self._lock = threading.Lock()
        self._running = False
        self._last_rx = 0.0             # any packet - used by clean-close handling
        self._last_heartbeat_rx = 0.0   # PKT_HEARTBEAT only - liveness watchdog
        self._heartbeat_lost = False    # avoids repeat set_amiga_client_state(False) calls
        # Tracks the last explicit PKT_CLIENT_STATE from the Amiga (e.g. via
        # BifrostCX/Exchange), independent of the heartbeat watchdog's own
        # disable/re-enable - so a resumed heartbeat never overrides an
        # intentional Exchange-disable that happened to coincide with it.
        self._explicitly_disabled = False
        self.amiga_pos = (0, 0)         # last (x, y) from PKT_HEARTBEAT

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

    def _watchdog_loop(self) -> None:
        """Soft-disable the Amiga client if its heartbeat goes quiet.

        Unlike _send()'s OSError path (a genuinely dead socket) or
        _reader_loop's clean-close handling (a graceful disconnect), this
        covers a TCP connection that's still technically open but whose
        daemon.c main loop has stopped responding (e.g. mid-reboot). It
        reuses the same client-enabled/disabled mechanism BifrostCX's
        Exchange integration already drives (capture.set_amiga_client_state) -
        forces PC focus and blocks re-entering Amiga focus, but leaves the
        TCP connection alone so a resumed heartbeat can re-enable it without
        a full reconnect.
        """
        while self._running:
            time.sleep(0.5)
            with self._lock:
                conn = self._conn
                elapsed = time.monotonic() - self._last_heartbeat_rx
                stale = conn is not None and not self._heartbeat_lost and elapsed > HEARTBEAT_TIMEOUT_S
                if stale:
                    self._heartbeat_lost = True
            if stale:
                print(f'[Bifrost] Amiga heartbeat lost ({elapsed:.1f}s) - forcing PC focus (connection kept open)')
                capture.set_amiga_client_state(False)

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
        PKT_CLIENT_STATE, PKT_HEARTBEAT) on the same TCP connection used for
        the forwarded events."""
        while True:
            data = self._recv_exact(conn, 8)
            if data is None:
                # Clean close (FIN/RST) - don't wait on the next _send()'s
                # OSError to hand focus back.
                with self._lock:
                    was_current = self._conn is conn
                    if was_current:
                        self._conn = None
                if was_current:
                    print('[Bifrost] Amiga disconnected - returning focus to PC')
                    capture._set_focus(capture.FOCUS_PC)
                return
            self._last_rx = time.monotonic()
            ptype = data[0]
            if ptype == PKT_HELLO:
                capture.apply_amiga_config(data)
            elif ptype == PKT_EDGE_TRIGGER:
                capture._set_focus(capture.FOCUS_PC, entry_percent=data[6])
            elif ptype == PKT_CLIENT_STATE:
                self._explicitly_disabled = data[6] != 1
                capture.set_amiga_client_state(data[6] == 1)
            elif ptype == PKT_HEARTBEAT:
                self._last_heartbeat_rx = self._last_rx
                self.amiga_pos = unpack_heartbeat(data)
                with self._lock:
                    was_lost = self._heartbeat_lost
                    self._heartbeat_lost = False
                if was_lost and not self._explicitly_disabled:
                    print('[Bifrost] Amiga heartbeat resumed - re-enabling client')
                    capture.set_amiga_client_state(True)

    def run(self) -> None:
        self._running = True

        # Start global input capture - events call self._send
        # connected_fn: capture blocks Amiga-mode toggle when not connected
        capture.start(self._send, connected_fn=lambda: self._conn is not None)

        # Heartbeat liveness watchdog
        watchdog_t = threading.Thread(target=self._watchdog_loop, daemon=True)
        watchdog_t.start()

        # UDP broadcast so Amiga discovers server without IP/port config -
        # discovery.DISC_PORT is fixed, independent of self._port, which is
        # embedded in the broadcast payload instead (see discovery.py)
        discovery.start(self._port)

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self._host, self._port))
        srv.listen(1)

        print(f'[Bifrost] TCP listening on port {self._port}')
        print(f'[Bifrost] Broadcasting discovery on UDP port {discovery.DISC_PORT}')
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
                capture.reset_amiga_config()
                capture._reset_amiga_client_state()
                with self._lock:
                    if self._conn:
                        try:
                            self._conn.close()
                        except OSError:
                            pass
                    self._conn = conn
                    now = time.monotonic()
                    self._last_rx = now
                    self._last_heartbeat_rx = now
                    self._heartbeat_lost = False
                    self._explicitly_disabled = False
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
