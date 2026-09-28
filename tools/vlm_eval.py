"""Evaluate the VLM API server against labeled images.

Images are read from <dataset>/yes/ and <dataset>/no/; the directory name is
the expected answer. Add real Themis frames there to grow the evaluation set.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from themis_video.vlm import VLMClient, VLMError


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "vlm"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
LABELS = ("no", "yes")


@dataclass(frozen=True)
class Case:
    path: Path
    expected: str


def collect_cases(dataset: Path) -> list[Case]:
    return [
        Case(path, label)
        for label in LABELS
        for path in sorted((dataset / label).glob("*"))
        if path.suffix.lower() in IMAGE_SUFFIXES
    ]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", type=Path, default=FIXTURE_DIR)
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("VLM_ENDPOINT", "http://127.0.0.1:5103/analyze"),
    )
    parser.add_argument("--api-key", default=os.environ.get("VLM_API_KEY") or None)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=0.0,
        help="exit non-zero when accuracy is below this ratio (0.0-1.0)",
    )
    args = parser.parse_args(argv)

    cases = collect_cases(args.dataset)
    if not cases:
        parser.error(f"no images under {args.dataset}/yes or {args.dataset}/no")

    client = VLMClient(args.endpoint, api_key=args.api_key, timeout=args.timeout)
    correct = errors = false_positive = false_negative = 0
    latencies = []
    for case in cases:
        name = case.path.relative_to(args.dataset)
        started = time.monotonic()
        try:
            actual = "yes" if client.analyze(case.path.read_bytes()) else "no"
        except (OSError, VLMError) as exc:
            errors += 1
            print(f"ERR\t{name}\texpected={case.expected}\t{exc}")
            continue
        latencies.append((time.monotonic() - started) * 1000)
        if actual == case.expected:
            correct += 1
            mark = "OK"
        else:
            mark = "NG"
            if actual == "yes":
                false_positive += 1
            else:
                false_negative += 1
        print(f"{mark}\t{name}\texpected={case.expected}\tactual={actual}")

    total = len(cases)
    accuracy = correct / total
    avg_ms = sum(latencies) / len(latencies) if latencies else 0.0
    print(
        f"accuracy {correct}/{total} ({accuracy:.1%})\t"
        f"false_positive={false_positive}\tfalse_negative={false_negative}\t"
        f"errors={errors}\tavg_latency={avg_ms:.0f}ms"
    )
    return 1 if errors or accuracy < args.min_accuracy else 0


if __name__ == "__main__":
    sys.exit(main())
