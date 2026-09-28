"""HTTP client for the VLM API server's speaking-to-Themis decision."""

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
        session: requests.Session | None = None,
    ) -> None:
        if not endpoint:
            raise ValueError("VLM endpoint must not be empty")
        if timeout <= 0:
            raise ValueError("VLM timeout must be positive")
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    def analyze_detail(self, image_bytes: bytes) -> dict:
        """Return the full server response (speaking_to_themis, answer, latency_ms)."""
        if not image_bytes:
            raise ValueError("image_bytes must not be empty")

        # The yes/no prompt is owned by the VLM server, so only the image is sent.
        payload = {"image_base64": base64.b64encode(image_bytes).decode("ascii")}
        try:
            response = self.session.post(
                self.endpoint,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise VLMError("VLM request failed") from exc

        if not isinstance(data.get("speaking_to_themis"), bool):
            raise VLMError("VLM response must contain boolean speaking_to_themis")
        return data

    def analyze(self, image_bytes: bytes) -> bool:
        return self.analyze_detail(image_bytes)["speaking_to_themis"]

    def health(self) -> bool:
        health_url = self.endpoint.rsplit("/", 1)[0] + "/health"
        try:
            response = self.session.get(
                health_url, headers=self._headers(), timeout=self.timeout
            )
            response.raise_for_status()
        except requests.RequestException:
            return False
        return True
