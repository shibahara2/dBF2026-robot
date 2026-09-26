import responses
import requests
from unittest.mock import patch

from app.clients.pf_client import PFClient


def make_client():
    return PFClient(base_url="http://pf.test", timeout=1.0)


@responses.activate
def test_pf_requests_include_api_key_header():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"status": "Ready"},
        status=200,
    )
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        json={"accepted": True},
        status=200,
    )

    client = PFClient(base_url="http://pf.test", timeout=1.0, api_key="test-key")

    assert client.get_guide_robot_status() == "ready"
    assert client.post_drink_placed() is True
    assert responses.calls[0].request.headers["X-API-Key"] == "test-key"
    assert responses.calls[1].request.headers["X-API-Key"] == "test-key"
    assert responses.calls[0].request.headers["Content-Type"] == "application/json"
    assert responses.calls[1].request.headers["Content-Type"] == "application/json"


@responses.activate
def test_pf_requests_use_configured_proxy():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"status": "Ready"},
        status=200,
    )

    with patch("app.clients.pf_client.requests.get") as get:
        get.return_value.status_code = 200
        get.return_value.json.return_value = {"status": "Ready"}
        client = PFClient(
            base_url="http://pf.test",
            timeout=1.0,
            proxy_url="http://115.69.226.50:8080",
        )

        assert client.get_guide_robot_status() == "ready"

    assert get.call_args.kwargs["proxies"] == {
        "http": "http://115.69.226.50:8080",
        "https": "http://115.69.226.50:8080",
    }


@responses.activate
def test_get_guide_robot_status_ready():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"status": "Ready"},
        status=200,
    )
    assert make_client().get_guide_robot_status() == "ready"


@responses.activate
def test_get_guide_robot_status_initializing():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"status": "Initializing"},
        status=200,
    )
    assert make_client().get_guide_robot_status() == "initializing"


@responses.activate
def test_get_guide_robot_status_422_is_retryable():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"message": "bad request"},
        status=422,
    )
    assert make_client().get_guide_robot_status() == "retryable_error"


@responses.activate
def test_get_guide_robot_status_500_is_fatal():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"message": "boom"},
        status=500,
    )
    assert make_client().get_guide_robot_status() == "fatal_error"


@responses.activate
def test_get_guide_robot_status_timeout():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        body=requests.exceptions.Timeout(),
    )
    assert make_client().get_guide_robot_status() == "timeout"


@responses.activate
def test_get_guide_robot_status_unexpected_body_is_fatal():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"status": "Unknown"},
        status=200,
    )
    assert make_client().get_guide_robot_status() == "fatal_error"


@responses.activate
def test_get_guide_robot_status_malformed_json_is_fatal_not_raising():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        body="not json",
        status=200,
        content_type="application/json",
    )
    assert make_client().get_guide_robot_status() == "fatal_error"


@responses.activate
def test_post_drink_placed_accepted():
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        json={"accepted": True},
        status=200,
    )
    assert make_client().post_drink_placed() is True
    assert responses.calls[0].request.body == b'{"result": "success"}'
    assert responses.calls[0].request.headers["Content-Type"] == "application/json"


@responses.activate
def test_post_drink_placed_not_accepted():
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        json={"accepted": False},
        status=200,
    )
    assert make_client().post_drink_placed() is False


@responses.activate
def test_post_drink_placed_http_error():
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        json={"message": "boom"},
        status=500,
    )
    assert make_client().post_drink_placed() is False


@responses.activate
def test_post_drink_placed_timeout():
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        body=requests.exceptions.Timeout(),
    )
    assert make_client().post_drink_placed() is False


@responses.activate
def test_post_drink_placed_malformed_json_is_false_not_raising():
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        body="not json",
        status=200,
        content_type="application/json",
    )
    assert make_client().post_drink_placed() is False
