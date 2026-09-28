"""Environment configuration for the VLM API server."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VLMServerSettings:
    backend_url: str
    backend_model: str = "qwen3.6-35b-a3b"
    backend_api_key: str | None = None
    backend_timeout_seconds: float = 30.0
    host: str = "127.0.0.1"
    port: int = 5103
    api_key: str | None = None
    max_image_side: int = 640


def load_server_settings(environ: dict[str, str] | None = None) -> VLMServerSettings:
    values = os.environ if environ is None else environ
    backend_url = values.get("VLM_BACKEND_URL")
    if not backend_url:
        raise ValueError("VLM_BACKEND_URL is required")
    return VLMServerSettings(
        backend_url=backend_url,
        backend_model=values.get("VLM_BACKEND_MODEL") or "qwen3.6-35b-a3b",
        backend_api_key=values.get("VLM_BACKEND_API_KEY") or None,
        backend_timeout_seconds=float(values.get("VLM_BACKEND_TIMEOUT_SECONDS", "30")),
        host=values.get("VLM_SERVER_HOST") or "127.0.0.1",
        port=int(values.get("VLM_SERVER_PORT", "5103")),
        api_key=values.get("VLM_API_KEY") or None,
        max_image_side=int(values.get("VLM_MAX_IMAGE_SIDE", "640")),
    )
