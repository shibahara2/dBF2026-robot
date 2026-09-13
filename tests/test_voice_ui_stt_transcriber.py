import numpy as np
import pytest

from voice_ui.stt import WhisperTranscriber


class _FakeSegment:
    def __init__(self, text, no_speech_prob, avg_logprob):
        self.text = text
        self.no_speech_prob = no_speech_prob
        self.avg_logprob = avg_logprob


class _FakeModel:
    def __init__(self, segments):
        self._segments = segments

    def transcribe(self, audio, language="ja"):
        return iter(self._segments), None


def test_transcribe_concatenates_text_and_aggregates_confidence():
    segments = [
        _FakeSegment("田中", 0.1, -0.2),
        _FakeSegment("太郎です", 0.3, -0.4),
    ]
    transcriber = WhisperTranscriber(model=_FakeModel(segments))

    text, no_speech_prob, avg_logprob = transcriber.transcribe(
        np.zeros(16000, dtype=np.float32)
    )

    assert text == "田中太郎です"
    assert no_speech_prob == 0.3
    assert avg_logprob == pytest.approx(-0.3)


def test_transcribe_empty_segments_returns_low_confidence_defaults():
    transcriber = WhisperTranscriber(model=_FakeModel([]))

    text, no_speech_prob, avg_logprob = transcriber.transcribe(
        np.zeros(1600, dtype=np.float32)
    )

    assert text == ""
    assert no_speech_prob == 1.0
    assert avg_logprob == -10.0
