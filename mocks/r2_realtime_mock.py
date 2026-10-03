"""Mimic R2's gamepad-server ``/realtime`` for local development.

Only what UI-DRP relies on is reproduced: a play_navigation5 reply and a
robot_aggregator stream whose under_mode goes _m1 -> _m3 -> _m5 -> _m3 -> _m1.
"""

import asyncio
import json
import os

import msgpack

START_REPLIES = ("success", "fail", "none")
_SEQUENCE = ("mock_m3", "mock_m5", "mock_m3", "mock_m1")


class R2RealtimeMock:
    def __init__(self, step_seconds=3.0, start_reply="success", aggregator_interval=0.5):
        if start_reply not in START_REPLIES:
            raise ValueError(f"start_reply must be one of {START_REPLIES}")
        self.step_seconds = step_seconds
        self.start_reply = start_reply
        self.aggregator_interval = aggregator_interval
        self.received = []
        self.under_mode = "mock_m1"
        self._sequence = None

    @classmethod
    def from_env(cls):
        return cls(
            step_seconds=float(os.environ.get("R2_MOCK_STEP_SECONDS", "3")),
            start_reply=os.environ.get("R2_MOCK_START_REPLY", "success"),
        )

    async def handle(self, websocket):
        sender = asyncio.create_task(self._send_aggregator(websocket))
        try:
            async for raw in websocket:
                if not isinstance(raw, str):
                    continue
                message = json.loads(raw)
                self.received.append(message)
                if message.get("type") == "play_navigation5":
                    await self._on_play(websocket, bool(message["data"]["value"]))
        finally:
            sender.cancel()

    async def _on_play(self, websocket, value):
        if not value:
            if self._sequence is not None:
                self._sequence.cancel()
                self._sequence = None
            await self._send(websocket, "play_navigation5_rp", {"success": True})
            return
        if self.start_reply == "none":
            return
        success = self.start_reply == "success"
        await self._send(websocket, "play_navigation5_rp", {"success": success})
        if success:
            self._sequence = asyncio.create_task(self._run_sequence())

    async def _run_sequence(self):
        for under_mode in _SEQUENCE:
            await asyncio.sleep(self.step_seconds)
            self.under_mode = under_mode

    async def _send_aggregator(self, websocket):
        while True:
            await self._send(
                websocket,
                "robot_aggregator",
                {"under_mode": {"data": {"data": self.under_mode}}},
            )
            await asyncio.sleep(self.aggregator_interval)

    @staticmethod
    async def _send(websocket, kind, data):
        await websocket.send(msgpack.packb({"type": kind, "data": data}))
