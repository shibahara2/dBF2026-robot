from flask import Blueprint, current_app, jsonify

from ..state_machine import PHASE_WAITING, STEP_AWAITING_CHECKIN
from ..visual_trigger import VisualStartGate


visual_bp = Blueprint("visual", __name__)


@visual_bp.route("/api/visual/start", methods=["POST"])
def visual_start():
    state = current_app.config["STATE_MACHINE"].snapshot()
    if not (
        state["phase"] == PHASE_WAITING
        and state["step"] == STEP_AWAITING_CHECKIN
    ):
        return jsonify({"message": "a cycle is already in progress"}), 409

    gate = current_app.config.setdefault("VISUAL_START_GATE", VisualStartGate())
    cooldown = current_app.config.get("VISUAL_START_COOLDOWN_SECONDS", 5.0)
    if not gate.accept(cooldown):
        return jsonify({"message": "visual start is rate limited"}), 429

    current_app.config["EVENT_BROADCASTER"].publish(
        {"type": "ui_action", "action": "start_checkin"}
    )
    return jsonify({"message": "start action accepted"}), 202
