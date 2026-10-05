import queue
import threading
from datetime import datetime, timezone
import time

from .clients.r2_controller import STATUS_COMPLETED, STATUS_FAILED, STATUS_LOADING

PHASE_WAITING = "waiting"
PHASE_ACTIVE = "active"
PHASE_ERROR = "error"

STEP_AWAITING_CHECKIN = "awaiting_checkin"
STEP_POLLING_PF_READY = "polling_pf_ready"
STEP_WAITING_R2_READY = "waiting_r2_ready"
STEP_STARTING_R2 = "starting_r2"
STEP_WAITING_R2_PLACED = "waiting_r2_placed"
STEP_NOTIFYING_PF_PLACED = "notifying_pf_placed"
# Steps before anything is sent to R2; a reset may abandon the cycle here.
CANCELLABLE_STEPS = (STEP_POLLING_PF_READY, STEP_WAITING_R2_READY)

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


def _r2_ready_or_failed(snap):
    if snap["status"] == STATUS_FAILED:
        return True
    return (
        snap["connection"] == "connected"
        and snap["status"] == STATUS_COMPLETED
        and not snap["starting"]
    )


def _r2_placed_or_failed(snap):
    # completed counts too: _m5 and _m1 can both land before we wake up.
    return snap["status"] != STATUS_LOADING


def _r2_failure_text(snap):
    return snap.get("failure_message") or snap.get("failure") or "不明"


_STEP0_FIELDS = {
    "phase": PHASE_WAITING,
    "step": STEP_AWAITING_CHECKIN,
    "guest_name": None,
    "error_message": None,
    "entry_source": None,
    "entry_stage": None,
    "entry_at": None,
    "entry_touched": None,
}


def default_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StateMachine:
    def __init__(
        self,
        r2_controller,
        pf_client,
        on_change,
        sleep=time.sleep,
        poll_interval=2.0,
        now=default_now,
        sequence_wait=1.0,
        monotonic=time.monotonic,
        entry_idle_seconds=DEFAULT_ENTRY_IDLE_SECONDS,
    ):
        self._r2 = r2_controller
        self._pf = pf_client
        self._on_change = on_change
        self._sleep = sleep
        self._poll_interval = poll_interval
        self._sequence_wait = sequence_wait
        self._now = now
        self._monotonic = monotonic
        self._entry_idle_seconds = entry_idle_seconds

        self._lock = threading.Lock()
        self._phase = PHASE_WAITING
        self._step = STEP_AWAITING_CHECKIN
        self._guest_name = None
        self._error_message = None
        self._pf_status = None
        self._pf_status_at = None
        self._entry_source = None
        self._entry_stage = None
        self._entry_at = None
        self._entry_touched = None
        # Bumped by every check-in and reset; a cycle stops once it is stale.
        self._cycle = 0

    def snapshot(self):
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self):
        return {
            "phase": self._phase,
            "step": self._step,
            "guest_name": self._guest_name,
            "error_message": self._error_message,
            "pf_status": self._pf_status,
            "pf_status_at": self._pf_status_at,
            "entry_source": self._entry_source,
            "entry_stage": self._entry_stage,
            "entry_at": self._entry_at,
        }

    def _update(self, **fields):
        with self._lock:
            self._apply_locked(fields)

    def _apply_locked(self, fields):
        for key, value in fields.items():
            setattr(self, f"_{key}", value)
        self._on_change(self._snapshot_locked())

    def _is_current(self, cycle):
        with self._lock:
            return self._cycle == cycle

    def _update_if_current(self, cycle, **fields):
        """Apply fields unless a reset has abandoned this cycle."""
        with self._lock:
            if self._cycle != cycle:
                return False
            self._apply_locked(fields)
        return True

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
            self._cycle += 1
            self._phase = PHASE_WAITING
            self._step = STEP_POLLING_PF_READY
            self._guest_name = guest_name
            self._error_message = None
            self._set_entry_locked(source, ENTRY_STAGE_CHECKIN)
            snap = self._snapshot_locked()
            self._on_change(snap)
        return True

    def try_reset(self):
        """Clear an error, or abandon a cycle that has not started R2 yet."""
        with self._lock:
            if self._phase == PHASE_ERROR:
                abandoning = False
            elif self._phase == PHASE_WAITING and self._step in CANCELLABLE_STEPS:
                abandoning = True
            else:
                return False
            self._cycle += 1
            self._apply_locked(_STEP0_FIELDS)
        if abandoning:
            # The cycle may be blocked waiting for R2; let it see it is stale.
            self._r2.wake()
        return True

    def can_resume_after_start(self):
        with self._lock:
            return self._phase == PHASE_ERROR and self._step == STEP_STARTING_R2

    def try_resume_after_start(self):
        """Clear a failed start once the operator's resend has started R2."""
        with self._lock:
            if not (self._phase == PHASE_ERROR and self._step == STEP_STARTING_R2):
                return False
            self._phase = PHASE_WAITING
            self._error_message = None
            self._on_change(self._snapshot_locked())
        return True

    def resume_after_start(self):
        self._run_after_start()

    def _to_waiting_step0(self):
        self._update(**_STEP0_FIELDS)

    def _fail(self, message):
        self._update(phase=PHASE_ERROR, error_message=message)

    def fail_unexpected(self, message):
        """Public entry point used by the runner's last-resort exception guard."""
        self._fail(message)

    def run_started_cycle(self):
        with self._lock:
            cycle = self._cycle
            if not (self._phase == PHASE_WAITING and self._step == STEP_POLLING_PF_READY):
                return  # reset before this queued cycle got to run
        self._wait_before_step()
        if not self._poll_pf_ready(cycle):
            return
        if not self._update_if_current(cycle, step=STEP_WAITING_R2_READY):
            return
        self._wait_before_step()
        if not self._wait_r2_ready(cycle):
            return
        # Leaving CANCELLABLE_STEPS here: from now on a reset is refused, so
        # nothing can abandon the cycle between this check and the start.
        if not self._update_if_current(cycle, step=STEP_STARTING_R2):
            return
        self._wait_before_step()
        if not self._start_r2():
            return
        self._run_after_start()

    def _run_after_start(self):
        self._update(phase=PHASE_ACTIVE, step=STEP_WAITING_R2_PLACED)
        self._wait_before_step()
        if not self._wait_r2_placed():
            return
        self._update(step=STEP_NOTIFYING_PF_PLACED)
        self._wait_before_step()
        if not self._notify_pf_placed():
            return
        self._to_waiting_step0()

    def _wait_before_step(self):
        self._sleep(self._sequence_wait)

    def _poll_pf_ready(self, cycle):
        while True:
            if not self._is_current(cycle):
                return False
            outcome = self._pf.get_guide_robot_status()
            if not self._update_if_current(cycle, pf_status=outcome, pf_status_at=self._now()):
                return False
            if outcome == "ready":
                return True
            if outcome in ("initializing", "timeout", "retryable_error"):
                self._sleep(self._poll_interval)
                continue
            self._update_if_current(
                cycle,
                phase=PHASE_ERROR,
                error_message=f"AI管制PFの状態確認に失敗しました: {outcome}",
            )
            return False

    def _wait_r2_ready(self, cycle):
        snap = self._r2.wait_until(
            lambda snap: not self._is_current(cycle) or _r2_ready_or_failed(snap)
        )
        if not self._is_current(cycle):
            return False
        if snap["status"] == STATUS_FAILED:
            self._update_if_current(
                cycle,
                phase=PHASE_ERROR,
                error_message=f"R2が failed です: {_r2_failure_text(snap)}",
            )
            return False
        return True

    def _start_r2(self):
        reason = self._r2.start_load_drink()
        if reason:
            self._fail(f"R2の開始に失敗しました: {reason}")
            return False
        return True

    def _wait_r2_placed(self):
        snap = self._r2.wait_until(_r2_placed_or_failed)
        if snap["status"] == STATUS_FAILED:
            self._fail(f"R2の動作が止まりました: {_r2_failure_text(snap)}")
            return False
        return True

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

    def can_resume_after_start(self):
        return self._state_machine.can_resume_after_start()

    def request_resume_after_start(self):
        resumed = self._state_machine.try_resume_after_start()
        if resumed:
            self._start_signal.put(self._state_machine.resume_after_start)
        return resumed

    def run_forever(self):
        while True:
            work = self._start_signal.get()
            try:
                work()
            except Exception:
                self._state_machine.fail_unexpected(
                    "内部エラーが発生しました。ログを確認してください。"
                )
