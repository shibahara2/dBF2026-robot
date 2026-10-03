"""WebSocket link to R2's gamepad-server (``/realtime``).

R2 sends MessagePack binary frames and takes JSON text frames, the same way
the vendor's UI-DRP talks to it.
"""

import json
import logging
import socket
import threading
from datetime import datetime, timezone

import msgpack

logger = logging.getLogger(__name__)

STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_DISCONNECTED = "disconnected"
STATE_STOPPED = "stopped"

# Notice a dead peer (e.g. the exhibit PC dropping off THEMIS_5G) within ~11s
# instead of the kernel's two-hour default.
_KEEPALIVE_SOCKOPT = (
    (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
    (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5),
    (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2),
    (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3),
)


def _default_websocket_factory(url, timeout):
    import websocket

    ws = websocket.create_connection(url, timeout=timeout, sockopt=_KEEPALIVE_SOCKOPT)
    # The timeout only bounds the handshake; R2 may stay quiet for a while.
    ws.settimeout(None)
    return ws


def default_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def encode_json(obj):
    """Serialize like JavaScript's JSON.stringify, as UI-DRP does."""
    return json.dumps(obj, separators=(",", ":"))


def _close_quietly(sock):
    if sock is None:
        return
    try:
        sock.close()
    except Exception:
        pass


class R2Link:
    def __init__(
        self,
        url,
        *,
        websocket_factory=None,
        reconnect_delay=1.0,
        connect_timeout=5.0,
        now=default_now,
    ):
        self.url = url
        self.on_message = None
        self.on_state_change = None
        self._factory = websocket_factory or _default_websocket_factory
        self._reconnect_delay = reconnect_delay
        self._connect_timeout = connect_timeout
        self._now = now
        self._lock = threading.Lock()
        self._state = STATE_STOPPED
        self._state_at = None
        self._socket = None
        self._enabled = False
        self._closed = False
        self._wake = threading.Event()
        self._thread = None
        self._failure_logged = False

    def state(self):
        with self._lock:
            return self._state, self._state_at

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="r2-link", daemon=True)
        self._thread.start()
        self.connect()

    def connect(self):
        with self._lock:
            self._enabled = True
        self._wake.set()

    def disconnect(self):
        with self._lock:
            self._enabled = False
            sock = self._socket
        self._wake.set()
        _close_quietly(sock)

    def close(self):
        with self._lock:
            self._closed = True
            self._enabled = False
            sock = self._socket
        self._wake.set()
        _close_quietly(sock)
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def send_json(self, obj):
        text = encode_json(obj)
        with self._lock:
            sock = self._socket if self._state == STATE_CONNECTED else None
        if sock is None:
            return False
        try:
            sock.send(text)
        except Exception as exc:
            logger.warning("R2 send failed: %s", exc)
            return False
        return True

    def _enabled_and_open(self):
        with self._lock:
            return self._enabled and not self._closed

    def _run(self):
        while True:
            with self._lock:
                if self._closed:
                    break
                enabled = self._enabled
            if not enabled:
                self._set_state(STATE_STOPPED)
                self._wake.wait()
                self._wake.clear()
                continue

            self._set_state(STATE_CONNECTING)
            try:
                sock = self._factory(self.url, self._connect_timeout)
            except Exception as exc:
                if not self._failure_logged:
                    logger.warning("R2 connect to %s failed: %s", self.url, exc)
                    self._failure_logged = True
                self._set_state(STATE_DISCONNECTED)
                self._pause()
                continue

            with self._lock:
                keep = self._enabled and not self._closed
                if keep:
                    self._socket = sock
            if not keep:
                _close_quietly(sock)
                continue

            self._failure_logged = False
            logger.info("R2 connected to %s", self.url)
            self._set_state(STATE_CONNECTED)
            try:
                self._receive(sock)
            except Exception as exc:
                if self._enabled_and_open():
                    logger.warning("R2 connection lost: %s", exc)
            finally:
                with self._lock:
                    self._socket = None
                _close_quietly(sock)

            if self._enabled_and_open():
                self._set_state(STATE_DISCONNECTED)
                self._pause()
        self._set_state(STATE_STOPPED)

    def _pause(self):
        self._wake.wait(self._reconnect_delay)
        self._wake.clear()

    def _set_state(self, state):
        with self._lock:
            if self._state == state:
                return
            self._state = state
            self._state_at = self._now()
        callback = self.on_state_change
        if callback is None:
            return
        try:
            callback(state)
        except Exception:
            logger.exception("R2 state callback failed")

    def _receive(self, sock):
        while True:
            message = sock.recv()
            if isinstance(message, (bytes, bytearray)):
                if message:
                    self._dispatch(bytes(message))
                continue
            if message is None or not getattr(sock, "connected", True):
                return
            # Text frames are not part of what UI-DRP reads from R2.

    def _dispatch(self, payload):
        try:
            message = msgpack.unpackb(payload, raw=False, strict_map_key=False)
        except Exception:
            logger.warning("R2 sent a frame that is not MessagePack (%d bytes)", len(payload))
            return
        if not isinstance(message, dict):
            return
        callback = self.on_message
        if callback is None:
            return
        try:
            callback(message)
        except Exception:
            logger.exception("R2 message handling failed")
