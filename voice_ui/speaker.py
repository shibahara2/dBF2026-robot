import threading

import sounddevice as sd


class SounddeviceSpeakerSink:
    def __init__(self, device_index=None):
        self._device_index = device_index
        self._lock = threading.Lock()
        self._stream = None
        self._stream_rate = None
        self._stream_channels = None

    def write(self, waveform, sample_rate, channels):
        with self._lock:
            if (
                self._stream is None
                or self._stream_rate != sample_rate
                or self._stream_channels != channels
            ):
                if self._stream is not None:
                    self._stream.stop()
                    self._stream.close()
                self._stream = sd.OutputStream(
                    device=self._device_index,
                    samplerate=sample_rate,
                    channels=channels,
                    dtype="int16",
                )
                self._stream.start()
                self._stream_rate = sample_rate
                self._stream_channels = channels
            self._stream.write(waveform)

    def stop(self):
        with self._lock:
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
