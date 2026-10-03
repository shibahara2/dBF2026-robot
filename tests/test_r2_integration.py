"""Real R2Link + R2Controller against the real /realtime mock over a socket."""

from ws_mock_server import running_mock

from app.clients.r2_controller import STATUS_COMPLETED, STATUS_LOADING, STATUS_RETURNING, R2Controller
from app.clients.r2_link import R2Link
from mocks.r2_realtime_mock import R2RealtimeMock


def test_controller_runs_a_full_cycle_against_the_mock():
    realtime = R2RealtimeMock(step_seconds=0.1, aggregator_interval=0.02)
    with running_mock(realtime) as port:
        link = R2Link(f"ws://127.0.0.1:{port}/realtime", reconnect_delay=0.05)
        controller = R2Controller(link, start_reply_timeout=2.0, sleep=lambda s: None)
        seen = []
        controller.add_listener(lambda snap: seen.append(snap["status"]))
        link.start()
        try:
            controller.wait_until(
                lambda s: s["connection"] == "connected" and s["under_mode"] == "mock_m1"
            )
            assert controller.start_load_drink() is None
            snap = controller.wait_until(lambda s: s["status"] == STATUS_COMPLETED)
        finally:
            link.close()

    assert snap["under_mode"] == "mock_m1"
    assert STATUS_LOADING in seen and STATUS_RETURNING in seen
    assert [m["type"] for m in realtime.received] == ["gamepad", "play_navigation5"]
