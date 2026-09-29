"""OpenAI-compatible chat client that returns a front-desk turn decision."""

import json

import requests

INTENTS = ("checkin", "chat", "ignore")

DIALOGUE_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "reply": {"type": "string"},
    },
    "required": ["intent", "reply"],
    "additionalProperties": False,
}


class DialogueLLMError(RuntimeError):
    """Raised when the LLM cannot produce a valid turn decision."""


class DialogueLLMClient:
    def __init__(self, base_url, model, *, api_key=None, timeout=8.0, session=None):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._session = session or requests.Session()
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def decide(self, messages):
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 200,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "front_desk_turn",
                    "schema": DIALOGUE_SCHEMA,
                    "strict": True,
                },
            },
        }
        try:
            response = self._session.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            decision = json.loads(content)
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            raise DialogueLLMError(f"dialogue LLM failed: {exc}") from exc

        intent = decision.get("intent") if isinstance(decision, dict) else None
        reply = decision.get("reply") if isinstance(decision, dict) else None
        if intent not in INTENTS or not isinstance(reply, str):
            raise DialogueLLMError(f"unexpected dialogue output: {content!r}")
        return {"intent": intent, "reply": reply}
