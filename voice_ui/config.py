import os

FLASK_BASE_URL = os.environ.get("FLASK_BASE_URL", "http://localhost:5000")
VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
WHISPER_FP16 = os.environ.get("WHISPER_FP16", "1") == "1"
STT_NO_SPEECH_PROB_MAX = float(os.environ.get("STT_NO_SPEECH_PROB_MAX", "0.6"))
STT_AVG_LOGPROB_MIN = float(os.environ.get("STT_AVG_LOGPROB_MIN", "-1.0"))
VAD_TRAILING_SILENCE_MS = float(os.environ.get("VAD_TRAILING_SILENCE_MS", "500"))
