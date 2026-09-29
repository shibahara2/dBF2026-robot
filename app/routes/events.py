import json
import queue

from flask import Blueprint, Response, current_app

events_bp = Blueprint("events", __name__)

# An idle stream is silently dropped by NAT/VPN hops between the kiosk and
# this server; a periodic SSE comment keeps traffic flowing (clients ignore it).
DEFAULT_KEEPALIVE_SECONDS = 15


@events_bp.route("/api/events")
def stream_events():
    broadcaster = current_app.config["EVENT_BROADCASTER"]
    state_machine = current_app.config["STATE_MACHINE"]
    keepalive_seconds = current_app.config.get(
        "SSE_KEEPALIVE_SECONDS", DEFAULT_KEEPALIVE_SECONDS
    )

    def generate():
        q = broadcaster.subscribe()
        try:
            yield _format_sse(state_machine.snapshot())
            while True:
                try:
                    snapshot = q.get(timeout=keepalive_seconds)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                yield _format_sse(snapshot)
        finally:
            broadcaster.unsubscribe(q)

    return Response(generate(), mimetype="text/event-stream")


def _format_sse(snapshot):
    return f"data: {json.dumps(snapshot)}\n\n"
