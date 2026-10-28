"""Causal, bounded gain refresh for frozen offline harmonic fits.

Only a positive real gain per string may change. Frequencies, decay rates,
phases and harmonic ratios stay fixed. No labels enter the calculation.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import lsq_linear

try:
    from .joint_harmonic_fit import _validate
    from .harmonic_drift_fit import _basis, _linear
    from .coupled_harmonic_fit import current_energy_audit
except ImportError:
    from joint_harmonic_fit import _validate
    from harmonic_drift_fit import _basis, _linear
    from coupled_harmonic_fit import current_energy_audit


def _verify_saved_audit(actual, saved):
    """Legacy reports lack an NPZ hash; bind every saved audit field again."""
    if isinstance(actual, dict):
        if not isinstance(saved, dict) or actual.keys() != saved.keys():
            raise ValueError('frozen audit identity mismatch')
        for key in actual:
            _verify_saved_audit(actual[key], saved[key])
    elif isinstance(actual, list):
        if not isinstance(saved, list) or len(actual) != len(saved):
            raise ValueError('frozen audit identity mismatch')
        for first, second in zip(actual, saved):
            _verify_saved_audit(first, second)
    elif isinstance(actual, float):
        if (not isinstance(saved, (float, int)) or isinstance(saved, bool) or
                not math.isclose(actual, saved, rel_tol=1e-9, abs_tol=1e-10)):
            raise ValueError('prepared audio or frozen audit identity mismatch')
    elif actual != saved:
        raise ValueError('frozen audit identity mismatch')


def refresh_gain(columns, signal):
    """Fit real gains in [0.5, 2] to already normalized training samples."""
    columns = np.asarray(columns, dtype=complex)
    signal = np.asarray(signal, dtype=complex)
    if (columns.ndim != 2 or signal.shape != (columns.shape[0],) or
            not 1 <= columns.shape[1] <= 4 or not np.isfinite(columns).all() or
            not np.isfinite(signal).all()):
        raise ValueError('invalid gain-refresh input')
    matrix = np.concatenate((columns.real, columns.imag))
    target = np.concatenate((signal.real, signal.imag))
    norms = np.linalg.norm(matrix, axis=0)
    if np.any(norms <= 1e-30):
        return {'gain': [1.0] * columns.shape[1], 'valid': False,
                'at_boundary': False, 'conditioning': 0.0}
    singular = np.linalg.svd(matrix / norms, compute_uv=False)
    conditioning = float(singular[-1] / singular[0])
    result = lsq_linear(matrix, target, bounds=(0.5, 2.0), tol=1e-10)
    bounded = bool(np.any(result.x <= 0.5001) or np.any(result.x >= 1.9999))
    return {'gain': result.x.tolist(), 'valid': bool(result.success and not bounded and conditioning > 1e-4),
            'at_boundary': bounded, 'conditioning': conditioning}


def audit_window(times, signal, center, note, sources, training, bands, models,
                 original_audit, median_guard, gap_guard):
    times, signal = _validate(times, signal, center, note, sources, training)
    _verify_saved_audit(current_energy_audit(times, signal, center, sources, training,
                                            bands, models, median_guard, gap_guard), original_audit)
    harmonics = [h for h in range(3) if bands & (1 << h)]
    by_string = {s['string']: s for s in sources}
    original = {(m['mask'], m['fit_family']): m for m in original_audit['models']}
    # Training-only normalization. Test audio cannot alter the refreshed gains.
    training_energy = np.mean(np.abs(signal[:, :training]) ** 2, axis=1)
    floor = max(float(training_energy[harmonics].max()), 1e-30) * 1e-3
    scale = np.sqrt(np.maximum(training_energy, floor))
    test_energy = np.mean(np.abs(signal[:, training:]) ** 2, axis=1)
    test_scale = np.sqrt(np.maximum(test_energy, max(floor, float(test_energy[harmonics].max()) * 1e-3)))
    recent_begin = training // 2
    inspected = []
    for model in models:
        members = model['members']
        selected = [by_string[m['string']] for m in members]
        starts = np.asarray([m.get('cents', m.get('cents_at_start')) for m in members])
        ends = np.asarray([m.get('cents_at_end', starts[i]) for i, m in enumerate(members)])
        growth = np.asarray([m.get('growth_per_second', 0) for m in members])
        if model['fit_family'] == 'coupled_profile':
            coefficients = np.asarray(model['coefficients_real']) + 1j * np.asarray(model['coefficients_imaginary'])
        else:
            coefficients = _linear(times[:training], signal[:, :training], center, selected,
                                   starts, ends, growth, times[-1], scale, bands)['amplitude']
        columns = np.concatenate([
            _basis(times[recent_begin:training], center, selected, starts, ends,
                   growth, times[-1], h) * coefficients[h] / scale[h] for h in harmonics])
        target = np.concatenate([signal[h, recent_begin:training] / scale[h] for h in harmonics])
        refreshed = refresh_gain(columns, target)
        gain = np.asarray(refreshed['gain'])
        loss = []
        for h in harmonics:
            prediction = _basis(times[training:], center, selected, starts, ends, growth,
                                times[-1], h) @ (coefficients[h] * gain)
            loss.append(float(np.mean(np.abs((prediction - signal[h, training:]) / test_scale[h]) ** 2)))
        row = dict(original[(model['mask'], model['fit_family'])])
        row['original_prediction_loss'] = row['test_prediction_loss']
        row['test_prediction_loss'] = float(np.mean(loss))
        row['amplitude_refresh'] = refreshed
        row['fit_valid'] = bool(row['fit_valid'] and refreshed['valid'])
        inspected.append(row)
    for row in inspected:
        smaller = [m for m in inspected if m['mask'].bit_count() < row['mask'].bit_count()]
        row['prediction_gain_over_best_smaller_model'] = (
            min(m['test_prediction_loss'] for m in smaller) - row['test_prediction_loss'] if smaller else None)
        common = bool(median_guard and gap_guard and len(harmonics) >= 2 and row['fit_valid'] and
                      (not smaller or (row['prediction_gain_over_best_smaller_model'] >= 0.005 and
                                       row['test_gain_over_best_smaller_model'] >= 0.005)))
        row['independent_cross_band_support'] = bool(common and row['minimum_supported_harmonics'] >= 2)
        row['one_band_per_member_profile_support'] = bool(common and row['fit_family'] == 'coupled_profile' and
                                                         row['minimum_supported_harmonics'] >= 1)
    return {'models': inspected, 'refresh_training_begin': recent_begin,
            'refresh_training_end_exclusive': training, 'test_scale_squared': (test_scale ** 2).tolist(),
            'interpretation': 'Frozen pitch, decay, phase and harmonic ratios; gains0.5..2 fit only the later half of training audio. All models, including smaller competitors, get the same causal update. Bound hits and poorly conditioned gain fits cannot qualify. Diagnostic only; no MIDI change.'}
