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
        "arrow-waiting_r2_ready",
        "arrow-starting_r2",
        "arrow-waiting_r2_placed",
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
    assert b'id="current-time"' in resp.data
    assert b'id="r2-status-value"' not in resp.data


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


def test_debug_js_handles_typed_events_before_rendering_snapshots():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert re.search(
        r"if \(payload\.type\) \{\s*if \(payload\.type === \"voice_turn\"\) \{\s*addVoiceTurn\(payload\);\s*\}\s*"
        r"if \(payload\.type === \"r2_state\"\) \{\s*renderR2\(payload\);\s*\}\s*return;\s*\}\s*render\(payload\);",
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


def test_debug_page_has_r2_panel():
    resp = make_client().get("/debug")

    for element_id in [
        "r2-panel",
        "r2-connection",
        "r2-connection-at",
        "r2-status",
        "r2-status-at",
        "r2-failure",
        "r2-under-mode",
        "r2-under-mode-at",
        "r2-last-reply",
        "r2-toggle-connection",
        "r2-stop",
        "r2-resend",
        "r2-mark-returning",
        "r2-mark-completed",
        "r2-mark-failed",
        "r2-reset",
        "r2-confirm",
        "r2-result",
        "r2-hint",
        "state-machine-reset",
    ]:
        assert f'id="{element_id}"'.encode() in resp.data
    assert b'id="skip-load-drink"' not in resp.data


def test_debug_js_drives_r2_api_and_confirms_risky_actions():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert 'fetch("/api/debug/r2")' in source
    for action in ["connect", "disconnect", "stop", "resend", "mark", "reset"]:
        assert f'"{action}"' in source
    assert "temi が出発します" in source
    assert "R2 が A にいることを確認しましたか" in source
    assert 'fetch("/api/reset", { method: "POST" })' in source
    # No browser dialogs: they block the page (and automation).
    for dialog in ["confirm(", "alert(", "prompt("]:
        assert dialog not in source
    assert "innerHTML" not in source


def test_debug_sequence_diagram_describes_the_websocket_exchange():
    text = make_client().get("/debug").data.decode()

    assert "play_navigation5" in text
    assert "under_mode" in text
    assert "GET load-drink/status" not in text
    assert "POST load-drink" not in text


def test_debug_js_stop_button_is_not_disabled_by_starting():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    # STOP button must not be guarded by snapshot.starting, only by its enabled rule.
    # The pattern shows STOP is handled separately from other buttons.
    assert re.search(
        r'if \(id === "r2-stop"\)',
        source,
    )


def _svg(text, svg_id):
    match = re.search(rf'<svg id="{svg_id}".*?</svg>', text, re.S)
    assert match, f"svg {svg_id} not found"
    return match.group(0)


def _state_nodes(svg):
    return {
        state
        for value in re.findall(r'class="state[^"]*" data-state="([^"]+)"', svg)
        for state in value.split()
    }


def test_debug_page_has_state_diagrams_for_three_parties():
    text = make_client().get("/debug").data.decode()

    assert 'id="state-diagrams"' in text
    assert text.index('id="state-diagrams"') < text.index('id="sequence-diagram"')
    assert _state_nodes(_svg(text, "sm-robot")) == {
        "awaiting_checkin",
        "polling_pf_ready",
        "waiting_r2_ready",
        "starting_r2",
        "waiting_r2_placed",
        "notifying_pf_placed",
        "error",
    }
    assert _state_nodes(_svg(text, "sm-r2")) == {
        "completed",
        "loading",
        "returning",
        "failed",
    }
    assert _state_nodes(_svg(text, "sm-pf")) == {
        "none",
        "initializing",
        "ready",
        "timeout",
        "retryable_error",
        "fatal_error",
    }


def test_r2_state_diagram_labels_transitions_with_under_mode():
    svg = _svg(make_client().get("/debug").data.decode(), "sm-r2")

    assert re.search(r'data-from="loading" data-to="returning".*?_m5', svg, re.S)
    assert re.search(r'data-from="returning" data-to="completed".*?_m1', svg, re.S)
    for element_id in ["sm-r2-connection", "sm-r2-under-mode", "sm-r2-failure"]:
        assert f'id="{element_id}"' in make_client().get("/debug").data.decode()


def test_robot_state_diagram_has_reset_and_resend_from_error():
    svg = _svg(make_client().get("/debug").data.decode(), "sm-robot")

    assert 'data-from="error" data-to="awaiting_checkin"' in svg
    assert 'data-from="error" data-to="starting_r2"' in svg
    assert 'data-from="notifying_pf_placed" data-to="awaiting_checkin"' in svg


def test_debug_js_renders_state_diagrams_from_both_streams():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert "function renderStateDiagram(" in source
    render = re.search(r"function render\(snapshot\) \{(.*?)\n\}", source, re.S).group(1)
    render_r2 = re.search(r"function renderR2\(snapshot\) \{(.*?)\n\}", source, re.S).group(1)
    assert "renderRobotStateDiagram(snapshot);" in render
    assert "renderPfStateDiagram(snapshot);" in render
    assert "renderR2StateDiagram(snapshot);" in render_r2
    for svg_id, name in [
        ("sm-robot", "renderRobotStateDiagram"),
        ("sm-pf", "renderPfStateDiagram"),
        ("sm-r2", "renderR2StateDiagram"),
    ]:
        body = re.search(rf"function {name}\(snapshot\) \{{(.*?)\n\}}", source, re.S).group(1)
        assert f'renderStateDiagram("{svg_id}"' in body


def test_debug_page_has_pf_manual_panel():
    resp = make_client().get("/debug")

    for element_id in [
        "pf-manual-panel",
        "pf-manual-status",
        "pf-manual-drink-placed",
        "pf-manual-confirm",
        "pf-manual-confirm-yes",
        "pf-manual-confirm-no",
        "pf-manual-result",
        "pf-manual-rows",
    ]:
        assert f'id="{element_id}"'.encode() in resp.data


def test_debug_js_sends_pf_requests_and_confirms_only_the_post():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert 'fetch("/api/debug/pf/" + action, { method: "POST" })' in source
    # GET goes straight out; POST waits for the in-page confirmation.
    assert re.search(
        r'"pf-manual-status"\)\.addEventListener\("click", \(\) => \{\s*sendPfManual\("status"\);',
        source,
    )
    assert re.search(
        r'"pf-manual-confirm-yes"\)\.addEventListener\("click", \(\) => \{\s*pfManualConfirm\.hidden = true;\s*sendPfManual\("drink-placed"\);',
        source,
    )
    assert source.count('sendPfManual("drink-placed")') == 1
    assert "サイクル実行中です" in source
