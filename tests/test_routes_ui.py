from flask import Flask

from app.routes.ui import ui_bp


def make_client():
    app = Flask("app")
    app.register_blueprint(ui_bp)
    return app.test_client()


def test_index_page_renders_checkin_form():
    client = make_client()

    resp = client.get("/")

    assert resp.status_code == 200
    assert b'id="checkin-form"' in resp.data
    assert b'id="guest-name-input"' in resp.data


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
