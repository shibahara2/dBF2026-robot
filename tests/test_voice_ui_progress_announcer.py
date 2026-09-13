from voice_ui.progress_announcer import ProgressAnnouncer


def test_speaks_message_when_step_changes():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot({"phase": "waiting", "step": "polling_pf_ready"})

    assert spoken == ["AI管制PF(案内ロボット)の状態を確認しています"]


def test_does_not_repeat_message_for_same_step():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot({"phase": "waiting", "step": "polling_pf_ready"})
    announcer.handle_snapshot({"phase": "waiting", "step": "polling_pf_ready"})

    assert spoken == ["AI管制PF(案内ロボット)の状態を確認しています"]


def test_silent_for_awaiting_checkin_step():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot({"phase": "waiting", "step": "awaiting_checkin"})

    assert spoken == []


def test_speaks_error_message_once_on_entering_error_phase():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    snapshot = {
        "phase": "error",
        "step": "polling_r2_ready",
        "error_message": "R2の状態確認に失敗しました",
    }
    announcer.handle_snapshot(snapshot)
    announcer.handle_snapshot(snapshot)

    assert spoken == ["R2の状態確認に失敗しました"]


def test_speaks_fallback_text_when_error_message_missing():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot(
        {"phase": "error", "step": "polling_r2_ready", "error_message": None}
    )

    assert spoken == ["エラーが発生しました"]


def test_returning_to_waiting_after_error_allows_next_step_message():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot(
        {"phase": "error", "step": "polling_r2_ready", "error_message": "失敗"}
    )
    announcer.handle_snapshot({"phase": "waiting", "step": "awaiting_checkin"})
    announcer.handle_snapshot({"phase": "waiting", "step": "polling_pf_ready"})

    assert spoken == ["失敗", "AI管制PF(案内ロボット)の状態を確認しています"]
