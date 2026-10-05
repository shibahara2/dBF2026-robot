"""Integration test: binds the real PFClient to the real PF mock over actual HTTP."""

import socket
import threading
import time

import pytest
from werkzeug.serving import make_server

from app.clients.pf_client import PFClient
from mocks.pf_mock import create_pf_mock_app


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerThread:
    def __init__(self, app, port):
        self._server = make_server("127.0.0.1", port, app)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._thread.join(timeout=2)


@pytest.fixture()
def mock_servers(monkeypatch):
    pf_port = _free_port()

    pf_server = ServerThread(create_pf_mock_app(), pf_port)
    pf_server.start()

    try:
        yield {
            "pf_url": f"http://127.0.0.1:{pf_port}",
        }
    finally:
        pf_server.stop()


def test_real_pf_client_against_real_pf_mock(mock_servers):
    pf = PFClient(
        base_url=mock_servers["pf_url"], timeout=2.0, api_key="test-key"
    )

    # PF starts ready (no PF_MOCK_INITIALIZING_SECONDS set).
    assert pf.get_guide_robot_status() == "ready"
    assert pf.post_drink_placed() is True
