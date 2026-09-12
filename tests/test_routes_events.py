import json

from flask import Flask

from app.routes.events import events_bp


class FakeBroadcaster:
    def __init__(self):
        self.published = []

    def subscribe(self):
        import queue

        q = queue.Queue()
        q.put({"phase": "active", "step": "polling_r2_active"})
        return q

    def unsubscribe(self, q):
        pass


class FakeStateMachine:
    def snapshot(self):
        return {"phase": "waiting", "step": "awaiting_checkin"}


def make_client():
    app = Flask(__name__)
    app.config["EVENT_BROADCASTER"] = FakeBroadcaster()
    app.config["STATE_MACHINE"] = FakeStateMachine()
    app.register_blueprint(events_bp)
    return app.test_client()


def test_stream_sends_initial_snapshot_then_subsequent_updates():
    client = make_client()

    resp = client.get("/api/events")
    body_iter = resp.response

    first_chunk = next(iter(body_iter)).decode("utf-8")
    assert first_chunk.startswith("data: ")
    first_payload = json.loads(first_chunk[len("data: "):].strip())
    assert first_payload == {"phase": "waiting", "step": "awaiting_checkin"}

    second_chunk = next(iter(body_iter)).decode("utf-8")
    second_payload = json.loads(second_chunk[len("data: "):].strip())
    assert second_payload == {"phase": "active", "step": "polling_r2_active"}

    resp.close()


def test_stream_content_type_is_event_stream():
    client = make_client()
    resp = client.get("/api/events")
    assert resp.content_type.startswith("text/event-stream")
    resp.close()
