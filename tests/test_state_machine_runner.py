import threading
import time

from app.state_machine import StateMachine, StateMachineRunner, PHASE_WAITING, STEP_AWAITING_CHECKIN


class FakeR2:
    def __init__(self, status="completed", start_result=None):
        self.status = status
        self.start_result = start_result

    def wait_until(self, predicate):
        while True:
            snap = {"connection": "connected", "status": self.status, "starting": False,
                    "failure": None, "failure_message": None}
            if predicate(snap):
                return snap
            time.sleep(0.01)

    def start_load_drink(self):
        if self.start_result is None:
            self.status = "returning"
        return self.start_result


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


def make_machine(r2, pf=None):
    return StateMachine(
        r2_controller=r2,
        pf_client=pf or FakePFClient(["ready"]),
        on_change=lambda snap: None,
        sleep=lambda s: None,
    )


def test_request_checkin_runs_cycle_in_background_thread():
    sm = make_machine(FakeR2())
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    assert runner.request_checkin("Tanaka") is True

    assert wait_until(
        lambda: sm.snapshot()["phase"] == PHASE_WAITING
        and sm.snapshot()["step"] == STEP_AWAITING_CHECKIN
    )


def test_request_checkin_rejected_while_cycle_in_progress():
    sm = make_machine(FakeR2(status="loading"))
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    assert runner.request_checkin("Tanaka") is True
    assert wait_until(lambda: sm.snapshot()["step"] != STEP_AWAITING_CHECKIN)

    assert runner.request_checkin("Suzuki") is False


def test_request_reset_is_synchronous_and_does_not_need_the_thread():
    sm = make_machine(FakeR2(status="failed"))
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    runner.request_checkin("Tanaka")
    assert wait_until(lambda: sm.snapshot()["phase"] == "error")

    assert runner.request_reset() is True
    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN


class RaisingPFClient:
    def get_guide_robot_status(self):
        raise RuntimeError("boom: unexpected failure deep in the client")

    def post_drink_placed(self):
        return True


def test_unexpected_exception_in_cycle_does_not_wedge_the_thread():
    sm = make_machine(FakeR2(), RaisingPFClient())
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    assert runner.request_checkin("Tanaka") is True

    assert wait_until(lambda: sm.snapshot()["phase"] == "error")

    # The background thread must still be alive and able to service further
    # requests (i.e. it wasn't killed by the unhandled exception).
    assert runner.request_reset() is True
    assert wait_until(
        lambda: sm.snapshot()["phase"] == PHASE_WAITING
        and sm.snapshot()["step"] == STEP_AWAITING_CHECKIN
    )


def test_request_reset_rejected_when_not_in_error():
    runner = StateMachineRunner(make_machine(FakeR2()))
    assert runner.request_reset() is False


def test_request_resume_after_start_continues_a_failed_start_on_the_thread():
    r2 = FakeR2(start_result="R2から開始の返事がありませんでした")
    sm = make_machine(r2)
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    runner.request_checkin("Tanaka")
    assert wait_until(lambda: sm.snapshot()["phase"] == "error")
    assert runner.can_resume_after_start() is True

    r2.status = "returning"  # the operator's resend succeeded
    assert runner.request_resume_after_start() is True
    assert wait_until(
        lambda: sm.snapshot()["phase"] == PHASE_WAITING
        and sm.snapshot()["step"] == STEP_AWAITING_CHECKIN
    )


def test_request_resume_after_start_rejected_when_idle():
    runner = StateMachineRunner(make_machine(FakeR2()))
    assert runner.can_resume_after_start() is False
    assert runner.request_resume_after_start() is False
