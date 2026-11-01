"""Describe observed profile-only pairs; labels never feed the detector."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import math


REQUIRED = set((
    'sample tick note playable final_primary any_label expected_note expected_mask '
    'voices phase_valid phase_cents learned_cents group_proposal group_origin '
    'group_after beat_valid fine_valid profile_fit_observed profile_uses_long_memory '
    'profile_primary_error profile_best_single_error profile_mixture_error '
    'profile_weights profile_observed profile_single_errors candidate_age_ticks'
).split())
WINDOW_COLUMNS = ('profile_pair_primary', 'profile_pair_mask',
                  'profile_pair_current', 'profile_pair_short', 'profile_pair_long')


def window_evidence(encoded):
    values = [float(value) for value in encoded.split(':')]
    if len(values) != 12 or not all(math.isfinite(value) for value in values):
        raise ValueError('invalid profile window fields')
    valid, energy, primary, single, pair, weight, *observed = values
    if valid not in (0, 1):
        raise ValueError('invalid profile window validity')
    if not valid:
        return None
    if (energy <= 0 or min(primary, single, pair, *observed) < 0 or
            not 0 <= weight <= 1 or abs(sum(observed) - 1) > 1e-9 or
            single > primary + 1e-9 or pair > primary + 1e-9):
        raise ValueError('invalid normalized profile window')
    return dict(energy=energy, primary_error=primary, single_error=single,
                pair_error=pair, secondary_weight=weight,
                primary_gain=max(0., primary - pair), single_gain=single - pair)


def truth_class(expected_note, any_label, expected_mask, proposal):
    if not expected_note:
        return 'wrong_pitch' if any_label else 'extra_gap'
    if not expected_mask:
        return 'unscoped_pitch'
    count = expected_mask.bit_count()
    if count == 1:
        return 'false_pair' if expected_mask & proposal else 'wrong_assignment'
    if count == 2:
        return 'true_pair' if expected_mask == proposal else 'wrong_assignment'
    return 'larger_group'


def quantiles(values):
    values = sorted(values)
    if not values:
        return None
    def at(fraction):
        position = fraction * (len(values) - 1)
        low = int(position)
        high = min(low + 1, len(values) - 1)
        return values[low] + (values[high] - values[low]) * (position - low)
    return dict(count=len(values), minimum=values[0], p10=at(.1), p50=at(.5),
                p90=at(.9), maximum=values[-1])


def analyze_stream(stream, capture):
    if capture.get('truncated') or capture.get('decimation') != 16:
        raise ValueError('complete decimation-16 capture required')
    reader = csv.DictReader(stream, delimiter='\t')
    if not REQUIRED.issubset(reader.fieldnames or ()):
        raise ValueError('profile-pair trace fields missing')
    windows_present = set(WINDOW_COLUMNS).intersection(reader.fieldnames or ())
    if windows_present and windows_present != set(WINDOW_COLUMNS):
        raise ValueError('incomplete profile window schema')
    totals, population, by_note = Counter(), Counter(), Counter()
    evidence = defaultdict(lambda: defaultdict(list))
    policies = [dict(single_error_ceiling=s, mixture_ratio_floor=r,
                     observations=Counter(), removed_correct=0,
                     removed_wrong_string=0, removed_wrong_pitch=0,
                     removed_extra_gap=0, unscoped=0)
                for s in (.0001, .001, .005, .01, .02, .05, .1, .2, 1.)
                for r in (0., .1, .25, .5, .75)]
    phase_policies = [dict(primary_distance_ceiling=p, secondary_distance_floor=s,
                          observations=Counter(), removed_correct=0,
                          removed_wrong_string=0, removed_wrong_pitch=0,
                          removed_extra_gap=0, unscoped=0)
                      for p in (.5, 1., 2., 3.) for s in (8., 12., 16., 24.)]
    # Fixed before the corpus capture. A stale-history hypothesis, not a
    # classifier trained from the labels in this stream. Selection and holdout
    # results must be reported separately by the caller.
    recency_policies = [dict(window=w, gain_ratio_ceiling=r, blended_gain_floor=g,
                            observations=Counter(), removed_correct=0,
                            removed_wrong_string=0, removed_wrong_pitch=0,
                            removed_extra_gap=0, unscoped=0)
                       for w in ('current', 'short')
                       for r in (0., .05, .1, .25, .5)
                       for g in (.001, .005, .01, .02)]
    previous_key = (-1, -1)
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('incomplete profile-pair row')
        totals['rows'] += 1
        key = (int(row['tick']), int(row['note']))
        if key <= previous_key or key[0] % capture['decimation']:
            raise ValueError('duplicate or unordered profile-pair row')
        previous_key = key
        if not int(row['profile_fit_observed']):
            continue
        totals['profile_fits'] += 1
        proposal = int(row['group_proposal'])
        if proposal.bit_count() != 2 or int(row['group_origin']) != 3:
            continue
        totals['profile_pairs'] += 1
        if int(row['beat_valid']) or int(row['fine_valid']):
            totals['independently_supported_pairs'] += 1
            continue
        primary = int(row['final_primary'])
        if not 0 <= primary < 8 or not proposal & (1 << primary):
            totals['primary_changed_after_fit'] += 1
            continue
        if proposal & ~int(row['playable']):
            raise ValueError('infeasible profile pair')
        values = [float(row[name]) for name in (
            'profile_primary_error', 'profile_best_single_error', 'profile_mixture_error')]
        weights = [float(x) for x in row['profile_weights'].split(',')]
        observed = [float(x) for x in row['profile_observed'].split(',')]
        learned = [float(x) for x in row['learned_cents'].split(',')]
        singles = [float(x) for x in row['profile_single_errors'].split(',')]
        if (len(weights) != 8 or len(observed) != 6 or len(learned) != 8 or len(singles) != 8
                or not all(math.isfinite(x) for x in values + weights + observed + learned + singles)
                or min(values) < 0 or abs(sum(observed) - 1) > 1e-9
                or abs(sum(weights) - 1) > 1e-9):
            raise ValueError('invalid profile-fit evidence')
        secondary = (proposal ^ (1 << primary)).bit_length() - 1
        expected, any_label = int(row['expected_note']), int(row['any_label'])
        expected_mask = int(row['expected_mask'])
        truth = truth_class(expected, any_label, expected_mask, proposal)
        population[truth] += 1
        by_note[f'{truth}:{key[1]}:{proposal}'] += 1
        primary_error, single_error, mixture_error = values
        descriptors = dict(primary_error=primary_error, single_error=single_error,
            mixture_error=mixture_error,
            mixture_ratio=mixture_error / max(single_error, 1e-15),
            absolute_improvement=single_error - mixture_error,
            secondary_weight=weights[secondary], primary_weight=weights[primary],
            learned_separation=abs(learned[primary] - learned[secondary]),
            age_ticks=int(row['candidate_age_ticks']),
            long_memory=int(row['profile_uses_long_memory']))
        recency = {}
        if windows_present:
            if (int(row['profile_pair_primary']) != primary or
                    int(row['profile_pair_mask']) != proposal):
                totals['window_pair_changed_after_fit'] += 1
            else:
                blended_gain = max(0., primary_error - mixture_error)
                for name in ('current', 'short', 'long'):
                    window = window_evidence(row[f'profile_pair_{name}'])
                    if window is None:
                        totals[f'{name}_window_unavailable'] += 1
                        continue
                    window['gain_delta'] = window['primary_gain'] - blended_gain
                    window['gain_ratio'] = window['primary_gain'] / max(blended_gain, 1e-15)
                    recency[name] = window
                    descriptors.update({f'{name}_{key}': value for key, value in window.items()})
        if int(row['phase_valid']):
            phase = float(row['phase_cents'])
            if not math.isfinite(phase):
                raise ValueError('nonfinite phase')
            descriptors.update(primary_phase_distance=abs(phase - learned[primary]),
                secondary_phase_distance=abs(phase - learned[secondary]),
                primary_phase_advantage=abs(phase - learned[secondary]) - abs(phase - learned[primary]))
        for name, value in descriptors.items():
            evidence[truth][name].append(value)
        # These are only sampled, already-rendered secondary voices. Never
        # extrapolate them into recovered frames or account for future ownership.
        rendered_secondary = any(tuple(map(int, voice.split(':'))) ==
            (key[1], key[1], secondary) for voice in row['voices'].split(',') if voice)
        eligible = int(row['group_after']) == proposal and rendered_secondary
        if eligible:
            totals['rendered_secondary_eligible'] += 1
        removal_field = ('removed_wrong_pitch' if any_label else 'removed_extra_gap')
        if expected:
            removal_field = ('unscoped' if not expected_mask else
                             'removed_correct' if expected_mask & (1 << secondary) else
                             'removed_wrong_string')
        def count_policy(policy):
            policy['observations'][truth] += 1
            if eligible:
                policy[removal_field] += 1
        for policy in policies:
            if (single_error > policy['single_error_ceiling'] or
                    descriptors['mixture_ratio'] < policy['mixture_ratio_floor']):
                continue
            count_policy(policy)
        if 'primary_phase_distance' in descriptors:
            for policy in phase_policies:
                if (descriptors['primary_phase_distance'] <= policy['primary_distance_ceiling']
                        and descriptors['secondary_phase_distance'] >= policy['secondary_distance_floor']):
                    count_policy(policy)
        if int(row['profile_uses_long_memory']):
            for policy in recency_policies:
                window = recency.get(policy['window'])
                if (window is not None and
                        primary_error - mixture_error >= policy['blended_gain_floor'] and
                        window['gain_ratio'] <= policy['gain_ratio_ceiling']):
                    count_policy(policy)
    if totals['rows'] != capture['rows']:
        raise ValueError('profile trace row count disagrees with capture')
    for policy in policies + phase_policies + recency_policies:
        policy['observations'] = dict(policy['observations'])
    return dict(units='sampled candidate observations; not full frames or MIDI gains',
        totals=dict(totals), population=dict(population), by_note=dict(by_note),
        distributions={truth: {name: quantiles(values) for name, values in fields.items()}
                       for truth, fields in evidence.items()}, policies=policies,
        phase_policies=phase_policies,
        recency_windows_available=bool(windows_present), recency_policies=recency_policies,
        limitation='Static removals do not measure future MIDI, string ownership or onset/release effects.',
        production_changed=False)
