import importlib
import os


R2_ENV = (
    "R2_WS_URL",
    "R2_START_REPLY_TIMEOUT_SECONDS",
    "R2_WS_RECONNECT_DELAY_SECONDS",
    "R2_WS_CONNECT_TIMEOUT_SECONDS",
)


def test_defaults_when_env_not_set(monkeypatch, tmp_path):
    for name in R2_ENV + (
        "PF_BASE_URL",
        "PF_API_KEY",
        "PF_PROXY_URL",
        "POLL_INTERVAL_SECONDS",
        "HTTP_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)

    from app import config
    importlib.reload(config)

    assert config.R2_WS_URL == "ws://127.0.0.1:9002/realtime"
    assert config.R2_START_REPLY_TIMEOUT_SECONDS == 15.0
    assert config.R2_WS_RECONNECT_DELAY_SECONDS == 1.0
    assert config.R2_WS_CONNECT_TIMEOUT_SECONDS == 5.0
    assert config.PF_BASE_URL == "http://localhost:5002"
    assert config.PF_API_KEY == ""
    assert config.PF_PROXY_URL == ""
    assert config.POLL_INTERVAL_SECONDS == 2.0
    assert config.HTTP_TIMEOUT_SECONDS == 5.0
    for removed in ("R2_BASE_URL", "DRINK_TYPE", "TARGET_ROBOT_ID"):
        assert not hasattr(config, removed)


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("R2_WS_URL", "ws://10.17.4.171:9002/realtime")
    monkeypatch.setenv("R2_START_REPLY_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("R2_WS_RECONNECT_DELAY_SECONDS", "2")
    monkeypatch.setenv("R2_WS_CONNECT_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("PF_BASE_URL", "http://pf.example.com")
    monkeypatch.setenv("PF_API_KEY", "test-key")
    monkeypatch.setenv("PF_PROXY_URL", "http://115.69.226.50:8080")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "1.5")
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "3")
    monkeypatch.chdir(tmp_path)

    from app import config
    importlib.reload(config)

    assert config.R2_WS_URL == "ws://10.17.4.171:9002/realtime"
    assert config.R2_START_REPLY_TIMEOUT_SECONDS == 20.0
    assert config.R2_WS_RECONNECT_DELAY_SECONDS == 2.0
    assert config.R2_WS_CONNECT_TIMEOUT_SECONDS == 3.0
    assert config.PF_BASE_URL == "http://pf.example.com"
    assert config.PF_API_KEY == "test-key"
    assert config.PF_PROXY_URL == "http://115.69.226.50:8080"
    assert config.POLL_INTERVAL_SECONDS == 1.5
    assert config.HTTP_TIMEOUT_SECONDS == 3.0


def test_dotenv_values_are_loaded(monkeypatch, tmp_path):
    monkeypatch.delenv("PF_BASE_URL", raising=False)
    monkeypatch.delenv("PF_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "PF_BASE_URL=https://reception.robility-system-stg.com\n"
        "PF_API_KEY=dotenv-key\n",
        encoding="utf-8",
    )

    from app import config
    importlib.reload(config)

    assert config.PF_BASE_URL == "https://reception.robility-system-stg.com"
    assert config.PF_API_KEY == "dotenv-key"


def test_pf_proxy_url_is_loaded_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("PF_PROXY_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("PF_PROXY_URL=http://proxy.example:3128\n", encoding="utf-8")

    from app import config
    importlib.reload(config)

    assert config.PF_PROXY_URL == "http://proxy.example:3128"
