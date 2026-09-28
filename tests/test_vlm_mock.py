import base64

from mocks.vlm_mock import create_app
from mocks.themis_video_mock import MockThemisVideoConfig, make_payload


def test_vlm_mock_returns_configured_decision():
    client = create_app(decision=True).test_client()

    response = client.post(
        "/analyze",
        json={
            "image_base64": base64.b64encode(
                make_payload(MockThemisVideoConfig())
            ).decode("ascii"),
            "prompt": "test",
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"speaking_to_themis": True}


def test_vlm_mock_rejects_non_image_payload():
    client = create_app(decision=True).test_client()

    response = client.post(
        "/analyze",
        json={"image_base64": base64.b64encode(b"not an image").decode("ascii")},
    )

    assert response.status_code == 422
