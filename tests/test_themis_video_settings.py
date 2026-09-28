import pytest

from themis_video.settings import load_settings


def test_unset_url_is_allowed_for_optional_client():
    settings = load_settings({})

    assert settings.ws_url is None
    assert settings.reconnect_delay_seconds == 1.0
    assert settings.connect_timeout_seconds == 5.0


def test_loads_valid_websocket_settings():
    settings = load_settings(
        {
            "THEMIS_WS_URL": "wss://themis.example/zed2i",
            "THEMIS_WS_RECONNECT_DELAY_SECONDS": "2.5",
            "THEMIS_WS_CONNECT_TIMEOUT_SECONDS": "8",
        }
    )

    assert settings.ws_url == "wss://themis.example/zed2i"
    assert settings.reconnect_delay_seconds == 2.5
    assert settings.connect_timeout_seconds == 8.0


@pytest.mark.parametrize(
    "key,value",
    [
        ("THEMIS_WS_URL", "http://themis.example/zed2i"),
        ("THEMIS_WS_RECONNECT_DELAY_SECONDS", "nope"),
        ("THEMIS_WS_CONNECT_TIMEOUT_SECONDS", "0"),
    ],
)
def test_rejects_invalid_settings(key, value):
    with pytest.raises(ValueError, match=key.removeprefix("THEMIS_WS_")):
        load_settings({key: value})
