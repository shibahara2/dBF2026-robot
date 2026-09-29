import io
import logging
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
    def __init__(
        self,
        base_url,
        output_sink,
        speaker_id=_DEFAULT_SPEAKER_ID,
        speed_scale=1.0,
        synthesize=synthesize_speech,
    ):
        self._base_url = base_url
        self._output_sink = output_sink
        self._speaker_id = speaker_id
        self._speed_scale = speed_scale
        self._synthesize = synthesize
        self._cache = {}
        self._queue = []
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        _probe_voicevox(self._base_url)
        self._thread.start()

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
        if not text.strip():
            return
        with self._lock:
            self._queue.append(text)

    def stop(self):
        self._running = False
        self._thread.join(timeout=2.0)

    def _run(self):
        while self._running:
            text = None
            with self._lock:
                if self._queue:
                    text = self._queue.pop(0)
            if text is None:
                time.sleep(0.05)
                continue
            try:
                self._play(text)
            except Exception:  # noqa: BLE001 - keep the speak loop alive across failures
                logger.warning(
                    "音声合成/出力に失敗しました。text=%r", text, exc_info=True
                )
                continue

    def _play(self, text):
        audio = self._cache.get(text)
        if audio is None:
            audio = self._synthesize(
                text, self._base_url, self._speaker_id, self._speed_scale
            )
        waveform, sample_rate, channels = audio
        self._output_sink.write(waveform, sample_rate, channels)
