import re
from pathlib import Path

APP_JS = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text()


def _function_body(name):
    match = re.search(rf"function {name}\([^)]*\) {{(.*?)\n}}", APP_JS, re.S)
    assert match, f"function {name} not found"
    return match.group(1)


def test_report_helpers_ignore_failures():
    assert 'fetch("/api/entry", {' in _function_body("reportEntry")
    assert ".catch(() => {})" in _function_body("reportEntry")
    assert 'fetch("/api/entry", { method: "DELETE" }).catch(() => {})' in _function_body(
        "clearEntry"
    )


def test_report_body_sends_only_stage():
    assert "JSON.stringify({ stage: stage })" in _function_body("reportEntry")


def test_start_button_reports_start():
    assert re.search(
        r'startButton\.addEventListener\("click", \(\) => \{\s*showStage\("search"\);\s*reportEntry\("start"\);',
        APP_JS,
    )


def test_selecting_reservation_reports_select():
    assert 'reportEntry("select");' in _function_body("selectReservation")


def test_back_buttons_report_or_clear():
    assert re.search(r"resetFlow\(\);\s*clearEntry\(\);", APP_JS)
    assert re.search(
        r'showStage\(button\.dataset\.target\);\s*reportEntry\("start"\);', APP_JS
    )


def test_start_checkin_action_only_leaves_the_start_screen():
    # A visual/voice start must not pull a guest who is already searching or
    # selecting back to the search screen (their selection would be lost).
    assert re.search(
        r'payload\.action === "start_checkin"\) \{(?:\s*//[^\n]*)*\s*if \(!stages\.start\.hidden\) \{\s*showStage\("search"\);\s*\}\s*return;',
        APP_JS,
    )
