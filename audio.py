import threading
import numpy as np
import miniaudio
import sounddevice as sd


class AudioEngine:
    def __init__(self):
        self.samples: np.ndarray = np.zeros((0, 2), dtype=np.float32)
        self.sample_rate: int = 44100
        self.position_frames: int = 0
        self.volume: float = 0.8
        self._stream: sd.OutputStream | None = None
        self._lock = threading.Lock()

    def load(self, path: str) -> None:
        self.stop()
        decoded = miniaudio.decode_file(
            path,
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=2,
            sample_rate=44100,
        )
        raw = np.frombuffer(decoded.samples, dtype=np.float32)
        self.samples = raw.reshape(-1, 2)
        self.sample_rate = decoded.sample_rate
        self.position_frames = 0

    def _callback(self, outdata: np.ndarray, frames: int, time, status) -> None:
        with self._lock:
            pos = self.position_frames
            end = pos + frames
            total = len(self.samples)

            if pos >= total:
                outdata[:] = 0
                return

            chunk = self.samples[pos:end]
            if len(chunk) < frames:
                pad = np.zeros((frames - len(chunk), 2), dtype=np.float32)
                chunk = np.concatenate([chunk, pad])

            outdata[:] = chunk * self.volume
            self.position_frames = min(end, total)

    def play(self) -> None:
        if self._stream is not None and self._stream.active:
            return
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=2,
            dtype="float32",
            blocksize=1024,
            callback=self._callback,
        )
        self._stream.start()

    def pause(self) -> None:
        if self._stream and self._stream.active:
            self._stream.stop()

    def toggle(self) -> None:
        if self._stream and self._stream.active:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.position_frames = 0

    def seek(self, seconds: float) -> None:
        with self._lock:
            target = int(seconds * self.sample_rate)
            self.position_frames = max(0, min(target, len(self.samples) - 1))

    def seek_relative(self, delta_seconds: float) -> None:
        self.seek(self.elapsed + delta_seconds)

    def set_volume(self, delta: float) -> None:
        self.volume = max(0.0, min(1.0, self.volume + delta))

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate if self.sample_rate else 0.0

    @property
    def elapsed(self) -> float:
        return self.position_frames / self.sample_rate if self.sample_rate else 0.0

    @property
    def finished(self) -> bool:
        return len(self.samples) > 0 and self.position_frames >= len(self.samples)

    @property
    def is_playing(self) -> bool:
        return self._stream is not None and self._stream.active

    def get_window(self, n: int) -> np.ndarray:
        # Pull slightly behind position to match audible output (1024-frame buffer offset)
        pos = max(0, self.position_frames - 1024)
        chunk = self.samples[pos : pos + n]
        mono = chunk.mean(axis=1) if chunk.ndim == 2 else chunk
        if len(mono) < n:
            mono = np.concatenate([mono, np.zeros(n - len(mono), dtype=np.float32)])
        return mono
