from flask import Flask

from app.routes.ui import ui_bp


def make_client():
    app = Flask("app")
    app.register_blueprint(ui_bp)
    return app.test_client()


def test_debug_page_renders():
    client = make_client()

    resp = client.get("/debug")

    assert resp.status_code == 200
    assert b'id="sequence-diagram"' in resp.data


def test_debug_page_has_all_lanes():
    client = make_client()

    resp = client.get("/debug")

    assert resp.status_code == 200
    assert b'id="lane-guest"' in resp.data
    assert b'id="lane-venue"' in resp.data
    assert b'id="lane-pf"' in resp.data
    assert b'id="lane-r2"' in resp.data


def test_debug_page_has_all_step_arrows():
    client = make_client()

    resp = client.get("/debug")

    assert resp.status_code == 200
    for step_id in [
        "arrow-polling_pf_ready",
        "arrow-polling_r2_ready",
        "arrow-sending_load_drink",
        "arrow-polling_r2_active",
        "arrow-notifying_pf_placed",
    ]:
        assert step_id.encode() in resp.data


def test_debug_page_has_status_and_error_sections():
    client = make_client()

    resp = client.get("/debug")

    assert resp.status_code == 200
    assert b'id="debug-status"' in resp.data
    assert b'id="debug-error"' in resp.data


def test_debug_page_has_get_status_panel():
    client = make_client()

    resp = client.get("/debug")

    assert resp.status_code == 200
    assert b'id="pf-status-value"' in resp.data
    assert b'id="pf-status-at"' in resp.data
    assert b'id="r2-status-value"' in resp.data
    assert b'id="r2-status-at"' in resp.data
    assert b'id="current-time"' in resp.data


def test_debug_page_shows_connection_targets():
    client = make_client()

    resp = client.get("/debug")

    assert resp.status_code == 200
    assert b'id="r2-base-url"' in resp.data
    assert b'id="pf-base-url"' in resp.data


def test_debug_page_includes_static_assets():
    client = make_client()

    resp = client.get("/debug")

    assert resp.status_code == 200
    assert b"debug.js" in resp.data
    assert b"debug.css" in resp.data
