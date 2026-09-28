"""Client for an OpenAI-compatible multimodal chat endpoint (llama.cpp, vLLM)."""

from __future__ import annotations

import base64

import requests

from .prompt import ANSWER_SCHEMA, SYSTEM_PROMPT, USER_PROMPT, parse_answer


class BackendError(RuntimeError):
    """Raised when the VLM backend cannot produce a yes/no answer."""


class OpenAICompatibleBackend:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.session = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def ask(self, jpeg_bytes: bytes) -> str:
        image_url = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode(
            "ascii"
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 20,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "speaking_decision",
                    "schema": ANSWER_SCHEMA,
                    "strict": True,
                },
            },
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
        }
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return parse_answer(content)
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            raise BackendError(f"VLM backend failed: {exc}") from exc

    def healthy(self) -> bool:
        try:
            response = self.session.get(
                f"{self.base_url}/models", headers=self.headers, timeout=self.timeout
            )
            response.raise_for_status()
        except requests.RequestException:
            return False
        return True
