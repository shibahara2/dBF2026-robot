"""Flask app exposing POST /analyze with the same contract as mocks.vlm_mock."""

from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from .backend import BackendError, OpenAICompatibleBackend
from .image import InvalidImageError, prepare_image
from .settings import load_server_settings


logger = logging.getLogger(__name__)


def create_app(backend, *, api_key: str | None = None, max_image_side: int = 640):
    app = Flask(__name__)

    @app.before_request
    def check_api_key():
        if api_key is None or request.path == "/health":
            return None
        expected = f"Bearer {api_key}"
        given = request.headers.get("Authorization", "")
        if not hmac.compare_digest(given.encode(), expected.encode()):
            return jsonify({"message": "unauthorized"}), 401
        return None

    @app.post("/analyze")
    def analyze():
        body = request.get_json(silent=True) or {}
        encoded = body.get("image_base64")
        if not isinstance(encoded, str) or not encoded:
            return jsonify({"message": "image_base64 is required"}), 422
        try:
            image = base64.b64decode(encoded, validate=True)
            jpeg = prepare_image(image, max_side=max_image_side)
        except (ValueError, binascii.Error) as exc:
            return jsonify({"message": str(exc) or "image_base64 is invalid"}), 422

        started = time.monotonic()
        try:
            answer = backend.ask(jpeg)
        except BackendError as exc:
            logger.warning("VLM backend error: %s", exc)
            return jsonify({"message": "VLM backend failed"}), 502
        latency_ms = round((time.monotonic() - started) * 1000)
        logger.info("VLM answer=%s latency_ms=%d", answer, latency_ms)
        return jsonify(
            {
                "speaking_to_themis": answer == "yes",
                "answer": answer,
                "latency_ms": latency_ms,
            }
        )

    @app.get("/health")
    def health():
        if backend.healthy():
            return jsonify({"status": "ok"})
        return jsonify({"status": "backend_unavailable"}), 503

    return app


def main():
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--backend-url")
    args = parser.parse_args()
    values = dict(os.environ)
    if args.backend_url is not None:
        values["VLM_BACKEND_URL"] = args.backend_url
    try:
        settings = load_server_settings(values)
    except ValueError as exc:
        parser.error(str(exc))
    backend = OpenAICompatibleBackend(
        settings.backend_url,
        settings.backend_model,
        api_key=settings.backend_api_key,
        timeout=settings.backend_timeout_seconds,
    )
    app = create_app(
        backend, api_key=settings.api_key, max_image_side=settings.max_image_side
    )
    app.run(host=args.host or settings.host, port=args.port or settings.port)


if __name__ == "__main__":
    main()
