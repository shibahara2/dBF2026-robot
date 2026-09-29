import logging
from collections import deque

import pytest
import responses

from themis_video.pipeline import VisualConversationPipeline, VisualTriggerError


class FakeVLM:
    def __init__(self, decisions):
        self.decisions = deque(decisions)

    def analyze(self, image_bytes):
        return self.decisions.popleft()


@responses.activate
def test_pipeline_triggers_after_two_yes_decisions_in_three_frames():
    responses.add(
        responses.POST,
        "http://app/api/visual/start",
        json={"message": "start action accepted"},
        status=202,
    )
    pipeline = VisualConversationPipeline(
        FakeVLM([False, True, True]),
        "http://app/api/visual/start",
        window_size=3,
        yes_threshold=2,
        cooldown_seconds=60,
    )

    assert pipeline.process(b"f1") is False
    assert pipeline.process(b"f2") is False
    assert pipeline.process(b"f3") is True
    assert len(responses.calls) == 1


@responses.activate
def test_pipeline_does_not_trigger_repeated_yes_during_cooldown():
    responses.add(
        responses.POST,
        "http://app/api/visual/start",
        json={"message": "start action accepted"},
        status=202,
    )
    pipeline = VisualConversationPipeline(
        FakeVLM([True, True, True, True]),
        "http://app/api/visual/start",
        window_size=3,
        yes_threshold=2,
        cooldown_seconds=60,
    )

    assert pipeline.process(b"f1") is False
    assert pipeline.process(b"f2") is True
    assert pipeline.process(b"f3") is False
    assert pipeline.process(b"f4") is False
    assert len(responses.calls) == 1


@responses.activate
def test_continuous_yes_does_not_reopen_search_after_cooldown():
    responses.add(
        responses.POST,
        "http://app/api/visual/start",
        json={"message": "start action accepted"},
        status=202,
    )
    current_time = [0.0]
    pipeline = VisualConversationPipeline(
        FakeVLM([True] * 5),
        "http://app/api/visual/start",
        window_size=3,
        yes_threshold=2,
        cooldown_seconds=5,
        clock=lambda: current_time[0],
    )

    assert pipeline.process(b"f1") is False
    assert pipeline.process(b"f2") is True
    current_time[0] = 6.0
    assert [pipeline.process(b"frame") for _ in range(3)] == [False] * 3
    assert len(responses.calls) == 1


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


@pytest.mark.parametrize("status", [409, 429])
@responses.activate
def test_not_accepted_start_is_not_an_error_and_waits_for_cooldown(status, caplog):
    responses.add(
        responses.POST, "http://app/api/visual/start", json={"message": "busy"}, status=status
    )
    clock = FakeClock()
    pipeline = VisualConversationPipeline(
        FakeVLM([True] * 4),
        "http://app/api/visual/start",
        window_size=1,
        yes_threshold=1,
        cooldown_seconds=5,
        clock=clock,
    )

    with caplog.at_level(logging.INFO, logger="themis_video.pipeline"):
        assert pipeline.process(b"f1") is False
    assert len(responses.calls) == 1
    assert str(status) in caplog.text

    clock.value = 4.9
    assert pipeline.process(b"f2") is False
    assert len(responses.calls) == 1

    clock.value = 5.0
    assert pipeline.process(b"f3") is False
    assert len(responses.calls) == 2


@responses.activate
def test_server_error_still_raises():
    responses.add(responses.POST, "http://app/api/visual/start", status=500)
    pipeline = VisualConversationPipeline(
        FakeVLM([True]), "http://app/api/visual/start", window_size=1, yes_threshold=1
    )

    with pytest.raises(VisualTriggerError):
        pipeline.process(b"f1")
