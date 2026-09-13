from .step_messages import STEP_MESSAGES


class ProgressAnnouncer:
    def __init__(self, speak):
        self._speak = speak
        self._last_step = None
        self._last_phase = None

    def handle_snapshot(self, snapshot):
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
