import io
import json
import wave

import responses

from voice_ui.step_messages import PRELOAD_TEXTS, STEP_MESSAGES, VOICE_START_GUIDANCE
from voice_ui.tts import VoicevoxSpeaker, synthesize_speech


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
    def __init__(self):
        self.writes = []

    def write(self, waveform, sample_rate, channels):
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


def _speaker(synth, sink=None):
    return VoicevoxSpeaker(
        base_url="http://voicevox.test",
        output_sink=sink or _FakeSink(),
        synthesize=synth,
    )


def test_default_speaker_is_29_like_dimos():
    synth = _FakeSynth()
    speaker = _speaker(synth)

    speaker._play("こんにちは")

    assert synth.calls == [("こんにちは", 29)]


def test_preloaded_text_is_played_without_synthesizing_again():
    synth = _FakeSynth()
    sink = _FakeSink()
    speaker = _speaker(synth, sink)

    speaker.preload(["案内です"])
    speaker._play("案内です")

    assert synth.calls == [("案内です", 29)]
    assert sink.writes == [("wave:案内です", 24000, 1)]


def test_text_not_preloaded_is_synthesized_on_demand():
    synth = _FakeSynth()
    sink = _FakeSink()
    speaker = _speaker(synth, sink)
    speaker.preload(["案内です"])

    speaker._play("エラーが発生しました")

    assert synth.calls[-1] == ("エラーが発生しました", 29)
    assert sink.writes == [("wave:エラーが発生しました", 24000, 1)]


def test_preload_failure_is_skipped_and_retried_on_demand():
    synth = _FakeSynth(fail_on={"失敗する文"})
    sink = _FakeSink()
    speaker = _speaker(synth, sink)

    speaker.preload(["失敗する文", "成功する文"])
    speaker._play("成功する文")

    assert synth.calls == [("失敗する文", 29), ("成功する文", 29)]
    assert sink.writes == [("wave:成功する文", 24000, 1)]


def test_preload_texts_cover_every_fixed_message():
    assert set(PRELOAD_TEXTS) == set(STEP_MESSAGES.values()) | {VOICE_START_GUIDANCE}
