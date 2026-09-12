import threading
from datetime import datetime, timezone
import time

PHASE_WAITING = "waiting"
PHASE_ACTIVE = "active"
PHASE_ERROR = "error"

STEP_AWAITING_CHECKIN = "awaiting_checkin"
STEP_POLLING_PF_READY = "polling_pf_ready"
STEP_POLLING_R2_READY = "polling_r2_ready"
STEP_SENDING_LOAD_DRINK = "sending_load_drink"
STEP_POLLING_R2_ACTIVE = "polling_r2_active"
STEP_NOTIFYING_PF_PLACED = "notifying_pf_placed"


def default_request_id():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class StateMachine:
    def __init__(
        self,
        r2_client,
        pf_client,
        on_change,
        sleep=time.sleep,
        poll_interval=2.0,
        request_id_factory=default_request_id,
    ):
        self._r2 = r2_client
        self._pf = pf_client
        self._on_change = on_change
        self._sleep = sleep
        self._poll_interval = poll_interval
        self._request_id_factory = request_id_factory

        self._lock = threading.Lock()
        self._phase = PHASE_WAITING
        self._step = STEP_AWAITING_CHECKIN
        self._guest_name = None
        self._request_id = None
        self._error_message = None

    def snapshot(self):
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self):
        return {
            "phase": self._phase,
            "step": self._step,
            "guest_name": self._guest_name,
            "request_id": self._request_id,
            "error_message": self._error_message,
        }

    def _update(self, **fields):
        with self._lock:
            for key, value in fields.items():
                setattr(self, f"_{key}", value)
            snap = self._snapshot_locked()
        self._on_change(snap)

    def try_start(self, guest_name):
        with self._lock:
            if not (self._phase == PHASE_WAITING and self._step == STEP_AWAITING_CHECKIN):
                return False
            self._phase = PHASE_WAITING
            self._step = STEP_POLLING_PF_READY
            self._guest_name = guest_name
            self._request_id = None
            self._error_message = None
            snap = self._snapshot_locked()
        self._on_change(snap)
        return True

    def try_reset(self):
        with self._lock:
            if self._phase != PHASE_ERROR:
                return False
        self._to_waiting_step0()
        return True

    def _to_waiting_step0(self):
        self._update(
            phase=PHASE_WAITING,
            step=STEP_AWAITING_CHECKIN,
            guest_name=None,
            request_id=None,
            error_message=None,
        )

    def _fail(self, message):
        self._update(phase=PHASE_ERROR, error_message=message)

    def run_started_cycle(self):
        if not self._poll_pf_ready():
            return
        self._update(step=STEP_POLLING_R2_READY)
        if not self._poll_r2_ready():
            return
        request_id = self._request_id_factory()
        self._update(step=STEP_SENDING_LOAD_DRINK, request_id=request_id)
        if not self._send_load_drink(request_id):
            return
        self._update(phase=PHASE_ACTIVE, step=STEP_POLLING_R2_ACTIVE)
        if not self._poll_r2_active(request_id):
            return
        self._update(step=STEP_NOTIFYING_PF_PLACED)
        if not self._notify_pf_placed():
            return
        self._to_waiting_step0()

    def _poll_pf_ready(self):
        while True:
            outcome = self._pf.get_guide_robot_status()
            if outcome == "ready":
                return True
            if outcome in ("initializing", "timeout", "retryable_error"):
                self._sleep(self._poll_interval)
                continue
            self._fail(f"AI管制PFの状態確認に失敗しました: {outcome}")
            return False

    def _poll_r2_ready(self):
        while True:
            result = self._r2.get_status()
            outcome = result["outcome"]
            if outcome == "completed":
                return True
            if outcome in ("loading", "returning", "timeout"):
                self._sleep(self._poll_interval)
                continue
            self._fail(f"R2の状態確認に失敗しました: {outcome}")
            return False

    def _send_load_drink(self, request_id):
        while True:
            outcome = self._r2.post_load_drink(request_id)
            if outcome == "accepted":
                return True
            if outcome == "timeout":
                self._sleep(self._poll_interval)
                continue
            self._fail(f"R2へのload-drink送信に失敗しました: {outcome}")
            return False

    def _poll_r2_active(self, request_id):
        while True:
            result = self._r2.get_status()
            outcome = result["outcome"]
            response_request_id = result["request_id"]
            if response_request_id is not None and response_request_id != request_id:
                self._fail("R2から返ったrequest_idが一致しません")
                return False
            if outcome in ("returning", "completed"):
                return True
            if outcome in ("loading", "timeout"):
                self._sleep(self._poll_interval)
                continue
            self._fail(f"R2の状態確認に失敗しました: {outcome}")
            return False

    def _notify_pf_placed(self):
        if self._pf.post_drink_placed():
            return True
        self._fail("AI管制PFがdrink/placedを受理しませんでした")
        return False
