import io
import logging
import queue
import re
import threading
import time
import wave

import numpy as np
import requests

logger = logging.getLogger(__name__)

# Same voice as dimos' VOICEVOX profile.
_DEFAULT_SPEAKER_ID = 29


def synthesize_speech(text, base_url, speaker_id=_DEFAULT_SPEAKER_ID, speed_scale=1.0, timeout=30.0):
    query_resp = requests.post(
        f"{base_url}/audio_query",
        params={"text": text, "speaker": speaker_id},
        timeout=timeout,
    )
    query_resp.raise_for_status()
    query = query_resp.json()
    query["speedScale"] = speed_scale

    synth_resp = requests.post(
        f"{base_url}/synthesis",
        params={"speaker": speaker_id},
        json=query,
        timeout=timeout,
    )
    synth_resp.raise_for_status()

    with wave.open(io.BytesIO(synth_resp.content)) as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        pcm = wf.readframes(wf.getnframes())

    waveform = np.frombuffer(pcm, dtype=np.int16)
    return waveform, sample_rate, channels


_SENTENCE_END = re.compile(r"(?<=[。！？!?])")


def split_sentences(text):
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def _probe_voicevox(base_url, attempts=10, timeout=10.0):
    last_err = None
    for _ in range(attempts):
        try:
            resp = requests.get(f"{base_url}/version", timeout=timeout)
            resp.raise_for_status()
            return
        except Exception as e:  # noqa: BLE001 - probing is best-effort by design
            last_err = e
            time.sleep(2.0)
    raise RuntimeError(f"VOICEVOXエンジンに接続できません ({base_url}): {last_err}")


class VoicevoxSpeaker:
    """Speaks text sentence by sentence; synthesis runs ahead of playback."""

    def __init__(
        self,
        base_url,
        output_sink,
        speaker_id=_DEFAULT_SPEAKER_ID,
        speed_scale=1.0,
        synthesize=synthesize_speech,
        echo_guard_seconds=0.5,
        clock=time.monotonic,
    ):
        self._base_url = base_url
        self._output_sink = output_sink
        self._speaker_id = speaker_id
        self._speed_scale = speed_scale
        self._synthesize = synthesize
        self._echo_guard_seconds = echo_guard_seconds
        self._clock = clock
        self._cache = {}
        self._texts = queue.Queue()
        self._audio = queue.Queue()
        self._lock = threading.Lock()
        self._playing = False
        self._last_played_at = None
        self._running = True
        self._threads = [
            threading.Thread(target=self._loop, args=(self._synth_once,), daemon=True),
            threading.Thread(target=self._loop, args=(self._play_once,), daemon=True),
        ]

    def start(self):
        _probe_voicevox(self._base_url)
        for thread in self._threads:
            thread.start()

    def preload(self, texts):
        """Synthesize fixed phrases up front; failures fall back to on-demand."""
        for text in texts:
            try:
                self._cache[text] = self._synthesize(
                    text, self._base_url, self._speaker_id, self._speed_scale
                )
            except Exception:  # noqa: BLE001 - a missing phrase is synthesized later
                logger.warning("音声の事前合成に失敗しました。text=%r", text, exc_info=True)
        logger.info("音声を事前合成しました: %d/%d件", len(self._cache), len(texts))

    def speak(self, text):
        for sentence in split_sentences(text):
            self._texts.put(sentence)

    def is_busy(self):
        """True while playing and for a short tail, so the mic ignores our own voice."""
        with self._lock:
            if self._playing:
                return True
            if self._last_played_at is None:
                return False
            return self._clock() - self._last_played_at < self._echo_guard_seconds

    def stop(self):
        self._running = False
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=2.0)

    def _loop(self, step):
        while self._running:
            step(timeout=0.05)

    def _synth_once(self, timeout=0.0):
        try:
            text = self._texts.get(timeout=timeout) if timeout else self._texts.get_nowait()
        except queue.Empty:
            return False
        try:
            audio = self._cache.get(text) or self._synthesize(
                text, self._base_url, self._speaker_id, self._speed_scale
            )
        except Exception:  # noqa: BLE001 - keep speaking the remaining sentences
            logger.warning("音声合成に失敗しました。text=%r", text, exc_info=True)
            return True
        self._audio.put(audio)
        return True

    def _play_once(self, timeout=0.0):
        try:
            audio = self._audio.get(timeout=timeout) if timeout else self._audio.get_nowait()
        except queue.Empty:
            return False
        with self._lock:
            self._playing = True
        try:
            self._output_sink.write(*audio)
        except Exception:  # noqa: BLE001 - keep the playback loop alive
            logger.warning("音声の再生に失敗しました。", exc_info=True)
        finally:
            with self._lock:
                self._playing = False
                self._last_played_at = self._clock()
        return True
