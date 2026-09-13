def is_confident(
    no_speech_prob: float,
    avg_logprob: float,
    no_speech_prob_max: float,
    avg_logprob_min: float,
) -> bool:
    return no_speech_prob <= no_speech_prob_max and avg_logprob >= avg_logprob_min


class WhisperTranscriber:
    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        fp16: bool = True,
        model=None,
    ):
        self._fp16 = fp16
        self._model = model or _load_default_model(model_size, device)

    def transcribe(self, audio):
        result = self._model.transcribe(audio, language="ja", fp16=self._fp16)
        segments = result.get("segments", [])
        if not segments:
            return "", 1.0, -10.0
        text = result["text"].strip()
        no_speech_prob = max(seg["no_speech_prob"] for seg in segments)
        avg_logprob = sum(seg["avg_logprob"] for seg in segments) / len(segments)
        return text, no_speech_prob, avg_logprob


def _load_default_model(model_size, device):
    import whisper

    return whisper.load_model(model_size, device=device)
