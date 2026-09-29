import logging

from voice_ui.pipeline import run_start_once

KEYWORDS = ["チェックイン"]


class _FakeMicSource:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read_chunk(self, timeout=None):
        if not self._chunks:
            return None
        return self._chunks.pop(0)


class _FakeVadSegmenter:
    def __init__(self, utterance_after):
        self._utterance_after = utterance_after
        self._count = 0

    def feed(self, chunk):
        self._count += 1
        if self._count >= self._utterance_after:
            return "UTTERANCE"
        return None


class _FakeTranscriber:
    def __init__(self, result):
        self._result = result

    def transcribe(self, utterance):
        return self._result


class _FakeStartClient:
    def __init__(self, result="accepted"):
        self.calls = 0
        self._result = result

    def start(self):
        self.calls += 1
        return self._result


def _run(transcription, start_client, chunks=(object(),), utterance_after=1):
    return run_start_once(
        _FakeMicSource(list(chunks)),
        _FakeVadSegmenter(utterance_after=utterance_after),
        _FakeTranscriber(transcription),
        start_client,
        KEYWORDS,
        no_speech_prob_max=0.6,
        avg_logprob_min=-1.0,
    )


def test_keyword_utterance_requests_start():
    start_client = _FakeStartClient()

    assert _run(("チェックインお願いします", 0.1, -0.2), start_client) == "start_requested"
    assert start_client.calls == 1


def test_utterance_without_keyword_is_ignored(caplog):
    start_client = _FakeStartClient()

    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        outcome = _run(("田中太郎です", 0.1, -0.2), start_client)

    assert outcome == "no_keyword"
    assert start_client.calls == 0
    assert "田中太郎です" in caplog.text


def test_start_result_is_logged_even_when_not_accepted(caplog):
    start_client = _FakeStartClient(result="not_available")

    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        outcome = _run(("チェックイン", 0.1, -0.2), start_client)

    assert outcome == "start_requested"
    assert "not_available" in caplog.text


def test_low_confidence_transcription_is_rejected_without_start():
    start_client = _FakeStartClient()

    assert _run(("チェックイン", 0.9, -5.0), start_client) == "rejected_low_confidence"
    assert start_client.calls == 0


def test_low_confidence_rejection_logs_text_and_confidence_scores(caplog):
    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        _run(("ノイズ", 0.9, -5.0), _FakeStartClient())

    assert "ノイズ" in caplog.text
    assert "0.9" in caplog.text
    assert "-5.0" in caplog.text


def test_no_chunk_available_returns_without_start():
    start_client = _FakeStartClient()

    assert _run(("unused", 0.0, 0.0), start_client, chunks=()) == "no_utterance"
    assert start_client.calls == 0


def test_multiple_chunks_are_fed_until_utterance_completes():
    start_client = _FakeStartClient()

    outcome = _run(
        ("チェックイン", 0.1, -0.2),
        start_client,
        chunks=(object(), object(), object()),
        utterance_after=3,
    )

    assert outcome == "start_requested"
    assert start_client.calls == 1
