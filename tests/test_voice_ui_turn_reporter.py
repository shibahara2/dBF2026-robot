import json

import requests
import responses

from voice_ui.turn_reporter import TurnReporter

URL = "http://flask.test/api/voice/turns"


@responses.activate
def test_report_posts_turn():
    responses.add(responses.POST, URL, status=202, json={})

    assert TurnReporter("http://flask.test").report({"text": "こんにちは", "outcome": "chat"}) is True
    assert json.loads(responses.calls[0].request.body) == {"text": "こんにちは", "outcome": "chat"}


@responses.activate
def test_report_returns_false_on_rejection():
    responses.add(responses.POST, URL, status=422, json={})

    assert TurnReporter("http://flask.test").report({"text": "", "outcome": "chat"}) is False


@responses.activate
def test_report_swallows_connection_errors():
    responses.add(responses.POST, URL, body=requests.exceptions.ConnectionError())

    assert TurnReporter("http://flask.test").report({"text": "", "outcome": "chat"}) is False
