"""Offline, past-only harmonic identifiability screen; recorded audio runs on GHA.

The shadow baseline is frozen independently of the candidate replay. This is
not a measurement of a native feedback implementation or of real-time cost.
Annotations cannot enter the design, candidate selection, or cue scheduling.
"""
from collections import Counter, deque
import gzip
import json
import time

import numpy as np

from tools.candidate_outcome_analysis import HEADER, SCHEMAS, _candidates, _frame
from tools.portable_ordinary_harmonic_prediction import (
    CONFIG as PREDICTION_CONFIG, RATE, base_pitches, design, harmonic_frequencies)


CONFIG = {key: value for key, value in PREDICTION_CONFIG.items() if key != 'candidates'}
CONFIG.update(lowest_note=32, highest_note=84, minimum_independent_pairs=2,
    pair_singular_ratio_floor=1e-3, full_singular_ratio_floor=1e-4,
    numerical_guard_factor=64, score_ratio=.20, fundamental_ratio=.80,
    selection='all eligible below-threshold pitches at the past-only fixed cadence',
    baseline='frozen current detector shadow; not candidate replay feedback')
CUE_HEADER = 'm3_harmonic_admission_cues_v1\t96000\t1024\n'


def normalized(matrix, train):
    norms = np.linalg.norm(matrix[:train], axis=0)
    if np.any(norms <= np.finfo(float).tiny):
        raise ValueError('Zero design column')
    return matrix / norms


def factor(matrix):
    u, s, vt = np.linalg.svd(matrix, full_matrices=False)
    rank = int(np.count_nonzero(s >= s[0] * CONFIG['svd_relative_cutoff']))
    return u, s, vt, rank


def coefficients(parts, signal):
    u, s, vt, rank = parts
    return vt[:rank].T @ ((u[:, :rank].T @ signal) / s[:rank])


def independent_pairs(base, candidate, train, base_factor=None):
    """Candidate columns are [cos(all harmonics), sin(all harmonics)]."""
    base = normalized(base, train)
    candidate = normalized(candidate, train)
    parts = factor(base[:train]) if base_factor is None else base_factor
    q = parts[0][:, :parts[3]]
    residual = candidate[:train] - q @ (q.T @ candidate[:train])
    count = candidate.shape[1] // 2
    ratios = []
    for harmonic in range(count):
        indexes = [harmonic, harmonic + count]
        before = np.linalg.svd(candidate[:train, indexes], compute_uv=False)
        after = np.linalg.svd(residual[:, indexes], compute_uv=False)
        ratios.append(float(after[-1] / before[0]))
    passing = [index for index, ratio in enumerate(ratios)
               if ratio >= CONFIG['pair_singular_ratio_floor']]
    indexes = passing + [index + count for index in passing]
    return ratios, passing, candidate[:, indexes]


def numerical_gain_guard(base_error, added_error):
    # A conservative roundoff guard scaled by the maximum permitted squared
    # condition number. This is not a fitted audibility or note-quality floor.
    return (CONFIG['numerical_guard_factor'] * np.finfo(float).eps /
            CONFIG['full_singular_ratio_floor'] ** 2 * max(1., base_error, added_error))


def prediction_window(audio, available, state):
    train, hold = CONFIG['train_samples'], CONFIG['predict_samples']
    end, start = available + 1, available + 1 - train - hold
    result = dict(available_sample=available, window_start_sample=start,
                  baseline_state_sample=None, status='insufficient_history')
    if start < 0 or state is None:
        return result, None
    if state['sample'] > available - hold:
        raise ValueError('Baseline state uses prediction-period information')
    if end > len(audio):
        raise ValueError('Audio prefix shorter than requested sample')
    pitches = base_pitches(state)
    result.update(baseline_state_sample=state['sample'], base_pitches=pitches)
    if not pitches or len(pitches) > CONFIG['maximum_base_notes']:
        return dict(result, status='unavailable_base'), None
    signal = np.asarray(audio[start:end], dtype=float)
    if not np.isfinite(signal).all():
        raise ValueError('Nonfinite audio')
    energy = float(signal[train:] @ signal[train:])
    if energy <= np.finfo(float).tiny:
        return dict(result, status='zero_energy'), None
    frequencies = harmonic_frequencies(pitches)
    base = normalized(design(frequencies, train + hold), train)
    parts = factor(base[:train])
    ratio = float(parts[1][-1] / parts[1][0])
    result.update(base_partials=len(frequencies), base_singular_ratio=ratio)
    if ratio < CONFIG['full_singular_ratio_floor']:
        return dict(result, status='ill_conditioned_base'), None
    weights = coefficients(parts, signal[:train])
    residual = signal[train:] - base[train:] @ weights
    return dict(result, status='measured'), dict(base=base, factor=parts,
        signal=signal, energy=energy, base_error=float(residual @ residual) / energy)


def evaluate_candidate(window, prepared, note):
    result = dict(window, candidate_note=note, admitted=False)
    if prepared is None:
        return result
    if any(pitch['note'] == note for pitch in window['base_pitches']):
        return dict(result, status='already_owned')
    train = CONFIG['train_samples']
    f = CONFIG['a4_hz'] * 2 ** ((note - 69) / 12)
    frequencies = [f * h for h in range(1, CONFIG['candidate_harmonics'] + 1)
                   if f * h <= CONFIG['maximum_hz']]
    candidate = design(frequencies, train + CONFIG['predict_samples'])[:, 1:]
    ratios, passing, added = independent_pairs(prepared['base'], candidate, train, prepared['factor'])
    result.update(pair_singular_ratios=ratios, independent_harmonics=[i + 1 for i in passing])
    if len(passing) < CONFIG['minimum_independent_pairs']:
        return dict(result, status='insufficient_independent_pairs')
    full = np.column_stack((prepared['base'], added))
    parts = factor(full[:train])
    ratio = float(parts[1][-1] / parts[1][0])
    result['full_singular_ratio'] = ratio
    if ratio < CONFIG['full_singular_ratio_floor']:
        return dict(result, status='ill_conditioned_augmented_design')
    weights = coefficients(parts, prepared['signal'][:train])
    residual = prepared['signal'][train:] - full[train:] @ weights
    error = float(residual @ residual) / prepared['energy']
    base_error = prepared['base_error']
    gain = base_error - error
    guard = numerical_gain_guard(base_error, error)
    return dict(result, status='prediction_pass' if gain > guard else 'prediction_rejected',
        admitted=bool(gain > guard), base_prediction_error_fraction=base_error,
        added_prediction_error_fraction=error, prediction_gain_fraction=gain,
        numerical_gain_guard=guard)


def eligible_notes(frame):
    if frame['quiet']:
        return []
    return [note for note, row in _candidates(frame).items()
            if CONFIG['lowest_note'] <= note <= CONFIG['highest_note']
            and row['selection'] == 1 and not row['active']
            and row['score_ratio'] >= CONFIG['score_ratio']
            and row['fund_ratio'] >= CONFIG['fundamental_ratio']
            and row['band_score'] >= .90 and row['band_fund'] >= .80
            and row['direct'] and (row['local'] or row['evidence'])]


def causal_states(stream, samples):
    if stream.readline() not in SCHEMAS or stream.readline() != HEADER:
        raise ValueError('Unsupported shadow outcome schema')
    recent = deque(maxlen=1 + CONFIG['predict_samples'] // 64)
    count = 0
    for count, line in enumerate(stream, 1):
        fields = line.rstrip('\n').split('\t')
        if len(fields) != 8:
            raise ValueError('Malformed shadow outcome')
        # Labels and match decisions are not observable inputs to this model.
        fields[4] = fields[5] = ''
        frame = _frame('\t'.join(fields) + '\n')
        if (frame['sample'], frame['tick']) != (count * 64 - 1, count):
            raise ValueError('Incomplete shadow outcome clock')
        recent.append(frame)
        if (frame['sample'] + 1) % CONFIG['stride_samples'] == 0 and count * 64 < samples:
            old = recent[0] if len(recent) == recent.maxlen else None
            yield frame['sample'], old, frame
    if count != samples // 64:
        raise ValueError('Incomplete shadow outcome length')


def generate(audio, outcome_path, cue_path, evidence_path, deadline):
    statuses, notes = Counter(), Counter()
    windows = observations = admitted = 0
    with outcome_path.open() as states, cue_path.open('w') as cues, gzip.open(evidence_path, 'wt') as evidence:
        cues.write(CUE_HEADER)
        for available, state, current in causal_states(states, len(audio)):
            if time.monotonic() >= deadline:
                raise TimeoutError('Harmonic admission cue budget exhausted')
            windows += 1
            eligible = eligible_notes(current)
            if not eligible:
                continue
            window, prepared = prediction_window(audio, available, state)
            for note in sorted(eligible):
                row = evaluate_candidate(window, prepared, note)
                statuses[row['status']] += 1
                observations += 1
                if row['admitted']:
                    begin = available + 1
                    cues.write(f'{begin}\t{min(begin + CONFIG["stride_samples"], len(audio))}\t{note}\n')
                    notes[note] += 1
                    admitted += 1
                evidence.write(json.dumps(row, allow_nan=False) + '\n')
    return dict(windows=windows, observations=observations, statuses=dict(statuses),
                cue_spans=admitted, cue_spans_by_note=dict(sorted(notes.items())))
