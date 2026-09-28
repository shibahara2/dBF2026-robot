import base64

import pytest
import responses

from themis_video.vlm import VLMClient, VLMError


@responses.activate
def test_vlm_client_posts_base64_image_and_returns_decision():
    responses.add(
        responses.POST,
        "https://vlm.example/analyze",
        json={"speaking_to_themis": True},
        status=200,
    )
    client = VLMClient(
        "https://vlm.example/analyze",
        api_key="secret",
        timeout=3.0,
    )

    decision = client.analyze(b"image-bytes")

    assert decision is True
    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer secret"
    assert base64.b64encode(b"image-bytes").decode() in request.body.decode()


@responses.activate
def test_vlm_client_returns_false_for_negative_decision():
    responses.add(
        responses.POST,
        "https://vlm.example/analyze",
        json={"speaking_to_themis": False},
        status=200,
    )

    assert VLMClient("https://vlm.example/analyze").analyze(b"frame") is False


@responses.activate
def test_vlm_client_rejects_missing_decision():
    responses.add(
        responses.POST,
        "https://vlm.example/analyze",
        json={"answer": "yes"},
        status=200,
    )

    with pytest.raises(VLMError, match="speaking_to_themis"):
        VLMClient("https://vlm.example/analyze").analyze(b"frame")
