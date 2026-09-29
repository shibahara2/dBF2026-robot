from .step_messages import STEP_MESSAGES, VOICE_START_GUIDANCE

_VOICE_START = ("voice", "start")


class ProgressAnnouncer:
    def __init__(self, speak):
        self._speak = speak
        self._last_step = None
        self._last_phase = None
        self._last_entry = None

    def handle_snapshot(self, snapshot):
        # Typed events (e.g. ui_action) are not state snapshots.
        if "type" in snapshot:
            return

        entry = (snapshot.get("entry_source"), snapshot.get("entry_stage"))
        if entry == _VOICE_START and self._last_entry != _VOICE_START:
            self._speak(VOICE_START_GUIDANCE)
        self._last_entry = entry

        phase = snapshot.get("phase")
        step = snapshot.get("step")

        if phase == "error":
            if self._last_phase != "error":
                self._speak(snapshot.get("error_message") or "エラーが発生しました")
            self._last_phase = phase
            self._last_step = step
            return

        if step != self._last_step:
            message = STEP_MESSAGES.get(step)
            if message:
                self._speak(message)

        self._last_phase = phase
        self._last_step = step
