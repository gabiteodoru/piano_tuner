"""Pure-numpy DSP, no audio or GUI dependencies."""
import numpy as np


def band_spectrum(x, fs, f_lo, f_hi, pad=2):
    """Hann-windowed FFT of x, cropped to [f_lo, f_hi] Hz. Returns (freqs, dB).

    Resolution is ~fs/len(x) Hz regardless of the band; zero-padding (pad)
    only interpolates the display.
    """
    n = len(x)
    w = np.hanning(n)
    nfft = 1 << int(np.ceil(np.log2(n * pad)))
    spec = np.fft.rfft(x * w, nfft)
    freqs = np.fft.rfftfreq(nfft, 1.0 / fs)
    m = (freqs >= f_lo) & (freqs <= f_hi)
    mag = np.abs(spec[m]) / (w.sum() / 2)
    return freqs[m], 20 * np.log10(mag + 1e-12)


def peak_freq(freqs, db):
    """Frequency of the highest bin, refined by parabolic interpolation."""
    i = int(np.argmax(db))
    if 0 < i < len(db) - 1:
        a, b, c = db[i - 1], db[i], db[i + 1]
        d = a - 2 * b + c
        if d != 0:
            return freqs[i] + 0.5 * (a - c) / d * (freqs[1] - freqs[0])
    return freqs[i]


def cents(f, ref):
    return 1200 * np.log2(f / ref)


_NAMES = "A A# B C C# D D# E F F# G G#".split()


def note_name(k):
    """Name of key k, counting from key 0 = A0 (so C1 = 3, A4 = 48)."""
    return f"{_NAMES[k % 12]}{(k + 9) // 12}"


def equal_temperament(n_keys=88, a4_index=48, concert_pitch=440.0):
    """[(name, Hz)] for an equal-tempered keyboard."""
    return [(note_name(k), concert_pitch * 2 ** ((k - a4_index) / 12)) for k in range(n_keys)]


def load_targets_csv(path):
    """[(name, Hz)] from a key,frequency_hz CSV (key 0 = A0), as written by ept_to_csv.py."""
    import csv
    with open(path, newline="") as f:
        rows = sorted((int(r["key"]), float(r["frequency_hz"])) for r in csv.DictReader(f))
    return [(note_name(k), hz) for k, hz in rows]


def center_ticks(c, h, target=8):
    """Major ticks [(value, label)] at c + k*step, so c itself is always labeled.

    h is the half-width of the axis; step is a 1/2/5 x 10^n number giving ~target ticks.
    Labels use enough decimals for both the step and the center.
    """
    import math
    raw = 2 * h / target
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)
    d = max(0, -math.floor(math.log10(step)))
    cs = f"{c:.2f}".rstrip("0").rstrip(".")
    d = max(d, len(cs.split(".")[1]) if "." in cs else 0)
    kmax = int(h / step)
    return [(c + k * step, f"{c + k * step:.{d}f}") for k in range(-kmax, kmax + 1)]
