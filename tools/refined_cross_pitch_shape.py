"""Training-only frequency refinement for an offline diagnostic, never MIDI policy."""
import numpy as np
from scipy.optimize import least_squares
from tools.cross_pitch_shape_fit import fit_shape


def fit_refined_shape(samples, rate, fundamentals, *, input_role, harmonics=6):
    # Existing fitter validates all inputs and supplies the unchanged comparison.
    baseline = fit_shape(samples, rate, fundamentals, input_role=input_role,
                         harmonics=harmonics)
    if baseline.get('abstention') == 'silent_training':
        return {'baseline': baseline, 'refinement_abstention': 'silent_training'}
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

    def residual(cents):
        frequencies = (f0[:, None] * 2 ** (cents[:, None] / 1200)
                       * np.arange(1, harmonics + 1)).ravel()
        phase = 2 * np.pi * t[:, None] * frequencies
        basis = np.column_stack((np.ones(split), np.cos(phase), np.sin(phase)))
        design = basis * weight[:, None]
        target = train * weight
        coefficients = np.linalg.lstsq(design, target, rcond=1e-8)[0]
        return (design @ coefficients - target) / scale

    fitted = least_squares(residual, np.zeros(len(f0)), bounds=(-bound, bound),
                           max_nfev=60, ftol=1e-8, xtol=1e-8, gtol=1e-8)
    frequencies = f0 * 2 ** (fitted.x / 1200)
    result = fit_shape(y, rate, frequencies, input_role=input_role, harmonics=harmonics)
    return {'baseline': baseline, 'refined': result,
            'refinement': {'cents': fitted.x.tolist(), 'bound_cents': bound,
                           'success': bool(fitted.success), 'nfev': fitted.nfev,
                           'at_boundary': bool(np.any(np.abs(fitted.x) >= bound - .01)),
                           'fit_samples': split, 'validation_used_for_selection': False,
                           'pitch_membership_changed': False},
            'policy_admission': False}
