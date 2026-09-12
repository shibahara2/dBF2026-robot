import time

from mocks.pf_mock import create_pf_mock_app


def make_client(monkeypatch, initializing_seconds="0", accepted="true"):
    monkeypatch.setenv("PF_MOCK_INITIALIZING_SECONDS", initializing_seconds)
    monkeypatch.setenv("PF_MOCK_ACCEPTED", accepted)
    app = create_pf_mock_app()
    return app.test_client()


def test_status_is_ready_by_default(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/api/v1/guide-robot/status")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "Ready"}


def test_status_is_initializing_until_configured_delay_passes(monkeypatch):
    client = make_client(monkeypatch, initializing_seconds="0.1")
    resp = client.get("/api/v1/guide-robot/status")
    assert resp.get_json() == {"status": "Initializing"}

    time.sleep(0.15)
    resp = client.get("/api/v1/guide-robot/status")
    assert resp.get_json() == {"status": "Ready"}


def test_drink_placed_accepted_by_default(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.post("/api/v1/drink/placed")
    assert resp.status_code == 200
    assert resp.get_json() == {"accepted": True}


def test_drink_placed_can_be_forced_to_not_accepted(monkeypatch):
    client = make_client(monkeypatch, accepted="false")
    resp = client.post("/api/v1/drink/placed")
    assert resp.get_json() == {"accepted": False}
