import json

import pytest
import requests
import responses

from voice_ui.llm_client import (
    DIALOGUE_SCHEMA,
    DialogueLLMClient,
    DialogueLLMError,
)

URL = "http://llm.test/v1"
MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "こんにちは"}]


def _reply(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


@responses.activate
def test_decide_sends_schema_and_returns_decision():
    responses.add(
        responses.POST,
        f"{URL}/chat/completions",
        json=_reply('{"intent": "chat", "reply": "いらっしゃいませ。"}'),
    )
    client = DialogueLLMClient(URL, "qwen3.6-35b-a3b", api_key="k", timeout=3.0)

    assert client.decide(MESSAGES) == {"intent": "chat", "reply": "いらっしゃいませ。"}

    request = responses.calls[0].request
    body = json.loads(request.body)
    assert request.headers["Authorization"] == "Bearer k"
    assert body["model"] == "qwen3.6-35b-a3b"
    assert body["messages"] == MESSAGES
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 200
    assert body["response_format"]["json_schema"]["schema"] == DIALOGUE_SCHEMA


def test_schema_restricts_intent_and_requires_reply():
    assert DIALOGUE_SCHEMA["properties"]["intent"]["enum"] == ["checkin", "chat", "ignore"]
    assert DIALOGUE_SCHEMA["required"] == ["intent", "reply"]
    assert DIALOGUE_SCHEMA["additionalProperties"] is False


@responses.activate
@pytest.mark.parametrize(
    "content",
    [
        "はい",
        '{"intent": "maybe", "reply": ""}',
        '{"intent": "chat"}',
        '{"intent": "chat", "reply": 3}',
    ],
)
def test_decide_rejects_invalid_output(content):
    responses.add(responses.POST, f"{URL}/chat/completions", json=_reply(content))

    with pytest.raises(DialogueLLMError):
        DialogueLLMClient(URL, "m").decide(MESSAGES)


@responses.activate
def test_decide_wraps_http_error():
    responses.add(responses.POST, f"{URL}/chat/completions", status=503)

    with pytest.raises(DialogueLLMError):
        DialogueLLMClient(URL, "m").decide(MESSAGES)


@responses.activate
def test_decide_wraps_timeout():
    responses.add(
        responses.POST, f"{URL}/chat/completions", body=requests.exceptions.Timeout()
    )

    with pytest.raises(DialogueLLMError):
        DialogueLLMClient(URL, "m").decide(MESSAGES)
