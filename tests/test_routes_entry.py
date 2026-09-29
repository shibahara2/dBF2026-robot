import pytest
from flask import Flask

from app.routes.entry import entry_bp


class FakeStateMachine:
    def __init__(self, record_result=True, clear_result=True):
        self.record_result = record_result
        self.clear_result = clear_result
        self.stages = []
        self.clear_calls = 0

    def record_kiosk_stage(self, stage):
        self.stages.append(stage)
        return self.record_result

    def clear_entry(self):
        self.clear_calls += 1
        return self.clear_result


def make_client(state_machine):
    app = Flask(__name__)
    app.config["STATE_MACHINE"] = state_machine
    app.register_blueprint(entry_bp)
    return app.test_client()


@pytest.mark.parametrize("stage", ["start", "select"])
def test_entry_records_kiosk_stage(stage):
    state_machine = FakeStateMachine()

    resp = make_client(state_machine).post("/api/entry", json={"stage": stage})

    assert resp.status_code == 202
    assert state_machine.stages == [stage]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"stage": "checkin"},
        {"stage": "search"},
        {"stage": None},
        # The kiosk never names the source; the server decides it.
        {"source": "voice", "stage": "speech"},
    ],
)
def test_entry_rejects_unknown_stage(body):
    state_machine = FakeStateMachine()

    resp = make_client(state_machine).post("/api/entry", json=body)

    assert resp.status_code == 422
    assert state_machine.stages == []


def test_entry_returns_409_while_cycle_in_progress():
    resp = make_client(FakeStateMachine(record_result=False)).post(
        "/api/entry", json={"stage": "start"}
    )

    assert resp.status_code == 409


@pytest.mark.parametrize("cleared", [True, False])
def test_delete_entry_reports_whether_it_cleared(cleared):
    state_machine = FakeStateMachine(clear_result=cleared)

    resp = make_client(state_machine).delete("/api/entry")

    assert resp.status_code == 200
    assert resp.get_json() == {"cleared": cleared}
    assert state_machine.clear_calls == 1
