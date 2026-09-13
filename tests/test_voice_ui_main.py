import pytest

from voice_ui.main import (
    MicSilenceExceeded,
    _run_checkin_loop_body,
    run_progress_loop,
)


class _StopLoop(BaseException):
    """Escapes run_progress_loop's `while True` purely for test control flow.

    Deliberately a BaseException (not Exception) subclass so it is not
    swallowed by run_progress_loop's `except Exception` reconnect handler.
    """


class _FakeSpeaker:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def _gen(events, error=None):
    for event in events:
        yield event
    if error:
        raise error


def test_run_progress_loop_reconnects_on_error_with_exponential_backoff():
    scripts = [
        _gen([], error=ConnectionError("initial disconnect")),
        _gen(
            [{"phase": "waiting", "step": "awaiting_checkin"}],
            error=ConnectionError("later disconnect"),
        ),
    ]
    call_count = {"n": 0}

    def factory():
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(scripts):
            return scripts[idx]
        raise _StopLoop()

    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)

    speaker = _FakeSpeaker()

    with pytest.raises(_StopLoop):
        run_progress_loop(
            speaker,
            event_iterator_factory=factory,
            sleep_func=fake_sleep,
            initial_backoff=1.0,
            max_backoff=30.0,
        )

    # Both reconnect attempts happen at the initial backoff, because the
    # second attempt received a successfully-handled event before its
    # stream broke, which resets the backoff back to the initial value.
    assert sleeps == [1.0, 1.0]
    assert call_count["n"] == 3


def test_run_progress_loop_backoff_doubles_up_to_cap_when_no_events_succeed():
    call_count = {"n": 0}

    def factory():
        call_count["n"] += 1
        if call_count["n"] > 5:
            raise _StopLoop()
        return _gen([], error=ConnectionError("still down"))

    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)

    speaker = _FakeSpeaker()

    with pytest.raises(_StopLoop):
        run_progress_loop(
            speaker,
            event_iterator_factory=factory,
            sleep_func=fake_sleep,
            initial_backoff=1.0,
            max_backoff=4.0,
        )

    assert sleeps == [1.0, 2.0, 4.0, 4.0, 4.0]


def test_run_progress_loop_speaks_handled_snapshots():
    def factory():
        return _gen(
            [{"phase": "active", "step": "polling_r2_active"}],
            error=_StopLoop(),
        )

    speaker = _FakeSpeaker()

    with pytest.raises(_StopLoop):
        run_progress_loop(
            speaker,
            event_iterator_factory=factory,
            sleep_func=lambda seconds: None,
        )

    assert speaker.spoken  # STEP_MESSAGES lookup produced at least one utterance


def test_checkin_loop_body_raises_after_threshold_consecutive_no_utterance():
    outcomes = ["no_utterance"] * 30

    with pytest.raises(MicSilenceExceeded):
        _run_checkin_loop_body(iter(outcomes), no_utterance_exit_threshold=30)


def test_checkin_loop_body_resets_streak_on_other_outcomes():
    outcomes = ["no_utterance"] * 29 + ["checked_in"] + ["no_utterance"] * 29

    # 29 no_utterance, then a success resets the streak, then 29 more
    # no_utterance - never reaches 30 in a row, so it should not raise.
    _run_checkin_loop_body(iter(outcomes), no_utterance_exit_threshold=30)


def test_checkin_loop_body_does_not_raise_below_threshold():
    outcomes = ["no_utterance"] * 29

    _run_checkin_loop_body(iter(outcomes), no_utterance_exit_threshold=30)
