"""Configuration for the optional external Themis video client."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class ThemisVideoSettings:
    ws_url: str | None
    reconnect_delay_seconds: float = 1.0
    connect_timeout_seconds: float = 5.0


@dataclass(frozen=True)
class ThemisRuntimeSettings:
    mode: str
    ws_url: str
    vlm_endpoint: str
    trigger_url: str
    vlm_api_key: str | None = None


def load_settings(environ: dict[str, str] | None = None) -> ThemisVideoSettings:
    values = os.environ if environ is None else environ
    ws_url = values.get("THEMIS_WS_URL") or None
    if ws_url is not None:
        parsed = urlparse(ws_url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
            raise ValueError("URL must be a valid ws:// or wss:// URL")

    reconnect_delay = _read_float(
        values, "THEMIS_WS_RECONNECT_DELAY_SECONDS", default=1.0, minimum=0.0
    )
    connect_timeout = _read_float(
        values, "THEMIS_WS_CONNECT_TIMEOUT_SECONDS", default=5.0, minimum=0.000001
    )
    return ThemisVideoSettings(
        ws_url=ws_url,
        reconnect_delay_seconds=reconnect_delay,
        connect_timeout_seconds=connect_timeout,
    )


def load_runtime_settings(
    environ: dict[str, str] | None = None,
) -> ThemisRuntimeSettings:
    values = os.environ if environ is None else environ
    mode = values.get("THEMIS_VLM_MODE", "real").lower()
    if mode not in {"mock", "real"}:
        raise ValueError("THEMIS_VLM_MODE must be mock or real")

    ws_url = values.get("THEMIS_WS_URL")
    vlm_endpoint = values.get("VLM_ENDPOINT")
    if mode == "mock":
        ws_url = ws_url or "ws://127.0.0.1:9002/zed2i"
        vlm_endpoint = vlm_endpoint or "http://127.0.0.1:5103/analyze"
    else:
        if not ws_url:
            raise ValueError("THEMIS_WS_URL is required in real mode")
        if not vlm_endpoint:
            raise ValueError("VLM_ENDPOINT is required in real mode")

    trigger_url = values.get(
        "VISUAL_TRIGGER_URL", "http://127.0.0.1:5100/api/visual/start"
    )
    return ThemisRuntimeSettings(
        mode=mode,
        ws_url=ws_url,
        vlm_endpoint=vlm_endpoint,
        trigger_url=trigger_url,
        vlm_api_key=values.get("VLM_API_KEY") or None,
    )


def _read_float(
    environ: dict[str, str], key: str, *, default: float, minimum: float
) -> float:
    raw = environ.get(key)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number") from exc
    if value < minimum:
        raise ValueError(f"{key} must be at least {minimum}")
    return value
