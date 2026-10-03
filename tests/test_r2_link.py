import queue
import threading
import time

import msgpack

from app.clients.r2_link import (
    STATE_CONNECTED,
    STATE_CONNECTING,
    STATE_DISCONNECTED,
    STATE_STOPPED,
    R2Link,
    encode_json,
)


class FakeSocket:
    def __init__(self):
        self.incoming = queue.Queue()
        self.sent = []
        self.closed = False
        self.connected = True

    def recv(self):
        item = self.incoming.get(timeout=2)
        if isinstance(item, Exception):
            raise item
        return item

    def send(self, text):
        self.sent.append(text)

    def close(self):
        self.closed = True
        self.connected = False
        self.incoming.put(ConnectionError("closed"))


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def make_link(sockets, attempts=None):
    sockets = iter(sockets)

    def factory(url, timeout):
        if attempts is not None:
            attempts.append((url, timeout))
        item = next(sockets)
        if isinstance(item, Exception):
            raise item
        return item

    return R2Link(
        "ws://r2.test:9002/realtime",
        websocket_factory=factory,
        reconnect_delay=0.01,
        connect_timeout=5.0,
    )


def test_encode_json_matches_javascript_json_stringify():
    assert encode_json({"type": "play_navigation5", "data": {"value": True}}) == (
        '{"type":"play_navigation5","data":{"value":true}}'
    )


def test_start_connects_and_reports_states():
    socket = FakeSocket()
    link = make_link([socket])
    states = []
    link.on_state_change = states.append

    link.start()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)
    link.close()

    assert states[:2] == [STATE_CONNECTING, STATE_CONNECTED]
    assert link.state()[1] is not None


def test_decodes_msgpack_frames_and_skips_text_and_garbage():
    socket = FakeSocket()
    link = make_link([socket])
    received = []
    link.on_message = received.append
    link.start()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)

    socket.incoming.put("text frame")
    socket.incoming.put(b"\xc1")  # 0xc1 is never valid MessagePack
    socket.incoming.put(msgpack.packb({"type": "robot_aggregator", "data": {}}))

    wait_until(lambda: received == [{"type": "robot_aggregator", "data": {}}])
    link.close()


def test_send_json_sends_compact_json_while_connected():
    socket = FakeSocket()
    link = make_link([socket])
    link.start()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)

    assert link.send_json({"type": "gamepad", "data": {"combo": [0, 0, 1, 0, 0]}}) is True
    link.close()

    assert socket.sent == ['{"type":"gamepad","data":{"combo":[0,0,1,0,0]}}']


def test_send_json_returns_false_when_not_connected():
    link = make_link([])

    assert link.send_json({"type": "gamepad"}) is False


def test_reconnects_after_connection_lost():
    first, second = FakeSocket(), FakeSocket()
    attempts = []
    link = make_link([first, second], attempts)
    states = []
    link.on_state_change = states.append
    link.start()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)

    first.incoming.put(ConnectionError("dropped"))

    wait_until(lambda: len(attempts) == 2 and link.state()[0] == STATE_CONNECTED)
    link.close()
    assert STATE_DISCONNECTED in states
    assert attempts[0] == ("ws://r2.test:9002/realtime", 5.0)


def test_retries_when_connecting_fails():
    socket = FakeSocket()
    attempts = []
    link = make_link([ConnectionRefusedError("refused"), socket], attempts)

    link.start()

    wait_until(lambda: link.state()[0] == STATE_CONNECTED)
    link.close()
    assert len(attempts) == 2


def test_manual_disconnect_stops_reconnecting_until_connect():
    first, second = FakeSocket(), FakeSocket()
    attempts = []
    link = make_link([first, second], attempts)
    link.start()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)

    link.disconnect()
    wait_until(lambda: link.state()[0] == STATE_STOPPED)
    time.sleep(0.1)  # ten reconnect delays
    assert len(attempts) == 1
    assert first.closed

    link.connect()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)
    link.close()
    assert len(attempts) == 2
