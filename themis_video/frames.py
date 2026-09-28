"""Frame value objects and the replaceable Themis payload decoder boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RawThemisFrame:
    payload: bytes


class ThemisFrameDecoder(Protocol):
    def __call__(self, payload: bytes) -> RawThemisFrame:
        """Decode a WebSocket payload into a frame value."""


def raw_frame_from_payload(payload: bytes) -> RawThemisFrame:
    if not payload:
        raise ValueError("frame payload must not be empty")
    if not isinstance(payload, bytes):
        raise ValueError("frame payload must be bytes")
    return RawThemisFrame(payload=payload)
