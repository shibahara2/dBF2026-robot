import pytest
from flask import Flask

from app.routes.external_start import external_start_bp


class FakeBroadcaster:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


class FakeStateMachine:
    def __init__(self, available=True, start_result=True):
        self.available = available
        self.start_result = start_result
        self.started = []

    def external_start_available(self):
        return self.available

    def start_external_entry(self, source):
        self.started.append(source)
        return self.start_result


def make_client(state_machine=None):
    app = Flask(__name__)
    app.config["EVENT_BROADCASTER"] = FakeBroadcaster()
    app.config["STATE_MACHINE"] = state_machine or FakeStateMachine()
    app.config["VISUAL_START_COOLDOWN_SECONDS"] = 5.0
    app.register_blueprint(external_start_bp)
    return app.test_client(), app


@pytest.mark.parametrize(
    "path, source", [("/api/visual/start", "visual"), ("/api/voice/start", "voice")]
)
def test_start_records_entry_and_opens_search(path, source):
    client, app = make_client()

    response = client.post(path, json={})

    assert response.status_code == 202
    assert response.get_json() == {"message": "start action accepted"}
    assert app.config["STATE_MACHINE"].started == [source]
    assert app.config["EVENT_BROADCASTER"].events == [
        {"type": "ui_action", "action": "start_checkin"}
    ]


@pytest.mark.parametrize("path", ["/api/visual/start", "/api/voice/start"])
def test_start_rejected_when_not_available(path):
    # Cycle in progress, or someone is using the kiosk.
    state_machine = FakeStateMachine(available=False)
    client, app = make_client(state_machine)

    response = client.post(path, json={})

    assert response.status_code == 409
    assert state_machine.started == []
    assert app.config["EVENT_BROADCASTER"].events == []


def test_start_rejected_when_entry_recording_loses_race():
    state_machine = FakeStateMachine(available=True, start_result=False)
    client, app = make_client(state_machine)

    response = client.post("/api/voice/start", json={})

    assert response.status_code == 409
    assert app.config["EVENT_BROADCASTER"].events == []


def test_start_is_rate_limited_per_source():
    client, app = make_client()

    visual_first = client.post("/api/visual/start", json={})
    visual_second = client.post("/api/visual/start", json={})
    voice_first = client.post("/api/voice/start", json={})

    assert visual_first.status_code == 202
    assert visual_second.status_code == 429
    assert voice_first.status_code == 202
    assert app.config["STATE_MACHINE"].started == ["visual", "voice"]
