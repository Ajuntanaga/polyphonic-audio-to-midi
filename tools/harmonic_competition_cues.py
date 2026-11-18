"""Offline admission conditioned on independently supported lower hypotheses.

Only observed, unowned lower candidates at the training cutoff are compared.
Their presence alone cannot veto an upper note: each must predict at least two
partials beyond the fitted owned notes and proposed upper note. An upper note
must then survive each measurable comparison with a supported lower candidate's
harmonics. An unavailable comparison cannot overturn the original admission.
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
    comparison='upper support conditional on frozen fitted ownership and fixed supported lower full series',
    unavailable='retain original admission and record incomplete comparison',
    overflow='withhold; never truncate candidates or owned notes',
    lower_frequency='valid saved phase; otherwise equal temperament, fixed for support and comparison'))

MEASURED_REJECTIONS = frozenset((
    'insufficient_independent_pairs', 'prediction_rejected', 'insufficient_supported_pairs'))


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


def fundamental_comparison(prepared, frequency):
    """Experimental veto check, only after original two-partial admission.

    Fit the fundamental alone against the complete competing background; do not
    count a shared harmonic or borrow gain from other upper harmonics.
    """
    train = CONFIG['train_samples']
    candidate = design([frequency], train + CONFIG['predict_samples'])[:, 1:]
    ratios, passing, added = admission.independent_pairs(
        prepared['base'], candidate, train, prepared['factor'])
    result = dict(admitted=False, pair_singular_ratios=ratios)
    if passing != [0]:
        return dict(result, status='shared_or_unidentifiable_fundamental')
    full = np.column_stack((prepared['base'], added))
    parts = admission.factor(full[:train])
    ratio = float(parts[1][-1] / parts[1][0])
    if parts[3] != full.shape[1] or ratio < CONFIG['full_singular_ratio_floor']:
        return dict(result, status='unidentifiable_fundamental_fit', full_singular_ratio=ratio)
    weights = admission.coefficients(parts, prepared['signal'][:train])
    residual = prepared['signal'][train:] - full[train:] @ weights
    error = float(residual @ residual) / prepared['energy']
    gain = prepared['base_error'] - error
    guard = admission.numerical_gain_guard(prepared['base_error'], error)
    return dict(result, admitted=bool(gain > guard), status='fundamental_prediction_measured',
                prediction_gain_fraction=gain, numerical_gain_guard=guard,
                full_singular_ratio=ratio)


def evaluate_candidate(window, prepared, note, state, *, continuity_diagnostic=False,
                       fundamental_veto_check=False):
    original = admission.evaluate_candidate(window, prepared, note)
    result = dict(original, original_status=original['status'], lower_comparisons=[],
                  unavailable_comparisons=0)
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
        if continuity_diagnostic:
            from tools.harmonic_source_continuity import measure
            row['source_continuity'] = measure(conditional, partials(lower['frequency_hz']))
        result['lower_comparisons'].append(row)
        if not support['admitted']:
            continue
        if len(owned) + 1 > CONFIG['maximum_base_notes']:
            return dict(result, admitted=False, status='too_many_comparison_parents')
        # Keep the original fitted frequency list (including its fixed harmonic
        # indices) and the lower frequency whose independent support was just
        # measured. Refitting all parents introduces duplicate shared columns
        # and can turn an unavailable fit into a veto against a real upper note.
        comparison_frequencies = list(frequencies)
        for frequency in harmonic_frequencies([lower]):
            # Same exact-sharing tolerance as harmonic_frequencies; do not merge
            # nearby but distinguishable harmonics or move any fitted frequency.
            if not any(abs(frequency - old) < 1e-6 for old in comparison_frequencies):
                comparison_frequencies.append(frequency)
        compared = prepared_with_base(prepared, design(sorted(comparison_frequencies), count))
        parts = compared['factor']
        ratio = float(parts[1][-1] / parts[1][0])
        if ratio < CONFIG['full_singular_ratio_floor']:
            row['upper_comparison'] = dict(admitted=False, status='ill_conditioned_comparison_base',
                                            base_singular_ratio=ratio)
        else:
            row['upper_comparison'] = admission.evaluate_partial_support(compared, partials(upper_hz))
        check = row['upper_comparison']
        if (fundamental_veto_check and check['status'] == 'insufficient_supported_pairs'
                and check.get('supported_harmonics') == [1]):
            row['fundamental_veto_check'] = fundamental_comparison(compared, upper_hz)
            if row['fundamental_veto_check']['admitted']:
                row['comparison_outcome'] = 'fundamental_prediction_pass'
                continue
        if check['admitted']:
            row['comparison_outcome'] = 'pass'
        elif check['status'] in MEASURED_REJECTIONS:
            row['comparison_outcome'] = 'measured_rejection'
            return dict(result, admitted=False, status='lower_competition_withheld',
                        withholding_lower_note=lower['note'])
        else:
            row['comparison_outcome'] = 'unavailable'
            result['unavailable_comparisons'] += 1
    return dict(result, status='competition_incomplete' if result['unavailable_comparisons'] else 'competition_pass')


def generate(audio, outcome_path, cue_path, evidence_path, deadline, *,
             fundamental_veto_check=False):
    from functools import partial
    decision = (partial(evaluate_candidate, fundamental_veto_check=True)
                if fundamental_veto_check else evaluate_candidate)
    return admission.generate(audio, outcome_path, cue_path, evidence_path, deadline,
                              decision=decision)
