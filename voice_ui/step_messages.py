VOICE_START_GUIDANCE = "画面にお名前、予約番号、または電話番号を入力してください"
BUSY_MESSAGE = "ただいま他のお客様をご案内しています。少々お待ちください"

# Every fixed phrase voice_ui can speak; synthesized once at startup so the
# kiosk never waits on VOICEVOX for them.
PRELOAD_TEXTS = [VOICE_START_GUIDANCE, BUSY_MESSAGE]
