"""Pure band/feature arithmetic for one frozen causal SuperFlux baseline.

Equations: Boeck and Widmer, DAFx 2013, Maximum Filter Vibrato Suppression
for Onset Detection. This is an explicit 96 kHz adaptation, not a claim of
bit identity with CPJKU's reference program. No waveform reads or FFT here.
"""
from __future__ import annotations

import math

from tools.spectral_sparsity_attack import peak_candidates, decode


def filterbank(sample_rate, frame_size, bands_per_octave=24, low=30, high=17000):
    """Return sparse, peak-one triangular filters; discard duplicate FFT edges."""
    if not (sample_rate > 0 and frame_size >= 8 and frame_size % 2 == 0 and
            bands_per_octave > 0 and 0 < low < high <= sample_rate / 2):
        raise ValueError('Invalid filterbank geometry')
    ratio = 2 ** (1 / bands_per_octave)
    frequencies = [440.0]
    value = 440.0
    while value <= high:
        value *= ratio
        frequencies.append(value)
    value = 440.0
    while value >= low:
        value /= ratio
        frequencies.append(value)
    edges = sorted({round(f * frame_size / sample_rate) for f in frequencies
                    if round(f * frame_size / sample_rate) < frame_size // 2})
    if len(edges) < 5:
        raise ValueError('Insufficient distinct filter edges')
    result = []
    for left, centre, right in zip(edges, edges[1:], edges[2:]):
        weights = [(k - left) / (centre - left) if k < centre
                   else (right - k) / (right - centre) for k in range(left, right)]
        result.append((left, weights))
    return result


def logarithmic_bands(magnitudes, filters):
    values = [float(x) for x in magnitudes]
    if not values or any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError('Magnitudes must be finite and nonnegative')
    result = []
    for start, weights in filters:
        if start < 0 or start + len(weights) > len(values):
            raise ValueError('Filter outside spectrum')
        energy = math.fsum(values[start + k] * w for k, w in enumerate(weights))
        result.append(math.log10(1 + energy))
    return result


def positive_flux(current, previous):
    """Sum rectified rises over a three-band maximum of the past frame."""
    if len(current) != len(previous) or not current:
        raise ValueError('Equal nonempty band vectors required')
    if any(not math.isfinite(x) or x < 0 for x in (*current, *previous)):
        raise ValueError('Band values must be finite and nonnegative')
    return math.fsum(max(0.0, value - max(previous[max(0, k - 1):k + 2]))
                     for k, value in enumerate(current))


def pick_events(rows, threshold=1.1, max_history=6, mean_history=20, refractory=6):
    """Past-only 30/100 ms peak rule at 200 fps, strict 30 ms refractory.

    Startup mean is zero padded; all windows include the current frame.
    Availability is the exclusive input-hop end, without centre backdating.
    Refractory compares with the last emitted event, as in the paper rule.
    """
    return decode(peak_candidates(rows, max_history, mean_history), threshold, refractory)
