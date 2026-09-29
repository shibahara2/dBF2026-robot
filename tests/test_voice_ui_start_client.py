import pytest
import requests
import responses

from voice_ui.start_client import VoiceStartClient

URL = "http://flask.test/api/voice/start"


def make_client():
    return VoiceStartClient(base_url="http://flask.test", timeout=1.0)


@responses.activate
@pytest.mark.parametrize(
    "status, expected",
    [
        (202, "accepted"),
        (409, "not_available"),
        (429, "rate_limited"),
        (500, "server_error"),
    ],
)
def test_start_classifies_status(status, expected):
    responses.add(responses.POST, URL, json={}, status=status)

    assert make_client().start() == expected
    assert responses.calls[0].request.body == b"{}"


@responses.activate
def test_start_timeout():
    responses.add(responses.POST, URL, body=requests.exceptions.Timeout())

    assert make_client().start() == "timeout"


@responses.activate
def test_start_connection_error():
    responses.add(responses.POST, URL, body=requests.exceptions.ConnectionError())

    assert make_client().start() == "connection_error"
