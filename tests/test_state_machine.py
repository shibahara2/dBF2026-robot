from app.state_machine import (
    StateMachine,
    PHASE_WAITING,
    PHASE_ACTIVE,
    PHASE_ERROR,
    STEP_AWAITING_CHECKIN,
)


class FakeR2Client:
    def __init__(self, status_sequence, load_drink_result="accepted"):
        self._status_sequence = list(status_sequence)
        self.load_drink_result = load_drink_result
        self.load_drink_calls = []

    def get_status(self):
        if len(self._status_sequence) > 1:
            return self._status_sequence.pop(0)
        return self._status_sequence[0]

    def post_load_drink(self, request_id):
        self.load_drink_calls.append(request_id)
        return self.load_drink_result


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
        r2_client=r2,
        pf_client=pf,
        on_change=changes.append,
        sleep=sleeps.append,
        poll_interval=2.0,
        request_id_factory=lambda: "RID",
    )
    if now is not None:
        kwargs["now"] = now
    return StateMachine(**kwargs)


def test_try_start_from_awaiting_checkin_succeeds_and_transitions():
    changes = []
    sm = make_state_machine(FakeR2Client([{"outcome": "completed", "request_id": "none"}]), FakePFClient(["ready"]), changes, [])

    assert sm.try_start("Tanaka") is True
    snap = sm.snapshot()
    assert snap["phase"] == PHASE_WAITING
    assert snap["step"] == "polling_pf_ready"
    assert snap["guest_name"] == "Tanaka"
    assert changes[-1] == snap


def test_try_start_fails_when_not_awaiting_checkin():
    sm = make_state_machine(
        FakeR2Client([{"outcome": "completed", "request_id": "none"}]), FakePFClient(["ready"]), [], []
    )
    assert sm.try_start("Tanaka") is True
    assert sm.try_start("Suzuki") is False


def test_full_cycle_returns_to_waiting_awaiting_checkin():
    changes = []
    sleeps = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "loading", "request_id": "none"},
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "loading", "request_id": "RID"},
            {"outcome": "completed", "request_id": "RID"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(status_sequence=["initializing", "ready"], placed_result=True)
    sm = make_state_machine(r2, pf, changes, sleeps)

    assert sm.try_start("Tanaka") is True
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["phase"] == PHASE_WAITING
    assert final["step"] == STEP_AWAITING_CHECKIN
    assert final["guest_name"] is None
    assert final["request_id"] is None
    assert final["error_message"] is None
    assert r2.load_drink_calls == ["RID"]
    assert pf.placed_calls == 1
    assert sleeps == [2.0, 2.0, 2.0]


def test_cycle_passes_through_active_phase():
    changes = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "returning", "request_id": "RID"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(status_sequence=["ready"], placed_result=True)
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    phases_seen = [c["phase"] for c in changes]
    assert PHASE_ACTIVE in phases_seen


def test_pf_fatal_error_moves_to_error_phase():
    changes = []
    r2 = FakeR2Client([{"outcome": "completed", "request_id": "none"}])
    pf = FakePFClient(["unexpected"])
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["phase"] == PHASE_ERROR
    assert "AI管制PF" in final["error_message"]
    assert final["guest_name"] == "Tanaka"


def test_r2_failed_during_waiting_moves_to_error_phase():
    changes = []
    r2 = FakeR2Client([{"outcome": "failed", "request_id": "none"}])
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert sm.snapshot()["phase"] == PHASE_ERROR


def test_r2_validation_error_on_load_drink_moves_to_error_phase():
    changes = []
    r2 = FakeR2Client(
        [{"outcome": "completed", "request_id": "none"}], load_drink_result="validation_error"
    )
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert sm.snapshot()["phase"] == PHASE_ERROR
    assert r2.load_drink_calls == ["RID"]


def test_r2_request_id_mismatch_during_active_moves_to_error_phase():
    changes = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "loading", "request_id": "OTHER"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert sm.snapshot()["phase"] == PHASE_ERROR


def test_r2_failed_during_active_moves_to_error_phase():
    changes = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "failed", "request_id": "RID"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert sm.snapshot()["phase"] == PHASE_ERROR


def test_pf_drink_placed_not_accepted_moves_to_error_immediately():
    changes = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "completed", "request_id": "RID"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(status_sequence=["ready"], placed_result=False)
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["phase"] == PHASE_ERROR
    assert pf.placed_calls == 1


def test_try_reset_from_error_returns_to_awaiting_checkin():
    changes = []
    r2 = FakeR2Client([{"outcome": "failed", "request_id": "none"}])
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])

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
    sm = make_state_machine(
        FakeR2Client([{"outcome": "completed", "request_id": "none"}]), FakePFClient(["ready"]), [], []
    )
    assert sm.try_reset() is False


def test_pf_and_r2_get_status_are_recorded_with_timestamps():
    changes = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "loading", "request_id": "none"},
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "loading", "request_id": "RID"},
            {"outcome": "completed", "request_id": "RID"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(status_sequence=["initializing", "ready"], placed_result=True)
    timestamps = iter(
        [f"2026-09-13T09:00:{i:02d}Z" for i in range(20)]
    )
    sm = make_state_machine(r2, pf, changes, [], now=lambda: next(timestamps))

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["pf_status"] == "ready"
    assert final["pf_status_at"] is not None
    assert final["r2_status"] == "completed"
    assert final["r2_status_at"] is not None
