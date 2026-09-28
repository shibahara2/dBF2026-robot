"""Run the external-side Themis WebSocket to VLM to UI-trigger pipeline."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

from themis_video.client import ThemisVideoClient, VideoClientStatus
from themis_video.pipeline import VisualConversationPipeline
from themis_video.settings import load_runtime_settings
from themis_video.vlm import VLMClient


logger = logging.getLogger(__name__)
HEALTH_REPORT_INTERVAL_SECONDS = 30.0
FRAME_STALE_AFTER_SECONDS = 10.0


def report_video_health(
    status: VideoClientStatus,
    *,
    now: float | None = None,
    stale_after_seconds: float = FRAME_STALE_AFTER_SECONDS,
) -> None:
    current_time = time.monotonic() if now is None else now
    age = (
        None
        if status.last_frame_at is None
        else max(0.0, current_time - status.last_frame_at)
    )
    details = (
        f"connect_attempts={status.connect_attempts} "
        f"frames={status.frames_received} "
        f"processing_errors={status.processing_errors} "
        f"last_frame_age={'never' if age is None else f'{age:.1f}s'}"
    )
    if not status.connected:
        logger.warning("Themis video disconnected: %s", details)
    elif age is None or age > stale_after_seconds:
        logger.warning("Themis video stalled: %s", details)
    else:
        logger.info("Themis video healthy: %s", details)


def run(ws_url: str, vlm_endpoint: str, trigger_url: str, api_key: str | None):
    stop_event = threading.Event()
    vlm = VLMClient(vlm_endpoint, api_key=api_key)
    pipeline = VisualConversationPipeline(vlm, trigger_url)
    video = ThemisVideoClient(ws_url, pipeline.process)

    def stop(*_args):
        stop_event.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    video.start()
    try:
        while not stop_event.wait(HEALTH_REPORT_INTERVAL_SECONDS):
            report_video_health(video.status())
    finally:
        video.stop()


def main():
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ws-url")
    parser.add_argument("--vlm-endpoint")
    parser.add_argument("--trigger-url")
    parser.add_argument("--api-key")
    args = parser.parse_args()
    values = dict(os.environ)
    if args.ws_url is not None:
        values["THEMIS_WS_URL"] = args.ws_url
    if args.vlm_endpoint is not None:
        values["VLM_ENDPOINT"] = args.vlm_endpoint
    if args.trigger_url is not None:
        values["VISUAL_TRIGGER_URL"] = args.trigger_url
    if args.api_key is not None:
        values["VLM_API_KEY"] = args.api_key
    try:
        settings = load_runtime_settings(values)
    except ValueError as exc:
        parser.error(str(exc))
    run(
        settings.ws_url,
        settings.vlm_endpoint,
        settings.trigger_url,
        settings.vlm_api_key,
    )


if __name__ == "__main__":
    main()
