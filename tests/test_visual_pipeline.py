from collections import deque

import responses

from themis_video.pipeline import VisualConversationPipeline


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
