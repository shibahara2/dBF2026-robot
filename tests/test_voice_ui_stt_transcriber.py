import numpy as np
import pytest

from voice_ui.stt import WhisperTranscriber


class _FakeModel:
    def __init__(self, result, expected_kwargs=None):
        self._result = result
        self._expected_kwargs = expected_kwargs
        self.received_kwargs = None

    def transcribe(self, audio, **kwargs):
        self.received_kwargs = kwargs
        if self._expected_kwargs is not None:
            assert kwargs == self._expected_kwargs
        return self._result


def test_transcribe_uses_result_text_and_aggregates_segment_confidence():
    result = {
        "text": "田中太郎です",
        "segments": [
            {"text": "田中", "no_speech_prob": 0.1, "avg_logprob": -0.2},
            {"text": "太郎です", "no_speech_prob": 0.3, "avg_logprob": -0.4},
        ],
    }
    transcriber = WhisperTranscriber(model=_FakeModel(result))

    text, no_speech_prob, avg_logprob = transcriber.transcribe(
        np.zeros(16000, dtype=np.float32)
    )

    assert text == "田中太郎です"
    assert no_speech_prob == 0.3
    assert avg_logprob == pytest.approx(-0.3)


def test_transcribe_empty_segments_returns_low_confidence_defaults():
    result = {"text": "", "segments": []}
    transcriber = WhisperTranscriber(model=_FakeModel(result))

    text, no_speech_prob, avg_logprob = transcriber.transcribe(
        np.zeros(1600, dtype=np.float32)
    )

    assert text == ""
    assert no_speech_prob == 1.0
    assert avg_logprob == -10.0


def test_transcribe_passes_language_and_fp16_to_model():
    result = {"text": "x", "segments": [{"text": "x", "no_speech_prob": 0.0, "avg_logprob": 0.0}]}
    fake_model = _FakeModel(result, expected_kwargs={"language": "ja", "fp16": True})
    transcriber = WhisperTranscriber(model=fake_model, fp16=True)

    transcriber.transcribe(np.zeros(1600, dtype=np.float32))

    assert fake_model.received_kwargs == {"language": "ja", "fp16": True}


def test_transcribe_passes_fp16_false_when_configured():
    result = {"text": "x", "segments": [{"text": "x", "no_speech_prob": 0.0, "avg_logprob": 0.0}]}
    fake_model = _FakeModel(result, expected_kwargs={"language": "ja", "fp16": False})
    transcriber = WhisperTranscriber(model=fake_model, fp16=False)

    transcriber.transcribe(np.zeros(1600, dtype=np.float32))

    assert fake_model.received_kwargs == {"language": "ja", "fp16": False}
