import logging

from voice_ui.pipeline import run_checkin_once


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


class _FakeCheckinClient:
    def __init__(self, result="accepted"):
        self.calls = []
        self._result = result

    def checkin(self, name):
        self.calls.append(name)
        return self._result


def test_confident_transcription_triggers_checkin_with_extracted_name():
    mic = _FakeMicSource([object()])
    vad = _FakeVadSegmenter(utterance_after=1)
    transcriber = _FakeTranscriber(("田中太郎です", 0.1, -0.2))
    checkin_client = _FakeCheckinClient()

    outcome = run_checkin_once(
        mic,
        vad,
        transcriber,
        checkin_client,
        no_speech_prob_max=0.6,
        avg_logprob_min=-1.0,
    )

    assert outcome == "checked_in"
    assert checkin_client.calls == ["田中太郎"]


def test_successful_checkin_logs_extracted_name_and_checkin_result(caplog):
    mic = _FakeMicSource([object()])
    vad = _FakeVadSegmenter(utterance_after=1)
    transcriber = _FakeTranscriber(("田中太郎です", 0.1, -0.2))
    checkin_client = _FakeCheckinClient()

    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        outcome = run_checkin_once(
            mic,
            vad,
            transcriber,
            checkin_client,
            no_speech_prob_max=0.6,
            avg_logprob_min=-1.0,
        )

    assert outcome == "checked_in"
    joined = "\n".join(record.message for record in caplog.records)
    assert "田中太郎" in joined
    assert "accepted" in joined


def test_non_accepted_checkin_result_is_logged_even_though_outcome_stays_checked_in(caplog):
    mic = _FakeMicSource([object()])
    vad = _FakeVadSegmenter(utterance_after=1)
    transcriber = _FakeTranscriber(("田中太郎です", 0.1, -0.2))
    checkin_client = _FakeCheckinClient(result="already_in_progress")

    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        outcome = run_checkin_once(
            mic,
            vad,
            transcriber,
            checkin_client,
            no_speech_prob_max=0.6,
            avg_logprob_min=-1.0,
        )

    # pipeline's own three-way outcome contract is unchanged...
    assert outcome == "checked_in"
    # ...but the actual checkin_client result is visible in the logs.
    joined = "\n".join(record.message for record in caplog.records)
    assert "already_in_progress" in joined


def test_low_confidence_transcription_is_rejected_without_checkin():
    mic = _FakeMicSource([object()])
    vad = _FakeVadSegmenter(utterance_after=1)
    transcriber = _FakeTranscriber(("ノイズ", 0.9, -5.0))
    checkin_client = _FakeCheckinClient()

    outcome = run_checkin_once(
        mic,
        vad,
        transcriber,
        checkin_client,
        no_speech_prob_max=0.6,
        avg_logprob_min=-1.0,
    )

    assert outcome == "rejected_low_confidence"
    assert checkin_client.calls == []


def test_low_confidence_rejection_logs_text_and_confidence_scores(caplog):
    mic = _FakeMicSource([object()])
    vad = _FakeVadSegmenter(utterance_after=1)
    transcriber = _FakeTranscriber(("ノイズ", 0.9, -5.0))
    checkin_client = _FakeCheckinClient()

    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        run_checkin_once(
            mic,
            vad,
            transcriber,
            checkin_client,
            no_speech_prob_max=0.6,
            avg_logprob_min=-1.0,
        )

    joined = "\n".join(record.message for record in caplog.records)
    assert "ノイズ" in joined
    assert "0.9" in joined
    assert "-5.0" in joined


def test_no_chunk_available_returns_without_calling_transcriber():
    mic = _FakeMicSource([])
    vad = _FakeVadSegmenter(utterance_after=1)
    transcriber = _FakeTranscriber(("unused", 0.0, 0.0))
    checkin_client = _FakeCheckinClient()

    outcome = run_checkin_once(
        mic,
        vad,
        transcriber,
        checkin_client,
        no_speech_prob_max=0.6,
        avg_logprob_min=-1.0,
    )

    assert outcome == "no_utterance"
    assert checkin_client.calls == []


def test_multiple_chunks_are_fed_until_utterance_completes():
    mic = _FakeMicSource([object(), object(), object()])
    vad = _FakeVadSegmenter(utterance_after=3)
    transcriber = _FakeTranscriber(("田中太郎です", 0.1, -0.2))
    checkin_client = _FakeCheckinClient()

    outcome = run_checkin_once(
        mic,
        vad,
        transcriber,
        checkin_client,
        no_speech_prob_max=0.6,
        avg_logprob_min=-1.0,
    )

    assert outcome == "checked_in"
    assert checkin_client.calls == ["田中太郎"]
