from flask import Blueprint, current_app, jsonify, request

from ..state_machine import KIOSK_ENTRY_STAGES

entry_bp = Blueprint("entry", __name__)


@entry_bp.route("/api/entry", methods=["POST"])
def report_entry():
    """Kiosk reports of steps the server cannot observe (debug view only)."""
    stage = (request.get_json(silent=True) or {}).get("stage")
    if stage not in KIOSK_ENTRY_STAGES:
        return jsonify({"message": "stage must be start or select"}), 422

    state_machine = current_app.config["STATE_MACHINE"]
    if not state_machine.record_kiosk_stage(stage):
        return jsonify({"message": "a cycle is already in progress"}), 409
    return jsonify({"message": "entry recorded"}), 202


@entry_bp.route("/api/entry", methods=["DELETE"])
def clear_entry():
    state_machine = current_app.config["STATE_MACHINE"]
    return jsonify({"cleared": state_machine.clear_entry()}), 200
