import responses
import requests

from voice_ui.checkin_client import CheckinClient


def make_client():
    return CheckinClient(base_url="http://flask.test", timeout=1.0)


@responses.activate
def test_checkin_accepted():
    responses.add(
        responses.POST,
        "http://flask.test/api/checkin",
        json={"message": "checkin accepted"},
        status=200,
    )
    assert make_client().checkin("田中太郎") == "accepted"
    sent_body = responses.calls[0].request.body
    assert b'"name": "\xe7\x94\xb0\xe4\xb8\xad\xe5\xa4\xaa\xe9\x83\x8e"' in sent_body


@responses.activate
def test_checkin_already_in_progress():
    responses.add(
        responses.POST,
        "http://flask.test/api/checkin",
        json={"message": "a cycle is already in progress"},
        status=409,
    )
    assert make_client().checkin("田中太郎") == "already_in_progress"


@responses.activate
def test_checkin_validation_error():
    responses.add(
        responses.POST,
        "http://flask.test/api/checkin",
        json={"message": "name is required"},
        status=422,
    )
    assert make_client().checkin("") == "validation_error"


@responses.activate
def test_checkin_server_error():
    responses.add(
        responses.POST,
        "http://flask.test/api/checkin",
        json={"message": "boom"},
        status=500,
    )
    assert make_client().checkin("田中太郎") == "server_error"


@responses.activate
def test_checkin_timeout():
    responses.add(
        responses.POST,
        "http://flask.test/api/checkin",
        body=requests.exceptions.Timeout(),
    )
    assert make_client().checkin("田中太郎") == "timeout"


@responses.activate
def test_checkin_connection_error():
    responses.add(
        responses.POST,
        "http://flask.test/api/checkin",
        body=requests.exceptions.ConnectionError(),
    )
    assert make_client().checkin("田中太郎") == "connection_error"
