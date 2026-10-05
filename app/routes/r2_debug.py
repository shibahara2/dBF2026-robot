"""Operator controls for R2 on the debug page."""

from flask import Blueprint, current_app, jsonify, request

r2_debug_bp = Blueprint("r2_debug", __name__)


def _controller():
    return current_app.config["R2_CONTROLLER"]


def _respond(reason):
    if reason:
        return jsonify({"message": reason}), 409
    return jsonify(_controller().snapshot()), 200


@r2_debug_bp.route("/api/debug/r2", methods=["GET"])
def r2_state():
    return jsonify(_controller().snapshot())


@r2_debug_bp.route("/api/debug/r2/connect", methods=["POST"])
def r2_connect():
    return _respond(_controller().connect())


@r2_debug_bp.route("/api/debug/r2/disconnect", methods=["POST"])
def r2_disconnect():
    return _respond(_controller().disconnect())


@r2_debug_bp.route("/api/debug/r2/stop", methods=["POST"])
def r2_stop():
    return _respond(_controller().stop())


@r2_debug_bp.route("/api/debug/r2/reset", methods=["POST"])
def r2_reset():
    return _respond(_controller().reset())


@r2_debug_bp.route("/api/debug/r2/mark", methods=["POST"])
def r2_mark():
    status = (request.get_json(silent=True) or {}).get("status")
    if not status:
        return jsonify({"message": "status is required"}), 422
    return _respond(_controller().mark(status))


@r2_debug_bp.route("/api/debug/r2/resend", methods=["POST"])
def r2_resend():
    runner = current_app.config["STATE_MACHINE_RUNNER"]
    # Never move R2 unless a stopped cycle is there to pick it up.
    if not runner.can_resume_after_start():
        return jsonify(
            {"message": "ステートマシンが R2 の開始の失敗で止まっているときだけ再送できます"}
        ), 409
    reason = _controller().resend_start()
    if reason:
        return jsonify({"message": reason}), 409
    runner.request_resume_after_start()
    return jsonify(_controller().snapshot()), 200
