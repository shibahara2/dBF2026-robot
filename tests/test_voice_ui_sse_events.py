import json

import responses

from voice_ui.sse_events import iter_sse_events


@responses.activate
def test_iter_sse_events_yields_parsed_json_payloads():
    body = (
        b"data: "
        + json.dumps({"phase": "waiting", "step": "awaiting_checkin"}).encode("utf-8")
        + b"\n\n"
        + b"data: "
        + json.dumps({"phase": "active", "step": "polling_r2_active"}).encode("utf-8")
        + b"\n\n"
    )
    responses.add(
        responses.GET,
        "http://flask.test/api/events",
        body=body,
        status=200,
        content_type="text/event-stream",
    )

    events = list(iter_sse_events("http://flask.test"))

    assert events == [
        {"phase": "waiting", "step": "awaiting_checkin"},
        {"phase": "active", "step": "polling_r2_active"},
    ]


@responses.activate
def test_iter_sse_events_skips_blank_lines():
    body = b"\n\ndata: " + json.dumps({"phase": "waiting"}).encode("utf-8") + b"\n\n\n"
    responses.add(
        responses.GET,
        "http://flask.test/api/events",
        body=body,
        status=200,
        content_type="text/event-stream",
    )

    events = list(iter_sse_events("http://flask.test"))

    assert events == [{"phase": "waiting"}]


@responses.activate
def test_iter_sse_events_skips_malformed_json_line_and_continues():
    body = (
        b"data: {not valid json\n\n"
        + b"data: "
        + json.dumps({"phase": "active", "step": "polling_r2_active"}).encode("utf-8")
        + b"\n\n"
    )
    responses.add(
        responses.GET,
        "http://flask.test/api/events",
        body=body,
        status=200,
        content_type="text/event-stream",
    )

    events = list(iter_sse_events("http://flask.test"))

    assert events == [{"phase": "active", "step": "polling_r2_active"}]


@responses.activate
def test_iter_sse_events_ignores_keepalive_comments():
    body = (
        b": keepalive\n\n"
        + b"data: "
        + json.dumps({"phase": "waiting"}).encode("utf-8")
        + b"\n\n"
        + b": keepalive\n\n"
    )
    responses.add(
        responses.GET,
        "http://flask.test/api/events",
        body=body,
        status=200,
        content_type="text/event-stream",
    )

    events = list(iter_sse_events("http://flask.test"))

    assert events == [{"phase": "waiting"}]


def test_iter_sse_events_uses_read_timeout_longer_than_server_keepalive(monkeypatch):
    from app.routes.events import DEFAULT_KEEPALIVE_SECONDS
    import voice_ui.sse_events as sse_events

    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop")

    monkeypatch.setattr(sse_events.requests, "get", fake_get)

    try:
        next(iter_sse_events("http://flask.test"))
    except RuntimeError:
        pass

    connect_timeout, read_timeout = captured["timeout"]
    assert connect_timeout > 0
    assert read_timeout > DEFAULT_KEEPALIVE_SECONDS
