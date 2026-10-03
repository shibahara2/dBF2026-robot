import queue
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

# How a check-in was initiated and how far it got (see
# docs/superpowers/specs/2026-09-29-checkin-entry-design.md).
ENTRY_SCREEN = "screen"
ENTRY_VISUAL = "visual"
ENTRY_VOICE = "voice"
EXTERNAL_ENTRY_SOURCES = (ENTRY_VISUAL, ENTRY_VOICE)

ENTRY_STAGE_START = "start"
ENTRY_STAGE_SELECT = "select"
ENTRY_STAGE_CHECKIN = "checkin"
KIOSK_ENTRY_STAGES = (ENTRY_STAGE_START, ENTRY_STAGE_SELECT)

DEFAULT_ENTRY_IDLE_SECONDS = 60.0

SKIP_PENDING = "pending"
SKIP_RESUME = "resume"


def default_request_id():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def default_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StateMachine:
    def __init__(
        self,
        r2_client,
        pf_client,
        on_change,
        sleep=time.sleep,
        poll_interval=2.0,
        request_id_factory=default_request_id,
        now=default_now,
        sequence_wait=1.0,
        monotonic=time.monotonic,
        entry_idle_seconds=DEFAULT_ENTRY_IDLE_SECONDS,
    ):
        self._r2 = r2_client
        self._pf = pf_client
        self._on_change = on_change
        self._sleep = sleep
        self._poll_interval = poll_interval
        self._sequence_wait = sequence_wait
        self._request_id_factory = request_id_factory
        self._now = now
        self._monotonic = monotonic
        self._entry_idle_seconds = entry_idle_seconds

        self._lock = threading.Lock()
        self._phase = PHASE_WAITING
        self._step = STEP_AWAITING_CHECKIN
        self._guest_name = None
        self._request_id = None
        self._error_message = None
        self._pf_status = None
        self._pf_status_at = None
        self._r2_status = None
        self._r2_status_at = None
        self._entry_source = None
        self._entry_stage = None
        self._entry_at = None
        self._entry_touched = None
        self._load_drink_skipped = False

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
            "pf_status": self._pf_status,
            "pf_status_at": self._pf_status_at,
            "r2_status": self._r2_status,
            "r2_status_at": self._r2_status_at,
            "entry_source": self._entry_source,
            "entry_stage": self._entry_stage,
            "entry_at": self._entry_at,
        }

    def _record_pf_status(self, status):
        self._update(pf_status=status, pf_status_at=self._now())

    def _record_r2_status(self, status):
        self._update(r2_status=status, r2_status_at=self._now())

    def _update(self, **fields):
        with self._lock:
            for key, value in fields.items():
                setattr(self, f"_{key}", value)
            snap = self._snapshot_locked()
            self._on_change(snap)

    def _awaiting_checkin_locked(self):
        return self._phase == PHASE_WAITING and self._step == STEP_AWAITING_CHECKIN

    def _entry_in_progress_locked(self):
        return self._entry_stage in KIOSK_ENTRY_STAGES

    def _kiosk_source_locked(self):
        if self._entry_in_progress_locked():
            return self._entry_source
        return ENTRY_SCREEN

    def _set_entry_locked(self, source, stage):
        self._entry_source = source
        self._entry_stage = stage
        self._entry_at = self._now()
        self._entry_touched = self._monotonic()

    def _external_start_available_locked(self):
        if not self._awaiting_checkin_locked():
            return False
        if not self._entry_in_progress_locked():
            return True
        # An abandoned kiosk must not block visual/voice starts forever.
        return self._monotonic() - self._entry_touched >= self._entry_idle_seconds

    def external_start_available(self):
        with self._lock:
            return self._external_start_available_locked()

    def start_external_entry(self, source):
        """Record a visual/voice start unless someone is using the kiosk."""
        if source not in EXTERNAL_ENTRY_SOURCES:
            raise ValueError(f"unknown external entry source: {source!r}")
        with self._lock:
            if not self._external_start_available_locked():
                return False
            self._set_entry_locked(source, ENTRY_STAGE_START)
            self._on_change(self._snapshot_locked())
        return True

    def record_kiosk_stage(self, stage):
        """Record a kiosk stage, keeping the source of an entry in progress."""
        if stage not in KIOSK_ENTRY_STAGES:
            raise ValueError(f"unknown kiosk entry stage: {stage!r}")
        with self._lock:
            if not self._awaiting_checkin_locked():
                return False
            self._set_entry_locked(self._kiosk_source_locked(), stage)
            self._on_change(self._snapshot_locked())
        return True

    def clear_entry(self):
        """Forget the entry when the kiosk goes back to its start screen."""
        with self._lock:
            if not (self._awaiting_checkin_locked() and self._entry_source is not None):
                return False
            self._entry_source = None
            self._entry_stage = None
            self._entry_at = None
            self._entry_touched = None
            self._on_change(self._snapshot_locked())
        return True

    def try_start(self, guest_name):
        with self._lock:
            if not self._awaiting_checkin_locked():
                return False
            source = self._kiosk_source_locked()
            self._phase = PHASE_WAITING
            self._step = STEP_POLLING_PF_READY
            self._guest_name = guest_name
            self._request_id = None
            self._error_message = None
            self._load_drink_skipped = False
            self._set_entry_locked(source, ENTRY_STAGE_CHECKIN)
            snap = self._snapshot_locked()
            self._on_change(snap)
        return True

    def try_reset(self):
        with self._lock:
            if self._phase != PHASE_ERROR:
                return False
        self._to_waiting_step0()
        return True

    def try_skip_load_drink(self):
        """Let an operator move past POST load-drink without R2 accepting it.

        Returns SKIP_PENDING when the send loop is still retrying (it stops at
        its next attempt), SKIP_RESUME when load-drink already failed and the
        cycle must be resumed by the runner, or None when not at that step.
        """
        with self._lock:
            if self._step != STEP_SENDING_LOAD_DRINK:
                return None
            self._load_drink_skipped = True
            if self._phase != PHASE_ERROR:
                return SKIP_PENDING
            self._phase = PHASE_WAITING
            self._error_message = None
            self._on_change(self._snapshot_locked())
            return SKIP_RESUME

    def _to_waiting_step0(self):
        self._update(
            phase=PHASE_WAITING,
            step=STEP_AWAITING_CHECKIN,
            guest_name=None,
            request_id=None,
            error_message=None,
            entry_source=None,
            entry_stage=None,
            entry_at=None,
            entry_touched=None,
        )

    def _fail(self, message):
        self._update(phase=PHASE_ERROR, error_message=message)

    def fail_unexpected(self, message):
        """Public entry point used by the runner's last-resort exception guard."""
        self._fail(message)

    def run_started_cycle(self):
        self._wait_before_step()
        if not self._poll_pf_ready():
            return
        self._update(step=STEP_POLLING_R2_READY)
        self._wait_before_step()
        if not self._poll_r2_ready():
            return
        request_id = self._request_id_factory()
        self._update(step=STEP_SENDING_LOAD_DRINK, request_id=request_id)
        self._wait_before_step()
        if not self._send_load_drink(request_id):
            return
        self._run_after_load_drink(request_id)

    def resume_after_load_drink(self):
        """Continue a cycle whose load-drink was skipped after it had failed."""
        self._run_after_load_drink(self.snapshot()["request_id"])

    def _run_after_load_drink(self, request_id):
        self._update(phase=PHASE_ACTIVE, step=STEP_POLLING_R2_ACTIVE)
        self._wait_before_step()
        if not self._poll_r2_active(request_id):
            return
        self._update(step=STEP_NOTIFYING_PF_PLACED)
        self._wait_before_step()
        if not self._notify_pf_placed():
            return
        self._to_waiting_step0()

    def _wait_before_step(self):
        self._sleep(self._sequence_wait)

    def _poll_pf_ready(self):
        while True:
            outcome = self._pf.get_guide_robot_status()
            self._record_pf_status(outcome)
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
            self._record_r2_status(outcome)
            if outcome == "completed":
                return True
            if outcome in ("loading", "returning", "timeout"):
                self._sleep(self._poll_interval)
                continue
            self._fail(f"R2の状態確認に失敗しました: {outcome}")
            return False

    def _send_load_drink(self, request_id):
        while True:
            if self._load_drink_skipped:
                return True
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
            self._record_r2_status(outcome)
            # R2 never saw our request_id when load-drink was skipped.
            if (
                not self._load_drink_skipped
                and response_request_id is not None
                and response_request_id != request_id
            ):
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


class StateMachineRunner:
    def __init__(self, state_machine):
        self._state_machine = state_machine
        self._start_signal = queue.Queue()

    def request_checkin(self, name):
        started = self._state_machine.try_start(name)
        if started:
            self._start_signal.put(self._state_machine.run_started_cycle)
        return started

    def request_reset(self):
        return self._state_machine.try_reset()

    def request_skip_load_drink(self):
        outcome = self._state_machine.try_skip_load_drink()
        if outcome == SKIP_RESUME:
            self._start_signal.put(self._state_machine.resume_after_load_drink)
        return outcome is not None

    def run_forever(self):
        while True:
            work = self._start_signal.get()
            try:
                work()
            except Exception:
                self._state_machine.fail_unexpected(
                    "内部エラーが発生しました。ログを確認してください。"
                )
