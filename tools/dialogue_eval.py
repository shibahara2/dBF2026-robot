"""Evaluate the front-desk dialogue intent against labeled utterances.

Each case is judged with a fresh agent (no history), so cases are independent.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from voice_ui import config
from voice_ui.dialogue import DialogueAgent
from voice_ui.llm_client import DialogueLLMClient

FIXTURE_FILE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "dialogue" / "cases.json"


def load_cases(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=FIXTURE_FILE)
    parser.add_argument("--llm-url", default=config.DIALOGUE_LLM_URL)
    parser.add_argument("--model", default=config.DIALOGUE_LLM_MODEL)
    parser.add_argument("--hotel-info", type=Path, default=Path(config.HOTEL_INFO_FILE))
    parser.add_argument("--min-accuracy", type=float, default=0.0)
    args = parser.parse_args(argv)

    hotel_info = args.hotel_info.read_text(encoding="utf-8")
    llm = DialogueLLMClient(args.llm_url, args.model, timeout=config.DIALOGUE_LLM_TIMEOUT_SECONDS)
    cases = load_cases(args.cases)
    correct = 0
    confusion = Counter()
    latencies = []
    for case in cases:
        agent = DialogueAgent(llm, hotel_info)
        started = time.monotonic()
        decision = agent.respond(case["text"])
        latencies.append((time.monotonic() - started) * 1000)
        ok = decision.intent == case["intent"]
        correct += ok
        confusion[(case["intent"], decision.intent)] += 1
        reply = f"\treply={decision.reply}" if decision.reply else ""
        print(f"{'OK' if ok else 'NG'}\t{case['text']}\texpected={case['intent']}\tactual={decision.intent}{reply}")

    accuracy = correct / len(cases)
    mistakes = ", ".join(f"{e}->{a}:{n}" for (e, a), n in sorted(confusion.items()) if e != a)
    print(
        f"accuracy {correct}/{len(cases)} ({accuracy:.1%})\t"
        f"mistakes={mistakes or '-'}\tavg_latency={sum(latencies) / len(latencies):.0f}ms"
    )
    return 1 if accuracy < args.min_accuracy else 0


if __name__ == "__main__":
    sys.exit(main())
