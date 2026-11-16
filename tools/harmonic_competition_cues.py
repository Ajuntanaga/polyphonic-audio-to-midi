"""Offline admission conditioned on independently supported lower hypotheses.

Only observed, unowned lower candidates at the training cutoff are compared.
Their presence alone cannot veto an upper note: each must predict at least two
partials beyond the fitted owned notes and proposed upper note. An upper note
must then survive comparison with each supported lower candidate's harmonics.
This frozen-shadow model is not a native real-time implementation.
"""
import numpy as np

from tools import harmonic_admission_cues as admission
from tools.candidate_outcome_analysis import _candidates
from tools.portable_ordinary_harmonic_prediction import design, harmonic_frequencies


CONFIG = dict(admission.CONFIG, lower_competition=dict(
    selection='observed unowned lower candidates at training cutoff; no labels',
    score_ratio=.20, fundamental_ratio=.20, band_score=.90, band_fund=.80,
    maximum_candidates=8,
    support='two independent supported pairs conditional on owned notes and upper partials',
    comparison='upper must survive each supported lower full harmonic series',
    overflow='withhold; never truncate candidates or owned notes',
    lower_frequency='valid saved phase; otherwise equal temperament for support, training-only fit for comparison'))


def partials(frequency):
    return [frequency * h for h in range(1, CONFIG['candidate_harmonics'] + 1)
            if frequency * h <= CONFIG['maximum_hz']]


def lower_candidates(state, note, owned):
    if state is None or state['quiet']:
        return []
    limits = CONFIG['lower_competition']
    result = []
    for lower, row in sorted(_candidates(state).items()):
        if (not CONFIG['lowest_note'] <= lower < note or lower in owned
                or row['selection'] in (4, 5) or row['active']
                or row['score_ratio'] < limits['score_ratio']
                or row['fund_ratio'] < limits['fundamental_ratio']
                or row['band_score'] < limits['band_score']
                or row['band_fund'] < limits['band_fund']
                or not row['direct'] or not (row['local'] or row['evidence'])):
            continue
        cents = row['phase_cents'] if row['phase_valid'] else 0.
        frequency = CONFIG['a4_hz'] * 2 ** ((lower - 69 + cents / 100) / 12)
        if not np.isfinite(frequency) or not 0 < frequency < CONFIG['maximum_hz']:
            raise ValueError('Unusable causal lower frequency')
        result.append(dict(note=lower, frequency_hz=frequency,
            phase_cents=cents, phase_valid=bool(row['phase_valid'])))
    return result


def prepared_with_base(prepared, base):
    train = CONFIG['train_samples']
    base = admission.normalized(base, train)
    parts = admission.factor(base[:train])
    weights = admission.coefficients(parts, prepared['signal'][:train])
    residual = prepared['signal'][train:] - base[train:] @ weights
    return dict(prepared, base=base, factor=parts,
        base_error=float(residual @ residual) / prepared['energy'])


def evaluate_candidate(window, prepared, note, state):
    original = admission.evaluate_candidate(window, prepared, note)
    result = dict(original, original_status=original['status'], lower_comparisons=[])
    if not original['admitted']:
        return result
    if (state is None or state['sample'] > window['available_sample'] - CONFIG['predict_samples']
            or state['sample'] != window['baseline_state_sample']):
        raise ValueError('Competition state differs from the causal baseline')
    owned = {pitch['note'] for pitch in window['base_pitches']}
    lowers = lower_candidates(state, note, owned)
    result['lower_candidates'] = lowers
    if len(lowers) > CONFIG['lower_competition']['maximum_candidates']:
        return dict(result, admitted=False, status='too_many_lower_candidates')
    if not lowers:
        return dict(result, status='competition_pass')

    # Reuse the original fitted parent frequencies. Do not tune the nuisance
    # model on held-out samples or let labels select the competitors.
    count = CONFIG['train_samples'] + CONFIG['predict_samples']
    tuning = original['parent_tuning']
    frequencies = (tuning['frequencies_hz'] if tuning['status'] == 'fitted'
                   else harmonic_frequencies(original['base_pitches']))
    fitted = prepared_with_base(prepared, design(frequencies, count))
    upper_hz = CONFIG['a4_hz'] * 2 ** ((note - 69) / 12)
    upper = design(partials(upper_hz), count)[:, 1:]
    _, _, independent_upper = admission.independent_pairs(
        fitted['base'], upper, CONFIG['train_samples'], fitted['factor'])
    conditional = prepared_with_base(prepared, np.column_stack((fitted['base'], independent_upper)))

    for lower in lowers:
        support = admission.evaluate_partial_support(conditional, partials(lower['frequency_hz']))
        row = dict(lower=lower, independent_lower_support=support)
        result['lower_comparisons'].append(row)
        if not support['admitted']:
            continue
        if len(owned) + 1 > CONFIG['maximum_base_notes']:
            return dict(result, admitted=False, status='too_many_comparison_parents')
        # Use original seeds, not the previously fitted invalid-phase parents:
        # otherwise the same +/-50 cent fitting bound could shift a second time.
        pitches = sorted(window['base_pitches'] + [lower], key=lambda pitch: pitch['note'])
        compared = prepared_with_base(prepared, design(harmonic_frequencies(pitches), count))
        parts = compared['factor']
        ratio = float(parts[1][-1] / parts[1][0])
        if ratio < CONFIG['full_singular_ratio_floor']:
            row['upper_comparison'] = dict(admitted=False, status='ill_conditioned_comparison_base',
                                            base_singular_ratio=ratio)
        else:
            row['upper_comparison'] = admission.evaluate_candidate(
                dict(window, base_pitches=pitches), compared, note)
        if not row['upper_comparison']['admitted']:
            return dict(result, admitted=False, status='lower_competition_withheld',
                        withholding_lower_note=lower['note'])
    return dict(result, status='competition_pass')


def generate(audio, outcome_path, cue_path, evidence_path, deadline):
    return admission.generate(audio, outcome_path, cue_path, evidence_path, deadline,
                              decision=evaluate_candidate)
