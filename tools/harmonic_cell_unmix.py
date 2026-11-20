"""Offline diagnostic: recover harmonic coefficients from complex cell readings.

Requires source frequencies as an explicit hypothesis. This is not a pitch or
string classifier. Missing competing sources and nonstationary envelopes remain
model errors; a square fit alone is not evidence that the hypothesis is right.
"""
from __future__ import annotations
import numpy as np


def response_matrix(cell_hz, source_hz, sample_rate, decay):
    """Map current-time source cosine/sine coefficients to rotated cell values.

    Cell values are (fast_real + i*fast_imaginary) * (cosine + i*sine),
    matching read_harmonic_correlations. Coefficient pairs describe
    x[n-k] = a*cos(w*k) + b*sin(w*k). Includes the real signal's negative
    frequency image; uses the detector's infinite exponential window.
    """
    cells = np.asarray(cell_hz, dtype=float)
    sources = np.asarray(source_hz, dtype=float)
    if (cells.ndim != 1 or sources.ndim != 1 or not len(cells) or not len(sources)
            or not np.isfinite(sample_rate) or sample_rate <= 0
            or not np.isfinite(decay) or not 0 < decay < 1
            or not np.all(np.isfinite(cells)) or not np.all(np.isfinite(sources))
            or np.any(cells <= 0) or np.any(sources <= 0)
            or np.any(cells >= sample_rate / 2) or np.any(sources >= sample_rate / 2)):
        raise ValueError('Invalid frequencies, rate or decay')
    def window(hz):
        return (1-decay) / (1-decay*np.exp(2j*np.pi*hz/sample_rate))
    difference = window(cells[:, None]-sources[None, :])
    summation = window(cells[:, None]+sources[None, :])
    cosine = (difference+summation)/2
    sine = (summation-difference)/(2j)
    matrix = np.empty((2*len(cells), 2*len(sources)))
    matrix[0::2, 0::2] = cosine.real
    matrix[1::2, 0::2] = cosine.imag
    matrix[0::2, 1::2] = sine.real
    matrix[1::2, 1::2] = sine.imag
    return matrix


def recover(cell_hz, correlations, source_hz, sample_rate, decay, max_condition=1e6):
    matrix = response_matrix(cell_hz, source_hz, sample_rate, decay)
    values = np.asarray(correlations, dtype=complex)
    if values.shape != (len(cell_hz),) or not np.all(np.isfinite(values)):
        raise ValueError('Invalid complex readings')
    observed = np.empty(2*len(values))
    observed[0::2], observed[1::2] = values.real, values.imag
    singular = np.linalg.svd(matrix, compute_uv=False)
    condition = float(singular[0]/singular[-1]) if singular[-1] > 0 else float('inf')
    if matrix.shape[0] < matrix.shape[1] or condition > max_condition:
        return dict(eligible=False, reason='Unidentifiable or ill-conditioned hypothesis')
    coefficients = np.linalg.lstsq(matrix, observed, rcond=None)[0].reshape(-1, 2)
    power = np.sum(coefficients**2, axis=1)/2
    return dict(eligible=True, condition=condition, power=power.tolist(),
                coefficients=coefficients.tolist(),
                residual_norm=float(np.linalg.norm(matrix@coefficients.ravel()-observed)))
