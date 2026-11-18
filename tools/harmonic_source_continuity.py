"""Diagnostic only: resolve lower-partial changes within an observed window.

Fits three disjoint, already available segments using the same frozen nuisance
model. This distinguishes loss of energy from poor forward prediction without
calling either observation a re-pick. It never emits cues or changes admission.
"""
import numpy as np

from tools import harmonic_admission_cues as admission
from tools.portable_ordinary_harmonic_prediction import design


def measure(prepared, frequencies):
    train = admission.CONFIG['train_samples']
    total = train + admission.CONFIG['predict_samples']
    signal = prepared['signal']
    if len(signal) != total or len(prepared['base']) != total:
        raise ValueError('Continuity requires exactly the observed prediction window')
    candidate = design(frequencies, total)[:, 1:]
    _, passing, added = admission.independent_pairs(
        prepared['base'], candidate, train, prepared['factor'])
    result = dict(status='unavailable', independent_harmonics=[i + 1 for i in passing],
                  segments=[], interpretation='energy/phase observations, not acoustic onset labels')
    if not passing:
        return dict(result, reason='no_independent_lower_partials')
    full = np.column_stack((prepared['base'], added))
    base_columns = prepared['base'].shape[1]
    count = len(passing)
    for name, begin, end in (('early_train', 0, train // 2),
                             ('late_train', train // 2, train),
                             ('observed_prediction', train, total)):
        matrix = full[begin:end]
        norms = np.linalg.norm(matrix, axis=0)
        row = dict(name=name, begin_offset=begin, end_offset=end, available=False)
        result['segments'].append(row)
        if np.any(norms <= np.finfo(float).tiny):
            row['reason'] = 'zero_column'
            continue
        scaled = matrix / norms
        nuisance = admission.factor(scaled[:, :base_columns])
        q = nuisance[0][:, :nuisance[3]]
        proposed = scaled[:, base_columns:]
        independent = proposed - q @ (q.T @ proposed)
        independent_values = np.linalg.svd(independent, compute_uv=False)
        proposed_scale = np.linalg.svd(proposed, compute_uv=False)[0]
        row.update(nuisance_columns=base_columns, nuisance_rank=nuisance[3],
                   proposed_columns=proposed.shape[1],
                   conditional_singular_ratio=float(independent_values[-1] / proposed_scale))
        # Geometry only: do not reinterpret a truncated nuisance fit as proof
        # that the source vanished, or relax the original availability gate.
        parts = admission.factor(scaled)
        ratio = float(parts[1][-1] / parts[1][0])
        row['singular_ratio'] = ratio
        if parts[3] != matrix.shape[1] or ratio < admission.CONFIG['full_singular_ratio_floor']:
            row['reason'] = 'unidentifiable_segment'
            continue
        weights = admission.coefficients(parts, signal[begin:end]) / norms
        residual = signal[begin:end] - matrix @ weights
        row.update(available=True, residual_mean_square=float(np.mean(residual ** 2)), partials=[])
        for index, harmonic in enumerate(passing):
            # Same training-normalized sinusoidal columns in all three segments;
            # powers are comparable across segments, not raw source amplitudes.
            a, b = weights[base_columns + index], weights[base_columns + count + index]
            row['partials'].append(dict(harmonic=harmonic + 1,
                coefficient_power=float(a*a + b*b), phase_radians=float(np.arctan2(b, a))))
    result['status'] = ('measured' if all(r['available'] for r in result['segments'])
                        else 'partially_unavailable')
    return result
