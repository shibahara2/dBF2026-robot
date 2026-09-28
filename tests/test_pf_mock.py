import time

from mocks.pf_mock import create_pf_mock_app


def make_client(monkeypatch, initializing_seconds="0", accepted="true"):
    monkeypatch.setenv("PF_MOCK_INITIALIZING_SECONDS", initializing_seconds)
    monkeypatch.setenv("PF_MOCK_ACCEPTED", accepted)
    app = create_pf_mock_app()
    return app.test_client()


def auth_headers():
    return {"X-API-Key": "test-key"}


def test_pf_endpoints_require_api_key(monkeypatch):
    client = make_client(monkeypatch)

    status_resp = client.get("/api/v1/guide-robot/status")
    drink_resp = client.post("/api/v1/drink/placed")

    assert status_resp.status_code == 401
    assert drink_resp.status_code == 401
    assert status_resp.get_json() == {"message": "unauthorized"}


def test_pf_endpoints_accept_any_api_key_value(monkeypatch):
    client = make_client(monkeypatch)
    headers = {"X-API-Key": "any-value-is-accepted"}

    status_resp = client.get("/api/v1/guide-robot/status", headers=headers)
    drink_resp = client.post("/api/v1/drink/placed", headers=headers)

    assert status_resp.status_code == 200
    assert drink_resp.status_code == 200


def test_pf_endpoints_reject_missing_api_key(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.get("/api/v1/guide-robot/status")

    assert resp.status_code == 401


def test_status_is_ready_by_default(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/api/v1/guide-robot/status", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "Ready"}


def test_status_is_initializing_until_configured_delay_passes(monkeypatch):
    client = make_client(monkeypatch, initializing_seconds="0.1")
    resp = client.get("/api/v1/guide-robot/status", headers=auth_headers())
    assert resp.get_json() == {"status": "Initializing"}

    time.sleep(0.15)
    resp = client.get("/api/v1/guide-robot/status", headers=auth_headers())
    assert resp.get_json() == {"status": "Ready"}


def test_drink_placed_accepted_by_default(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.post("/api/v1/drink/placed", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.get_json() == {"accepted": True}


def test_drink_placed_can_be_forced_to_not_accepted(monkeypatch):
    client = make_client(monkeypatch, accepted="false")
    resp = client.post("/api/v1/drink/placed", headers=auth_headers())
    assert resp.get_json() == {"accepted": False}


def test_status_can_be_forced_to_422(monkeypatch):
    monkeypatch.setenv("PF_MOCK_FORCE_FAILURE", "422")
    app = create_pf_mock_app()
    client = app.test_client()
    resp = client.get("/api/v1/guide-robot/status", headers=auth_headers())
    assert resp.status_code == 422


def test_status_can_be_forced_to_500(monkeypatch):
    monkeypatch.setenv("PF_MOCK_FORCE_FAILURE", "500")
    app = create_pf_mock_app()
    client = app.test_client()
    resp = client.get("/api/v1/guide-robot/status", headers=auth_headers())
    assert resp.status_code == 500
