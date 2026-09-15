import numpy as np

from voice_ui.vad_segmenter import CHUNK_SAMPLES, SileroVadSegmenter


class _FakeVadModel:
    def __init__(self, probs):
        self._probs = iter(probs)

    def predict(self, chunk, sample_rate):
        return next(self._probs)


def _chunk(value):
    return np.full(CHUNK_SAMPLES, value, dtype=np.float32)


def test_silence_only_never_emits():
    segmenter = SileroVadSegmenter(
        sample_rate=16000,
        speech_prob_threshold=0.5,
        trailing_silence_ms=64,  # 2 chunks @ 32ms
        vad_model=_FakeVadModel([0.1, 0.1, 0.1]),
    )

    results = [segmenter.feed(_chunk(i)) for i in range(3)]

    assert results == [None, None, None]


def test_speech_then_enough_silence_emits_full_utterance():
    segmenter = SileroVadSegmenter(
        sample_rate=16000,
        speech_prob_threshold=0.5,
        trailing_silence_ms=64,  # 2 chunks needed
        vad_model=_FakeVadModel([0.9, 0.9, 0.1, 0.1]),
    )

    results = [segmenter.feed(_chunk(i)) for i in range(4)]

    assert results[0] is None
    assert results[1] is None
    assert results[2] is None  # only 1 silence chunk so far
    assert results[3] is not None
    assert results[3].shape[0] == CHUNK_SAMPLES * 4


def test_state_resets_after_emission_for_next_utterance():
    segmenter = SileroVadSegmenter(
        sample_rate=16000,
        speech_prob_threshold=0.5,
        trailing_silence_ms=64,
        vad_model=_FakeVadModel([0.9, 0.9, 0.1, 0.1, 0.9, 0.9, 0.1, 0.1]),
    )

    first_results = [segmenter.feed(_chunk(i)) for i in range(4)]
    second_results = [segmenter.feed(_chunk(i)) for i in range(4)]

    assert first_results[3] is not None
    assert second_results[3] is not None
    assert first_results[:3] == [None, None, None]
    assert second_results[:3] == [None, None, None]
