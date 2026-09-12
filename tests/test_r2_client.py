import responses
import requests

from app.clients.r2_client import R2Client


def make_client():
    return R2Client(base_url="http://r2.test", timeout=1.0)


@responses.activate
def test_get_status_loading():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        json={"request_id": "RID", "status": "loading"},
        status=200,
    )
    assert make_client().get_status() == {"outcome": "loading", "request_id": "RID"}


@responses.activate
def test_get_status_completed():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        json={"request_id": "none", "status": "completed"},
        status=200,
    )
    assert make_client().get_status() == {"outcome": "completed", "request_id": "none"}


@responses.activate
def test_get_status_failed():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        json={"request_id": "RID", "status": "failed"},
        status=200,
    )
    assert make_client().get_status() == {"outcome": "failed", "request_id": "RID"}


@responses.activate
def test_get_status_timeout():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        body=requests.exceptions.Timeout(),
    )
    assert make_client().get_status() == {"outcome": "timeout", "request_id": None}


@responses.activate
def test_get_status_500_is_fatal():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        json={"message": "boom"},
        status=500,
    )
    assert make_client().get_status() == {"outcome": "fatal_error", "request_id": None}


@responses.activate
def test_get_status_malformed_json_is_fatal_not_raising():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        body="not json",
        status=200,
        content_type="application/json",
    )
    assert make_client().get_status() == {"outcome": "fatal_error", "request_id": None}


@responses.activate
def test_post_load_drink_accepted_sends_expected_body():
    responses.add(
        responses.POST,
        "http://r2.test/v1/commands/load-drink",
        json={},
        status=200,
    )
    result = make_client().post_load_drink("RID")
    assert result == "accepted"
    sent_body = responses.calls[0].request.body
    assert b'"request_id": "RID"' in sent_body
    assert b'"drink_type": "water"' in sent_body
    assert b'"target_robot_id": "temi"' in sent_body


@responses.activate
def test_post_load_drink_validation_error():
    responses.add(
        responses.POST,
        "http://r2.test/v1/commands/load-drink",
        json={"message": "bad"},
        status=422,
    )
    assert make_client().post_load_drink("RID") == "validation_error"


@responses.activate
def test_post_load_drink_server_error():
    responses.add(
        responses.POST,
        "http://r2.test/v1/commands/load-drink",
        json={"message": "boom"},
        status=500,
    )
    assert make_client().post_load_drink("RID") == "server_error"


@responses.activate
def test_post_load_drink_timeout():
    responses.add(
        responses.POST,
        "http://r2.test/v1/commands/load-drink",
        body=requests.exceptions.Timeout(),
    )
    assert make_client().post_load_drink("RID") == "timeout"
