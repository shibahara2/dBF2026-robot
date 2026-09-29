import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FLASK_BASE_URL = os.environ.get("FLASK_BASE_URL", "http://localhost:5100")
VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
WHISPER_FP16 = os.environ.get("WHISPER_FP16", "1") == "1"
STT_NO_SPEECH_PROB_MAX = float(os.environ.get("STT_NO_SPEECH_PROB_MAX", "0.6"))
STT_AVG_LOGPROB_MIN = float(os.environ.get("STT_AVG_LOGPROB_MIN", "-1.0"))
VAD_TRAILING_SILENCE_MS = float(os.environ.get("VAD_TRAILING_SILENCE_MS", "500"))
VOICE_START_KEYWORDS = [
    keyword.strip()
    for keyword in os.environ.get("VOICE_START_KEYWORDS", "チェックイン").split(",")
    if keyword.strip()
]
DIALOGUE_ENABLED = os.environ.get("DIALOGUE_ENABLED", "1") == "1"
DIALOGUE_LLM_URL = os.environ.get("DIALOGUE_LLM_URL", "http://localhost:8080/v1")
DIALOGUE_LLM_MODEL = os.environ.get("DIALOGUE_LLM_MODEL", "qwen3.6-35b-a3b")
DIALOGUE_LLM_API_KEY = os.environ.get("DIALOGUE_LLM_API_KEY") or None
DIALOGUE_LLM_TIMEOUT_SECONDS = float(os.environ.get("DIALOGUE_LLM_TIMEOUT_SECONDS", "8"))
DIALOGUE_HISTORY_TURNS = int(os.environ.get("DIALOGUE_HISTORY_TURNS", "6"))
DIALOGUE_IDLE_RESET_SECONDS = float(os.environ.get("DIALOGUE_IDLE_RESET_SECONDS", "60"))
HOTEL_INFO_FILE = os.environ.get(
    "HOTEL_INFO_FILE", os.path.join(_PROJECT_ROOT, "data", "hotel_info.md")
)
ECHO_GUARD_SECONDS = float(os.environ.get("ECHO_GUARD_SECONDS", "0.5"))
