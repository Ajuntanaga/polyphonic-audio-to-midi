#!/usr/bin/env python3
"""Stream an assignment trace into annotation-age evidence summaries.

This measures disagreement, not a counterfactual improvement. Likelihood inputs
already include causal filtering. Cached prior is the bank state before its
transition, not the transition-predicted prior. An eight-lane posterior chooses
one owner; it is not a posterior over multi-string masks.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import heapq
import itertools
import math

AGE_BINS = ('attack_0_100ms', 'early_100_350ms', 'settled_350ms_plus')
OPEN_NOTES = (32, 36, 40, 44, 48, 52, 56, 60)


def age_bin(samples, sample_rate):
    # Integer arithmetic keeps boundary annotations reproducible.
    return AGE_BINS[0 if samples * 1000 < sample_rate * 100 else
                    1 if samples * 1000 < sample_rate * 350 else 2]


def vector(text):
    values = tuple(float(value) for value in text.split(','))
    if len(values) != 8 or not all(math.isfinite(value) for value in values):
        raise ValueError('expected eight finite lane values')
    return values


def rank(values, mask, expected):
    lanes = [i for i in range(8) if mask & (1 << i)]
    if expected not in lanes:
        return None
    highest = max(values[i] for i in lanes)
    leaders = [i for i in lanes if abs(values[i] - highest) <= 1e-10]
    wrong = [values[i] for i in lanes if i != expected]
    return {
        'correct': leaders == [expected], 'tie': len(leaders) > 1,
        'rank': 1 + sum(values[i] > values[expected] + 1e-10 for i in lanes),
        'expected_margin': values[expected] - max(wrong) if wrong else None,
    }


def observe(row, expected_mask):
    """One annotated note at one sampled tick; missing rows stay unavailable."""
    counts = Counter(targets=1)
    if row is None:
        counts['missing_assignment_row'] = 1
        return counts, {}
    counts['captured'] = 1
    rendered = int(row['rendered_mask'])
    counts['fixed_context'] = int(row['fixed_context'])
    counts['posterior_used'] = int(row['use_posterior'])
    counts['candidate_age_ticks_sum'] = int(row['candidate_age_ticks'])
    if expected_mask == 0:
        counts['note_only_label'] = 1
        return counts, {}
    counts['render_exact'] = int(rendered == expected_mask)
    counts['render_contains_expected'] = int((rendered & expected_mask) == expected_mask)
    counts['extra_rendered_strings'] = (rendered & ~expected_mask).bit_count()
    if expected_mask.bit_count() != 1:
        counts['multi_string_target_no_lane_rank'] = 1
        return counts, {}
    lane = expected_mask.bit_length() - 1
    mask = int(row['playable'])
    if not mask & expected_mask:
        counts['infeasible_expected_lane'] = 1
        return counts, {}
    counts['feasible_single_target'] = 1
    counts['expected_lane_reserved'] = int(bool(
        expected_mask & (int(row['reserved_coasting']) | int(row['reserved_extras']))))
    if not int(row['posterior_observation_available']):
        counts['observation_unavailable'] = 1
        return counts, {}
    counts['observation_available'] = 1
    onset = float(row['posterior_onset_strength'])
    if not math.isfinite(onset) or not 0 <= onset <= 1:
        raise ValueError('invalid onset strength')
    counts['onset_strength_sum'] = onset
    counts['onset_at_least_half'] = int(onset >= 0.5)
    likelihood = rank(vector(row['posterior_log_likelihood']), mask, lane)
    prior_values = vector(row['posterior_prior'])
    prior_sum = sum(prior_values)
    if any(p < 0 or p > 1 for p in prior_values) or (
            prior_sum != 0 and not math.isclose(prior_sum, 1, abs_tol=1e-8)):
        raise ValueError('invalid cached prior')
    # A cached state can have a different feasible set. Rank its own support.
    prior_mask = sum(1 << i for i, p in enumerate(prior_values) if p > 0)
    prior = rank(prior_values, prior_mask, lane) if prior_sum else None
    counts['prior_uninitialized'] = int(prior_sum == 0)
    counts['prior_excludes_expected'] = int(prior_sum > 0 and prior is None)
    ranks = {'likelihood': likelihood, 'prior': prior}
    if not int(row['posterior_updated']):
        counts['update_failed'] = 1
        return counts, ranks
    post_values = vector(row['posterior_probability'])
    if (any(p < 0 or p > 1 or (p > 0 and not mask & (1 << i))
            for i, p in enumerate(post_values)) or
            not math.isclose(sum(post_values), 1, abs_tol=1e-8)):
        raise ValueError('invalid updated posterior')
    counts['updated'] = 1
    posterior = rank(post_values, mask, lane)
    ranks['posterior'] = posterior
    lc, pc = likelihood['correct'], posterior['correct']
    counts['likelihood_correct_posterior_not_correct'] = int(lc and not pc)
    counts['posterior_correct_likelihood_not_correct'] = int(pc and not lc)
    counts['posterior_correct_render_missing'] = int(pc and not rendered & expected_mask)
    counts['used_posterior_correct_render_missing'] = int(
        pc and not rendered & expected_mask and int(row['use_posterior']))
    counts['likelihood_and_posterior_correct_dp_wrong'] = int(
        lc and pc and int(row['valid']) and int(row['dp_primary']) != lane)
    counts['prior_wrong_likelihood_correct_posterior_wrong'] = int(
        prior is not None and not prior['correct'] and lc and not pc)
    counts['prior_correct_likelihood_wrong_posterior_correct'] = int(
        prior is not None and prior['correct'] and not lc and pc)
    return counts, ranks


def add(bucket, counts, ranks):
    bucket.update(counts)
    for name, measured in ranks.items():
        if measured is None:
            continue
        bucket[name + '_ranked'] += 1
        bucket[name + '_unique_correct'] += int(measured['correct'])
        bucket[name + '_top_tie'] += int(measured['tie'])
        bucket[f'{name}_rank_{measured["rank"]}'] += 1
        if measured['expected_margin'] is not None:
            bucket[name + '_margin_count'] += 1
            bucket[name + '_expected_margin_sum'] += measured['expected_margin']


def summarize(rows, labels, *, sample_rate, sample_count, sampled_frames,
              source_identity, decision_quantum=64, decimation=16):
    """Memory scales with annotations, never with audio duration/trace rows.

    The complete fixed decision grid includes frames with no assignment row.
    The producer's sampled-frame count and every row's sample/tick must agree
    with that grid, or this function refuses to report coverage.
    """
    if min(sample_rate, decision_quantum, decimation) <= 0 or sample_count < 0:
        raise ValueError('invalid recording clock')
    stride = decision_quantum * decimation
    if sampled_frames != sample_count // stride:
        raise ValueError('incomplete or incompatible sampled-frame clock')
    parsed = []
    for i, label in enumerate(labels):
        start, end = int(label['start_sample']), int(label['end_sample'])
        note, mask = int(label['midi_note']), int(label['string_mask'])
        if not (0 <= start < end <= sample_count and 0 <= note < 128 and 0 <= mask < 256):
            raise ValueError('invalid annotation bounds or identity')
        parsed.append(dict(index=i, start=start, end=end, note=note, mask=mask))
    starts = sorted(parsed, key=lambda label: (label['start'], label['index']))
    active, ends, cursor = {}, [], 0
    groups = iter(itertools.groupby(rows, key=lambda row: int(row['sample'])))
    group = next(groups, None)
    total, ages, cases = Counter(), defaultdict(Counter), defaultdict(Counter)
    row_count = 0
    for sample in range(stride - 1, sample_count, stride):
        while ends and ends[0][0] <= sample:
            _, index = heapq.heappop(ends)
            active.pop(index)
        while cursor < len(starts) and starts[cursor]['start'] <= sample:
            label = starts[cursor]
            cursor += 1
            if label['end'] > sample:
                active[label['index']] = label
                heapq.heappush(ends, (label['end'], label['index']))
        captured = {}
        if group is not None and group[0] < sample:
            raise ValueError('trace is out of order or off the decision grid')
        if group is not None and group[0] == sample:
            for row in group[1]:
                note = int(row['note'])
                if (note in captured or not 0 <= note < 128 or
                        int(row['tick']) * decision_quantum - 1 != sample):
                    raise ValueError('duplicate note or incompatible trace clock')
                captured[note] = row
                row_count += 1
            group = next(groups, None)
        by_note = defaultdict(list)
        for label in active.values():
            by_note[label['note']].append(label)
        for note, matching in by_note.items():
            mask = 0
            for label in matching:
                mask |= label['mask']
            # A note-only label makes string identity unknown even when another
            # overlapping label specifies a lane; don't silently infer it.
            if any(label['mask'] == 0 for label in matching):
                mask = 0
            row = captured.get(note)
            if row is not None and (not int(row['expected_note']) or
                                      int(row['expected_mask']) != mask):
                # Native trace ORs note-only (zero) labels. Permit that precise
                # representation while withholding string scores here.
                native_mask = 0
                for label in matching:
                    native_mask |= label['mask']
                if not int(row['expected_note']) or int(row['expected_mask']) != native_mask:
                    raise ValueError('trace/annotation join mismatch')
            counts, ranks = observe(row, mask)
            add(total, counts, ranks)
            if len(matching) == 1:
                label = matching[0]
                age = age_bin(sample - label['start'], sample_rate)
                add(ages[age], counts, ranks)
                add(cases[label['index']], counts, ranks)
            else:
                total['overlapping_annotations_no_age_bucket'] += 1
        total['unlabeled_candidate_rows'] += sum(note not in by_note for note in captured)
    if group is not None:
        raise ValueError('trace extends past recording or is off the decision grid')
    annotations = []
    for label in parsed:
        lane = label['mask'].bit_length() - 1 if label['mask'].bit_count() == 1 else None
        annotations.append({**label, 'expected_lane': lane,
                            'fret': label['note'] - OPEN_NOTES[lane] if lane is not None else None,
                            'counts': dict(cases[label['index']])})
    return {
        'source_identity': source_identity, 'sample_rate': sample_rate,
        'sample_count': sample_count, 'sampled_frames': sampled_frames,
        'trace_rows': row_count, 'grid_stride_samples': stride,
        'total': dict(total), 'age_bins': {age: dict(ages[age]) for age in AGE_BINS},
        'annotations': annotations,
        'interpretation': {
            'denominator': 'targets are annotated note/tick pairs on the fixed sampled grid',
            'missing_assignment_row': 'not observed by this trace; not a measured missing MIDI note',
            'rank_denominator': 'available, feasible, single-string targets only',
            'likelihood': 'current update input, already causally filtered; not raw acoustics',
            'prior': 'cached bank state before transition; own support may differ from current mask',
            'age': 'annotation elapsed time, separate from detector candidate age and onset strength',
            'causality': 'annotation joins are for scoring only; disagreement does not prove a fix',
            'classifier_gain': 'not measured', 'multi_string_posterior': 'not measured',
        },
    }


def summarize_files(trace, labels, **kwargs):
    with open(trace) as rows, open(labels) as annotations:
        return summarize(csv.DictReader(rows, delimiter='\t'),
                         csv.DictReader(annotations, delimiter='\t'), **kwargs)
