import numpy as np


def compute_spectrum(window: np.ndarray, n_bars: int, sample_rate: int) -> np.ndarray:
    if len(window) == 0 or n_bars == 0:
        return np.zeros(n_bars, dtype=np.float32)

    n = len(window)
    hann = np.hanning(n)
    windowed = window * hann
    magnitude = np.abs(np.fft.rfft(windowed))

    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
    f_min, f_max = 40.0, 16000.0

    log_edges = np.logspace(np.log10(f_min), np.log10(f_max), n_bars + 1)
    bars = np.zeros(n_bars, dtype=np.float32)
    for i in range(n_bars):
        mask = (freqs >= log_edges[i]) & (freqs < log_edges[i + 1])
        if mask.any():
            bars[i] = magnitude[mask].mean()

    # Log-amplitude scaling (dB-ish)
    bars = np.log1p(bars)

    max_val = bars.max()
    if max_val > 0:
        bars /= max_val

    return bars


def smooth(
    prev: np.ndarray,
    current: np.ndarray,
    attack: float = 0.6,
    decay: float = 0.15,
) -> np.ndarray:
    if prev is None or len(prev) != len(current):
        return current.copy()
    rising = current > prev
    result = np.where(rising, prev + attack * (current - prev), prev + decay * (current - prev))
    return result.astype(np.float32)
