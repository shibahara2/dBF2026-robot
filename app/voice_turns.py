"""In-memory log of recent voice turns for the debug page."""

import threading
from collections import deque

from .state_machine import default_now

VOICE_TURN_OUTCOMES = (
    "rejected_low_confidence",
    "self_echo",
    "keyword_start",
    "checkin",
    "chat",
    "ignore",
    "no_keyword",
)


class VoiceTurnLog:
    def __init__(self, max_turns=20, now=default_now):
        self._turns = deque(maxlen=max_turns)
        self._now = now
        self._lock = threading.Lock()

    def add(self, turn):
        record = {**turn, "at": self._now()}
        with self._lock:
            self._turns.append(record)
        return record

    def recent(self):
        with self._lock:
            return list(reversed(self._turns))
