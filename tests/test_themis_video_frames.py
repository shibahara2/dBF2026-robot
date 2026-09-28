import pytest

from themis_video.frames import RawThemisFrame, raw_frame_from_payload


def test_raw_frame_preserves_binary_payload():
    payload = b"themis-frame"

    frame = raw_frame_from_payload(payload)

    assert isinstance(frame, RawThemisFrame)
    assert frame.payload == payload


@pytest.mark.parametrize("payload", (b"", None))
def test_raw_frame_rejects_empty_or_missing_payload(payload):
    with pytest.raises(ValueError, match="payload"):
        raw_frame_from_payload(payload)
