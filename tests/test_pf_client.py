import responses
import requests

from app.clients.pf_client import PFClient


def make_client():
    return PFClient(base_url="http://pf.test", timeout=1.0)


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
def test_post_drink_placed_accepted():
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        json={"accepted": True},
        status=200,
    )
    assert make_client().post_drink_placed() is True


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
