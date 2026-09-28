from flask import Flask

from app.routes.visual import visual_bp


class FakeBroadcaster:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


class FakeStateMachine:
    def __init__(self, phase="waiting", step="awaiting_checkin"):
        self.phase = phase
        self.step = step

    def snapshot(self):
        return {"phase": self.phase, "step": self.step}


def make_client(state_machine=None):
    app = Flask(__name__)
    app.config["EVENT_BROADCASTER"] = FakeBroadcaster()
    app.config["STATE_MACHINE"] = state_machine or FakeStateMachine()
    app.config["VISUAL_START_COOLDOWN_SECONDS"] = 5.0
    app.register_blueprint(visual_bp)
    return app.test_client(), app


def test_visual_start_publishes_ui_action_without_starting_checkin():
    client, app = make_client()

    response = client.post("/api/visual/start", json={})

    assert response.status_code == 202
    assert response.get_json() == {"message": "start action accepted"}
    assert app.config["EVENT_BROADCASTER"].events == [
        {"type": "ui_action", "action": "start_checkin"}
    ]


def test_visual_start_is_rejected_when_cycle_is_active():
    client, app = make_client(
        FakeStateMachine(phase="active", step="polling_r2_active")
    )

    response = client.post("/api/visual/start", json={})

    assert response.status_code == 409
    assert app.config["EVENT_BROADCASTER"].events == []


def test_visual_start_is_rate_limited():
    client, app = make_client()

    first = client.post("/api/visual/start", json={})
    second = client.post("/api/visual/start", json={})

    assert first.status_code == 202
    assert second.status_code == 429
    assert len(app.config["EVENT_BROADCASTER"].events) == 1
