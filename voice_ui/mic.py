import queue

import numpy as np
import sounddevice as sd

from .vad_segmenter import CHUNK_SAMPLES


class SounddeviceMicSource:
    def __init__(self, sample_rate=16000, device_index=None):
        self._sample_rate = sample_rate
        self._device_index = device_index
        self._queue = queue.Queue()
        self._stream = None

    def start(self):
        def callback(indata, frames, time_info, status):
            self._queue.put(indata[:, 0].copy())

        self._stream = sd.InputStream(
            device=self._device_index,
            samplerate=self._sample_rate,
            channels=1,
            blocksize=CHUNK_SAMPLES,
            dtype=np.float32,
            callback=callback,
        )
        self._stream.start()

    def read_chunk(self, timeout=None):
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
