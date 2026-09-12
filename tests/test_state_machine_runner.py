import threading
import time

from app.state_machine import StateMachine, StateMachineRunner, PHASE_WAITING, STEP_AWAITING_CHECKIN


class FakeR2Client:
    def __init__(self, status_sequence, load_drink_result="accepted"):
        self._status_sequence = list(status_sequence)
        self.load_drink_result = load_drink_result

    def get_status(self):
        if len(self._status_sequence) > 1:
            return self._status_sequence.pop(0)
        return self._status_sequence[0]

    def post_load_drink(self, request_id):
        return self.load_drink_result


class FakePFClient:
    def __init__(self, status_sequence, placed_result=True):
        self._status_sequence = list(status_sequence)
        self.placed_result = placed_result

    def get_guide_robot_status(self):
        if len(self._status_sequence) > 1:
            return self._status_sequence.pop(0)
        return self._status_sequence[0]

    def post_drink_placed(self):
        return self.placed_result


def start_runner_thread(runner):
    thread = threading.Thread(target=runner.run_forever, daemon=True)
    thread.start()
    return thread


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_request_checkin_runs_cycle_in_background_thread():
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "completed", "request_id": None},
        ]
    )
    pf = FakePFClient(["ready"])
    sm = StateMachine(r2_client=r2, pf_client=pf, on_change=lambda snap: None, sleep=lambda s: None)
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    assert runner.request_checkin("Tanaka") is True

    assert wait_until(
        lambda: sm.snapshot()["phase"] == PHASE_WAITING
        and sm.snapshot()["step"] == STEP_AWAITING_CHECKIN
    )


def test_request_checkin_rejected_while_cycle_in_progress():
    r2 = FakeR2Client(status_sequence=[{"outcome": "loading", "request_id": "none"}])
    pf = FakePFClient(["ready"])
    sm = StateMachine(r2_client=r2, pf_client=pf, on_change=lambda snap: None, sleep=lambda s: None)
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    assert runner.request_checkin("Tanaka") is True
    assert wait_until(lambda: sm.snapshot()["step"] != STEP_AWAITING_CHECKIN)

    assert runner.request_checkin("Suzuki") is False


def test_request_reset_is_synchronous_and_does_not_need_the_thread():
    r2 = FakeR2Client(status_sequence=[{"outcome": "failed", "request_id": "none"}])
    pf = FakePFClient(["ready"])
    sm = StateMachine(r2_client=r2, pf_client=pf, on_change=lambda snap: None, sleep=lambda s: None)
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    runner.request_checkin("Tanaka")
    assert wait_until(lambda: sm.snapshot()["phase"] == "error")

    assert runner.request_reset() is True
    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN


def test_request_reset_rejected_when_not_in_error():
    sm = StateMachine(
        r2_client=FakeR2Client([{"outcome": "completed", "request_id": "none"}]),
        pf_client=FakePFClient(["ready"]),
        on_change=lambda snap: None,
    )
    runner = StateMachineRunner(sm)
    assert runner.request_reset() is False
