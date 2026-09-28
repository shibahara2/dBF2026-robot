import logging

import pytest

from themis_video.client import VideoClientStatus
from themis_video.settings import load_runtime_settings
from tools import run_themis_vlm


def test_mock_mode_selects_local_mock_endpoints():
    settings = load_runtime_settings({"THEMIS_VLM_MODE": "mock"})

    assert settings.mode == "mock"
    assert settings.ws_url == "ws://127.0.0.1:9002/zed2i"
    assert settings.vlm_endpoint == "http://127.0.0.1:5103/analyze"


def test_real_mode_requires_explicit_endpoints():
    with pytest.raises(ValueError, match="THEMIS_WS_URL"):
        load_runtime_settings({"THEMIS_VLM_MODE": "real"})


def test_real_mode_loads_dotenv_style_values():
    settings = load_runtime_settings(
        {
            "THEMIS_VLM_MODE": "real",
            "THEMIS_WS_URL": "ws://themis:9002/zed2i",
            "VLM_ENDPOINT": "https://vlm.example/analyze",
            "VISUAL_TRIGGER_URL": "https://app.example/api/visual/start",
        }
    )

    assert settings.mode == "real"
    assert settings.ws_url == "ws://themis:9002/zed2i"
    assert settings.vlm_endpoint == "https://vlm.example/analyze"
    assert settings.trigger_url == "https://app.example/api/visual/start"


def test_cli_endpoints_work_in_real_mode_without_env_values(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("THEMIS_VLM_MODE", "real")
    monkeypatch.delenv("THEMIS_WS_URL", raising=False)
    monkeypatch.delenv("VLM_ENDPOINT", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_themis_vlm.py",
            "--ws-url", "ws://themis:9002/zed2i",
            "--vlm-endpoint", "https://vlm.example/analyze",
        ],
    )
    received = []
    monkeypatch.setattr(run_themis_vlm, "run", lambda *args: received.append(args))

    run_themis_vlm.main()

    assert received == [
        (
            "ws://themis:9002/zed2i",
            "https://vlm.example/analyze",
            "http://127.0.0.1:5100/api/visual/start",
            None,
        )
    ]


def test_health_report_warns_when_connected_stream_has_stalled(caplog):
    status = VideoClientStatus(
        connected=True,
        connect_attempts=2,
        frames_received=12,
        processing_errors=1,
        last_frame_at=20.0,
    )

    with caplog.at_level(logging.INFO):
        run_themis_vlm.report_video_health(status, now=35.0)

    assert "stalled" in caplog.text
    assert "frames=12" in caplog.text
    assert "processing_errors=1" in caplog.text


def test_health_report_recognizes_recent_frame(caplog):
    status = VideoClientStatus(
        connected=True,
        connect_attempts=1,
        frames_received=12,
        processing_errors=0,
        last_frame_at=34.0,
    )

    with caplog.at_level(logging.INFO):
        run_themis_vlm.report_video_health(status, now=35.0)

    assert "healthy" in caplog.text
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)
