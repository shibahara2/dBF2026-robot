import time

from mocks.r2_mock import create_r2_mock_app


def make_client(monkeypatch, loading_seconds="0.05", returning_seconds="0.05", force_failure=""):
    monkeypatch.setenv("R2_MOCK_LOADING_SECONDS", loading_seconds)
    monkeypatch.setenv("R2_MOCK_RETURNING_SECONDS", returning_seconds)
    monkeypatch.setenv("R2_MOCK_FORCE_FAILURE", force_failure)
    app = create_r2_mock_app()
    return app.test_client()


def test_initial_status_is_completed_with_no_request_id(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/v1/commands/load-drink/status")
    assert resp.status_code == 200
    assert resp.get_json() == {"request_id": "none", "status": "completed"}


def test_load_drink_accepts_and_transitions_through_loading_returning_completed(monkeypatch):
    client = make_client(monkeypatch, loading_seconds="0.01", returning_seconds="0.05")

    post_resp = client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID", "drink_type": "water", "target_robot_id": "temi"},
    )
    assert post_resp.status_code == 200

    status_resp = client.get("/v1/commands/load-drink/status")
    assert status_resp.get_json()["status"] == "loading"

    time.sleep(0.1)
    status_resp = client.get("/v1/commands/load-drink/status")
    assert status_resp.get_json()["status"] == "loading"

    time.sleep(1.0)
    status_resp = client.get("/v1/commands/load-drink/status")
    assert status_resp.get_json()["status"] in ("returning", "completed")


def test_load_drink_missing_fields_returns_422(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.post("/v1/commands/load-drink", json={"request_id": "RID"})
    assert resp.status_code == 422


def test_load_drink_rejected_while_already_in_progress(monkeypatch):
    client = make_client(monkeypatch, loading_seconds="1", returning_seconds="1")
    client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID1", "drink_type": "water", "target_robot_id": "temi"},
    )

    resp = client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID2", "drink_type": "water", "target_robot_id": "temi"},
    )
    assert resp.status_code == 500


def test_load_drink_same_request_id_is_idempotent(monkeypatch):
    client = make_client(monkeypatch, loading_seconds="1", returning_seconds="1")
    first = client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID1", "drink_type": "water", "target_robot_id": "temi"},
    )
    second = client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID1", "drink_type": "water", "target_robot_id": "temi"},
    )
    assert first.status_code == 200
    assert second.status_code == 200


def test_force_failure_422(monkeypatch):
    client = make_client(monkeypatch, force_failure="422")
    resp = client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID", "drink_type": "water", "target_robot_id": "temi"},
    )
    assert resp.status_code == 422


def test_force_failure_failed_status(monkeypatch):
    client = make_client(monkeypatch, loading_seconds="0.01", force_failure="failed")
    client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID", "drink_type": "water", "target_robot_id": "temi"},
    )
    time.sleep(0.05)
    resp = client.get("/v1/commands/load-drink/status")
    assert resp.get_json()["status"] == "failed"
