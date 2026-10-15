"""Audio sources. Each has .fs and .read_latest(n) -> last n samples (zero-padded)."""
import threading
import numpy as np


class _Ring:
    def __init__(self, size):
        self.buf = np.zeros(size, dtype=np.float32)
        self.pos = 0
        self.lock = threading.Lock()

    def write(self, x):
        with self.lock:
            n = len(x)
            idx = (self.pos + np.arange(n)) % len(self.buf)
            self.buf[idx] = x
            self.pos = (self.pos + n) % len(self.buf)

    def latest(self, n):
        with self.lock:
            idx = (self.pos - n + np.arange(n)) % len(self.buf)
            return self.buf[idx].copy()


class MicSource:
    def __init__(self, fs=48000, device=None, max_seconds=16):
        import sounddevice as sd
        self.fs = fs
        self.ring = _Ring(int(fs * max_seconds))
        self.stream = sd.InputStream(samplerate=fs, channels=1, device=device,
                                     dtype="float32",
                                     callback=lambda d, f, t, s: self.ring.write(d[:, 0]))
        self.stream.start()

    def read_latest(self, n):
        return self.ring.latest(n)


class SyntheticSource:
    """Three slightly detuned strings with inharmonic partials, looped."""
    def __init__(self, f0=440.0, detune_cents=(-3, 0, 2), B=0.0004, fs=48000, max_seconds=16):
        self.fs = fs
        t = np.arange(int(fs * max_seconds)) / fs
        x = np.zeros_like(t)
        for c in detune_cents:
            f = f0 * 2 ** (c / 1200)
            for k in range(1, 8):
                x += (1.0 / k) * np.sin(2 * np.pi * k * f * np.sqrt(1 + B * k * k) * t + k)
        self.x = (x / np.abs(x).max()).astype(np.float32)

    def read_latest(self, n):
        return self.x[-n:]
