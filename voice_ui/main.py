import logging
import threading
import time

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

# If the mic produces this many consecutive "no_utterance" outcomes in a row,
# treat it as the mic having been lost mid-run (spec: マイクデバイスが無い場合は
# 起動失敗をログに残しプロセスを終了する - this also covers loss mid-run).
# At the pipeline's default read_timeout=1.0s, 30 consecutive no_utterance
# outcomes is roughly 30 seconds of total silence from the mic.
NO_UTTERANCE_EXIT_THRESHOLD = 30

_RECONNECT_INITIAL_BACKOFF = 1.0
_RECONNECT_MAX_BACKOFF = 30.0


class MicSilenceExceeded(RuntimeError):
    """Raised when the mic has produced no audio for too long, mid-run."""


def _run_checkin_loop_body(outcome_iter, no_utterance_exit_threshold=NO_UTTERANCE_EXIT_THRESHOLD):
    """Consume a stream of pipeline outcomes, raising MicSilenceExceeded if
    "no_utterance" occurs `no_utterance_exit_threshold` times in a row.

    Factored out from run_checkin_loop so the counting/exit logic can be
    tested with a plain iterable of outcomes, without any hardware or I/O.
    """
    consecutive_no_utterance = 0
    for outcome in outcome_iter:
        logger.info("checkin pipeline outcome: %s", outcome)
        if outcome == "no_utterance":
            consecutive_no_utterance += 1
            if consecutive_no_utterance >= no_utterance_exit_threshold:
                logger.error(
                    "マイクから%d回連続で発話が検出されませんでした。"
                    "マイクが失われた可能性があるためプロセスを終了します",
                    consecutive_no_utterance,
                )
                raise MicSilenceExceeded(
                    f"{consecutive_no_utterance}回連続でマイクから発話が検出されませんでした"
                )
        else:
            consecutive_no_utterance = 0


def run_checkin_loop(
    mic_source,
    vad_segmenter,
    transcriber,
    checkin_client,
    no_utterance_exit_threshold=NO_UTTERANCE_EXIT_THRESHOLD,
):
    def _outcomes():
        while True:
            yield run_checkin_once(
                mic_source,
                vad_segmenter,
                transcriber,
                checkin_client,
                no_speech_prob_max=config.STT_NO_SPEECH_PROB_MAX,
                avg_logprob_min=config.STT_AVG_LOGPROB_MIN,
            )

    _run_checkin_loop_body(_outcomes(), no_utterance_exit_threshold)


def run_progress_loop(
    speaker,
    event_iterator_factory=None,
    sleep_func=time.sleep,
    initial_backoff=_RECONNECT_INITIAL_BACKOFF,
    max_backoff=_RECONNECT_MAX_BACKOFF,
):
    """Consume SSE progress events and speak them, reconnecting with
    exponential backoff whenever the stream ends or raises (spec: SSE切断時は
    指数バックオフで再接続する).

    `event_iterator_factory` (default: opens a fresh SSE connection) is
    injectable so this loop's reconnect behavior can be tested without a real
    HTTP connection or real sleeping.
    """
    if event_iterator_factory is None:
        event_iterator_factory = lambda: iter_sse_events(config.FLASK_BASE_URL)

    announcer = ProgressAnnouncer(speak=speaker.speak)
    backoff = initial_backoff
    while True:
        try:
            for snapshot in event_iterator_factory():
                announcer.handle_snapshot(snapshot)
                backoff = initial_backoff
        except Exception:
            logger.warning(
                "SSEストリームが切断されました。%.1f秒後に再接続します",
                backoff,
                exc_info=True,
            )
        else:
            logger.warning(
                "SSEストリームが終了しました。%.1f秒後に再接続します", backoff
            )
        sleep_func(backoff)
        backoff = min(backoff * 2, max_backoff)


def main():
    checkin_client = CheckinClient(base_url=config.FLASK_BASE_URL)

    mic_source = SounddeviceMicSource(sample_rate=16000)

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

    # Start capturing audio only once everything that will consume it is
    # ready. SounddeviceMicSource queues every captured frame in an unbounded
    # queue, so starting it before the (possibly slow) model load and engine
    # probe above would accumulate minutes of stale ambient audio that gets
    # replayed through VAD/Whisper the moment the loop starts.
    mic_source.start()

    run_checkin_loop(mic_source, vad_segmenter, transcriber, checkin_client)


if __name__ == "__main__":
    main()
