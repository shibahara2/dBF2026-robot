import pytest
from flask import Flask

from app.routes.voice_turns import voice_turns_bp
from app.voice_turns import VoiceTurnLog


class FakeBroadcaster:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def make_client(max_turns=20):
    app = Flask(__name__)
    app.config["EVENT_BROADCASTER"] = FakeBroadcaster()
    app.config["VOICE_TURN_LOG"] = VoiceTurnLog(
        max_turns=max_turns, now=lambda: "2026-09-29T00:00:00Z"
    )
    app.register_blueprint(voice_turns_bp)
    return app.test_client(), app


def turn(**overrides):
    body = {
        "text": "朝ごはんは何時ですか",
        "no_speech_prob": 0.12,
        "avg_logprob": -0.31,
        "outcome": "chat",
        "reply": "6時半からです。",
        "stt_ms": 840,
        "llm_ms": 1100,
    }
    body.update(overrides)
    return body


def test_post_turn_stores_and_publishes_typed_event():
    client, app = make_client()

    resp = client.post("/api/voice/turns", json=turn())

    assert resp.status_code == 202
    expected = {**turn(), "at": "2026-09-29T00:00:00Z"}
    assert app.config["EVENT_BROADCASTER"].events == [{"type": "voice_turn", **expected}]
    assert client.get("/api/voice/turns").get_json() == {"turns": [expected]}


def test_optional_fields_default_to_null_and_empty_reply():
    client, _app = make_client()

    client.post(
        "/api/voice/turns",
        json={"text": "ノイズ", "outcome": "rejected_low_confidence"},
    )

    stored = client.get("/api/voice/turns").get_json()["turns"][0]
    assert stored["reply"] == ""
    assert stored["llm_ms"] is None
    assert stored["no_speech_prob"] is None


@pytest.mark.parametrize(
    "body",
    [
        {},
        turn(outcome="unknown"),
        turn(text=3),
        turn(reply=5),
        turn(stt_ms="fast"),
        turn(no_speech_prob="high"),
    ],
)
def test_post_turn_rejects_invalid_body(body):
    client, app = make_client()

    resp = client.post("/api/voice/turns", json=body)

    assert resp.status_code == 422
    assert app.config["EVENT_BROADCASTER"].events == []


def test_get_returns_newest_first_and_keeps_limit():
    client, _app = make_client(max_turns=3)

    for i in range(5):
        client.post("/api/voice/turns", json=turn(text=f"発話{i}"))

    texts = [t["text"] for t in client.get("/api/voice/turns").get_json()["turns"]]
    assert texts == ["発話4", "発話3", "発話2"]
