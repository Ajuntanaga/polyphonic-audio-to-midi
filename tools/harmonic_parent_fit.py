"""Bounded training-only tuning fit for owned notes lacking a phase estimate.

This offline nuisance fit never sees labels or prediction audio. Proposed
partials have free amplitudes rather than being forced into parent tuning.
Existing valid phase estimates remain fixed. A single frequency parameter moves
all harmonics of each unresolved parent; amplitudes are eliminated linearly.
"""
import numpy as np
from scipy.optimize import least_squares

from tools.portable_ordinary_harmonic_prediction import RATE, design


FIT_CONFIG = dict(method='training-only variable projection for phase-invalid parents, conditional on proposed partials',
    bounds_cents=50., max_evaluations=12, tolerance=float(np.sqrt(np.finfo(float).eps)),
    partials='fixed harmonic indices selected at the seed; frequencies may cross 3000Hz',
    failure='withhold admission on rank loss, boundary, or nonconvergence')


def refine_parents(training, pitches, config, proposed_frequencies):
    """Return fitted pitches and evidence, or None when the fit is unusable."""
    unknown = [i for i, pitch in enumerate(pitches) if not pitch['phase_valid']]
    if not unknown:
        return pitches, dict(status='saved_phase', evaluations=0)
    if len(training) != config['train_samples']:
        raise ValueError('Parent fit requires exactly the training prefix')
    scale = float(np.linalg.norm(training))
    if not np.isfinite(scale) or scale <= np.finfo(float).tiny:
        return None, dict(status='unavailable_training_signal', evaluations=0)
    signal = np.asarray(training, dtype=float) / scale
    owners, harmonics = [], []
    for owner, pitch in enumerate(pitches):
        for harmonic in range(1, int(config['maximum_hz'] // pitch['frequency_hz']) + 1):
            owners.append(owner)
            harmonics.append(harmonic)
    owners, harmonics = np.asarray(owners), np.asarray(harmonics)
    seed = np.asarray([pitch['frequency_hz'] for pitch in pitches])
    time = np.arange(len(training), dtype=float) / RATE
    cache = {}
    evaluations = 0

    def solve(cents):
        nonlocal evaluations
        if 'cents' in cache and np.array_equal(cents, cache['cents']):
            return cache
        evaluations += 1
        fundamentals = seed.copy()
        fundamentals[unknown] *= 2 ** (cents / 1200.)
        parent_frequencies = fundamentals[owners] * harmonics
        frequencies = np.r_[parent_frequencies, proposed_frequencies]
        matrix = design(frequencies, len(training))
        norms = np.linalg.norm(matrix, axis=0)
        matrix /= norms
        u, s, vt = np.linalg.svd(matrix, full_matrices=False)
        if s[-1] / s[0] < config['full_singular_ratio_floor']:
            # Do not invent separate tuning for mathematically shared columns,
            # or fall back to a known-mistuned model after a failed fit.
            raise ValueError('unidentifiable_parent_fit')
        weights = vt.T @ ((u.T @ signal) / s)
        residual = signal - matrix @ weights
        phase = 2 * np.pi * time[:, None] * frequencies[None, :]
        jacobian = np.empty((len(training), len(unknown)))
        for column, owner in enumerate(unknown):
            indices = np.flatnonzero(owners == owner)
            columns = np.r_[1 + indices, 1 + len(frequencies) + indices]
            derivative_phase = phase[:, indices] * np.log(2) / 1200.
            derivative = np.column_stack((-np.sin(phase[:, indices]) * derivative_phase,
                                            np.cos(phase[:, indices]) * derivative_phase))
            derivative /= norms[columns]
            direction = derivative @ weights[columns]
            normal = np.zeros(matrix.shape[1])
            normal[columns] = derivative.T @ residual
            # Exact variable-projection residual derivative, including the
            # term that matters when an unmodeled independent note is present.
            jacobian[:, column] = -(direction - u @ (u.T @ direction)) - u @ ((vt @ normal) / s)
        cache.update(cents=cents.copy(), residual=residual, jacobian=jacobian,
                     fundamentals=fundamentals, singular_ratio=float(s[-1] / s[0]))
        return cache

    try:
        initial = solve(np.zeros(len(unknown)))
        initial_error = float(initial['residual'] @ initial['residual'])
        tolerance = FIT_CONFIG['tolerance']
        result = least_squares(lambda x: solve(x)['residual'], np.zeros(len(unknown)),
            jac=lambda x: solve(x)['jacobian'], bounds=(-FIT_CONFIG['bounds_cents'], FIT_CONFIG['bounds_cents']),
            max_nfev=FIT_CONFIG['max_evaluations'], ftol=tolerance, xtol=tolerance, gtol=tolerance)
        final = solve(result.x)
    except (ValueError, np.linalg.LinAlgError) as error:
        return None, dict(status=str(error), evaluations=evaluations)
    evidence = dict(status='fitted', evaluations=evaluations,
        optimizer_status=int(result.status), proposed_partials=len(proposed_frequencies),
        initial_training_error_fraction=initial_error,
        final_training_error_fraction=float(final['residual'] @ final['residual']),
        singular_ratio=final['singular_ratio'], notes=[pitches[i]['note'] for i in unknown],
        offsets_cents=result.x.tolist())
    if not result.success or np.any(result.active_mask):
        evidence['status'] = 'parent_fit_nonconvergence_or_boundary'
        return None, evidence
    fitted = [dict(pitch, frequency_hz=float(final['fundamentals'][i]))
              for i, pitch in enumerate(pitches)]
    # Use the exact fixed-index training design for prediction as well.
    evidence['frequencies_hz'] = (final['fundamentals'][owners] * harmonics).tolist()
    return fitted, evidence
