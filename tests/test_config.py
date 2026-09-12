import importlib
import os


def test_defaults_when_env_not_set(monkeypatch):
    monkeypatch.delenv("R2_BASE_URL", raising=False)
    monkeypatch.delenv("PF_BASE_URL", raising=False)
    monkeypatch.delenv("POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("HTTP_TIMEOUT_SECONDS", raising=False)

    from app import config
    importlib.reload(config)

    assert config.R2_BASE_URL == "http://localhost:5001"
    assert config.PF_BASE_URL == "http://localhost:5002"
    assert config.POLL_INTERVAL_SECONDS == 2.0
    assert config.HTTP_TIMEOUT_SECONDS == 5.0
    assert config.DRINK_TYPE == "water"
    assert config.TARGET_ROBOT_ID == "temi"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("R2_BASE_URL", "http://r2.example.com")
    monkeypatch.setenv("PF_BASE_URL", "http://pf.example.com")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "1.5")
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "3")

    from app import config
    importlib.reload(config)

    assert config.R2_BASE_URL == "http://r2.example.com"
    assert config.PF_BASE_URL == "http://pf.example.com"
    assert config.POLL_INTERVAL_SECONDS == 1.5
    assert config.HTTP_TIMEOUT_SECONDS == 3.0
