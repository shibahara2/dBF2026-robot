import pytest
from pathlib import Path

from mocks.themis_video_mock import MockThemisVideoConfig, make_payload


def test_default_mock_payload_is_the_person_png():
    payload = make_payload(MockThemisVideoConfig())
    image_path = Path(__file__).resolve().parents[1] / "person.png"

    assert payload == image_path.read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")


def test_mock_payload_is_binary_and_configurable():
    config = MockThemisVideoConfig(payload=b"jpeg-like-frame", interval_seconds=0.5)

    assert make_payload(config) == b"jpeg-like-frame"


def test_mock_config_rejects_non_positive_interval():
    with pytest.raises(ValueError, match="interval_seconds"):
        MockThemisVideoConfig(payload=b"frame", interval_seconds=0)
