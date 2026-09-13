import io
import json
import wave

import responses

from voice_ui.tts import synthesize_speech


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
