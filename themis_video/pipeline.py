"""Connect received frames, VLM decisions, and the visual UI trigger."""

from __future__ import annotations

import logging
import time
from collections import deque

import requests


logger = logging.getLogger(__name__)
_NOT_ACCEPTED = (409, 429)


class VisualTriggerError(RuntimeError):
    pass


class VisualConversationPipeline:
    def __init__(
        self,
        vlm,
        trigger_url: str,
        *,
        window_size: int = 3,
        yes_threshold: int = 2,
        cooldown_seconds: float = 5.0,
        timeout: float = 5.0,
        clock=time.monotonic,
        session: requests.Session | None = None,
    ) -> None:
        if not trigger_url:
            raise ValueError("trigger_url must not be empty")
        if window_size <= 0 or not 0 < yes_threshold <= window_size:
            raise ValueError("yes_threshold must be within window_size")
        if cooldown_seconds < 0 or timeout <= 0:
            raise ValueError("cooldown_seconds or timeout is invalid")
        self.vlm = vlm
        self.trigger_url = trigger_url
        self.window = deque(maxlen=window_size)
        self.yes_threshold = yes_threshold
        self.cooldown_seconds = cooldown_seconds
        self.timeout = timeout
        self.clock = clock
        self.session = session or requests.Session()
        self._last_triggered = None
        self._armed = True

    def process(self, image_bytes: bytes) -> bool:
        decision = self.vlm.analyze(image_bytes)
        self.window.append(decision)
        if sum(self.window) < self.yes_threshold:
            self._armed = True
            return False
        if not self._armed:
            return False

        now = self.clock()
        if (
            self._last_triggered is not None
            and now - self._last_triggered < self.cooldown_seconds
        ):
            return False

        try:
            response = self.session.post(self.trigger_url, json={}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise VisualTriggerError("visual start trigger failed") from exc
        if response.status_code in _NOT_ACCEPTED:
            # Expected while a cycle runs or someone is using the kiosk: stay
            # armed but wait out the cooldown instead of posting every frame.
            logger.info("visual start not accepted: HTTP %d", response.status_code)
            self._last_triggered = now
            return False
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise VisualTriggerError("visual start trigger failed") from exc
        self._last_triggered = now
        self._armed = False
        return True
