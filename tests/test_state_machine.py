import pytest

from app.state_machine import (
    StateMachine,
    PHASE_WAITING,
    PHASE_ACTIVE,
    PHASE_ERROR,
    STEP_AWAITING_CHECKIN,
    STEP_STARTING_R2,
    STEP_WAITING_R2_PLACED,
    STEP_WAITING_R2_READY,
)


class FakeR2:
    """Scripted R2Controller: each wait walks through ``states`` until one fits.

    A state is a status string (connected) or a dict overriding snapshot keys.
    """

    def __init__(self, states=("completed",), start_result=None, after_start=("loading", "returning")):
        self.states = list(states)
        self.start_result = start_result
        self.after_start = list(after_start)
        self.start_calls = 0
        self.seen = []

    def _snapshot(self):
        state = self.states[0]
        snap = {"connection": "connected", "starting": False, "failure": None,
                "failure_message": None}
        snap.update({"status": state} if isinstance(state, str) else state)
        return snap

    def wait_until(self, predicate):
        while True:
            snap = self._snapshot()
            self.seen.append(snap["status"])
            if predicate(snap):
                return snap
            if len(self.states) == 1:
                raise AssertionError(f"would wait forever on {snap}")
            self.states.pop(0)

    def start_load_drink(self):
        self.start_calls += 1
        if self.start_result is None:
            self.states = list(self.after_start)
        return self.start_result


class FakePFClient:
    def __init__(self, status_sequence, placed_result=True):
        self._status_sequence = list(status_sequence)
        self.placed_result = placed_result
        self.placed_calls = 0

    def get_guide_robot_status(self):
        if len(self._status_sequence) > 1:
            return self._status_sequence.pop(0)
        return self._status_sequence[0]

    def post_drink_placed(self):
        self.placed_calls += 1
        return self.placed_result


def make_state_machine(r2, pf, changes, sleeps, now=None):
    kwargs = dict(
        r2_controller=r2,
        pf_client=pf,
        on_change=changes.append,
        sleep=sleeps.append,
        poll_interval=2.0,
    )
    if now is not None:
        kwargs["now"] = now
    return StateMachine(**kwargs)


def test_try_start_from_awaiting_checkin_succeeds_and_transitions():
    changes = []
    sm = make_state_machine(FakeR2(), FakePFClient(["ready"]), changes, [])

    assert sm.try_start("Tanaka") is True
    snap = sm.snapshot()
    assert snap["phase"] == PHASE_WAITING
    assert snap["step"] == "polling_pf_ready"
    assert snap["guest_name"] == "Tanaka"
    assert changes[-1] == snap


def test_snapshot_no_longer_carries_http_r2_fields():
    snap = make_state_machine(FakeR2(), FakePFClient(["ready"]), [], []).snapshot()

    for key in ("request_id", "r2_status", "r2_status_at"):
        assert key not in snap


def test_state_machine_preserves_positional_constructor_arguments():
    r2 = FakeR2()
    pf = FakePFClient(["ready"])
    sm = StateMachine(r2, pf, [].append, [].append, 2.0, lambda: "NOW")

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert r2.start_calls == 1


def test_try_start_fails_when_not_awaiting_checkin():
    sm = make_state_machine(FakeR2(), FakePFClient(["ready"]), [], [])
    assert sm.try_start("Tanaka") is True
    assert sm.try_start("Suzuki") is False


def test_full_cycle_returns_to_waiting_awaiting_checkin():
    changes = []
    sleeps = []
    r2 = FakeR2(states=["loading", "completed"], after_start=["loading", "returning"])
    pf = FakePFClient(status_sequence=["initializing", "ready"], placed_result=True)
    sm = make_state_machine(r2, pf, changes, sleeps)

    assert sm.try_start("Tanaka") is True
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["phase"] == PHASE_WAITING
    assert final["step"] == STEP_AWAITING_CHECKIN
    assert final["guest_name"] is None
    assert final["error_message"] is None
    assert r2.start_calls == 1
    assert pf.placed_calls == 1
    assert sleeps == [1.0, 2.0, 1.0, 1.0, 1.0, 1.0]
    steps = [c["step"] for c in changes]
    for step in (STEP_WAITING_R2_READY, STEP_STARTING_R2, STEP_WAITING_R2_PLACED):
        assert step in steps


def test_cycle_passes_through_active_phase():
    changes = []
    sm = make_state_machine(FakeR2(), FakePFClient(["ready"]), changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert PHASE_ACTIVE in [c["phase"] for c in changes]


def test_ready_wait_keeps_waiting_while_disconnected():
    r2 = FakeR2(states=[{"connection": "disconnected", "status": "completed"}, "completed"])
    sm = make_state_machine(r2, FakePFClient(["ready"]), [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert r2.start_calls == 1
    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN


def test_pf_fatal_error_moves_to_error_phase():
    sm = make_state_machine(FakeR2(), FakePFClient(["unexpected"]), [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["phase"] == PHASE_ERROR
    assert "AI管制PF" in final["error_message"]
    assert final["guest_name"] == "Tanaka"


def test_r2_failed_during_ready_wait_moves_to_error_phase():
    r2 = FakeR2(states=[{"status": "failed", "failure_message": "オペレーターがSTOPしました"}])
    sm = make_state_machine(r2, FakePFClient(["ready"]), [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert (final["phase"], final["step"]) == (PHASE_ERROR, STEP_WAITING_R2_READY)
    assert "STOP" in final["error_message"]
    assert r2.start_calls == 0


def test_r2_start_failure_moves_to_error_at_starting_r2():
    r2 = FakeR2(start_result="R2から開始の返事がありませんでした")
    sm = make_state_machine(r2, FakePFClient(["ready"]), [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert (final["phase"], final["step"]) == (PHASE_ERROR, STEP_STARTING_R2)
    assert "返事がありません" in final["error_message"]


def test_r2_failed_while_waiting_for_placement_moves_to_error():
    r2 = FakeR2(after_start=["loading", {"status": "failed", "failure_message": "動作中にR2との接続が切れました"}])
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert (final["phase"], final["step"]) == (PHASE_ERROR, STEP_WAITING_R2_PLACED)
    assert "接続が切れました" in final["error_message"]
    assert pf.placed_calls == 0


def test_placed_wait_accepts_completed_after_a_quick_return():
    # _m5 and _m1 can both land before the state machine wakes up.
    r2 = FakeR2(after_start=["completed"])
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert pf.placed_calls == 1
    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN


def test_pf_drink_placed_not_accepted_moves_to_error_immediately():
    pf = FakePFClient(status_sequence=["ready"], placed_result=False)
    sm = make_state_machine(FakeR2(), pf, [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert sm.snapshot()["phase"] == PHASE_ERROR
    assert pf.placed_calls == 1


def test_try_reset_from_error_returns_to_awaiting_checkin():
    sm = make_state_machine(FakeR2(states=["failed"]), FakePFClient(["ready"]), [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()
    assert sm.snapshot()["phase"] == PHASE_ERROR

    assert sm.try_reset() is True
    final = sm.snapshot()
    assert final["phase"] == PHASE_WAITING
    assert final["step"] == STEP_AWAITING_CHECKIN
    assert final["guest_name"] is None
    assert final["error_message"] is None


def test_try_reset_fails_when_not_in_error():
    sm = make_state_machine(FakeR2(), FakePFClient(["ready"]), [], [])
    assert sm.try_reset() is False


def test_pf_status_is_recorded_with_timestamp():
    timestamps = iter([f"2026-09-13T09:00:{i:02d}Z" for i in range(20)])
    sm = make_state_machine(
        FakeR2(), FakePFClient(["initializing", "ready"]), [], [], now=lambda: next(timestamps)
    )

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["pf_status"] == "ready"
    assert final["pf_status_at"] is not None


def test_resume_after_start_continues_from_placement_wait():
    changes = []
    r2 = FakeR2(start_result="R2から開始の返事がありませんでした")
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])
    sm.try_start("Tanaka")
    sm.run_started_cycle()
    assert sm.can_resume_after_start() is True

    assert sm.try_resume_after_start() is True
    assert sm.snapshot()["phase"] == PHASE_WAITING
    assert sm.snapshot()["error_message"] is None

    r2.states = ["loading", "returning"]  # the operator's resend succeeded
    sm.resume_after_start()

    assert r2.start_calls == 1
    assert pf.placed_calls == 1
    assert STEP_WAITING_R2_PLACED in [c["step"] for c in changes]
    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN


@pytest.mark.parametrize("states", [["completed"], ["failed"]])
def test_resume_after_start_rejected_unless_stopped_at_starting_r2(states):
    sm = make_state_machine(FakeR2(states=states), FakePFClient(["ready"]), [], [])
    if states == ["failed"]:
        sm.try_start("Tanaka")
        sm.run_started_cycle()  # error at waiting_r2_ready

    assert sm.can_resume_after_start() is False
    assert sm.try_resume_after_start() is False


# --- check-in entry tracking -------------------------------------------------


class FakeClock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

def _entry_state_machine(changes=None, clock=None, idle=60.0):
    sm = StateMachine(
        r2_controller=FakeR2(),
        pf_client=FakePFClient(["ready"]),
        on_change=(changes if changes is not None else []).append,
        sleep=lambda s: None,
        now=lambda: "2026-09-29T00:00:00Z",
        monotonic=clock or FakeClock(),
        entry_idle_seconds=idle,
    )
    return sm


def _entry(sm):
    snap = sm.snapshot()
    return snap["entry_source"], snap["entry_stage"], snap["entry_at"]


def test_snapshot_starts_without_entry():
    assert _entry(_entry_state_machine()) == (None, None, None)


def test_external_start_records_start_stage_and_publishes():
    changes = []
    sm = _entry_state_machine(changes)

    assert sm.start_external_entry("visual") is True

    assert _entry(sm) == ("visual", "start", "2026-09-29T00:00:00Z")
    assert changes[-1] == sm.snapshot()


def test_external_start_rejects_screen_source():
    sm = _entry_state_machine()

    try:
        sm.start_external_entry("screen")
    except ValueError:
        return
    raise AssertionError("screen is not an external source")


def test_external_start_rejected_while_entry_in_progress():
    sm = _entry_state_machine()
    sm.record_kiosk_stage("select")

    assert sm.external_start_available() is False
    assert sm.start_external_entry("voice") is False
    assert _entry(sm)[:2] == ("screen", "select")


def test_external_start_accepted_after_entry_idle_seconds():
    clock = FakeClock(1000.0)
    sm = _entry_state_machine(clock=clock, idle=60.0)
    sm.record_kiosk_stage("start")

    clock.value = 1059.9
    assert sm.start_external_entry("visual") is False
    clock.value = 1060.0
    assert sm.start_external_entry("visual") is True
    assert _entry(sm)[:2] == ("visual", "start")


def test_external_start_rejected_while_cycle_in_progress():
    sm = _entry_state_machine()
    sm.try_start("田中太郎")

    assert sm.external_start_available() is False
    assert sm.start_external_entry("visual") is False


def test_kiosk_stage_without_entry_is_screen():
    sm = _entry_state_machine()

    assert sm.record_kiosk_stage("start") is True

    assert _entry(sm)[:2] == ("screen", "start")


def test_kiosk_stage_keeps_external_source_even_after_idle_seconds():
    clock = FakeClock(1000.0)
    sm = _entry_state_machine(clock=clock, idle=60.0)
    sm.start_external_entry("voice")

    clock.value = 1500.0
    sm.record_kiosk_stage("select")

    assert _entry(sm)[:2] == ("voice", "select")


def test_back_to_search_returns_select_to_start_keeping_source():
    sm = _entry_state_machine()
    sm.start_external_entry("visual")
    sm.record_kiosk_stage("select")

    sm.record_kiosk_stage("start")

    assert _entry(sm)[:2] == ("visual", "start")


def test_kiosk_stage_rejects_unknown_stage():
    sm = _entry_state_machine()

    for stage in ["checkin", "search", None]:
        try:
            sm.record_kiosk_stage(stage)
        except ValueError:
            continue
        raise AssertionError(f"{stage!r} should be rejected")


def test_kiosk_stage_ignored_while_cycle_in_progress():
    sm = _entry_state_machine()
    sm.try_start("田中太郎")

    assert sm.record_kiosk_stage("start") is False
    assert _entry(sm)[:2] == ("screen", "checkin")


def test_try_start_records_checkin_with_inherited_source():
    sm = _entry_state_machine()
    sm.start_external_entry("visual")
    sm.record_kiosk_stage("select")

    sm.try_start("田中太郎")

    assert _entry(sm)[:2] == ("visual", "checkin")


def test_try_start_without_entry_records_screen_checkin():
    sm = _entry_state_machine()

    sm.try_start("田中太郎")

    assert _entry(sm)[:2] == ("screen", "checkin")


def test_clear_entry_forgets_any_source():
    changes = []
    sm = _entry_state_machine(changes)
    sm.start_external_entry("voice")

    assert sm.clear_entry() is True

    assert _entry(sm) == (None, None, None)
    assert changes[-1] == sm.snapshot()


def test_clear_entry_without_entry_returns_false():
    assert _entry_state_machine().clear_entry() is False


def test_clear_entry_ignored_while_cycle_in_progress():
    sm = _entry_state_machine()
    sm.try_start("田中太郎")

    assert sm.clear_entry() is False
    assert _entry(sm)[:2] == ("screen", "checkin")


def test_entry_cleared_when_cycle_returns_to_awaiting_checkin():
    sm = _entry_state_machine()
    sm.try_start("田中太郎")

    sm.run_started_cycle()

    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN
    assert _entry(sm) == (None, None, None)


def test_entry_cleared_on_reset_from_error():
    sm = _entry_state_machine()
    sm.try_start("田中太郎")
    sm.fail_unexpected("boom")

    assert sm.try_reset() is True
    assert _entry(sm) == (None, None, None)

