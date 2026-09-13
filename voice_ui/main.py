import logging
import threading

from . import config
from .checkin_client import CheckinClient
from .mic import SounddeviceMicSource
from .pipeline import run_checkin_once
from .progress_announcer import ProgressAnnouncer
from .speaker import SounddeviceSpeakerSink
from .sse_events import iter_sse_events
from .stt import WhisperTranscriber
from .tts import VoicevoxSpeaker
from .vad_segmenter import SileroVadSegmenter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_checkin_loop(mic_source, vad_segmenter, transcriber, checkin_client):
    while True:
        outcome = run_checkin_once(
            mic_source,
            vad_segmenter,
            transcriber,
            checkin_client,
            no_speech_prob_max=config.STT_NO_SPEECH_PROB_MAX,
            avg_logprob_min=config.STT_AVG_LOGPROB_MIN,
        )
        logger.info("checkin pipeline outcome: %s", outcome)


def run_progress_loop(speaker):
    announcer = ProgressAnnouncer(speak=speaker.speak)
    for snapshot in iter_sse_events(config.FLASK_BASE_URL):
        announcer.handle_snapshot(snapshot)


def main():
    checkin_client = CheckinClient(base_url=config.FLASK_BASE_URL)

    mic_source = SounddeviceMicSource(sample_rate=16000)
    mic_source.start()

    vad_segmenter = SileroVadSegmenter(
        sample_rate=16000, trailing_silence_ms=config.VAD_TRAILING_SILENCE_MS
    )
    transcriber = WhisperTranscriber(model_size=config.WHISPER_MODEL)

    speaker_sink = SounddeviceSpeakerSink()
    speaker = VoicevoxSpeaker(base_url=config.VOICEVOX_URL, output_sink=speaker_sink)
    speaker.start()

    progress_thread = threading.Thread(
        target=run_progress_loop, args=(speaker,), daemon=True
    )
    progress_thread.start()

    run_checkin_loop(mic_source, vad_segmenter, transcriber, checkin_client)


if __name__ == "__main__":
    main()
