import os
import time

from flask import Flask, jsonify


def create_pf_mock_app():
    app = Flask(__name__)
    start_time = time.monotonic()

    @app.route("/api/v1/guide-robot/status", methods=["GET"])
    def guide_robot_status():
        force_failure = os.environ.get("PF_MOCK_FORCE_FAILURE", "")
        if force_failure == "422":
            return jsonify({"message": "forced validation error"}), 422
        if force_failure == "500":
            return jsonify({"message": "forced server error"}), 500

        initializing_seconds = float(os.environ.get("PF_MOCK_INITIALIZING_SECONDS", "0"))
        elapsed = time.monotonic() - start_time
        status = "Initializing" if elapsed < initializing_seconds else "Ready"
        return jsonify({"status": status}), 200

    @app.route("/api/v1/drink/placed", methods=["POST"])
    def drink_placed():
        accepted = os.environ.get("PF_MOCK_ACCEPTED", "true").lower() != "false"
        return jsonify({"accepted": accepted}), 200

    return app
