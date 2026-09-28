"""Send image files to the VLM API server and print its yes/no decisions."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from themis_video.vlm import VLMClient, VLMError


def main(argv: list[str] | None = None) -> int:
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="*", type=Path)
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("VLM_ENDPOINT", "http://127.0.0.1:5103/analyze"),
    )
    parser.add_argument("--api-key", default=os.environ.get("VLM_API_KEY") or None)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--health", action="store_true", help="check /health only")
    args = parser.parse_args(argv)

    client = VLMClient(args.endpoint, api_key=args.api_key, timeout=args.timeout)
    if args.health:
        healthy = client.health()
        print("healthy" if healthy else "unhealthy")
        return 0 if healthy else 1
    if not args.images:
        parser.error("at least one image is required unless --health is given")

    failed = False
    for path in args.images:
        started = time.monotonic()
        try:
            result = client.analyze_detail(path.read_bytes())
        except (OSError, ValueError, VLMError) as exc:
            print(f"{path}\terror\t{exc}")
            failed = True
            continue
        total_ms = round((time.monotonic() - started) * 1000)
        answer = result.get("answer", "yes" if result["speaking_to_themis"] else "no")
        print(
            f"{path}\t{answer}\tvlm={result.get('latency_ms', '-')}ms\t"
            f"total={total_ms}ms"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
