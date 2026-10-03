import threading

from flask import Flask

from . import config
from .clients.pf_client import PFClient
from .clients.r2_controller import R2Controller
from .clients.r2_link import R2Link
from .routes.checkin import checkin_bp
from .routes.entry import entry_bp
from .routes.events import events_bp
from .routes.ui import ui_bp
from .routes.voice_turns import voice_turns_bp
from .routes.external_start import external_start_bp
from .reservations import ReservationStore
from .sse import EventBroadcaster
from .state_machine import StateMachine, StateMachineRunner
from .voice_turns import VoiceTurnLog


def create_app(r2_controller=None, pf_client=None, reservation_store=None, start_r2=True):
    app = Flask(__name__)

    r2_link = None
    if r2_controller is None:
        r2_link = R2Link(
            config.R2_WS_URL,
            reconnect_delay=config.R2_WS_RECONNECT_DELAY_SECONDS,
            connect_timeout=config.R2_WS_CONNECT_TIMEOUT_SECONDS,
        )
        r2_controller = R2Controller(
            r2_link, start_reply_timeout=config.R2_START_REPLY_TIMEOUT_SECONDS
        )
    pf_client = pf_client or PFClient(
        base_url=config.PF_BASE_URL,
        timeout=config.HTTP_TIMEOUT_SECONDS,
        api_key=config.PF_API_KEY,
        proxy_url=config.PF_PROXY_URL,
    )

    reservation_store = reservation_store or ReservationStore.from_file(
        config.RESERVATIONS_FILE
    )

    broadcaster = EventBroadcaster()
    state_machine = StateMachine(
        r2_controller=r2_controller,
        pf_client=pf_client,
        on_change=broadcaster.publish,
        poll_interval=config.POLL_INTERVAL_SECONDS,
        entry_idle_seconds=config.ENTRY_IDLE_SECONDS,
    )
    runner = StateMachineRunner(state_machine)

    app.config["EVENT_BROADCASTER"] = broadcaster
    app.config["STATE_MACHINE"] = state_machine
    app.config["STATE_MACHINE_RUNNER"] = runner
    app.config["R2_CONTROLLER"] = r2_controller
    app.config["R2_LINK"] = r2_link
    app.config["RESERVATION_STORE"] = reservation_store
    app.config["VOICE_TURN_LOG"] = VoiceTurnLog()
    app.config["VISUAL_START_COOLDOWN_SECONDS"] = float(
        config.VISUAL_START_COOLDOWN_SECONDS
    )

    app.register_blueprint(checkin_bp)
    app.register_blueprint(entry_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(ui_bp)
    app.register_blueprint(external_start_bp)
    app.register_blueprint(voice_turns_bp)

    thread = threading.Thread(target=runner.run_forever, daemon=True)
    thread.start()

    if r2_link is not None and start_r2:
        r2_link.start()

    return app
