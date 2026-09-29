from voice_ui.progress_announcer import ProgressAnnouncer


def test_step_progress_is_not_spoken():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    for step in [
        "awaiting_checkin",
        "polling_pf_ready",
        "polling_r2_ready",
        "sending_load_drink",
        "polling_r2_active",
        "notifying_pf_placed",
    ]:
        announcer.handle_snapshot({"phase": "waiting", "step": step})

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


def test_next_error_after_recovery_is_spoken_again():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot(
        {"phase": "error", "step": "polling_r2_ready", "error_message": "失敗1"}
    )
    announcer.handle_snapshot({"phase": "waiting", "step": "awaiting_checkin"})
    announcer.handle_snapshot({"phase": "waiting", "step": "polling_pf_ready"})
    announcer.handle_snapshot(
        {"phase": "error", "step": "polling_pf_ready", "error_message": "失敗2"}
    )

    assert spoken == ["失敗1", "失敗2"]


GUIDANCE = "画面にお名前、予約番号、または電話番号を入力してください"


def _waiting(entry_source=None, entry_stage=None):
    return {
        "phase": "waiting",
        "step": "awaiting_checkin",
        "entry_source": entry_source,
        "entry_stage": entry_stage,
    }


def test_speaks_guidance_when_voice_start_is_recorded():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot(_waiting())
    announcer.handle_snapshot(_waiting("voice", "start"))
    announcer.handle_snapshot(_waiting("voice", "start"))

    assert spoken == [GUIDANCE]


def test_no_guidance_for_other_entries():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot(_waiting("visual", "start"))
    announcer.handle_snapshot(_waiting("screen", "start"))
    announcer.handle_snapshot(_waiting("voice", "select"))

    assert spoken == []


def test_ui_action_events_do_not_reset_error_memory():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)
    error = {"phase": "error", "step": "polling_pf_ready", "error_message": "失敗"}

    announcer.handle_snapshot(error)
    announcer.handle_snapshot({"type": "ui_action", "action": "start_checkin"})
    announcer.handle_snapshot(error)

    assert spoken == ["失敗"]
