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
    def __init__(self):
        self.calls = []

    def checkin(self, name):
        self.calls.append(name)
        return "accepted"


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
