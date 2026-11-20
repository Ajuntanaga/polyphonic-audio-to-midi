"""Training-only frequency refinement for an offline diagnostic, never MIDI policy."""
import numpy as np
from scipy.optimize import least_squares
from tools.cross_pitch_shape_fit import fit_shape


def fit_refined_shape(samples, rate, fundamentals, *, input_role, harmonics=6, frozen_prefix=0):
    # Existing fitter validates all inputs and supplies the unchanged comparison.
    baseline = fit_shape(samples, rate, fundamentals, input_role=input_role,
                         harmonics=harmonics)
    if baseline.get('abstention') == 'silent_training':
        return {'baseline': baseline, 'refinement_abstention': 'silent_training'}
    if type(frozen_prefix) is not int or not 0 <= frozen_prefix < len(fundamentals):
        raise ValueError("Expected at least one free frequency")
    y = np.asarray(samples, dtype=float)
    f0 = np.asarray(fundamentals, dtype=float)
    split = len(y) // 2
    train = y[:split]
    t = np.arange(split) / rate
    weight = np.sqrt(np.hanning(split))
    scale = np.sqrt(np.mean((train - train.mean()) ** 2))
    bound = 35.0
    if np.max(f0) * 2 ** (bound / 1200) * harmonics >= rate / 2:
        raise ValueError('Refinement search exceeds Nyquist')

    def residual(free_cents):
        cents = np.concatenate((np.zeros(frozen_prefix), free_cents))
        frequencies = (f0[:, None] * 2 ** (cents[:, None] / 1200)
                       * np.arange(1, harmonics + 1)).ravel()
        phase = 2 * np.pi * t[:, None] * frequencies
        basis = np.column_stack((np.ones(split), np.cos(phase), np.sin(phase)))
        design = basis * weight[:, None]
        target = train * weight
        coefficients = np.linalg.lstsq(design, target, rcond=1e-8)[0]
        return (design @ coefficients - target) / scale

    fitted = least_squares(residual, np.zeros(len(f0) - frozen_prefix), bounds=(-bound, bound),
                           max_nfev=60, ftol=1e-8, xtol=1e-8, gtol=1e-8)
    cents = np.concatenate((np.zeros(frozen_prefix), fitted.x))
    frequencies = f0 * 2 ** (cents / 1200)
    result = fit_shape(y, rate, frequencies, input_role=input_role, harmonics=harmonics)
    return {'baseline': baseline, 'refined': result,
            'refinement': {'cents': cents.tolist(), 'frozen_prefix': frozen_prefix, 'bound_cents': bound,
                           'success': bool(fitted.success), 'nfev': fitted.nfev,
                           'at_boundary': bool(np.any(np.abs(fitted.x) >= bound - .01)),
                           'fit_samples': split, 'validation_used_for_selection': False,
                           'pitch_membership_changed': False},
            'policy_admission': False}


def fit_paired_addition(samples, rate, fundamentals, candidate_hz, *, input_role, harmonics=6):
    """Fit competitors on training, freeze their frequencies, then test one addition."""
    base = fit_refined_shape(samples, rate, fundamentals,
                             input_role=input_role, harmonics=harmonics)
    if (base.get('refinement_abstention') or
            not base['refinement']['success'] or base['refinement']['at_boundary'] or
            not base['refined']['shape_available']):
        return {'without': base, 'abstention': 'invalid_competing_fit', 'policy_admission': False}
    frozen = base['refined']['fundamentals_hz']
    added = fit_refined_shape(samples, rate, [*frozen, candidate_hz],
                              input_role=input_role, harmonics=harmonics,
                              frozen_prefix=len(frozen))
    valid = (added['refinement']['success'] and not added['refinement']['at_boundary']
             and added['refined']['shape_available'])
    result = {'without': base, 'with': added, 'comparison_available': valid,
              'competing_frequencies_frozen': True, 'coefficients_refit_on_training': True,
              'validation_used_for_selection': False, 'policy_admission': False}
    if valid:
        result['validation_residual_reduction'] = (
            base['refined']['validation_residual_ratio'] - added['refined']['validation_residual_ratio'])
    else:
        result['abstention'] = 'invalid_augmented_fit'
    return result
