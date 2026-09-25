from flask import Blueprint, current_app, jsonify, request

checkin_bp = Blueprint("checkin", __name__)

_PUBLIC_FIELDS = (
    "reservation_id",
    "reservation_number",
    "guest_name",
    "guest_name_kana",
    "room_number",
    "plan",
    "check_in_date",
    "check_out_date",
    "nights",
    "guests",
    "status",
)


def _mask_phone(phone):
    """Keep only the head and tail so a kiosk screen never shows a full number."""
    if not phone:
        return None
    digits = [ch for ch in phone if ch.isdigit()]
    if len(digits) < 6:
        return "*" * len(digits)
    masked = digits[:3] + ["*"] * (len(digits) - 7) + digits[-4:]
    return "".join(masked)


def _public_reservation(record):
    payload = {field: record.get(field) for field in _PUBLIC_FIELDS}
    payload["phone_masked"] = _mask_phone(record.get("phone"))
    return payload


@checkin_bp.route("/api/reservations/search", methods=["POST"])
def search_reservations():
    store = current_app.config["RESERVATION_STORE"]
    body = request.get_json(silent=True) or {}
    query = (body.get("query") or "").strip()
    if not query:
        return jsonify({"message": "query is required"}), 422

    matches = store.search(query)
    return jsonify({"reservations": [_public_reservation(r) for r in matches]}), 200


@checkin_bp.route("/api/checkin", methods=["POST"])
def checkin():
    runner = current_app.config["STATE_MACHINE_RUNNER"]
    body = request.get_json(silent=True) or {}
    reservation_id = body.get("reservation_id")

    if reservation_id:
        return _checkin_by_reservation(runner, reservation_id)

    # Name-only check-in, kept for voice_ui and any client without a reservation.
    name = body.get("name")
    if not name:
        return jsonify({"message": "name or reservation_id is required"}), 422
    if not runner.request_checkin(name):
        return jsonify({"message": "a cycle is already in progress"}), 409
    return jsonify({"message": "checkin accepted"}), 200


def _checkin_by_reservation(runner, reservation_id):
    store = current_app.config["RESERVATION_STORE"]
    reservation = store.get(reservation_id)
    if reservation is None:
        return jsonify({"message": "reservation not found"}), 404

    if not runner.request_checkin(reservation["guest_name"]):
        return jsonify({"message": "a cycle is already in progress"}), 409

    return (
        jsonify(
            {
                "message": "checkin accepted",
                "reservation": _public_reservation(reservation),
            }
        ),
        200,
    )


@checkin_bp.route("/api/reset", methods=["POST"])
def reset():
    runner = current_app.config["STATE_MACHINE_RUNNER"]
    if not runner.request_reset():
        return jsonify({"message": "not in error state"}), 409
    return jsonify({"message": "reset accepted"}), 200
