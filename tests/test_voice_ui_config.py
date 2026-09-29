import importlib


def test_defaults_when_env_not_set(monkeypatch):
    monkeypatch.delenv("FLASK_BASE_URL", raising=False)
    monkeypatch.delenv("VOICEVOX_URL", raising=False)
    monkeypatch.delenv("WHISPER_MODEL", raising=False)
    monkeypatch.delenv("WHISPER_DEVICE", raising=False)
    monkeypatch.delenv("WHISPER_FP16", raising=False)
    monkeypatch.delenv("STT_NO_SPEECH_PROB_MAX", raising=False)
    monkeypatch.delenv("STT_AVG_LOGPROB_MIN", raising=False)
    monkeypatch.delenv("VAD_TRAILING_SILENCE_MS", raising=False)
    monkeypatch.delenv("VOICE_START_KEYWORDS", raising=False)
    monkeypatch.delenv("DIALOGUE_ENABLED", raising=False)
    monkeypatch.delenv("DIALOGUE_LLM_URL", raising=False)
    monkeypatch.delenv("DIALOGUE_LLM_MODEL", raising=False)
    monkeypatch.delenv("DIALOGUE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("DIALOGUE_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("DIALOGUE_HISTORY_TURNS", raising=False)
    monkeypatch.delenv("DIALOGUE_IDLE_RESET_SECONDS", raising=False)
    monkeypatch.delenv("HOTEL_INFO_FILE", raising=False)
    monkeypatch.delenv("ECHO_GUARD_SECONDS", raising=False)

    from voice_ui import config
    importlib.reload(config)

    assert config.FLASK_BASE_URL == "http://localhost:5100"
    assert config.VOICEVOX_URL == "http://127.0.0.1:50021"
    assert config.WHISPER_MODEL == "large-v3"
    assert config.WHISPER_DEVICE == "cuda"
    assert config.WHISPER_FP16 is True
    assert config.STT_NO_SPEECH_PROB_MAX == 0.6
    assert config.STT_AVG_LOGPROB_MIN == -1.0
    assert config.VAD_TRAILING_SILENCE_MS == 500.0
    assert config.VOICE_START_KEYWORDS == ["チェックイン"]
    assert config.DIALOGUE_ENABLED is True
    assert config.DIALOGUE_LLM_URL == "http://10.43.10.179:8000/v1"
    assert config.DIALOGUE_LLM_MODEL == "qwen3.6-35b-a3b"
    assert config.DIALOGUE_LLM_API_KEY is None
    assert config.DIALOGUE_LLM_TIMEOUT_SECONDS == 8.0
    assert config.DIALOGUE_HISTORY_TURNS == 6
    assert config.DIALOGUE_IDLE_RESET_SECONDS == 60.0
    assert config.HOTEL_INFO_FILE.endswith("data/hotel_info.md")
    assert config.ECHO_GUARD_SECONDS == 0.5


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("FLASK_BASE_URL", "http://kiosk.example.com")
    monkeypatch.setenv("VOICEVOX_URL", "http://voicevox.example.com")
    monkeypatch.setenv("WHISPER_MODEL", "small")
    monkeypatch.setenv("WHISPER_DEVICE", "cpu")
    monkeypatch.setenv("WHISPER_FP16", "0")
    monkeypatch.setenv("STT_NO_SPEECH_PROB_MAX", "0.7")
    monkeypatch.setenv("STT_AVG_LOGPROB_MIN", "-0.8")
    monkeypatch.setenv("VAD_TRAILING_SILENCE_MS", "300")
    monkeypatch.setenv("VOICE_START_KEYWORDS", "チェックイン, check in ,")

    from voice_ui import config
    importlib.reload(config)

    assert config.FLASK_BASE_URL == "http://kiosk.example.com"
    assert config.VOICEVOX_URL == "http://voicevox.example.com"
    assert config.WHISPER_MODEL == "small"
    assert config.WHISPER_DEVICE == "cpu"
    assert config.WHISPER_FP16 is False
    assert config.STT_NO_SPEECH_PROB_MAX == 0.7
    assert config.STT_AVG_LOGPROB_MIN == -0.8
    assert config.VAD_TRAILING_SILENCE_MS == 300.0
    assert config.VOICE_START_KEYWORDS == ["チェックイン", "check in"]


def test_dialogue_env_overrides(monkeypatch):
    monkeypatch.setenv("DIALOGUE_ENABLED", "0")
    monkeypatch.setenv("DIALOGUE_LLM_URL", "http://llm.example/v1")
    monkeypatch.setenv("DIALOGUE_LLM_MODEL", "other")
    monkeypatch.setenv("DIALOGUE_LLM_API_KEY", "secret")
    monkeypatch.setenv("DIALOGUE_LLM_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("DIALOGUE_HISTORY_TURNS", "2")
    monkeypatch.setenv("DIALOGUE_IDLE_RESET_SECONDS", "30")
    monkeypatch.setenv("HOTEL_INFO_FILE", "/tmp/hotel.md")
    monkeypatch.setenv("ECHO_GUARD_SECONDS", "0.8")

    from voice_ui import config
    importlib.reload(config)

    assert config.DIALOGUE_ENABLED is False
    assert config.DIALOGUE_LLM_URL == "http://llm.example/v1"
    assert config.DIALOGUE_LLM_MODEL == "other"
    assert config.DIALOGUE_LLM_API_KEY == "secret"
    assert config.DIALOGUE_LLM_TIMEOUT_SECONDS == 3.0
    assert config.DIALOGUE_HISTORY_TURNS == 2
    assert config.DIALOGUE_IDLE_RESET_SECONDS == 30.0
    assert config.HOTEL_INFO_FILE == "/tmp/hotel.md"
    assert config.ECHO_GUARD_SECONDS == 0.8
