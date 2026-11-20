"""Offline fixed-frequency cross-pitch shape diagnostic; never a MIDI policy.

Callers supply frequencies and explicitly identify oracle versus detector input.
Coefficients use the older half only; the newer half scores the frozen model.
Recorded audio execution belongs on GitHub Actions.
"""
from __future__ import annotations
import numpy as np


def fit_shape(samples, rate, fundamentals, *, input_role, harmonics=6):
    if input_role not in ('annotation_oracle', 'detector_candidates'):
        raise ValueError('Explicit input role required')
    y = np.asarray(samples, dtype=float)
    f0 = np.asarray(fundamentals, dtype=float)
    if (y.ndim != 1 or len(y) < 64 or not np.isfinite(y).all() or
            not np.isfinite(rate) or rate <= 0 or f0.ndim != 1 or
            not 1 <= len(f0) <= 8 or not np.isfinite(f0).all() or
            np.any(f0 <= 0) or not isinstance(harmonics, int) or not 1 <= harmonics <= 12):
        raise ValueError('Invalid signal or candidate frequencies')
    frequencies = (f0[:, None] * np.arange(1, harmonics + 1)).ravel()
    if frequencies.max() >= rate / 2:
        raise ValueError('Harmonic exceeds Nyquist')
    split = len(y) // 2
    t = np.arange(len(y)) / rate
    phase = 2 * np.pi * t[:, None] * frequencies
    basis = np.column_stack((np.ones(len(y)), np.cos(phase), np.sin(phase)))
    if split <= basis.shape[1]:
        raise ValueError('Insufficient training support')
    weight = np.sqrt(np.hanning(split))
    design = basis[:split] * weight[:, None]
    coefficients, _, rank, singular = np.linalg.lstsq(design, y[:split] * weight, rcond=1e-8)
    ratio = float(singular[-1] / singular[0])
    train_energy = float(np.mean((y[:split] - y[:split].mean()) ** 2))
    result = dict(input_role=input_role, fundamentals_hz=f0.tolist(),
                  training_samples=split, validation_samples=len(y)-split,
                  rank=int(rank), columns=basis.shape[1], singular_ratio=ratio,
                  shape_available=False, policy_admission=False,
                  limitations=['Fixed supplied frequencies; no pitch estimation, drift or decay model.',
                               'Low residual cannot prove all competing sources are present.',
                               'Shared harmonics and unisons may make individual shapes unidentifiable.',
                               'This is an offline diagnostic, not a runtime timing or note-quality result.'])
    if train_energy <= 1e-20:
        result['abstention'] = 'silent_training'
        return result
    prediction = basis @ coefficients
    result['training_residual_ratio'] = float(np.mean((prediction[:split]-y[:split])**2)/train_energy)
    result['validation_residual_ratio'] = float(np.mean((prediction[split:]-y[split:])**2)/train_energy)
    if rank != basis.shape[1] or ratio < 1e-6:
        result['abstention'] = 'unidentifiable_coefficients'
        return result
    count = len(frequencies)
    power = (coefficients[1:count+1]**2 + coefficients[count+1:]**2).reshape(len(f0), harmonics)
    result['harmonic_power'] = power.tolist()
    # Do not floor missing partials into a confident profile. Expose them.
    result['relative_partial_power'] = (power / max(float(power.max()), 1e-30)).tolist()
    result['shape_available'] = True
    return result
