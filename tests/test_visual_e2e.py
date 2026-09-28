"""Exercise the WebSocket image decision through the kiosk event boundary."""

import asyncio
import socket
import threading
import time

import websocket

from werkzeug.serving import make_server

from app import create_app
from mocks.themis_video_mock import MockThemisVideoConfig, serve_mock
from mocks.vlm_mock import create_app as create_vlm_mock
from themis_video.client import ThemisVideoClient
from themis_video.pipeline import VisualConversationPipeline
from themis_video.vlm import VLMClient


def test_video_yes_decision_starts_search_without_checkin(caplog):
    app = create_app()
    vlm_app = create_vlm_mock(decision=True)
    with socket.socket() as available_port:
        available_port.bind(("127.0.0.1", 0))
        video_port = available_port.getsockname()[1]
    stop_video_server = threading.Event()
    video_server_errors = []

    def run_video_server():
        async def run():
            task = asyncio.create_task(
                serve_mock(
                    port=video_port,
                    config=MockThemisVideoConfig(interval_seconds=0.05),
                )
            )
            try:
                await asyncio.to_thread(stop_video_server.wait)
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        try:
            asyncio.run(run())
        except Exception as exc:
            video_server_errors.append(exc)

    video_thread = threading.Thread(target=run_video_server, daemon=True)
    app_server = make_server("127.0.0.1", 0, app, threaded=True)
    vlm_server = make_server("127.0.0.1", 0, vlm_app, threaded=True)
    app_thread = threading.Thread(target=app_server.serve_forever, daemon=True)
    vlm_thread = threading.Thread(target=vlm_server.serve_forever, daemon=True)
    subscriber = app.config["EVENT_BROADCASTER"].subscribe()
    video = None

    try:
        video_thread.start()
        app_thread.start()
        vlm_thread.start()
        video_url = f"ws://127.0.0.1:{video_port}/zed2i"
        deadline = time.monotonic() + 3
        while True:
            try:
                ready_socket = websocket.create_connection(video_url, timeout=0.2)
                ready_socket.close()
                break
            except (OSError, websocket.WebSocketException):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
        vlm = VLMClient(f"http://127.0.0.1:{vlm_server.server_port}/analyze")
        pipeline = VisualConversationPipeline(
            vlm,
            f"http://127.0.0.1:{app_server.server_port}/api/visual/start",
        )
        video = ThemisVideoClient(
            video_url,
            pipeline.process,
            reconnect_delay=0.05,
        )
        video.start()

        assert subscriber.get(timeout=10) == {
            "type": "ui_action",
            "action": "start_checkin",
        }
        assert app.config["STATE_MACHINE"].snapshot()["step"] == "awaiting_checkin"
    finally:
        if video is not None:
            video.stop()
        stop_video_server.set()
        video_thread.join(timeout=2)
        app.config["EVENT_BROADCASTER"].unsubscribe(subscriber)
        app_server.shutdown()
        vlm_server.shutdown()
        app_thread.join(timeout=2)
        vlm_thread.join(timeout=2)
    assert video_server_errors == []
    assert not any(
        record.name == "websockets.server" and record.levelname == "ERROR"
        for record in caplog.records
    )
