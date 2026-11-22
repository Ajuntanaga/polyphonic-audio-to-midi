"""Narrow-band level curves around label ends and starts from the corpus audio.  Pure numpy; no model, no weights.

Plan, definitions and predictions: docs/recovery/CLAUDE-M3-AUDIO-RELEASE-PROPOSAL-20261122.md.  A level is the root-sum-square amplitude of the
first harmonics of a labelled pitch inside one Hann-windowed 80 ms stretch of the 96 kHz recording, in dB relative to full scale.  Curves are
sampled on a 10 ms grid of window starts; every derived quantity (pre-end level, level after the end, rise at a start) is computed later from
the curves by the registered analysis, never here.
"""
import numpy as np

SOURCE_RATE = 96000
WINDOW_MS = 80
HOP_MS = 10
HARMONICS = 4
MAX_HARMONIC_HZ = 2000.0
END_GRID = (-20, 30)       # window starts E + HOP_MS * j for j in END_GRID, both ends included
START_GRID = (-20, 20)     # window starts S + HOP_MS * j
FLOOR = 1e-9


def ms_samples(ms):
    return ms * SOURCE_RATE // 1000


def fundamental(midi):
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def harmonic_numbers(midi):
    """Harmonic numbers 1..HARMONICS of the pitch that lie at or below MAX_HARMONIC_HZ."""
    return [k for k in range(1, HARMONICS + 1) if k * fundamental(midi) <= MAX_HARMONIC_HZ]


def window_levels(x, midi, first, count, hop):
    """dB level of `count` windows of WINDOW_MS starting at samples first, first+hop, ...; NaN where a window does not fit inside x.

    Hann window (periodic), weighted mean removed, amplitude A_k = 2|sum w x e^{-2 pi i k f0 n / fs}| / sum w for harmonics k, level
    20 log10(sqrt(sum A_k^2) + FLOOR).  A pure sinusoid of amplitude a at k f0 gives a (to a fraction of a dB once the window holds a few cycles).
    The magnitude does not depend on the window's absolute position, so one basis per harmonic serves every window.
    """
    length = ms_samples(WINDOW_MS)
    positions = first + hop * np.arange(count, dtype=np.int64)
    fits = (positions >= 0) & (positions + length <= len(x))
    out = np.full(count, np.nan)
    if not fits.any():
        return out
    chosen = positions[fits]
    low, high = int(chosen.min()), int(chosen.max()) + length
    view = np.lib.stride_tricks.sliding_window_view(np.asarray(x[low:high], dtype=np.float64), length)
    rows = view[chosen - low]
    n = np.arange(length)
    weight = 0.5 - 0.5 * np.cos(2.0 * np.pi * n / length)
    total = weight.sum()
    mean = rows @ weight / total
    power = np.zeros(len(rows))
    for k in harmonic_numbers(midi):
        basis = weight * np.exp(-2j * np.pi * k * fundamental(midi) * n / SOURCE_RATE)
        coefficient = rows @ basis - mean * basis.sum()
        power += (2.0 * np.abs(coefficient) / total) ** 2
    out[fits] = 20.0 * np.log10(np.sqrt(power) + FLOOR)
    return out


def grid_curve(x, midi, anchor, grid):
    first = anchor + ms_samples(HOP_MS) * grid[0]
    return window_levels(x, midi, first, grid[1] - grid[0] + 1, ms_samples(HOP_MS))


def end_curve(x, midi, end):
    return grid_curve(x, midi, end, END_GRID)


def start_curve(x, midi, start):
    return grid_curve(x, midi, start, START_GRID)


def grid_index(grid, j):
    """Index of grid step j (a multiple of HOP_MS) inside a curve, or None when it is outside the grid."""
    i = j - grid[0]
    return i if 0 <= i <= grid[1] - grid[0] else None
