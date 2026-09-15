import numpy as np

CHUNK_SAMPLES = 512  # Silero VAD推奨チャンクサイズ(16kHz時32ms)


class SileroVadSegmenter:
    def __init__(
        self,
        sample_rate=16000,
        speech_prob_threshold=0.5,
        trailing_silence_ms=500.0,
        vad_model=None,
    ):
        self._sample_rate = sample_rate
        self._threshold = speech_prob_threshold
        chunk_ms = CHUNK_SAMPLES / sample_rate * 1000
        self._silence_chunks_needed = max(1, round(trailing_silence_ms / chunk_ms))
        self._vad_model = vad_model or _load_default_silero_vad()

        self._buffer = []
        self._in_speech = False
        self._silence_run = 0

    def feed(self, chunk: np.ndarray):
        prob = self._vad_model.predict(chunk, self._sample_rate)
        is_speech = prob >= self._threshold

        if is_speech:
            self._in_speech = True
            self._silence_run = 0
            self._buffer.append(chunk)
            return None

        if not self._in_speech:
            return None

        self._silence_run += 1
        self._buffer.append(chunk)
        if self._silence_run < self._silence_chunks_needed:
            return None

        utterance = np.concatenate(self._buffer)
        self._buffer = []
        self._in_speech = False
        self._silence_run = 0
        return utterance


def _load_default_silero_vad():
    from silero_vad import load_silero_vad

    model = load_silero_vad(onnx=True)

    class _Adapter:
        def predict(self, chunk, sample_rate):
            import torch

            with torch.no_grad():
                return model(torch.from_numpy(chunk), sample_rate).item()

    return _Adapter()
