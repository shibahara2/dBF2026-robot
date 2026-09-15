from flask import Blueprint, current_app, jsonify, request

checkin_bp = Blueprint("checkin", __name__)


@checkin_bp.route("/api/checkin", methods=["POST"])
def checkin():
    runner = current_app.config["STATE_MACHINE_RUNNER"]
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    if not name:
        return jsonify({"message": "name is required"}), 422

    if not runner.request_checkin(name):
        return jsonify({"message": "a cycle is already in progress"}), 409
    return jsonify({"message": "checkin accepted"}), 200


@checkin_bp.route("/api/reset", methods=["POST"])
def reset():
    runner = current_app.config["STATE_MACHINE_RUNNER"]
    if not runner.request_reset():
        return jsonify({"message": "not in error state"}), 409
    return jsonify({"message": "reset accepted"}), 200
