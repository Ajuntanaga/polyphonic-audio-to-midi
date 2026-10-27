"""Offline joint pitch/decay/phase fits with bounded harmonic-power variation.

Ascending isolated attacks supply power profiles. No evaluation labels or
desired source count enter fitting. This experiment never changes MIDI.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
from scipy.optimize import least_squares

try:
    from .joint_harmonic_fit import _validate
    from .harmonic_drift_fit import _basis, _linear
except ImportError:
    from joint_harmonic_fit import _validate
    from harmonic_drift_fit import _basis, _linear


PROFILE_LOG_POWER_SIGMA = math.log(2)  # 3.01 dB: a broad modeling assumption.
PROFILE_LOG_POWER_LIMIT = 2 * PROFILE_LOG_POWER_SIGMA
PROFILE_PENALTY = 0.01


def _transfer(frequencies, growth, rate):
    decay = math.exp(-1 / (0.040 * rate))
    return (1 - decay) / (1 - decay * np.exp(
        -(growth[None, :] + 2j * np.pi * frequencies) / rate))


def fit_mask(times, signal, center, sources, training, rate, prototypes, bands,
             seeds, maximum_starts=4):
    count = len(sources)
    harmonics = np.asarray([h for h in range(3) if bands & (1 << h)])
    band_count = len(harmonics)
    prior = np.asarray([prototypes[str(s['string'])] for s in sources]).T
    prior = np.maximum(prior[harmonics], 1e-12)
    prior /= prior.sum(axis=0)
    partials = np.asarray([s['partial_cents'] for s in sources]).T
    energy = np.mean(np.abs(signal[:, :training]) ** 2, axis=1)
    energy[[h for h in range(3) if h not in harmonics]] = 0
    scale = np.sqrt(np.maximum(energy, max(float(energy.max()), 1e-30) * 1e-3))
    unit = max(float(np.sqrt(energy.sum())), 1e-15)

    def unpack(parameters):
        cents, growth = parameters[:count], parameters[count:2 * count]
        amplitude = unit * np.exp(parameters[2 * count:3 * count])
        phase = parameters[3 * count:(3 + band_count) * count].reshape(band_count, count)
        tilt = np.zeros((band_count, count))
        if band_count > 1:
            tilt[1:] = parameters[(3 + band_count) * count:].reshape(band_count - 1, count)
        profile = prior * np.exp(tilt)
        profile /= profile.sum(axis=0)
        frequency = np.arange(1, 4)[:, None] * center * (
            np.exp2((cents[None, :] + partials) / 1200) - 1)
        coefficients = np.zeros((3, count), dtype=complex)
        coefficients[harmonics] = (amplitude[None, :] * np.sqrt(profile) * np.exp(1j * phase) *
                                   _transfer(frequency, growth, rate)[harmonics])
        return cents, growth, coefficients, frequency, tilt, profile

    def prediction(parameters, selected_times):
        _, growth, coefficients, frequency, _, _ = unpack(parameters)
        return np.sum(coefficients[:, None, :] * np.exp(
            selected_times[None, :, None] * (growth[None, None, :] +
                                           2j * np.pi * frequency[:, None, :])), axis=2)

    def residual(parameters):
        values = ((prediction(parameters, times[:training]) - signal[:, :training]) /
                  scale[:, None])[harmonics]
        data = np.concatenate((values.real.ravel(), values.imag.ravel())) / math.sqrt(training * band_count)
        tilt = unpack(parameters)[4]
        return np.concatenate((data, math.sqrt(PROFILE_PENALTY) * tilt[1:].ravel() /
                               PROFILE_LOG_POWER_SIGMA))

    lower = np.asarray([-50] * count + [-1] * count + [-15] * count +
                       [-4 * math.pi] * (band_count * count) +
                       [-PROFILE_LOG_POWER_LIMIT] * ((band_count - 1) * count))
    upper = np.asarray([50] * count + [1] * count + [5] * count +
                       [4 * math.pi] * (band_count * count) +
                       [PROFILE_LOG_POWER_LIMIT] * ((band_count - 1) * count))
    starts = []
    for seed in seeds:
        initial_cents = [m.get('cents', m.get('cents_at_start')) for m in seed['members']]
        initial_growth = np.asarray([m.get('growth_per_second', 0) for m in seed['members']])
        for permutation in itertools.permutations(range(count)):
            cents = np.asarray(initial_cents)[list(permutation)]
            growth = initial_growth[list(permutation)]
            linear = _linear(times[:training], signal[:, :training], center, sources,
                             cents, cents, growth, times[-1], scale, bands)
            frequencies = np.arange(1, 4)[:, None] * center * (
                np.exp2((cents[None, :] + partials) / 1200) - 1)
            coefficients = (linear['amplitude'] / _transfer(frequencies, growth, rate))[harmonics]
            powers = np.abs(coefficients) ** 2
            magnitudes = np.sqrt(powers.sum(axis=0))
            ratios = np.log(np.maximum(powers[1:], 1e-30) / np.maximum(powers[:1], 1e-30))
            expected_ratios = np.log(prior[1:] / prior[:1])
            parameters = np.concatenate((cents, growth, np.log(np.maximum(magnitudes / unit, 1e-8)),
                                          np.angle(coefficients).ravel(), (ratios - expected_ratios).ravel()))
            starts.append(np.clip(parameters, lower + 1e-6, upper - 1e-6))
    if not starts:
        raise ValueError('a label-free signal-fit seed is required')
    starts.sort(key=lambda parameters: float(np.sum(residual(parameters) ** 2)))
    best = None
    for start in starts[:maximum_starts]:
        fitted = least_squares(residual, start, bounds=(lower, upper), max_nfev=200,
                               ftol=1e-8, xtol=1e-8, gtol=1e-8)
        value = float(np.sum(fitted.fun ** 2))
        if best is None or value < best[0]:
            best = value, fitted
    objective, fitted = best
    cents, growth, coefficients, frequencies, tilt, profile = unpack(fitted.x)
    train_error = np.mean(np.abs((prediction(fitted.x, times[:training]) -
                                 signal[:, :training]) / scale[:, None]) ** 2, axis=1)
    test_error = np.mean(np.abs((prediction(fitted.x, times[training:]) -
                                signal[:, training:]) / scale[:, None]) ** 2, axis=1)

    def refit(begin, end, positions):
        return _linear(times[begin:end], signal[:, begin:end], center,
                       [sources[i] for i in positions], cents[positions], cents[positions],
                       growth[positions], times[-1], scale, bands)

    positions = list(range(count))
    train = refit(0, training, positions)
    test = refit(training, len(times), positions)
    members = []
    for i, source in enumerate(sources):
        others = [j for j in positions if j != i]
        train_support = refit(0, training, others)['loss'] - train['loss']
        test_support = refit(training, len(times), others)['loss'] - test['loss']
        supported = ((train_support >= 0.005) & (test_support >= 0.005) &
                     (train['conditioning'] > 1e-4) & (test['conditioning'] > 1e-4))
        members.append({'string': source['string'], 'cents': float(cents[i]),
                        'growth_per_second': float(growth[i]),
                        'fitted_profile': profile[:, i].tolist(),
                        'profile_change_db': (10 * tilt[:, i] / math.log(10)).tolist(),
                        'training_support_by_harmonic': train_support.tolist(),
                        'test_support_by_harmonic': test_support.tolist(),
                        'supported_harmonics': int(supported.sum())})
    return {'mask': sum(1 << s['string'] for s in sources), 'fit_family': 'coupled_profile',
            'members': members, 'converged': bool(fitted.success),
            'coefficients_real': coefficients.real.tolist(),
            'coefficients_imaginary': coefficients.imag.tolist(),
            'training_objective': objective, 'training_loss': float(train_error[harmonics].mean()),
            'test_prediction_loss': float(test_error[harmonics].mean()),
            'test_refit_loss': float(test['loss'][harmonics].mean()),
            'at_pitch_boundary': bool(np.any(np.abs(cents) >= 49.9)),
            'at_growth_boundary': bool(np.any(np.abs(growth) >= 0.999)),
            'at_profile_boundary': bool(np.any(np.abs(tilt) >= PROFILE_LOG_POWER_LIMIT - 1e-4)),
            'minimum_supported_harmonics': min(m['supported_harmonics'] for m in members),
            'comparison_harmonic_mask': bands}


def current_energy_audit(times, signal, center, sources, training, bands, models,
                         median_guard, gap_guard):
    """Rescore frozen fits at the later signal level; never refit frequencies.

    Both model and competitors use the same current-band denominator. The old
    training-derived noise floor remains in force, including through silence.
    """
    training_energy = np.mean(np.abs(signal[:, :training]) ** 2, axis=1)
    test_energy = np.mean(np.abs(signal[:, training:]) ** 2, axis=1)
    harmonics = np.asarray([h for h in range(3) if bands & (1 << h)])
    floor = max(float(training_energy[harmonics].max()), 1e-30) * 1e-3
    training_scale = np.sqrt(np.maximum(training_energy, floor))
    test_scale = np.sqrt(np.maximum(test_energy, max(floor, float(test_energy[harmonics].max()) * 1e-3)))
    by_string = {s['string']: s for s in sources}
    inspected = []
    for model in models:
        members = model['members']
        selected = [by_string[m['string']] for m in members]
        starts = np.asarray([m.get('cents', m.get('cents_at_start')) for m in members])
        ends = np.asarray([m.get('cents_at_end', starts[i]) for i, m in enumerate(members)])
        growth = np.asarray([m.get('growth_per_second', 0) for m in members])

        def solve(begin, end, scale, positions):
            return _linear(times[begin:end], signal[:, begin:end], center,
                           [selected[i] for i in positions], starts[positions], ends[positions],
                           growth[positions], times[-1], scale, bands)

        positions = list(range(len(members)))
        train = solve(0, training, training_scale, positions)
        test = solve(training, len(times), test_scale, positions)
        if model['fit_family'] == 'coupled_profile':
            amplitudes = np.asarray(model['coefficients_real']) + 1j * np.asarray(model['coefficients_imaginary'])
        else:
            amplitudes = train['amplitude']
        prediction = np.zeros_like(signal[:, training:])
        for h in harmonics:
            prediction[h] = _basis(times[training:], center, selected, starts, ends,
                                    growth, times[-1], h) @ amplitudes[h]
        error = np.mean(np.abs((prediction - signal[:, training:]) / test_scale[:, None]) ** 2, axis=1)
        counts = []
        for i in positions:
            others = [j for j in positions if j != i]
            training_gain = solve(0, training, training_scale, others)['loss'] - train['loss']
            test_gain = solve(training, len(times), test_scale, others)['loss'] - test['loss']
            counts.append(int(((training_gain >= 0.005) & (test_gain >= 0.005) &
                               (train['conditioning'] > 1e-4) & (test['conditioning'] > 1e-4)).sum()))
        inspected.append({'mask': model['mask'], 'fit_family': model['fit_family'],
                          'test_prediction_loss': float(error[harmonics].mean()),
                          'test_refit_loss': float(test['loss'][harmonics].mean()),
                          'minimum_supported_harmonics': min(counts),
                          'supported_harmonics_per_member': counts,
                          'fit_valid': bool(model['converged'] and not model.get('at_pitch_boundary', False) and
                                            not model.get('at_growth_boundary', False) and
                                            not model.get('at_profile_boundary', False))})
    for model in inspected:
        smaller = [m for m in inspected if m['mask'].bit_count() < model['mask'].bit_count()]
        model['prediction_gain_over_best_smaller_model'] = (
            min(m['test_prediction_loss'] for m in smaller) - model['test_prediction_loss'] if smaller else None)
        model['test_gain_over_best_smaller_model'] = (
            min(m['test_refit_loss'] for m in smaller) - model['test_refit_loss'] if smaller else None)
        common = bool(median_guard and gap_guard and len(harmonics) >= 2 and model['fit_valid'] and
                      (not smaller or (model['prediction_gain_over_best_smaller_model'] >= 0.005 and
                                       model['test_gain_over_best_smaller_model'] >= 0.005)))
        model['independent_cross_band_support'] = bool(common and model['minimum_supported_harmonics'] >= 2)
        model['one_band_per_member_profile_support'] = bool(common and model['fit_family'] == 'coupled_profile' and
                                                           model['minimum_supported_harmonics'] >= 1)
    return {'models': inspected, 'training_band_power': training_energy.tolist(),
            'test_band_power': test_energy.tolist(), 'training_noise_floor': floor,
            'test_scale_squared': (test_scale ** 2).tolist(),
            'interpretation': 'Only confidence scoring changes. Fits remain trained on older audio. Every model shares the current-band denominator, with the original training-derived noise floor. Single-band-only windows cannot qualify. This is an offline alternative, not a production admission rule.'}


def fit_window(times, signal, center, note, sources, training, rate, prototypes, control):
    times, signal = _validate(times, signal, center, note, sources, training)
    if rate <= 0:
        raise ValueError('invalid sample rate')
    bands = 7
    for source in sources:
        profile = prototypes[str(source['string'])]
        if len(profile) != 3 or not np.isfinite(profile).all() or min(profile) < 0 or sum(profile) <= 0:
            raise ValueError('invalid measured power profile')
        bands &= source['valid_mask']
    maximum_frequency = max(abs((h + 1) * center * (2 ** ((edge + source['partial_cents'][h]) / 1200) - 1))
                            for source in sources for h in range(3) if bands & (1 << h)
                            for edge in (-50, 50))
    median_guard = maximum_frequency < 0.5 / float(np.median(np.diff(times)))
    gap_guard = maximum_frequency < 0.5 / float(np.max(np.diff(times)))
    models = []
    for count in range(1, min(4, len(sources)) + 1):
        for selected in itertools.combinations(sorted(sources, key=lambda s: s['string']), count):
            mask = sum(1 << s['string'] for s in selected)
            seeds = [m for m in control if m['mask'] == mask and m['fit_family'] in ('static', 'gain_drift')]
            models.append(fit_mask(times, signal, center, list(selected), training, rate,
                                   prototypes, bands, seeds))
    for model in models:
        smaller = [m for m in models + control if m['mask'].bit_count() < model['mask'].bit_count()]
        model['prediction_gain_over_best_smaller_model'] = (
            min(m['test_prediction_loss'] for m in smaller) - model['test_prediction_loss'] if smaller else None)
        model['test_gain_over_best_smaller_model'] = (
            min(m['test_refit_loss'] for m in smaller) - model['test_refit_loss'] if smaller else None)
        common = (median_guard and gap_guard and bands.bit_count() >= 2 and model['converged'] and not model['at_pitch_boundary'] and
                  not model['at_growth_boundary'] and not model['at_profile_boundary'] and
                  (not smaller or (model['prediction_gain_over_best_smaller_model'] >= 0.005 and
                                   model['test_gain_over_best_smaller_model'] >= 0.005)))
        model['independent_cross_band_support'] = bool(common and model['minimum_supported_harmonics'] >= 2)
        # Diagnostic alternative for a string with a naturally weak overtone.
        # This alone is insufficient to admit a production voice.
        model['one_band_per_member_profile_support'] = bool(common and model['minimum_supported_harmonics'] >= 1)
    return {'models': models, 'comparison_harmonic_mask': bands,
            'current_energy_audit': current_energy_audit(times, signal, center, sources, training,
                                                       bands, models + control, median_guard, gap_guard),
            'median_spacing_guard_passed': median_guard, 'conservative_spacing_guard_passed': gap_guard,
            'profile_variation_sigma_db': 10 * PROFILE_LOG_POWER_SIGMA / math.log(10),
            'profile_variation_limit_db': 10 * PROFILE_LOG_POWER_LIMIT / math.log(10),
            'profile_penalty': PROFILE_PENALTY,
            'interpretation': 'Pitch, decay, complex phase and bounded harmonic balance fit older samples only. Newer audio scores frozen prediction and separate amplitude refit. Ascending measured profiles have a deliberately broad 3-dB modeling scale and 6-dB limit; these are assumptions, not estimated confidence intervals. Larger masks compete with all smaller unconstrained and profile models. No MIDI output changes.'}
