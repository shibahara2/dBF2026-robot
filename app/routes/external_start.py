from flask import Blueprint, current_app, jsonify

from ..state_machine import ENTRY_VISUAL, ENTRY_VOICE
from ..visual_trigger import VisualStartGate


external_start_bp = Blueprint("external_start", __name__)


@external_start_bp.route("/api/visual/start", methods=["POST"])
def visual_start():
    return _external_start(ENTRY_VISUAL)


@external_start_bp.route("/api/voice/start", methods=["POST"])
def voice_start():
    return _external_start(ENTRY_VOICE)


def _external_start(source):
    """Open the kiosk search screen for a visual/voice start.

    Both entries only stand in for the kiosk's start button, so they share
    this handler and differ only in the recorded source.
    """
    state_machine = current_app.config["STATE_MACHINE"]
    if not state_machine.external_start_available():
        return jsonify({"message": "check-in start is not available"}), 409

    gates = current_app.config.setdefault("EXTERNAL_START_GATES", {})
    gate = gates.setdefault(source, VisualStartGate())
    cooldown = current_app.config.get("VISUAL_START_COOLDOWN_SECONDS", 5.0)
    if not gate.accept(cooldown):
        return jsonify({"message": "start is rate limited"}), 429

    if not state_machine.start_external_entry(source):
        return jsonify({"message": "check-in start is not available"}), 409

    current_app.config["EVENT_BROADCASTER"].publish(
        {"type": "ui_action", "action": "start_checkin"}
    )
    return jsonify({"message": "start action accepted"}), 202
