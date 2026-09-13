def is_confident(
    no_speech_prob: float,
    avg_logprob: float,
    no_speech_prob_max: float,
    avg_logprob_min: float,
) -> bool:
    return no_speech_prob <= no_speech_prob_max and avg_logprob >= avg_logprob_min


class WhisperTranscriber:
    def __init__(self, model_size: str = "base", model=None):
        self._model = model or _load_default_model(model_size)

    def transcribe(self, audio):
        segments, _info = self._model.transcribe(audio, language="ja")
        segments = list(segments)
        if not segments:
            return "", 1.0, -10.0
        text = "".join(seg.text for seg in segments).strip()
        no_speech_prob = max(seg.no_speech_prob for seg in segments)
        avg_logprob = sum(seg.avg_logprob for seg in segments) / len(segments)
        return text, no_speech_prob, avg_logprob


def _load_default_model(model_size):
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device="auto", compute_type="int8")
