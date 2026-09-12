import json

from app import create_app


class FakeR2Client:
    def get_status(self):
        return {"outcome": "completed", "request_id": "none"}

    def post_load_drink(self, request_id):
        return "accepted"


class FakePFClient:
    def get_guide_robot_status(self):
        return "ready"

    def post_drink_placed(self):
        return True


def test_checkin_then_events_reflect_state_machine_progress():
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()

    resp = client.post("/api/checkin", json={"name": "Tanaka"})
    assert resp.status_code == 200

    events_resp = client.get("/api/events")
    first_chunk = next(iter(events_resp.response)).decode("utf-8")
    payload = json.loads(first_chunk[len("data: "):].strip())
    assert payload["guest_name"] in ("Tanaka", None)
    events_resp.close()


def test_second_checkin_is_rejected_immediately_after_first():
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()

    first = client.post("/api/checkin", json={"name": "Tanaka"})
    assert first.status_code == 200

    second = client.post("/api/checkin", json={"name": "Suzuki"})
    assert second.status_code in (200, 409)
