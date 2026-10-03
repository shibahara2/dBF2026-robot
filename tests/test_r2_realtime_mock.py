import json
import time

import msgpack
import websocket
from ws_mock_server import running_mock

from mocks.r2_realtime_mock import R2RealtimeMock


def recv_until(ws, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        frame = ws.recv()
        if isinstance(frame, bytes):
            message = msgpack.unpackb(frame, raw=False)
            if predicate(message):
                return message
    raise AssertionError("expected message did not arrive")


def is_under_mode(value):
    return lambda m: m.get("type") == "robot_aggregator" and (
        m["data"]["under_mode"]["data"]["data"] == value
    )


def test_video_path_still_streams_frames():
    with running_mock(R2RealtimeMock(step_seconds=0.05, aggregator_interval=0.02)) as port:
        ws = websocket.create_connection(f"ws://127.0.0.1:{port}/zed2i", timeout=2)
        try:
            assert ws.recv() == b"frame"
        finally:
            ws.close()


def test_realtime_runs_the_sequence_after_play_navigation5():
    realtime = R2RealtimeMock(step_seconds=0.05, aggregator_interval=0.02)
    with running_mock(realtime) as port:
        ws = websocket.create_connection(f"ws://127.0.0.1:{port}/realtime", timeout=2)
        try:
            recv_until(ws, is_under_mode("mock_m1"))
            ws.send(json.dumps({"type": "play_navigation5", "data": {"value": True}}))
            reply = recv_until(ws, lambda m: m.get("type") == "play_navigation5_rp")
            assert reply["data"] == {"success": True}
            recv_until(ws, is_under_mode("mock_m5"))
            recv_until(ws, is_under_mode("mock_m1"))
        finally:
            ws.close()
    assert realtime.received[0] == {"type": "play_navigation5", "data": {"value": True}}


def test_realtime_can_reject_or_ignore_the_start():
    rejecting = R2RealtimeMock(step_seconds=0.05, start_reply="fail", aggregator_interval=0.02)
    with running_mock(rejecting) as port:
        ws = websocket.create_connection(f"ws://127.0.0.1:{port}/realtime", timeout=2)
        try:
            ws.send(json.dumps({"type": "play_navigation5", "data": {"value": True}}))
            reply = recv_until(ws, lambda m: m.get("type") == "play_navigation5_rp")
            assert reply["data"] == {"success": False}
        finally:
            ws.close()

    silent = R2RealtimeMock(step_seconds=0.05, start_reply="none", aggregator_interval=0.02)
    with running_mock(silent) as port:
        ws = websocket.create_connection(f"ws://127.0.0.1:{port}/realtime", timeout=2)
        try:
            ws.send(json.dumps({"type": "play_navigation5", "data": {"value": True}}))
            seen = []
            deadline = time.monotonic() + 0.3
            while time.monotonic() < deadline:
                frame = ws.recv()
                seen.append(msgpack.unpackb(frame, raw=False)["type"])
            assert "play_navigation5_rp" not in seen
        finally:
            ws.close()


def test_from_env(monkeypatch):
    monkeypatch.setenv("R2_MOCK_STEP_SECONDS", "0.5")
    monkeypatch.setenv("R2_MOCK_START_REPLY", "none")

    mock = R2RealtimeMock.from_env()

    assert (mock.step_seconds, mock.start_reply) == (0.5, "none")
