"""Probe the existing Themis WebSocket video endpoint."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from themis_video.client import ThemisVideoClient


@dataclass(frozen=True)
class ProbeSample:
    number: int
    size: int
    interval_seconds: float | None


def probe(
    url: str,
    *,
    duration_seconds: float = 10.0,
    client_factory: Callable[[str, Callable[[bytes], None]], object] | None = None,
    output: Callable[[str], None] = print,
    save_first_frame: Path | None = None,
) -> list[ProbeSample]:
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be non-negative")

    samples: list[ProbeSample] = []
    last_received: float | None = None

    def on_frame(payload: bytes) -> None:
        nonlocal last_received
        if save_first_frame is not None and not samples:
            save_first_frame.write_bytes(payload)
        now = time.monotonic()
        interval = None if last_received is None else now - last_received
        last_received = now
        sample = ProbeSample(len(samples) + 1, len(payload), interval)
        samples.append(sample)
        interval_text = "-" if interval is None else f"{interval:.3f}s"
        output(f"frame={sample.number} size={sample.size} interval={interval_text}")

    client = (
        ThemisVideoClient(url, on_frame)
        if client_factory is None
        else client_factory(url, on_frame)
    )
    client.start()
    try:
        time.sleep(duration_seconds)
    finally:
        client.stop()
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="e.g. ws://themis-main-pc:9002/zed2i")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--save-first-frame", type=Path)
    args = parser.parse_args()
    probe(
        args.url,
        duration_seconds=args.duration,
        save_first_frame=args.save_first_frame,
    )


if __name__ == "__main__":
    main()
