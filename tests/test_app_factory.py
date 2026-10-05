import json
import time

from app import create_app


class FakeR2Controller:
    """An R2 that is always connected and loads the drink instantly."""

    def __init__(self):
        self.listeners = []

    def snapshot(self):
        return {"connection": "connected", "status": "completed", "starting": False,
                "failure": None, "failure_message": None}

    def wait_until(self, predicate):
        snap = self.snapshot()
        assert predicate(snap)
        return snap

    def start_load_drink(self):
        return None

    def add_listener(self, listener):
        self.listeners.append(listener)


class FakePFClient:
    def get_guide_robot_status(self):
        return "ready"

    def post_drink_placed(self):
        return True


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_checkin_then_events_reflect_state_machine_progress():
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())
    client = app.test_client()
    state_machine = app.config["STATE_MACHINE"]

    resp = client.post("/api/checkin", json={"reservation_id": "RSV-0001"})
    assert resp.status_code == 200

    events_resp = client.get("/api/events")
    first_chunk = next(iter(events_resp.response)).decode("utf-8")
    payload = json.loads(first_chunk[len("data: "):].strip())
    assert payload["guest_name"] in ("田中太郎", None)
    events_resp.close()

    # Prove the cycle actually completes successfully back to
    # waiting/awaiting_checkin through the wired Flask app, rather than
    # merely not crashing (see finding #2 of the final review).
    assert wait_until(
        lambda: state_machine.snapshot()["phase"] == "waiting"
        and state_machine.snapshot()["step"] == "awaiting_checkin",
        timeout=8.0,
    )
    final = state_machine.snapshot()
    assert final["error_message"] is None
    assert final["guest_name"] is None


def test_second_checkin_is_rejected_immediately_after_first():
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())
    client = app.test_client()

    first = client.post("/api/checkin", json={"reservation_id": "RSV-0001"})
    assert first.status_code == 200

    second = client.post("/api/checkin", json={"reservation_id": "RSV-0003"})
    assert second.status_code in (200, 409)


def test_search_then_checkin_against_the_seeded_reservations():
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())
    client = app.test_client()
    state_machine = app.config["STATE_MACHINE"]

    found = client.post("/api/reservations/search", json={"query": "DBF-1003"})
    assert found.status_code == 200
    reservations = found.get_json()["reservations"]
    assert len(reservations) == 1
    reservation = reservations[0]
    assert reservation["guest_name"] == "鈴木翔太"

    resp = client.post(
        "/api/checkin", json={"reservation_id": reservation["reservation_id"]}
    )
    assert resp.status_code == 200
    assert resp.get_json()["reservation"]["status"] == "reserved"

    assert wait_until(
        lambda: state_machine.snapshot()["step"] == "awaiting_checkin"
        and state_machine.snapshot()["phase"] == "waiting",
        timeout=8.0,
    )

    # Check-in never writes back to the store, so the same reservation can run
    # the demo again once the cycle is done.
    again = client.post(
        "/api/checkin", json={"reservation_id": reservation["reservation_id"]}
    )
    assert again.status_code == 200


def test_index_route_served_through_app_factory():
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())
    client = app.test_client()

    resp = client.get("/")

    assert resp.status_code == 200
    assert b'id="search-form"' in resp.data

    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_voice_start_blocked_while_kiosk_user_is_selecting():
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())
    client = app.test_client()
    state_machine = app.config["STATE_MACHINE"]

    assert client.post("/api/visual/start", json={}).status_code == 202
    state_machine.record_kiosk_stage("select")

    assert client.post("/api/voice/start", json={}).status_code == 409
    snap = state_machine.snapshot()
    assert (snap["entry_source"], snap["entry_stage"]) == ("visual", "select")


def test_entry_idle_seconds_comes_from_config(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "ENTRY_IDLE_SECONDS", 0.0)
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())
    client = app.test_client()
    app.config["STATE_MACHINE"].record_kiosk_stage("start")

    # With no idle window, an abandoned kiosk entry never blocks a start.
    assert client.post("/api/voice/start", json={}).status_code == 202


def test_kiosk_flow_records_entry_through_checkin():
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())
    client = app.test_client()
    state_machine = app.config["STATE_MACHINE"]

    def entry():
        snap = state_machine.snapshot()
        return snap["entry_source"], snap["entry_stage"]

    assert client.post("/api/entry", json={"stage": "start"}).status_code == 202
    assert entry() == ("screen", "start")
    assert client.post("/api/entry", json={"stage": "select"}).status_code == 202
    assert entry() == ("screen", "select")
    assert client.post("/api/checkin", json={"reservation_id": "RSV-0001"}).status_code == 200
    assert entry()[1] == "checkin"
    assert wait_until(lambda: entry() == (None, None), timeout=8.0)


def test_back_to_start_clears_visual_entry():
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())
    client = app.test_client()

    client.post("/api/visual/start", json={})
    resp = client.delete("/api/entry")

    assert resp.get_json() == {"cleared": True}
    assert app.config["STATE_MACHINE"].snapshot()["entry_source"] is None


def test_voice_turns_are_wired_into_app_factory():
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())
    client = app.test_client()

    assert client.post(
        "/api/voice/turns", json={"text": "こんにちは", "outcome": "chat", "reply": "こんにちは。"}
    ).status_code == 202
    assert client.get("/api/voice/turns").get_json()["turns"][0]["text"] == "こんにちは"


def test_default_app_builds_an_r2_link_without_starting_it_when_asked(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "R2_WS_URL", "ws://r2.test:9002/realtime")
    app = create_app(pf_client=FakePFClient(), start_r2=False)

    link = app.config["R2_LINK"]
    assert link.url == "ws://r2.test:9002/realtime"
    assert link.state()[0] == "stopped"
    assert app.config["R2_CONTROLLER"].snapshot()["status"] == "completed"


def test_r2_changes_are_published_as_typed_sse_events():
    controller = FakeR2Controller()
    app = create_app(r2_controller=controller, pf_client=FakePFClient())
    subscriber = app.config["EVENT_BROADCASTER"].subscribe()

    controller.listeners[0]({"status": "loading", "connection": "connected"})

    assert subscriber.get(timeout=1) == {
        "type": "r2_state",
        "status": "loading",
        "connection": "connected",
    }


def test_r2_debug_routes_are_registered():
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())

    assert app.test_client().get("/api/debug/r2").status_code == 200


def test_pf_debug_routes_use_the_apps_pf_client():
    class RawPFClient(FakePFClient):
        def raw_get_status(self):
            return {"method": "GET", "status_code": 200}

    app = create_app(r2_controller=FakeR2Controller(), pf_client=RawPFClient())
    resp = app.test_client().post("/api/debug/pf/status")
    assert resp.status_code == 200
    assert resp.get_json() == {"method": "GET", "status_code": 200}
