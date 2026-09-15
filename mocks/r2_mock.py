import os
import threading
import time

from flask import Flask, jsonify, request


def create_r2_mock_app():
    app = Flask(__name__)
    lock = threading.Lock()
    state = {"request_id": "none", "status": "completed", "phase_started_at": None}

    def loading_seconds():
        return float(os.environ.get("R2_MOCK_LOADING_SECONDS", "3"))

    def returning_seconds():
        return float(os.environ.get("R2_MOCK_RETURNING_SECONDS", "3"))

    def force_failure():
        return os.environ.get("R2_MOCK_FORCE_FAILURE", "")

    def current_status_locked():
        if force_failure() == "failed" and state["status"] in ("loading", "returning"):
            state["status"] = "failed"
            return "failed"
        if state["status"] not in ("loading", "returning"):
            return state["status"]

        elapsed = time.monotonic() - state["phase_started_at"]
        if state["status"] == "loading" and elapsed >= loading_seconds():
            state["status"] = "returning"
            state["phase_started_at"] = time.monotonic()
            return "returning"
        if state["status"] == "returning" and elapsed >= returning_seconds():
            state["status"] = "completed"
            state["phase_started_at"] = None
            return "completed"
        return state["status"]

    @app.route("/v1/commands/load-drink", methods=["POST"])
    def load_drink():
        body = request.get_json(silent=True) or {}
        request_id = body.get("request_id")
        drink_type = body.get("drink_type")
        target_robot_id = body.get("target_robot_id")
        if not request_id or not drink_type or not target_robot_id:
            return jsonify({"message": "request_id, drink_type, target_robot_id are required"}), 422

        if force_failure() == "422":
            return jsonify({"message": "forced validation error"}), 422
        if force_failure() == "500":
            return jsonify({"message": "forced server error"}), 500

        with lock:
            if request_id == state["request_id"]:
                return jsonify({}), 200
            if current_status_locked() != "completed":
                return jsonify({"message": "a command is already in progress"}), 500
            state["request_id"] = request_id
            state["status"] = "loading"
            state["phase_started_at"] = time.monotonic()
        return jsonify({}), 200

    @app.route("/v1/commands/load-drink/status", methods=["GET"])
    def load_drink_status():
        with lock:
            status = current_status_locked()
            return jsonify({"request_id": state["request_id"], "status": status}), 200

    return app
