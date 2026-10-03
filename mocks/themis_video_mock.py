"""Local WebSocket server that mimics Themis' gamepad-server (video and /realtime)."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from mocks.r2_realtime_mock import R2RealtimeMock


DEFAULT_IMAGE_PATH = Path(__file__).resolve().parents[1] / "person.png"


@dataclass(frozen=True)
class MockThemisVideoConfig:
    payload: bytes | None = None
    interval_seconds: float = 0.5

    def __post_init__(self):
        if self.payload is not None and not self.payload:
            raise ValueError("payload must not be empty")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")


def make_payload(config: MockThemisVideoConfig) -> bytes:
    if config.payload is not None:
        return config.payload
    return DEFAULT_IMAGE_PATH.read_bytes()


async def serve_mock(
    host: str = "127.0.0.1",
    port: int = 9002,
    config: MockThemisVideoConfig | None = None,
    realtime=None,
) -> None:
    try:
        import websockets
        from websockets.exceptions import ConnectionClosed
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError("websockets is required for the mock server") from exc

    active_config = config or MockThemisVideoConfig()
    payload = make_payload(active_config)

    async def handler(websocket):
        # Like the real gamepad-server, one port serves /realtime and video.
        if realtime is not None and websocket.path == "/realtime":
            try:
                await realtime.handle(websocket)
            except ConnectionClosed:
                pass
            return
        try:
            while True:
                await websocket.send(payload)
                await asyncio.sleep(active_config.interval_seconds)
        except ConnectionClosed:
            return

    async with websockets.serve(handler, host, port):
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9002)
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()
    asyncio.run(
        serve_mock(
            args.host,
            args.port,
            MockThemisVideoConfig(interval_seconds=args.interval),
            realtime=R2RealtimeMock.from_env(),
        )
    )


if __name__ == "__main__":
    main()
