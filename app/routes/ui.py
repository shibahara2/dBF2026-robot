from flask import Blueprint, render_template

from .. import config

ui_bp = Blueprint("ui", __name__)


@ui_bp.route("/")
def index():
    return render_template("index.html")


@ui_bp.route("/debug")
def debug():
    return render_template(
        "debug.html",
        r2_base_url=config.R2_BASE_URL,
        pf_base_url=config.PF_BASE_URL,
    )
