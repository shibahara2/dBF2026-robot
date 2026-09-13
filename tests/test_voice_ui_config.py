import importlib


def test_defaults_when_env_not_set(monkeypatch):
    monkeypatch.delenv("FLASK_BASE_URL", raising=False)
    monkeypatch.delenv("VOICEVOX_URL", raising=False)
    monkeypatch.delenv("WHISPER_MODEL", raising=False)
    monkeypatch.delenv("STT_NO_SPEECH_PROB_MAX", raising=False)
    monkeypatch.delenv("STT_AVG_LOGPROB_MIN", raising=False)
    monkeypatch.delenv("VAD_TRAILING_SILENCE_MS", raising=False)

    from voice_ui import config
    importlib.reload(config)

    assert config.FLASK_BASE_URL == "http://localhost:5000"
    assert config.VOICEVOX_URL == "http://127.0.0.1:50021"
    assert config.WHISPER_MODEL == "base"
    assert config.STT_NO_SPEECH_PROB_MAX == 0.6
    assert config.STT_AVG_LOGPROB_MIN == -1.0
    assert config.VAD_TRAILING_SILENCE_MS == 500.0


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("FLASK_BASE_URL", "http://kiosk.example.com")
    monkeypatch.setenv("VOICEVOX_URL", "http://voicevox.example.com")
    monkeypatch.setenv("WHISPER_MODEL", "small")
    monkeypatch.setenv("STT_NO_SPEECH_PROB_MAX", "0.7")
    monkeypatch.setenv("STT_AVG_LOGPROB_MIN", "-0.8")
    monkeypatch.setenv("VAD_TRAILING_SILENCE_MS", "300")

    from voice_ui import config
    importlib.reload(config)

    assert config.FLASK_BASE_URL == "http://kiosk.example.com"
    assert config.VOICEVOX_URL == "http://voicevox.example.com"
    assert config.WHISPER_MODEL == "small"
    assert config.STT_NO_SPEECH_PROB_MAX == 0.7
    assert config.STT_AVG_LOGPROB_MIN == -0.8
    assert config.VAD_TRAILING_SILENCE_MS == 300.0
