import io
import json
import wave

import pytest
import responses

from voice_ui.step_messages import BUSY_MESSAGE, PRELOAD_TEXTS, VOICE_START_GUIDANCE
from voice_ui.tts import VoicevoxSpeaker, split_sentences, synthesize_speech


def _make_wav_bytes(sample_rate=24000, channels=1, samples=b"\x00\x00\x01\x00"):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples)
    return buf.getvalue()


@responses.activate
def test_synthesize_speech_returns_waveform_and_metadata():
    responses.add(
        responses.POST,
        "http://voicevox.test/audio_query",
        json={"accent_phrases": []},
        status=200,
    )
    responses.add(
        responses.POST,
        "http://voicevox.test/synthesis",
        body=_make_wav_bytes(),
        status=200,
        content_type="audio/wav",
    )

    waveform, sample_rate, channels = synthesize_speech(
        "テスト", base_url="http://voicevox.test", speaker_id=74
    )

    assert sample_rate == 24000
    assert channels == 1
    assert len(waveform) == 2


@responses.activate
def test_synthesize_speech_sends_speaker_and_speed_scale():
    responses.add(
        responses.POST,
        "http://voicevox.test/audio_query",
        json={"accent_phrases": []},
        status=200,
    )
    responses.add(
        responses.POST,
        "http://voicevox.test/synthesis",
        body=_make_wav_bytes(),
        status=200,
        content_type="audio/wav",
    )

    synthesize_speech(
        "テスト", base_url="http://voicevox.test", speaker_id=3, speed_scale=1.2
    )

    audio_query_call = responses.calls[0]
    assert audio_query_call.request.params["speaker"] == "3"

    synthesis_call = responses.calls[1]
    sent_query = json.loads(synthesis_call.request.body)
    assert sent_query["speedScale"] == 1.2


# --- VoicevoxSpeaker ----------------------------------------------------------



class _FakeSink:
    def __init__(self, on_write=None):
        self.writes = []
        self._on_write = on_write

    def write(self, waveform, sample_rate, channels):
        if self._on_write:
            self._on_write()
        self.writes.append((waveform, sample_rate, channels))


class _FakeSynth:
    def __init__(self, fail_on=()):
        self.calls = []
        self._fail_on = set(fail_on)

    def __call__(self, text, base_url, speaker_id, speed_scale):
        self.calls.append((text, speaker_id))
        if text in self._fail_on:
            raise RuntimeError("synthesis failed")
        return f"wave:{text}", 24000, 1


class _FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


def _speaker(synth, sink=None, clock=None):
    return VoicevoxSpeaker(
        base_url="http://voicevox.test",
        output_sink=sink or _FakeSink(),
        synthesize=synth,
        echo_guard_seconds=0.5,
        clock=clock or _FakeClock(),
    )


def _drain(speaker):
    while speaker._synth_once() or speaker._play_once():
        pass


@pytest.mark.parametrize(
    "text, expected",
    [
        ("朝食は7時からです。場所は1階です。", ["朝食は7時からです。", "場所は1階です。"]),
        ("ようこそ！何かお手伝いしますか？", ["ようこそ！", "何かお手伝いしますか？"]),
        ("Wi-Fiは無料です!パスワードはカードにあります?", ["Wi-Fiは無料です!", "パスワードはカードにあります?"]),
        ("句点のない文", ["句点のない文"]),
        ("  ", []),
    ],
)
def test_split_sentences(text, expected):
    assert split_sentences(text) == expected


def test_default_speaker_is_29_like_dimos():
    synth = _FakeSynth()
    speaker = _speaker(synth)

    speaker.speak("こんにちは")
    _drain(speaker)

    assert synth.calls == [("こんにちは", 29)]


def test_speak_plays_every_sentence_in_order():
    synth = _FakeSynth()
    sink = _FakeSink()
    speaker = _speaker(synth, sink)

    speaker.speak("一文目です。二文目です。三文目")
    _drain(speaker)

    assert [w[0] for w in sink.writes] == ["wave:一文目です。", "wave:二文目です。", "wave:三文目"]


def test_next_sentence_is_synthesized_before_current_one_finishes_playing():
    synth = _FakeSynth()
    sink = _FakeSink()
    speaker = _speaker(synth, sink)
    speaker.speak("一文目です。二文目です。")

    speaker._synth_once()
    speaker._synth_once()

    assert [c[0] for c in synth.calls] == ["一文目です。", "二文目です。"]
    assert sink.writes == []


def test_preloaded_text_is_played_without_synthesizing_again():
    synth = _FakeSynth()
    sink = _FakeSink()
    speaker = _speaker(synth, sink)

    speaker.preload(["案内です。"])
    speaker.speak("案内です。")
    _drain(speaker)

    assert synth.calls == [("案内です。", 29)]
    assert sink.writes == [("wave:案内です。", 24000, 1)]


def test_failed_sentence_is_skipped_and_next_one_plays():
    synth = _FakeSynth(fail_on={"失敗する文。"})
    sink = _FakeSink()
    speaker = _speaker(synth, sink)

    speaker.speak("失敗する文。成功する文。")
    _drain(speaker)

    assert sink.writes == [("wave:成功する文。", 24000, 1)]


def test_preload_failure_is_skipped_and_retried_on_demand():
    synth = _FakeSynth(fail_on={"失敗する文"})
    sink = _FakeSink()
    speaker = _speaker(synth, sink)

    speaker.preload(["失敗する文", "成功する文"])
    speaker.speak("成功する文")
    _drain(speaker)

    assert synth.calls == [("失敗する文", 29), ("成功する文", 29)]
    assert sink.writes == [("wave:成功する文", 24000, 1)]


def _played_for_two_seconds(clock):
    """Speak one sentence whose playback runs from t=100.0 to t=102.0."""
    def on_write():
        clock.value += 2.0

    speaker = _speaker(_FakeSynth(), _FakeSink(on_write=on_write), clock)
    speaker.speak("こんにちは。")
    speaker._synth_once()
    speaker._play_once()
    return speaker


def test_nothing_played_is_not_echo():
    assert _speaker(_FakeSynth()).was_speaking_during(5.0) is False


def test_reported_as_speaking_while_playing():
    clock = _FakeClock()
    seen = []
    speaker = None

    def on_write():
        seen.append(speaker.was_speaking_during(0.1))

    speaker = _speaker(_FakeSynth(), _FakeSink(on_write=on_write), clock)
    speaker.speak("こんにちは。")
    speaker._synth_once()
    speaker._play_once()

    assert seen == [True]


def test_echo_segment_closed_after_trailing_silence_is_caught():
    # The mic heard our reply (100-102) and VAD closed the segment only after
    # ~0.5 s of trailing silence, i.e. later than the 0.5 s guard after playback.
    clock = _FakeClock()
    speaker = _played_for_two_seconds(clock)

    clock.value = 102.0 + 0.55
    assert speaker.was_speaking_during(2.55) is True


def test_utterance_starting_within_guard_is_echo():
    clock = _FakeClock()
    speaker = _played_for_two_seconds(clock)

    clock.value = 104.3  # segment 102.3-104.3 starts 0.3 s after playback ended
    assert speaker.was_speaking_during(2.0) is True


def test_visitor_utterance_after_guard_is_not_echo():
    clock = _FakeClock()
    speaker = _played_for_two_seconds(clock)

    clock.value = 105.0  # segment 103.0-105.0 starts 1 s after playback ended
    assert speaker.was_speaking_during(2.0) is False


def test_preloaded_multi_sentence_phrase_needs_no_synthesis():
    synth = _FakeSynth()
    speaker = _speaker(synth)
    speaker.preload([BUSY_MESSAGE])
    synth.calls.clear()

    speaker.speak(BUSY_MESSAGE)
    _drain(speaker)

    assert synth.calls == []


def test_preload_texts_are_the_fixed_phrases_voice_ui_speaks():
    assert PRELOAD_TEXTS == [VOICE_START_GUIDANCE, BUSY_MESSAGE]
    assert BUSY_MESSAGE == "ただいま他のお客様をご案内しています。少々お待ちください"
