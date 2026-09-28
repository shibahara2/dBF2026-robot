import threading
import time

from themis_video.client import ThemisVideoClient


class FakeSocket:
    def __init__(self, messages=(), block_event=None):
        self.messages = iter(messages)
        self.block_event = block_event
        self.closed = False

    def recv(self):
        if self.block_event is not None:
            self.block_event.wait(timeout=1)
            return None
        return next(self.messages)

    def close(self):
        self.closed = True


def wait_until(predicate, timeout=1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_delivers_binary_messages_and_ignores_text_messages():
    received = []
    socket = FakeSocket(messages=("status", b"frame-1"))

    client = ThemisVideoClient(
        "ws://themis:9002/zed2i",
        received.append,
        websocket_factory=lambda url, timeout: socket,
        reconnect_delay=0.01,
    )
    client.start()

    wait_until(lambda: received == [b"frame-1"])
    client.stop()

    assert socket.closed


def test_reconnects_after_connection_failure():
    received = []
    attempts = []

    class FailingSocket:
        def recv(self):
            raise ConnectionError("disconnected")

        def close(self):
            pass

    sockets = iter((FailingSocket(), FakeSocket(messages=(b"frame-2",))))

    def connect(url, timeout):
        attempts.append((url, timeout))
        return next(sockets)

    client = ThemisVideoClient(
        "ws://themis:9002/zed2i",
        received.append,
        websocket_factory=connect,
        reconnect_delay=0.01,
    )
    client.start()

    wait_until(lambda: received == [b"frame-2"])
    client.stop()

    assert len(attempts) >= 2


def test_stop_closes_socket_and_ends_receive_loop():
    block_event = threading.Event()
    socket = FakeSocket(block_event=block_event)
    client = ThemisVideoClient(
        "ws://themis:9002/zed2i",
        lambda payload: None,
        websocket_factory=lambda url, timeout: socket,
    )

    client.start()
    wait_until(lambda: socket is not None)
    client.stop()

    assert socket.closed


def test_frame_processing_failure_does_not_drop_video_connection():
    received = []
    connections = []
    socket = FakeSocket(messages=(b"bad-frame", b"good-frame"))

    def on_frame(payload):
        if payload == b"bad-frame":
            raise ValueError("invalid image")
        received.append(payload)

    def connect(url, timeout):
        connections.append(url)
        return socket

    client = ThemisVideoClient(
        "ws://themis:9002/zed2i",
        on_frame,
        websocket_factory=connect,
        reconnect_delay=1,
    )
    client.start()
    try:
        wait_until(lambda: received == [b"good-frame"])
    finally:
        client.stop()

    assert connections == ["ws://themis:9002/zed2i"]


def test_status_reports_received_frames_and_processing_errors():
    class HoldingSocket:
        def __init__(self):
            self.messages = iter((b"bad-frame", b"good-frame"))
            self.closed = threading.Event()

        def recv(self):
            try:
                return next(self.messages)
            except StopIteration:
                self.closed.wait(timeout=2)
                return None

        def close(self):
            self.closed.set()

    socket = HoldingSocket()

    def on_frame(payload):
        if payload == b"bad-frame":
            raise ValueError("invalid image")

    client = ThemisVideoClient(
        "ws://themis:9002/zed2i",
        on_frame,
        websocket_factory=lambda url, timeout: socket,
    )
    client.start()
    try:
        wait_until(lambda: client.status().frames_received == 2)
        status = client.status()
        assert status.connected is True
        assert status.connect_attempts == 1
        assert status.processing_errors == 1
        assert status.last_frame_at is not None
    finally:
        client.stop()

    assert client.status().connected is False
