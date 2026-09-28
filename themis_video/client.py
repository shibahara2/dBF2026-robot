"""WebSocket transport for the existing Themis video relay."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoClientStatus:
    connected: bool
    connect_attempts: int
    frames_received: int
    processing_errors: int
    last_frame_at: float | None


def _default_websocket_factory(url: str, timeout: float) -> Any:
    try:
        import websocket
    except ImportError as exc:  # pragma: no cover - exercised in deployment
        raise RuntimeError(
            "websocket-client is required for ThemisVideoClient"
        ) from exc
    return websocket.create_connection(url, timeout=timeout)


class ThemisVideoClient:
    """Receive binary video frames from Themis in a background thread."""

    def __init__(
        self,
        url: str,
        on_frame: Callable[[bytes], None],
        *,
        websocket_factory: Callable[[str, float], Any] | None = None,
        reconnect_delay: float = 1.0,
        connect_timeout: float = 5.0,
    ) -> None:
        if not url:
            raise ValueError("Themis WebSocket URL must not be empty")
        if reconnect_delay < 0:
            raise ValueError("reconnect_delay must be non-negative")
        if connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")

        self.url = url
        self.on_frame = on_frame
        self.websocket_factory = websocket_factory or _default_websocket_factory
        self.reconnect_delay = reconnect_delay
        self.connect_timeout = connect_timeout
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._socket: Any | None = None
        self._socket_lock = threading.Lock()
        self._connect_attempts = 0
        self._frames_received = 0
        self._processing_errors = 0
        self._last_frame_at: float | None = None

    def status(self) -> VideoClientStatus:
        with self._socket_lock:
            return VideoClientStatus(
                connected=self._socket is not None and not self._stop_event.is_set(),
                connect_attempts=self._connect_attempts,
                frames_received=self._frames_received,
                processing_errors=self._processing_errors,
                last_frame_at=self._last_frame_at,
            )

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="themis-video-client",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._socket_lock:
            socket = self._socket
        if socket is not None:
            try:
                socket.close()
            except Exception:
                pass
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=max(1.0, self.connect_timeout))
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            socket = None
            try:
                with self._socket_lock:
                    self._connect_attempts += 1
                socket = self.websocket_factory(self.url, self.connect_timeout)
                with self._socket_lock:
                    self._socket = socket
                logger.info("Themis WebSocket connected")
                self._receive(socket)
            except Exception:
                if self._stop_event.is_set():
                    break
                logger.exception("Themis WebSocket connection lost; retrying")
            finally:
                with self._socket_lock:
                    if self._socket is socket:
                        self._socket = None
                if socket is not None:
                    try:
                        socket.close()
                    except Exception:
                        pass

            if not self._stop_event.wait(self.reconnect_delay):
                continue

    def _receive(self, socket: Any) -> None:
        while not self._stop_event.is_set():
            message = socket.recv()
            if message is None:
                return
            if isinstance(message, bytes):
                payload = message
            elif isinstance(message, bytearray):
                payload = bytes(message)
            else:
                continue
            with self._socket_lock:
                self._frames_received += 1
                self._last_frame_at = time.monotonic()
            try:
                self.on_frame(payload)
            except Exception:
                with self._socket_lock:
                    self._processing_errors += 1
                logger.exception("Themis video frame processing failed")
