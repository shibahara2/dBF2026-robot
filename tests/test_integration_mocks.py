"""Integration test: binds the real R2Client/PFClient to the real mock
servers over actual HTTP (not fakes, not `responses`), so the R2/PF
contracts asserted separately by app/clients/*.py and mocks/*.py are
regression-protected as a pair (final review finding #3)."""

import socket
import threading
import time

import pytest
from werkzeug.serving import make_server

from app.clients.pf_client import PFClient
from app.clients.r2_client import R2Client
from mocks.pf_mock import create_pf_mock_app
from mocks.r2_mock import create_r2_mock_app


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
    monkeypatch.setenv("R2_MOCK_LOADING_SECONDS", "0.1")
    monkeypatch.setenv("R2_MOCK_RETURNING_SECONDS", "0.1")

    r2_port = _free_port()
    pf_port = _free_port()

    r2_server = ServerThread(create_r2_mock_app(), r2_port)
    pf_server = ServerThread(create_pf_mock_app(), pf_port)
    r2_server.start()
    pf_server.start()

    try:
        yield {
            "r2_url": f"http://127.0.0.1:{r2_port}",
            "pf_url": f"http://127.0.0.1:{pf_port}",
        }
    finally:
        r2_server.stop()
        pf_server.stop()


def test_real_clients_against_real_mocks_full_cycle(mock_servers):
    r2 = R2Client(base_url=mock_servers["r2_url"], timeout=2.0)
    pf = PFClient(base_url=mock_servers["pf_url"], timeout=2.0)

    # PF starts ready (no PF_MOCK_INITIALIZING_SECONDS set).
    assert pf.get_guide_robot_status() == "ready"

    # R2 starts idle/completed.
    initial = r2.get_status()
    assert initial == {"outcome": "completed", "request_id": "none"}

    # Post a new load-drink command; mock accepts and starts loading.
    assert r2.post_load_drink("RID-1") == "accepted"

    # Poll until the mock's internal timers move it through
    # loading -> returning -> completed (kept fast via env vars above).
    deadline = time.monotonic() + 5.0
    outcomes_seen = set()
    result = None
    while time.monotonic() < deadline:
        result = r2.get_status()
        outcomes_seen.add(result["outcome"])
        assert result["request_id"] == "RID-1"
        if result["outcome"] == "completed":
            break
        time.sleep(0.02)

    assert result["outcome"] == "completed"
    assert "loading" in outcomes_seen or "returning" in outcomes_seen

    # Finally notify PF that the drink was placed.
    assert pf.post_drink_placed() is True
