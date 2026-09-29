import logging

import numpy as np

from voice_ui.dialogue import Decision
from voice_ui.pipeline import run_turn_once
from voice_ui.step_messages import BUSY_MESSAGE

KEYWORDS = ["チェックイン"]


class _FakeMicSource:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read_chunk(self, timeout=None):
        if not self._chunks:
            return None
        return self._chunks.pop(0)


class _FakeVadSegmenter:
    def __init__(self, utterance_after, utterance="UTTERANCE"):
        self._utterance_after = utterance_after
        self._utterance = utterance
        self._count = 0

    def feed(self, chunk):
        self._count += 1
        if self._count >= self._utterance_after:
            return self._utterance
        return None


class _FakeTranscriber:
    def __init__(self, result):
        self._result = result

    def transcribe(self, utterance):
        return self._result


class _FakeStartClient:
    def __init__(self, result="accepted"):
        self.calls = 0
        self._result = result

    def start(self):
        self.calls += 1
        return self._result


class _FakeSpeaker:
    def __init__(self, busy=False):
        self.spoken = []
        self.echo_checks = []
        self._busy = busy

    def speak(self, text):
        self.spoken.append(text)

    def was_speaking_during(self, seconds):
        self.echo_checks.append(seconds)
        return self._busy


class _FakeReporter:
    def __init__(self):
        self.turns = []

    def report(self, turn):
        self.turns.append(turn)
        return True


class _FakeAgent:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []
        self.resets = 0

    def respond(self, text):
        self.calls.append(text)
        return self.decision

    def reset(self):
        self.resets += 1


class _Env:
    def __init__(self, transcription, decision=Decision("ignore", ""), start_result="accepted",
                 busy=False, dialogue=True, chunks=(object(),), utterance_after=1,
                 utterance="UTTERANCE"):
        self.mic = _FakeMicSource(list(chunks))
        self.vad = _FakeVadSegmenter(utterance_after, utterance)
        self.transcriber = _FakeTranscriber(transcription)
        self.start_client = _FakeStartClient(start_result)
        self.speaker = _FakeSpeaker(busy)
        self.reporter = _FakeReporter()
        self.agent = _FakeAgent(decision) if dialogue else None

    def run(self):
        return run_turn_once(
            self.mic, self.vad, self.transcriber, self.start_client, self.speaker,
            self.reporter, KEYWORDS, self.agent,
            no_speech_prob_max=0.6, avg_logprob_min=-1.0,
        )


def test_keyword_starts_without_asking_llm():
    env = _Env(("チェックインお願いします", 0.1, -0.2), decision=Decision("chat", "x"))

    assert env.run() == "keyword_start"
    assert env.start_client.calls == 1
    assert env.agent.calls == []
    assert env.reporter.turns[0]["outcome"] == "keyword_start"
    assert env.reporter.turns[0]["llm_ms"] is None


def test_llm_checkin_requests_start():
    env = _Env(("部屋に入りたいんですけど", 0.1, -0.2), decision=Decision("checkin", ""))

    assert env.run() == "checkin"
    assert env.start_client.calls == 1
    assert env.speaker.spoken == []


def test_chat_reply_is_spoken_and_reported():
    env = _Env(("朝ごはんは何時ですか", 0.1, -0.2), decision=Decision("chat", "6時半からです。"))

    assert env.run() == "chat"
    assert env.speaker.spoken == ["6時半からです。"]
    assert env.start_client.calls == 0
    turn = env.reporter.turns[0]
    assert turn["text"] == "朝ごはんは何時ですか"
    assert turn["reply"] == "6時半からです。"
    assert turn["no_speech_prob"] == 0.1
    assert turn["avg_logprob"] == -0.2
    assert isinstance(turn["stt_ms"], int)
    assert isinstance(turn["llm_ms"], int)


def test_ignore_says_nothing():
    env = _Env(("それでさあ", 0.1, -0.2), decision=Decision("ignore", ""))

    assert env.run() == "ignore"
    assert env.speaker.spoken == []
    assert env.start_client.calls == 0


def test_busy_message_when_start_is_not_available():
    keyword = _Env(("チェックイン", 0.1, -0.2), start_result="not_available")
    llm = _Env(("部屋に入りたい", 0.1, -0.2), decision=Decision("checkin", ""), start_result="not_available")

    keyword.run()
    llm.run()

    assert keyword.speaker.spoken == [BUSY_MESSAGE]
    assert llm.speaker.spoken == [BUSY_MESSAGE]


def test_rate_limited_start_says_nothing():
    env = _Env(("チェックイン", 0.1, -0.2), start_result="rate_limited")

    env.run()

    assert env.speaker.spoken == []


def test_utterance_while_speaker_busy_is_discarded_as_self_echo():
    env = _Env(("チェックインお願いします", 0.1, -0.2), decision=Decision("chat", "x"), busy=True)

    assert env.run() == "self_echo"
    assert env.start_client.calls == 0
    assert env.agent.calls == []
    assert env.reporter.turns[0]["outcome"] == "self_echo"


def test_low_confidence_is_rejected_and_reported(caplog):
    env = _Env(("ノイズ", 0.9, -5.0), decision=Decision("chat", "x"))

    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        assert env.run() == "rejected_low_confidence"

    assert env.agent.calls == []
    assert env.reporter.turns[0]["outcome"] == "rejected_low_confidence"
    assert "ノイズ" in caplog.text and "0.9" in caplog.text and "-5.0" in caplog.text


def test_without_dialogue_non_keyword_is_ignored_as_no_keyword():
    env = _Env(("こんにちは", 0.1, -0.2), dialogue=False)

    assert env.run() == "no_keyword"
    assert env.speaker.spoken == []
    assert env.reporter.turns[0]["outcome"] == "no_keyword"


def test_no_chunk_returns_no_utterance_without_report():
    env = _Env(("unused", 0.0, 0.0), chunks=())

    assert env.run() == "no_utterance"
    assert env.reporter.turns == []


def test_multiple_chunks_are_fed_until_utterance_completes():
    env = _Env(("チェックイン", 0.1, -0.2), chunks=(object(), object(), object()), utterance_after=3)

    assert env.run() == "keyword_start"


def test_echo_check_covers_the_whole_utterance_duration():
    env = _Env(("こんにちは", 0.1, -0.2), utterance=np.zeros(32000, dtype=np.float32))

    env.run()

    assert env.speaker.echo_checks == [2.0]


def test_keyword_start_clears_dialogue_history():
    env = _Env(("チェックインお願いします", 0.1, -0.2))

    env.run()

    assert env.agent.resets == 1
