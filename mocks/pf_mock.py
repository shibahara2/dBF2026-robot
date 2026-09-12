import os
import time

from flask import Flask, jsonify


def create_pf_mock_app():
    app = Flask(__name__)
    start_time = time.monotonic()

    @app.route("/api/v1/guide-robot/status", methods=["GET"])
    def guide_robot_status():
        initializing_seconds = float(os.environ.get("PF_MOCK_INITIALIZING_SECONDS", "0"))
        elapsed = time.monotonic() - start_time
        status = "Initializing" if elapsed < initializing_seconds else "Ready"
        return jsonify({"status": status}), 200

    @app.route("/api/v1/drink/placed", methods=["POST"])
    def drink_placed():
        accepted = os.environ.get("PF_MOCK_ACCEPTED", "true").lower() != "false"
        return jsonify({"accepted": accepted}), 200

    return app
