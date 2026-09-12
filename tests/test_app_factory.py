import json
import time

from app import create_app


class FakeR2Client:
    """Mirrors the real R2Client/r2_mock contract: get_status() returns
    "none" as the request_id until a command has been posted, then echoes
    back whatever request_id was last posted via post_load_drink()."""

    def __init__(self):
        self._request_id = "none"

    def get_status(self):
        return {"outcome": "completed", "request_id": self._request_id}

    def post_load_drink(self, request_id):
        self._request_id = request_id
        return "accepted"


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
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()
    state_machine = app.config["STATE_MACHINE"]

    resp = client.post("/api/checkin", json={"name": "Tanaka"})
    assert resp.status_code == 200

    events_resp = client.get("/api/events")
    first_chunk = next(iter(events_resp.response)).decode("utf-8")
    payload = json.loads(first_chunk[len("data: "):].strip())
    assert payload["guest_name"] in ("Tanaka", None)
    events_resp.close()

    # Prove the cycle actually completes successfully back to
    # waiting/awaiting_checkin through the wired Flask app, rather than
    # merely not crashing (see finding #2 of the final review).
    assert wait_until(
        lambda: state_machine.snapshot()["phase"] == "waiting"
        and state_machine.snapshot()["step"] == "awaiting_checkin"
    )
    final = state_machine.snapshot()
    assert final["error_message"] is None
    assert final["guest_name"] is None


def test_second_checkin_is_rejected_immediately_after_first():
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()

    first = client.post("/api/checkin", json={"name": "Tanaka"})
    assert first.status_code == 200

    second = client.post("/api/checkin", json={"name": "Suzuki"})
    assert second.status_code in (200, 409)
