"""Run the Themis WebSocket mock (video + /realtime) on a free port for tests."""

import asyncio
import socket
import threading
import time
from contextlib import contextmanager

import websocket

from mocks.themis_video_mock import MockThemisVideoConfig, serve_mock


@contextmanager
def running_mock(realtime):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    stop = threading.Event()

    def run():
        async def main():
            task = asyncio.create_task(
                serve_mock(
                    port=port,
                    config=MockThemisVideoConfig(payload=b"frame", interval_seconds=0.05),
                    realtime=realtime,
                )
            )
            try:
                await asyncio.to_thread(stop.wait)
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        asyncio.run(main())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3
    while True:
        try:
            websocket.create_connection(f"ws://127.0.0.1:{port}/zed2i", timeout=0.2).close()
            break
        except (OSError, websocket.WebSocketException):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)
    try:
        yield port
    finally:
        stop.set()
        thread.join(timeout=2)
