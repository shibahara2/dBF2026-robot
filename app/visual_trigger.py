import threading
import time


class VisualStartGate:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._last_accepted = None
        self._lock = threading.Lock()

    def accept(self, cooldown_seconds):
        now = self._clock()
        with self._lock:
            if (
                self._last_accepted is not None
                and now - self._last_accepted < cooldown_seconds
            ):
                return False
            self._last_accepted = now
            return True
