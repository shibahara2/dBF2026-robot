from flask import Flask

from app.routes.ui import ui_bp


def make_client():
    app = Flask("app")
    app.register_blueprint(ui_bp)
    return app.test_client()


def test_index_page_renders_checkin_flow_stages():
    client = make_client()

    resp = client.get("/")

    assert resp.status_code == 200
    assert b'id="start-button"' in resp.data
    assert b'id="search-form"' in resp.data
    assert b'id="search-input"' in resp.data
    assert b'id="candidate-list"' in resp.data
    assert b'id="reservation-detail"' in resp.data
    assert b'id="confirm-button"' in resp.data


def test_index_page_has_progress_and_error_sections():
    client = make_client()

    resp = client.get("/")

    assert resp.status_code == 200
    assert b'id="progress-view"' in resp.data
    assert b'id="progress-message"' in resp.data
    assert b'id="error-view"' in resp.data
    assert b'id="error-message"' in resp.data
    assert b'id="reset-button"' in resp.data


def test_index_page_includes_static_assets():
    client = make_client()

    resp = client.get("/")

    assert resp.status_code == 200
    assert b"app.js" in resp.data
    assert b"style.css" in resp.data
