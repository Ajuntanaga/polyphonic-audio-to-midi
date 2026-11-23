"""Pure feature/clock/calibration contracts for the frozen NINOS2 spike.

No waveform reader, FFT, model, or native execution lives in this module.
"""
from __future__ import annotations

import math

from tools.complex_attack_baseline import score_fixture


def ninos2(magnitudes, fraction=0.955):
    """Equation 13, log1p magnitudes, lowest fixed fraction of eligible bins."""
    values = [float(x) for x in magnitudes]
    if not values or not 0 < fraction <= 1:
        raise ValueError('Invalid magnitude subset')
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError('Magnitudes must be finite and nonnegative')
    count = math.floor(fraction * len(values))
    if count < 2:
        raise ValueError('NINOS2 requires at least two retained bins')
    values = [math.log1p(x) for x in sorted(values)[:count]]
    energy = math.sqrt(math.fsum(x * x for x in values))
    if energy == 0:
        return 0.0
    norm4 = math.sqrt(math.sqrt(math.fsum(x ** 4 for x in values)))
    inverse_sparsity = (energy / norm4 - 1) / (count ** .25 - 1)
    # Analytic range is [0, 1]; only roundoff is clamped.
    return energy * min(1.0, max(0.0, inverse_sparsity))


def peak_candidates(rows, before_max_frames, before_mean_frames):
    """Past/current-only peak statistic. Missing startup history is zero."""
    if before_max_frames < 0 or before_mean_frames < 0:
        raise ValueError('Negative history')
    values, result = [], []
    previous_sample = 0
    for index, row in enumerate(rows):
        value = row['feature']
        if not math.isfinite(value) or value < 0 or row['available_sample'] <= previous_sample:
            raise ValueError('Invalid feature row')
        previous_sample = row['available_sample']
        values.append(value)
        maximum = max(values[max(0, index - before_max_frames):index + 1])
        mean = math.fsum(values[max(0, index - before_mean_frames):index + 1]) / (before_mean_frames + 1)
        strength = value - mean
        # The explicit positive test prevents a zero threshold firing on silence.
        if value == maximum and strength > 0:
            result.append({**row, 'frame': index, 'strength': strength})
    return result


def decode(candidates, threshold, refractory_frames):
    if not math.isfinite(threshold) or threshold < 0 or refractory_frames < 0:
        raise ValueError('Invalid fixed peak-picking setting')
    events, last = [], -math.inf
    for row in candidates:
        if row['strength'] >= threshold and row['frame'] - last > refractory_frames:
            events.append({
                'available_sample': row['available_sample'],
                'nominal_sample': row['available_sample'],
                'padded_samples': row['padded_samples'], 'call_ns': 0,
                'feature': row['feature'], 'strength': row['strength'],
            })
            last = row['frame']
    return events


def score(candidates, threshold, refractory_frames, geometry):
    return score_fixture(decode(candidates, threshold, refractory_frames), **geometry)


def fit_threshold(training, refractory_frames):
    """Fit only delta on the declared calibration fixtures, never test fixtures.

    Events change only immediately above a candidate strength. Enumerate those
    exact regimes (and zero), retaining the smallest delta that passes ALL
    calibration fixtures. No feasible value means no selected operating point.
    """
    if not training:
        raise ValueError('Calibration fixtures required')
    thresholds = [0.0] + sorted({math.nextafter(row['strength'], math.inf)
                                 for item in training for row in item['candidates']})
    histogram = [0] * (len(training) + 1)
    selected, feasible = None, 0
    for threshold in thresholds:
        passed = sum(score(item['candidates'], threshold, refractory_frames,
                           item['geometry'])['fixed_screen_pass'] for item in training)
        histogram[passed] += 1
        if passed == len(training):
            feasible += 1
            if selected is None:
                selected = threshold
    return {
        'selected_threshold': selected, 'calibration_pass': selected is not None,
        'threshold_regimes_evaluated': len(thresholds),
        'feasible_regimes': feasible, 'fixture_pass_histogram': histogram,
        'best_fixtures_passed': max(i for i, count in enumerate(histogram) if count),
        'fixture_total': len(training),
        'selection_rule': 'smallest threshold passing every calibration fixture; no fallback',
    }
