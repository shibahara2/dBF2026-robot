"""HTTP client for the external VLM decision endpoint."""

from __future__ import annotations

import base64

import requests


class VLMError(RuntimeError):
    """Raised when the VLM endpoint cannot produce a valid decision."""


class VLMClient:
    def __init__(
        self,
        endpoint: str,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        prompt: str = (
            "画像を見て、人がThemisに話しかけている様子ならtrue、"
            "そうでなければfalseを返してください。"
        ),
        session: requests.Session | None = None,
    ) -> None:
        if not endpoint:
            raise ValueError("VLM endpoint must not be empty")
        if timeout <= 0:
            raise ValueError("VLM timeout must be positive")
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout
        self.prompt = prompt
        self.session = session or requests.Session()

    def analyze(self, image_bytes: bytes) -> bool:
        if not image_bytes:
            raise ValueError("image_bytes must not be empty")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "prompt": self.prompt,
        }
        try:
            response = self.session.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise VLMError("VLM request failed") from exc

        decision = data.get("speaking_to_themis")
        if not isinstance(decision, bool):
            raise VLMError("VLM response must contain boolean speaking_to_themis")
        return decision
