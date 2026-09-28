import importlib
import os


def test_defaults_when_env_not_set(monkeypatch, tmp_path):
    monkeypatch.delenv("R2_BASE_URL", raising=False)
    monkeypatch.delenv("PF_BASE_URL", raising=False)
    monkeypatch.delenv("PF_API_KEY", raising=False)
    monkeypatch.delenv("PF_PROXY_URL", raising=False)
    monkeypatch.delenv("POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("HTTP_TIMEOUT_SECONDS", raising=False)
    monkeypatch.chdir(tmp_path)

    from app import config
    importlib.reload(config)

    assert config.R2_BASE_URL == "http://localhost:5001"
    assert config.PF_BASE_URL == "http://localhost:5002"
    assert config.PF_API_KEY == ""
    assert config.PF_PROXY_URL == ""
    assert config.POLL_INTERVAL_SECONDS == 2.0
    assert config.HTTP_TIMEOUT_SECONDS == 5.0
    assert config.DRINK_TYPE == "water"
    assert config.TARGET_ROBOT_ID == "temi"


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("R2_BASE_URL", "http://r2.example.com")
    monkeypatch.setenv("PF_BASE_URL", "http://pf.example.com")
    monkeypatch.setenv("PF_API_KEY", "test-key")
    monkeypatch.setenv("PF_PROXY_URL", "http://115.69.226.50:8080")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "1.5")
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "3")
    monkeypatch.chdir(tmp_path)

    from app import config
    importlib.reload(config)

    assert config.R2_BASE_URL == "http://r2.example.com"
    assert config.PF_BASE_URL == "http://pf.example.com"
    assert config.PF_API_KEY == "test-key"
    assert config.PF_PROXY_URL == "http://115.69.226.50:8080"
    assert config.POLL_INTERVAL_SECONDS == 1.5
    assert config.HTTP_TIMEOUT_SECONDS == 3.0


def test_dotenv_values_are_loaded(monkeypatch, tmp_path):
    monkeypatch.delenv("R2_BASE_URL", raising=False)
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
