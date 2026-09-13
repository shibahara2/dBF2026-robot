import re
from pathlib import Path

from voice_ui.step_messages import STEP_MESSAGES
from app.state_machine import (
    STEP_POLLING_PF_READY,
    STEP_POLLING_R2_READY,
    STEP_SENDING_LOAD_DRINK,
    STEP_POLLING_R2_ACTIVE,
    STEP_NOTIFYING_PF_PLACED,
)


def test_step_messages_covers_all_non_form_steps():
    expected_keys = {
        STEP_POLLING_PF_READY,
        STEP_POLLING_R2_READY,
        STEP_SENDING_LOAD_DRINK,
        STEP_POLLING_R2_ACTIVE,
        STEP_NOTIFYING_PF_PLACED,
    }
    assert set(STEP_MESSAGES.keys()) == expected_keys


def test_step_messages_matches_app_js_source_of_truth():
    app_js_path = Path(__file__).resolve().parent.parent / "app" / "static" / "app.js"
    app_js_text = app_js_path.read_text(encoding="utf-8")

    match = re.search(r"STEP_MESSAGES\s*=\s*\{(.*?)\};", app_js_text, re.DOTALL)
    assert match, "STEP_MESSAGES object not found in app.js"

    pairs = re.findall(r'(\w+):\s*"([^"]+)"', match.group(1))
    app_js_messages = dict(pairs)

    assert app_js_messages == STEP_MESSAGES
