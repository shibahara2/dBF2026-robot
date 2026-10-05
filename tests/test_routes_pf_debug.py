import threading

import pytest
from flask import Flask
from werkzeug.serving import make_server

from app.clients.pf_client import PFClient
from app.routes.pf_debug import pf_debug_bp
from mocks.pf_mock import create_pf_mock_app


class FakePFClient:
    def __init__(self):
        self.calls = []

    def raw_get_status(self):
        self.calls.append("get_status")
        return {"method": "GET", "status_code": 200, "body": '{"status": "Ready"}'}

    def raw_post_drink_placed(self):
        self.calls.append("post_drink_placed")
        return {"method": "POST", "status_code": None, "error": "timeout: slow"}


def make_client(pf_client):
    app = Flask(__name__)
    app.config["PF_CLIENT"] = pf_client
    app.register_blueprint(pf_debug_bp)
    return app.test_client()


def test_status_sends_one_get_and_returns_the_raw_result():
    pf = FakePFClient()
    resp = make_client(pf).post("/api/debug/pf/status")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "method": "GET",
        "status_code": 200,
        "body": '{"status": "Ready"}',
    }
    assert pf.calls == ["get_status"]


def test_drink_placed_sends_one_post_and_returns_errors_with_200():
    pf = FakePFClient()
    resp = make_client(pf).post("/api/debug/pf/drink-placed")

    assert resp.status_code == 200
    assert resp.get_json()["error"] == "timeout: slow"
    assert pf.calls == ["post_drink_placed"]


def test_get_is_not_allowed_so_a_page_load_cannot_send_to_pf():
    pf = FakePFClient()
    client = make_client(pf)

    assert client.get("/api/debug/pf/status").status_code == 405
    assert client.get("/api/debug/pf/drink-placed").status_code == 405
    assert pf.calls == []


@pytest.fixture
def pf_mock_url():
    server = make_server("127.0.0.1", 0, create_pf_mock_app())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_routes_reach_the_pf_mock(pf_mock_url):
    client = make_client(PFClient(pf_mock_url, timeout=2.0, api_key="mock-api-key"))

    status = client.post("/api/debug/pf/status").get_json()
    placed = client.post("/api/debug/pf/drink-placed").get_json()

    assert status["status_code"] == 200
    assert '"status"' in status["body"]
    assert placed["status_code"] == 200
    assert '"accepted"' in placed["body"]
