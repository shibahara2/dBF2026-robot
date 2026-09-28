"""Minimal HTTP VLM mock for end-to-end local testing."""

from __future__ import annotations

import argparse
import base64
import binascii
import os

from flask import Flask, jsonify, request


def create_app(decision: bool | None = None):
    app = Flask(__name__)
    configured_decision = (
        decision
        if decision is not None
        else os.environ.get("VLM_MOCK_DECISION", "false").lower() == "true"
    )

    @app.post("/analyze")
    def analyze():
        body = request.get_json(silent=True) or {}
        encoded = body.get("image_base64")
        if not isinstance(encoded, str) or not encoded:
            return jsonify({"message": "image_base64 is required"}), 422
        try:
            image = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            return jsonify({"message": "image_base64 is invalid"}), 422
        if not (
            image.startswith(b"\x89PNG\r\n\x1a\n")
            or image.startswith(b"\xff\xd8\xff")
        ):
            return jsonify({"message": "PNG or JPEG image is required"}), 422
        return jsonify({"speaking_to_themis": configured_decision})

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5103)
    args = parser.parse_args()
    create_app().run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
