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
    result['frozen_background'] = frozen_background(signal, full, base_columns, passing, train)
    result['shared_background_gain'] = frozen_background(
        signal, full, base_columns, passing, train, adapt_gain=True)
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


def frozen_background(signal, full, base_columns, passing, train, adapt_gain=False):
    """Conditional observation with nuisance coefficients frozen from training.

    Unlike independent segment fits, this cannot let a flexible background absorb
    the candidate in the short prediction segment. Background evolution can still
    contaminate the estimate: this is not an independent source-presence verdict.
    """
    norms = np.linalg.norm(full[:train], axis=0)
    if np.any(norms <= np.finfo(float).tiny):
        return dict(available=False, reason='zero_training_column')
    scaled = full / norms
    parts = admission.factor(scaled[:train])
    ratio = float(parts[1][-1] / parts[1][0])
    result = dict(available=False, training_singular_ratio=ratio,
                  assumption=('one common nuisance gain after training' if adapt_gain else
                              'nuisance coefficients stationary after training'),
                  interpretation='conditional fit, not proof of source presence or onset')
    if parts[3] != full.shape[1] or ratio < admission.CONFIG['full_singular_ratio_floor']:
        return dict(result, reason='unidentifiable_training_fit')
    weights = admission.coefficients(parts, signal[:train])
    background = scaled[:, :base_columns] @ weights[:base_columns]
    residual = signal[train:] - background[train:]
    candidate = scaled[train:, base_columns:]
    if adapt_gain:
        # Only one fitted background waveform may change amplitude. Individual
        # nuisance harmonics remain tied to their training coefficients.
        candidate = np.column_stack((background[train:], candidate))
        residual = signal[train:]
        if np.linalg.norm(background[train:]) <= np.finfo(float).eps * max(1., np.linalg.norm(signal[:train])):
            return dict(result, reason='no_resolvable_background_gain')
    candidate_norms = np.linalg.norm(candidate, axis=0)
    if np.any(candidate_norms <= np.finfo(float).tiny):
        return dict(result, reason='zero_prediction_column')
    fit = admission.factor(candidate / candidate_norms)
    prediction_ratio = float(fit[1][-1] / fit[1][0])
    result['prediction_singular_ratio'] = prediction_ratio
    if fit[3] != candidate.shape[1] or prediction_ratio < admission.CONFIG['full_singular_ratio_floor']:
        return dict(result, reason='unidentifiable_prediction_candidate')
    updated = admission.coefficients(fit, residual) / candidate_norms
    before_weights = (np.r_[1., weights[base_columns:]] if adapt_gain else weights[base_columns:])
    before = residual - candidate @ before_weights
    after = residual - candidate @ updated
    result.update(available=True, partials=[],
                  frozen_residual_mean_square=float(np.mean(before**2)),
                  adapted_residual_mean_square=float(np.mean(after**2)))
    if adapt_gain:
        result['background_gain'] = float(updated[0])
        updated = updated[1:]
    count = len(passing)
    for i, harmonic in enumerate(passing):
        a, b = weights[base_columns+i], weights[base_columns+count+i]
        c, d = updated[i], updated[count+i]
        result['partials'].append(dict(harmonic=harmonic+1,
            training_coefficient_power=float(a*a+b*b),
            prediction_coefficient_power=float(c*c+d*d),
            training_phase_radians=float(np.arctan2(b,a)),
            prediction_phase_radians=float(np.arctan2(d,c))))
    return result
