import pytest

from voice_ui.start_keyword import contains_start_keyword


@pytest.mark.parametrize(
    "text",
    [
        "チェックイン",
        "チェックインお願いします",
        "チェックイン。",
        "チェック イン",
        "ﾁｪｯｸｲﾝ",
        "すみません、チェックインしたいです",
    ],
)
def test_matches_whisper_variants(text):
    assert contains_start_keyword(text, ["チェックイン"]) is True


@pytest.mark.parametrize("text", ["", "こんにちは", "チェックアウト", "田中太郎です"])
def test_ignores_other_utterances(text):
    assert contains_start_keyword(text, ["チェックイン"]) is False


def test_any_configured_keyword_matches():
    assert contains_start_keyword("Check in please", ["チェックイン", "check in"]) is True


def test_blank_keywords_never_match():
    assert contains_start_keyword("こんにちは", ["", " "]) is False
