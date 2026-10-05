"""Manual AI管制PF requests from the debug page.

Each call sends exactly one request to PF and returns what came back. It
does not touch the state machine.
"""

from flask import Blueprint, current_app, jsonify

pf_debug_bp = Blueprint("pf_debug", __name__)


def _pf():
    return current_app.config["PF_CLIENT"]


@pf_debug_bp.route("/api/debug/pf/status", methods=["POST"])
def pf_status():
    return jsonify(_pf().raw_get_status())


@pf_debug_bp.route("/api/debug/pf/drink-placed", methods=["POST"])
def pf_drink_placed():
    return jsonify(_pf().raw_post_drink_placed())
