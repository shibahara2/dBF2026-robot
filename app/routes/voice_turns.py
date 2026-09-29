from flask import Blueprint, current_app, jsonify, request

from ..voice_turns import VOICE_TURN_OUTCOMES

voice_turns_bp = Blueprint("voice_turns", __name__)

_NUMBER_FIELDS = ("no_speech_prob", "avg_logprob", "stt_ms", "llm_ms")


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@voice_turns_bp.route("/api/voice/turns", methods=["POST"])
def add_turn():
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    outcome = body.get("outcome")
    reply = body.get("reply", "")
    if not isinstance(text, str) or outcome not in VOICE_TURN_OUTCOMES:
        return jsonify({"message": "text and a known outcome are required"}), 422
    if reply is None:
        reply = ""
    if not isinstance(reply, str):
        return jsonify({"message": "reply must be a string"}), 422
    turn = {"text": text, "outcome": outcome, "reply": reply}
    for field in _NUMBER_FIELDS:
        value = body.get(field)
        if value is not None and not _is_number(value):
            return jsonify({"message": f"{field} must be a number"}), 422
        turn[field] = value

    record = current_app.config["VOICE_TURN_LOG"].add(turn)
    current_app.config["EVENT_BROADCASTER"].publish({"type": "voice_turn", **record})
    return jsonify({"message": "turn recorded"}), 202


@voice_turns_bp.route("/api/voice/turns", methods=["GET"])
def list_turns():
    return jsonify({"turns": current_app.config["VOICE_TURN_LOG"].recent()}), 200
