"""Fixed yes/no prompt and answer schema for the speaking-to-Themis decision."""

from __future__ import annotations

import json


SYSTEM_PROMPT = (
    "You are the vision module of a reception robot. The image is from the "
    "robot's front camera. Answer yes only if a person is close to the camera, "
    "facing the robot, and appears to be talking to it (mouth open, engaged "
    "gaze, or gesturing toward the camera). Answer no if there is no person, "
    "the person is far away, walking past, facing away, looking at something "
    "else, or talking to someone else."
)
USER_PROMPT = "Answer yes or no."

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string", "enum": ["yes", "no"]}},
    "required": ["answer"],
    "additionalProperties": False,
}


def parse_answer(content: str) -> str:
    """Return "yes" or "no" from the model's schema-constrained JSON output."""
    try:
        answer = json.loads(content)["answer"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"unexpected VLM output: {content!r}") from exc
    if not isinstance(answer, str) or answer.lower() not in {"yes", "no"}:
        raise ValueError(f"unexpected VLM answer: {answer!r}")
    return answer.lower()
