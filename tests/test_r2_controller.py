import threading
import time

import pytest

from app.clients.r2_controller import (
    FAILURE_DISCONNECTED,
    FAILURE_MANUAL,
    FAILURE_START_DISCONNECTED,
    FAILURE_START_NO_REPLY,
    FAILURE_START_REJECTED,
    FAILURE_MESSAGES,
    FAILURE_STOPPED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_LOADING,
    STATUS_RETURNING,
    R2Controller,
)
from app.clients.r2_link import encode_json

# Copied from what UI-DRP's JSON.stringify sends; must match byte for byte.
ENTER_NAV = (
    '{"type":"gamepad","data":{"button":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],'
    '"axis":[0,0,0,0,0,0],"combo":[0,0,1,0,0]}}'
)
LEAVE_NAV = (
    '{"type":"gamepad","data":{"button":[0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0],'
    '"axis":[0,0,0,0,0,0],"combo":[1,0,0,0,0]}}'
)
RELEASE = (
    '{"type":"gamepad","data":{"button":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],'
    '"axis":[0,0,0,0,0,0],"combo":[0,0,0,0,0]}}'
)
PLAY_TRUE = '{"type":"play_navigation5","data":{"value":true}}'
PLAY_FALSE = '{"type":"play_navigation5","data":{"value":false}}'


class FakeLink:
    def __init__(self, state="connected"):
        self.url = "ws://r2.test:9002/realtime"
        self.on_message = None
        self.on_state_change = None
        self._state = state
        self.sent = []
        self.on_send = None
        self.connect_calls = 0
        self.disconnect_calls = 0
        self._connection_id = 1 if state == "connected" else 0

    def state(self):
        return self._state, "2026-10-04T00:00:00Z"

    def connection_id(self):
        return self._connection_id

    def send_json(self, obj):
        if self._state != "connected":
            return False
        self.sent.append(encode_json(obj))
        if self.on_send is not None:
            self.on_send(obj)
        return True

    def connect(self):
        self.connect_calls += 1

    def disconnect(self):
        self.disconnect_calls += 1

    def set_state(self, state):
        if state == "connected" and self._state != "connected":
            self._connection_id += 1
        self._state = state
        self.on_state_change(state)

    def reconnect(self):
        self.set_state("disconnected")
        self.set_state("connected")

    def receive(self, message):
        self.on_message(message)


def reply(success):
    return {"type": "play_navigation5_rp", "data": {"success": success}}


def aggregator(under_mode):
    return {"type": "robot_aggregator", "data": {"under_mode": {"data": {"data": under_mode}}}}


def replies_with(link, success):
    def on_send(obj):
        if obj == {"type": "play_navigation5", "data": {"value": True}}:
            link.receive(reply(success))

    link.on_send = on_send


def make_controller(link=None, sleeps=None):
    link = link or FakeLink()
    controller = R2Controller(
        link,
        start_reply_timeout=0.05,
        sleep=(sleeps if sleeps is not None else []).append,
        now=lambda: "2026-10-04T00:00:00Z",
    )
    return link, controller


def loading_controller():
    link, controller = make_controller()
    replies_with(link, True)
    assert controller.start_load_drink() is None
    link.on_send = None
    link.sent.clear()
    return link, controller


def test_initial_snapshot():
    _, controller = make_controller()

    snap = controller.snapshot()

    assert snap["url"] == "ws://r2.test:9002/realtime"
    assert snap["connection"] == "connected"
    assert snap["status"] == STATUS_COMPLETED
    assert snap["failure"] is None
    assert snap["starting"] is False
    assert snap["under_mode"] is None


def test_start_sends_what_ui_drp_sends_and_starts_loading():
    sleeps = []
    link, controller = make_controller(sleeps=sleeps)
    replies_with(link, True)

    assert controller.start_load_drink() is None

    assert link.sent == [ENTER_NAV, PLAY_TRUE]
    assert sleeps == [2.0]
    snap = controller.snapshot()
    assert snap["status"] == STATUS_LOADING
    assert snap["last_reply"] == {"success": True}
    assert snap["last_reply_seconds"] is not None
    assert snap["starting"] is False


def test_start_rejected_fails():
    link, controller = make_controller()
    replies_with(link, False)

    reason = controller.start_load_drink()

    assert reason
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_START_REJECTED)


def test_start_without_reply_times_out():
    link, controller = make_controller()

    reason = controller.start_load_drink()

    assert reason
    assert link.sent == [ENTER_NAV, PLAY_TRUE]
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_START_NO_REPLY)


def test_start_disconnected_while_waiting_for_reply():
    link, controller = make_controller()

    def drop_on_play(obj):
        if obj["type"] == "play_navigation5":
            link.set_state("disconnected")

    link.on_send = drop_on_play

    assert controller.start_load_drink()
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_START_DISCONNECTED)


def test_start_refused_when_not_connected_or_not_completed():
    link, controller = make_controller(FakeLink(state="disconnected"))
    assert controller.start_load_drink()
    assert link.sent == []

    link, controller = loading_controller()
    assert controller.start_load_drink()
    assert link.sent == []


def test_late_reply_does_not_change_a_timed_out_start():
    link, controller = make_controller()
    controller.start_load_drink()

    link.receive(reply(True))

    snap = controller.snapshot()
    assert snap["status"] == STATUS_FAILED
    assert snap["last_reply"] == {"success": True}


def test_under_mode_m5_while_loading_then_m1_while_returning():
    link, controller = loading_controller()

    link.receive(aggregator("nav_m3"))
    assert controller.snapshot()["status"] == STATUS_LOADING
    link.receive(aggregator("nav_m5"))
    assert controller.snapshot()["status"] == STATUS_RETURNING
    link.receive(aggregator("nav_m1"))

    snap = controller.snapshot()
    assert snap["status"] == STATUS_COMPLETED
    assert snap["under_mode"] == "nav_m1"
    assert snap["under_mode_at"] == "2026-10-04T00:00:00Z"


def test_under_mode_ignored_outside_matching_status():
    link, controller = make_controller()
    link.receive(aggregator("nav_m5"))
    assert controller.snapshot()["status"] == STATUS_COMPLETED

    link, controller = loading_controller()
    link.receive(aggregator("nav_m1"))
    assert controller.snapshot()["status"] == STATUS_LOADING


def test_m5_that_was_already_current_does_not_count_again():
    link, controller = make_controller()
    link.receive(aggregator("nav_m5"))
    replies_with(link, True)
    controller.start_load_drink()

    link.receive(aggregator("nav_m5"))

    assert controller.snapshot()["status"] == STATUS_LOADING


def test_empty_or_missing_under_mode_is_ignored():
    link, controller = loading_controller()
    link.receive(aggregator("nav_m3"))

    link.receive(aggregator(""))
    link.receive({"type": "robot_aggregator", "data": {"battery_state": {}}})

    assert controller.snapshot()["under_mode"] == "nav_m3"


def test_disconnect_while_loading_fails_and_later_m1_is_ignored():
    link, controller = loading_controller()

    link.set_state("disconnected")
    link.set_state("connected")
    link.receive(aggregator("nav_m1"))

    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_DISCONNECTED)


def test_disconnect_while_completed_keeps_completed():
    link, controller = make_controller()

    link.set_state("disconnected")

    assert controller.snapshot()["status"] == STATUS_COMPLETED


def test_stop_sends_what_ui_drp_sends_and_fails():
    sleeps = []
    link, controller = make_controller(sleeps=sleeps)

    assert controller.stop() is None

    assert link.sent == [LEAVE_NAV] * 4 + [RELEASE, PLAY_FALSE]
    assert sleeps == [2.0]
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_STOPPED)


def test_stop_refused_when_disconnected():
    link, controller = make_controller(FakeLink(state="disconnected"))

    assert controller.stop()
    assert controller.snapshot()["status"] == STATUS_COMPLETED


def test_stop_during_start_aborts_the_start():
    link, controller = make_controller()
    sleeps = []
    results = {}

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 1:  # the 2s wait inside the start
            results["stop"] = controller.stop()

    controller._sleep = sleep

    reason = controller.start_load_drink()
    link.receive(reply(True))

    assert reason
    assert results["stop"] is None
    assert PLAY_TRUE not in link.sent
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_STOPPED)


@pytest.mark.parametrize(
    "start_status, target, allowed",
    [
        (STATUS_LOADING, STATUS_RETURNING, True),
        (STATUS_COMPLETED, STATUS_RETURNING, False),
        (STATUS_RETURNING, STATUS_COMPLETED, True),
        (STATUS_LOADING, STATUS_COMPLETED, False),
        (STATUS_LOADING, STATUS_FAILED, True),
        (STATUS_RETURNING, STATUS_FAILED, True),
        (STATUS_COMPLETED, STATUS_FAILED, False),
        (STATUS_LOADING, STATUS_LOADING, False),
    ],
)
def test_mark_rules(start_status, target, allowed):
    link, controller = loading_controller()
    if start_status == STATUS_RETURNING:
        link.receive(aggregator("nav_m5"))
    elif start_status == STATUS_COMPLETED:
        _, controller = make_controller()
    assert controller.snapshot()["status"] == start_status

    reason = controller.mark(target)

    assert (reason is None) is allowed
    snap = controller.snapshot()
    assert snap["status"] == (target if allowed else start_status)
    if allowed and target == STATUS_FAILED:
        assert snap["failure"] == FAILURE_MANUAL
    assert link.sent == []


def test_reset_only_from_failed():
    link, controller = make_controller()
    assert controller.reset()

    controller.stop()
    assert controller.reset() is None

    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_COMPLETED, None)


def test_resend_requires_a_start_failure_and_m1():
    link, controller = make_controller()
    controller.stop()
    assert controller.resend_start()  # stopped is not a start failure

    link, controller = make_controller()
    controller.start_load_drink()  # times out
    link.receive(aggregator("nav_m3"))
    assert controller.resend_start()  # not at A
    link.sent.clear()

    link.receive(aggregator("nav_m1"))
    replies_with(link, True)
    assert controller.resend_start() is None

    assert link.sent == [ENTER_NAV, PLAY_TRUE]
    assert controller.snapshot()["status"] == STATUS_LOADING


def test_connect_and_disconnect_are_passed_to_the_link():
    link, controller = make_controller()

    assert controller.connect() is None
    assert controller.disconnect() is None

    assert (link.connect_calls, link.disconnect_calls) == (1, 1)


def test_listeners_get_a_snapshot_on_every_change():
    link, controller = make_controller()
    seen = []
    controller.add_listener(lambda snap: seen.append(snap["status"]))

    link.receive(aggregator("nav_m1"))
    controller.stop()

    assert seen[-1] == STATUS_FAILED
    assert len(seen) >= 2


def test_wait_until_wakes_on_change():
    link, controller = loading_controller()
    result = {}

    waiter = threading.Thread(
        target=lambda: result.update(
            snap=controller.wait_until(lambda s: s["status"] != STATUS_LOADING)
        )
    )
    waiter.start()
    time.sleep(0.05)
    link.receive(aggregator("nav_m5"))
    waiter.join(timeout=2)

    assert result["snap"]["status"] == STATUS_RETURNING


def test_concurrent_disconnect_after_success_reply():
    """Test that disconnect between reply and LOADING status setting fails the start.

    This covers a race condition where a disconnect happens after the success
    reply is received but before the status transitions to LOADING.
    """
    link, controller = make_controller()

    def on_send_disconnect(obj):
        if obj["type"] == "play_navigation5":
            # Send success reply, then disconnect
            # This creates a race window between reply processing and status transition
            link.receive(reply(True))
            link.set_state("disconnected")

    link.on_send = on_send_disconnect

    # Start should fail due to disconnect, not succeed
    reason = controller.start_load_drink()

    snap = controller.snapshot()
    assert snap["status"] == STATUS_FAILED
    assert snap["failure"] == FAILURE_START_DISCONNECTED
    assert reason  # Should have a failure message


def test_stop_before_reply_processing_leaves_failed():
    """Test that stop() before reply is examined preserves failed(stopped) status.

    If stop() is called while waiting for a reply, even if a success reply arrives,
    the abort_start check must cause the start to fail with STOPPED, not LOADING.
    The abort_start flag set by stop() takes precedence over any success reply.
    """
    link, controller = make_controller()

    def on_send_with_stop(obj):
        if obj["type"] == "play_navigation5":
            # Send success reply, then call stop
            # stop() sets abort_start=True, which will be checked before using the reply
            link.receive(reply(True))
            controller.stop()

    link.on_send = on_send_with_stop

    # Start should fail due to stop, not succeed with LOADING
    reason = controller.start_load_drink()

    snap = controller.snapshot()
    assert snap["status"] == STATUS_FAILED
    assert snap["failure"] == FAILURE_STOPPED
    assert reason  # Should have a failure message


def test_reconnect_during_the_2s_wait_does_not_send_play_true():
    link, controller = make_controller()
    controller._sleep = lambda seconds: link.reconnect()

    reason = controller.start_load_drink()

    assert reason == FAILURE_MESSAGES[FAILURE_START_DISCONNECTED]
    assert link.sent == [ENTER_NAV]
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_START_DISCONNECTED)


def test_reconnect_during_the_stop_wait_does_not_send_play_false():
    link, controller = make_controller()
    controller._sleep = lambda seconds: link.reconnect()

    reason = controller.stop()

    assert reason == "STOP の送信中にR2との接続が切れました"
    assert link.sent == [LEAVE_NAV] * 4 + [RELEASE]
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_STOPPED)


def test_reconnect_while_waiting_for_the_reply_is_start_disconnected():
    link, controller = make_controller()

    def on_send(obj):
        if obj["type"] == "play_navigation5":
            link.reconnect()

    link.on_send = on_send

    reason = controller.start_load_drink()

    assert reason == FAILURE_MESSAGES[FAILURE_START_DISCONNECTED]
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_START_DISCONNECTED)


def test_reply_to_play_false_is_not_taken_as_the_start_reply():
    link, controller = make_controller()
    controller._awaiting_reply = True
    controller._pending_value = False

    link.receive(reply(True))

    assert controller._reply is None
    assert controller._awaiting_reply is True
    assert controller.snapshot()["last_reply"] == {"success": True}


def test_snapshot_connection_follows_the_controllers_own_view():
    link, controller = make_controller()
    link._state = "disconnected"  # the link changed but the callback has not run yet

    snap = controller.snapshot()

    assert snap["connection"] == "connected"
    link.set_state("disconnected")
    assert controller.snapshot()["connection"] == "disconnected"
