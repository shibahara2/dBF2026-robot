STEP_MESSAGES = {
    "polling_pf_ready": "AI管制PF(案内ロボット)の状態を確認しています",
    "polling_r2_ready": "ドリンク準備ロボットの状態を確認しています",
    "sending_load_drink": "ドリンクをセットしています",
    "polling_r2_active": "ドリンクを積み込み中です",
    "notifying_pf_placed": "積み込み完了をAI管制PFに通知しています",
}

VOICE_START_GUIDANCE = "画面にお名前、予約番号、または電話番号を入力してください"

# Every fixed phrase voice_ui can speak; synthesized once at startup so the
# kiosk never waits on VOICEVOX for them.
PRELOAD_TEXTS = [*STEP_MESSAGES.values(), VOICE_START_GUIDANCE]
