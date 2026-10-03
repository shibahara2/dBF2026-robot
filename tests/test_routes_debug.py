import re
from flask import Flask
from pathlib import Path

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
    assert b'id="r2-ws-url"' in resp.data
    assert b'id="pf-base-url"' in resp.data


def test_debug_page_includes_static_assets():
    client = make_client()

    resp = client.get("/debug")

    assert resp.status_code == 200
    assert b"debug.js" in resp.data
    assert b"debug.css" in resp.data


def test_debug_clock_formats_times_in_tokyo_timezone():
    debug_js = Path(__file__).parents[1] / "app" / "static" / "debug.js"

    source = debug_js.read_text()

    assert 'timeZone: "Asia/Tokyo"' in source


def test_debug_page_has_entry_panel():
    resp = make_client().get("/debug")

    for element_id in [
        "entry-panel",
        "entry-at",
        "entry-start-screen",
        "entry-start-visual",
        "entry-start-voice",
        "entry-stage-select",
        "entry-stage-checkin",
    ]:
        assert f'id="{element_id}"'.encode() in resp.data
    text = resp.data.decode()
    for label in ["開始ボタン", "VLM検知", "発話検知", "予約選択", "チェックイン完了"]:
        assert label in text


def test_debug_js_renders_entry_fields():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert 'const ENTRY_ORDER = ["start", "select", "checkin"];' in source
    for field in ["entry_source", "entry_stage", "entry_at"]:
        assert f"snapshot.{field}" in source


def test_debug_js_handles_voice_turns_and_skips_other_typed_events():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert re.search(
        r"if \(payload\.type\) \{\s*if \(payload\.type === \"voice_turn\"\) \{\s*addVoiceTurn\(payload\);\s*\}\s*return;\s*\}\s*render\(payload\);",
        source,
    )


def test_debug_page_has_voice_turn_panel():
    resp = make_client().get("/debug")

    assert b'id="voice-turn-panel"' in resp.data
    assert b'id="voice-turn-rows"' in resp.data
    for label in ["時刻", "書き起こし", "判定", "返事", "STT(ms)", "LLM(ms)"]:
        assert label in resp.data.decode()


def test_debug_js_loads_recent_voice_turns_and_escapes_text():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert 'fetch("/api/voice/turns")' in source
    assert "const MAX_VOICE_TURNS = 20;" in source
    # Transcripts come from a microphone; never inject them as HTML.
    assert "innerHTML" not in source


def test_debug_page_has_skip_load_drink_button():
    client = make_client()

    resp = client.get("/debug")

    assert resp.status_code == 200
    assert b'id="skip-load-drink"' in resp.data
