import json

from flask import Blueprint, Response, current_app

events_bp = Blueprint("events", __name__)


@events_bp.route("/api/events")
def stream_events():
    broadcaster = current_app.config["EVENT_BROADCASTER"]
    state_machine = current_app.config["STATE_MACHINE"]

    def generate():
        q = broadcaster.subscribe()
        try:
            yield _format_sse(state_machine.snapshot())
            while True:
                snapshot = q.get()
                yield _format_sse(snapshot)
        finally:
            broadcaster.unsubscribe(q)

    return Response(generate(), mimetype="text/event-stream")


def _format_sse(snapshot):
    return f"data: {json.dumps(snapshot)}\n\n"
