import threading

from flask import Flask

from . import config
from .clients.pf_client import PFClient
from .clients.r2_client import R2Client
from .routes.checkin import checkin_bp
from .routes.events import events_bp
from .routes.ui import ui_bp
from .sse import EventBroadcaster
from .state_machine import StateMachine, StateMachineRunner


def create_app(r2_client=None, pf_client=None):
    app = Flask(__name__)

    r2_client = r2_client or R2Client(
        base_url=config.R2_BASE_URL,
        timeout=config.HTTP_TIMEOUT_SECONDS,
        drink_type=config.DRINK_TYPE,
        target_robot_id=config.TARGET_ROBOT_ID,
    )
    pf_client = pf_client or PFClient(
        base_url=config.PF_BASE_URL,
        timeout=config.HTTP_TIMEOUT_SECONDS,
        api_key=config.PF_API_KEY,
        proxy_url=config.PF_PROXY_URL,
    )

    broadcaster = EventBroadcaster()
    state_machine = StateMachine(
        r2_client=r2_client,
        pf_client=pf_client,
        on_change=broadcaster.publish,
        poll_interval=config.POLL_INTERVAL_SECONDS,
    )
    runner = StateMachineRunner(state_machine)

    app.config["EVENT_BROADCASTER"] = broadcaster
    app.config["STATE_MACHINE"] = state_machine
    app.config["STATE_MACHINE_RUNNER"] = runner

    app.register_blueprint(checkin_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(ui_bp)

    thread = threading.Thread(target=runner.run_forever, daemon=True)
    thread.start()

    return app
