"""Drive R2's drink-loading sequence the way the vendor's UI-DRP does.

What is sent to R2 and how R2's messages are read mirror UI-DRP
(~/Linux/DRP-src/dist). R2 itself has no notion of these statuses; they are
built here from our own commands and changes of ``under_mode``.
"""

import logging
import threading
import time

from .r2_link import STATE_CONNECTED, default_now

logger = logging.getLogger(__name__)

STATUS_COMPLETED = "completed"
STATUS_LOADING = "loading"
STATUS_RETURNING = "returning"
STATUS_FAILED = "failed"

FAILURE_START_NO_REPLY = "start_no_reply"
FAILURE_START_REJECTED = "start_rejected"
FAILURE_START_DISCONNECTED = "start_disconnected"
FAILURE_DISCONNECTED = "disconnected"
FAILURE_STOPPED = "stopped"
FAILURE_MANUAL = "manual"
START_FAILURES = (FAILURE_START_NO_REPLY, FAILURE_START_REJECTED, FAILURE_START_DISCONNECTED)

FAILURE_MESSAGES = {
    FAILURE_START_NO_REPLY: "R2から開始の返事がありませんでした",
    FAILURE_START_REJECTED: "R2が開始を受け付けませんでした (success:false)",
    FAILURE_START_DISCONNECTED: "開始の返事を待つあいだにR2との接続が切れました",
    FAILURE_DISCONNECTED: "動作中にR2との接続が切れました",
    FAILURE_STOPPED: "オペレーターがSTOPしました",
    FAILURE_MANUAL: "オペレーターがfailedにしました",
}

# UI-DRP waits 2s between the gamepad combo and play_navigation5.
NAV_WAIT_SECONDS = 2.0
_NO_BUTTONS = [0] * 16
_BACK_START_BUTTONS = [0] * 8 + [1, 1] + [0] * 6  # BK + ST
_AXIS = [0] * 6
COMBO_NAVIGATION = [0, 0, 1, 0, 0]
COMBO_STAND = [1, 0, 0, 0, 0]
COMBO_NONE = [0, 0, 0, 0, 0]
LEAVE_NAV_REPEAT = 4

_MARK_FROM = {
    STATUS_RETURNING: (STATUS_LOADING,),
    STATUS_COMPLETED: (STATUS_RETURNING,),
    STATUS_FAILED: (STATUS_LOADING, STATUS_RETURNING),
}


def gamepad_message(buttons, combo):
    return {
        "type": "gamepad",
        "data": {"button": list(buttons), "axis": list(_AXIS), "combo": list(combo)},
    }


def play_navigation5_message(value):
    return {"type": "play_navigation5", "data": {"value": value}}


def under_mode_number(value):
    """UI-DRP's ``value.split("_m")[1]``; None where JavaScript gives undefined."""
    parts = value.split("_m")
    return parts[1] if len(parts) > 1 else None


def _under_mode_value(data):
    try:
        value = data["under_mode"]["data"]["data"]
    except (KeyError, TypeError):
        return None
    return value if isinstance(value, str) else None


class R2Controller:
    def __init__(self, link, *, start_reply_timeout=15.0, sleep=time.sleep, now=default_now):
        self._link = link
        self._start_reply_timeout = start_reply_timeout
        self._sleep = sleep
        self._now = now
        self._cond = threading.Condition()
        self._listeners = []

        self._connection = link.state()[0]
        self._status = STATUS_COMPLETED
        self._status_at = None
        self._failure = None
        self._starting = False
        self._stopping = False
        self._abort_start = False
        self._awaiting_reply = False
        self._reply = None
        self._reply_sent_at = None
        self._under_mode = None
        self._under_mode_at = None
        self._last_reply = None
        self._last_reply_at = None
        self._last_reply_seconds = None

        link.on_message = self._on_message
        link.on_state_change = self._on_link_state

    # --- reading ---------------------------------------------------------

    def snapshot(self):
        with self._cond:
            return self._snapshot_locked()

    def _snapshot_locked(self):
        connection, connection_at = self._link.state()
        return {
            "url": self._link.url,
            "connection": connection,
            "connection_at": connection_at,
            "status": self._status,
            "status_at": self._status_at,
            "failure": self._failure,
            "failure_message": FAILURE_MESSAGES.get(self._failure),
            "starting": self._starting,
            "under_mode": self._under_mode,
            "under_mode_at": self._under_mode_at,
            "last_reply": self._last_reply,
            "last_reply_at": self._last_reply_at,
            "last_reply_seconds": self._last_reply_seconds,
        }

    def wait_until(self, predicate):
        with self._cond:
            while True:
                snap = self._snapshot_locked()
                if predicate(snap):
                    return snap
                self._cond.wait()

    def add_listener(self, listener):
        self._listeners.append(listener)

    def _publish(self):
        snap = self.snapshot()
        for listener in list(self._listeners):
            try:
                listener(snap)
            except Exception:
                logger.exception("R2 listener failed")

    def _set_status_locked(self, status, failure=None):
        self._status = status
        self._failure = failure if status == STATUS_FAILED else None
        self._status_at = self._now()
        logger.info("R2 status -> %s%s", status, f" ({failure})" if failure else "")
        self._cond.notify_all()

    # --- what R2 sends ------------------------------------------------------

    def _on_link_state(self, state):
        with self._cond:
            self._connection = state
            if state != STATE_CONNECTED and self._status in (STATUS_LOADING, STATUS_RETURNING):
                self._set_status_locked(STATUS_FAILED, FAILURE_DISCONNECTED)
            self._cond.notify_all()
        self._publish()

    def _on_message(self, message):
        kind = message.get("type")
        if kind == "robot_aggregator":
            self._on_aggregator(message.get("data"))
        elif kind == "play_navigation5_rp":
            self._on_reply(message.get("data"))

    def _on_aggregator(self, data):
        under_mode = _under_mode_value(data)
        if not under_mode:
            return
        with self._cond:
            previous = self._under_mode
            if under_mode == previous:
                return
            self._under_mode = under_mode
            self._under_mode_at = self._now()
            logger.info("R2 under_mode: %s -> %s", previous, under_mode)
            number = under_mode_number(under_mode)
            previous_number = under_mode_number(previous) if previous else None
            if previous_number is None:
                previous_number = ""  # UI-DRP: ?? ""
            if number == "5" and previous_number != "5" and self._status == STATUS_LOADING:
                self._set_status_locked(STATUS_RETURNING)
            elif number == "1" and previous_number != "1" and self._status == STATUS_RETURNING:
                self._set_status_locked(STATUS_COMPLETED)
            self._cond.notify_all()
        self._publish()

    def _on_reply(self, data):
        with self._cond:
            self._last_reply = data
            self._last_reply_at = self._now()
            if self._awaiting_reply:
                self._last_reply_seconds = round(time.monotonic() - self._reply_sent_at, 3)
                self._reply = data if data is not None else {}
                self._awaiting_reply = False
            else:
                logger.info("R2 play_navigation5_rp outside a start: %s", data)
            self._cond.notify_all()
        self._publish()

    # --- starting -----------------------------------------------------------

    def start_load_drink(self):
        with self._cond:
            reason = self._start_refusal_locked()
            if reason:
                return reason
            self._starting = True
            self._abort_start = False
            self._cond.notify_all()
        self._publish()
        try:
            return self._run_start()
        finally:
            with self._cond:
                self._starting = False
                self._awaiting_reply = False
                self._cond.notify_all()
            self._publish()

    def _start_refusal_locked(self):
        if self._starting:
            return "開始の処理中です"
        if self._connection != STATE_CONNECTED:
            return "R2に接続していません"
        if self._status != STATUS_COMPLETED:
            return f"R2が待機中ではありません（status={self._status}）"
        return None

    def _run_start(self):
        if not self._link.send_json(gamepad_message(_NO_BUTTONS, COMBO_NAVIGATION)):
            return self._fail_start(FAILURE_START_DISCONNECTED)
        self._sleep(NAV_WAIT_SECONDS)
        with self._cond:
            if self._abort_start:
                return FAILURE_MESSAGES[FAILURE_STOPPED]
            self._reply = None
            self._awaiting_reply = True
            self._reply_sent_at = time.monotonic()
        if not self._link.send_json(play_navigation5_message(True)):
            return self._fail_start(FAILURE_START_DISCONNECTED)

        deadline = time.monotonic() + self._start_reply_timeout
        with self._cond:
            while (
                self._reply is None
                and not self._abort_start
                and self._connection == STATE_CONNECTED
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            reply = self._reply
            aborted = self._abort_start
            connected = self._connection == STATE_CONNECTED

        if aborted:
            return FAILURE_MESSAGES[FAILURE_STOPPED]
        if reply is None:
            return self._fail_start(
                FAILURE_START_NO_REPLY if connected else FAILURE_START_DISCONNECTED
            )
        if isinstance(reply, dict) and reply.get("success") is True:
            return_value = None
            with self._cond:
                # Guard: only transition to LOADING if conditions still hold
                if self._status == STATUS_COMPLETED and not self._abort_start and self._connection == STATE_CONNECTED:
                    self._set_status_locked(STATUS_LOADING)
                else:
                    # Conditions changed - handle as failure
                    if self._abort_start:
                        return_value = FAILURE_MESSAGES[FAILURE_STOPPED]
                    elif self._connection != STATE_CONNECTED:
                        if self._status == STATUS_COMPLETED:
                            self._set_status_locked(STATUS_FAILED, FAILURE_START_DISCONNECTED)
                        return_value = FAILURE_MESSAGES[FAILURE_START_DISCONNECTED]
                    else:
                        # Status is not COMPLETED (shouldn't happen but be safe)
                        return_value = FAILURE_MESSAGES[self._failure] if self._failure else "R2が待機中ではありません"
            self._publish()
            return return_value
        return self._fail_start(FAILURE_START_REJECTED)

    def _fail_start(self, failure):
        with self._cond:
            # A STOP while starting has already failed this cycle.
            if self._status == STATUS_COMPLETED:
                self._set_status_locked(STATUS_FAILED, failure)
            message = FAILURE_MESSAGES[self._failure or failure]
        self._publish()
        return message

    def resend_start(self):
        with self._cond:
            if self._status != STATUS_FAILED or self._failure not in START_FAILURES:
                return "開始の失敗で failed になっているときだけ再送できます"
            if under_mode_number(self._under_mode or "") != "1":
                return "under_mode が _m1（A にいる）のときだけ再送できます"
            if self._connection != STATE_CONNECTED:
                return "R2に接続していません"
            if self._starting:
                return "開始の処理中です"
            self._set_status_locked(STATUS_COMPLETED)
        self._publish()
        return self.start_load_drink()

    # --- operator actions ---------------------------------------------------

    def stop(self):
        with self._cond:
            if self._connection != STATE_CONNECTED:
                return "R2に接続していません"
            if self._stopping:
                return "STOP の処理中です"
            self._stopping = True
            self._abort_start = True
            self._set_status_locked(STATUS_FAILED, FAILURE_STOPPED)
        self._publish()
        try:
            for _ in range(LEAVE_NAV_REPEAT):
                if not self._link.send_json(gamepad_message(_BACK_START_BUTTONS, COMBO_STAND)):
                    return "STOP の送信中にR2との接続が切れました"
            if not self._link.send_json(gamepad_message(_NO_BUTTONS, COMBO_NONE)):
                return "STOP の送信中にR2との接続が切れました"
            self._sleep(NAV_WAIT_SECONDS)
            if not self._link.send_json(play_navigation5_message(False)):
                return "STOP の送信中にR2との接続が切れました"
            return None
        finally:
            with self._cond:
                self._stopping = False
                self._cond.notify_all()
            self._publish()

    def mark(self, status):
        allowed = _MARK_FROM.get(status)
        if allowed is None:
            return f"手動では {status} にできません"
        with self._cond:
            if self._status not in allowed:
                return f"{status} にできるのは status が {' / '.join(allowed)} のときだけです"
            self._set_status_locked(status, FAILURE_MANUAL if status == STATUS_FAILED else None)
        self._publish()
        return None

    def reset(self):
        with self._cond:
            if self._status != STATUS_FAILED:
                return "R2 を初期状態に戻せるのは failed のときだけです"
            self._set_status_locked(STATUS_COMPLETED)
        self._publish()
        return None

    def connect(self):
        self._link.connect()
        return None

    def disconnect(self):
        self._link.disconnect()
        return None
