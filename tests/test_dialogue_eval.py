import json

import responses

from tools.dialogue_eval import FIXTURE_FILE, load_cases, main

LLM = "http://llm.test/v1"


def _write_cases(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {"text": "チェックインしたい", "intent": "checkin"},
                {"text": "朝食は何時？", "intent": "chat"},
                {"text": "それでさあ", "intent": "ignore"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _reply_with(*intents):
    answers = iter(intents)

    def callback(_request):
        intent = next(answers)
        content = json.dumps({"intent": intent, "reply": "はい。" if intent == "chat" else ""})
        return 200, {}, json.dumps({"choices": [{"message": {"content": content}}]})

    return callback


def test_repository_cases_cover_all_intents():
    intents = {case["intent"] for case in load_cases(FIXTURE_FILE)}

    assert intents == {"checkin", "chat", "ignore"}
    assert len(load_cases(FIXTURE_FILE)) >= 12


@responses.activate
def test_all_correct_exits_zero(tmp_path, capsys):
    responses.add_callback(
        responses.POST, f"{LLM}/chat/completions", callback=_reply_with("checkin", "chat", "ignore")
    )

    code = main(["--cases", str(_write_cases(tmp_path)), "--llm-url", LLM])

    assert code == 0
    assert "accuracy 3/3 (100.0%)" in capsys.readouterr().out


@responses.activate
def test_mismatch_is_reported_and_fails_min_accuracy(tmp_path, capsys):
    responses.add_callback(
        responses.POST, f"{LLM}/chat/completions", callback=_reply_with("checkin", "ignore", "chat")
    )

    code = main(
        ["--cases", str(_write_cases(tmp_path)), "--llm-url", LLM, "--min-accuracy", "0.9"]
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "NG" in out and "朝食は何時？" in out
    assert "accuracy 1/3 (33.3%)" in out
