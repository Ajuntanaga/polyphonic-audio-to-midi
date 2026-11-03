#!/usr/bin/env python3
"""Compare one frozen-state lane objective without replaying or changing MIDI.

Reconstruct the recorded native DP first. Only then compare a single prechosen
observation cost. Labels and rendered outputs are read by score(), never solve()
or proposals(). A changed primary is not a causal change to rendered output.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path

from tools.string_evidence_audit import OPEN_NOTES, vector


def terms(text):
    result = tuple(tuple(float(x) for x in lane.split(':'))
                   for lane in text.split(','))
    if len(result) != 8 or any(len(lane) != 7 or
                              not all(math.isfinite(x) for x in lane)
                              for lane in result):
        raise ValueError('expected eight lanes of seven finite cost terms')
    return result


def solve(costs, playable, reserved):
    """Native state order, sequential additions, and packed-string tie break."""
    current = {reserved: (0.0, 0)}
    for ordinal, (lanes, mask) in enumerate(zip(costs, playable)):
        following = {}
        for used, (cost, packed) in sorted(current.items()):
            for lane in range(8):
                bit = 1 << lane
                if not mask & bit or used & bit:
                    continue
                proposal_cost = cost
                for term in lanes[lane]:
                    proposal_cost += term
                proposal = (proposal_cost, packed | (lane << (3 * ordinal)))
                occupied = used | bit
                if occupied not in following or proposal < following[occupied]:
                    following[occupied] = proposal
        current = following
    return min(current.values()) if current else None


def eligibility(row, lanes):
    """Only recorded pre-assignment guards; no labels or render-stage fields.

    Selector/pending-group prestate is absent from this schema. Therefore this
    is a conditional diagnostic, not a sufficient guard for native integration.
    """
    guards = (
        (2 <= int(row['selected_count']) <= 5, 'not_measured_polyphonic_range'),
        (not int(row['isolated']), 'isolated'),
        (not int(row['prior_committed']), 'committed_owner'),
        (int(row['prior_mask']).bit_count() <= 1, 'prior_group'),
        (not int(row['spectral_proposal']), 'spectral_proposal'),
        (not any(lane[5] != 0 for lane in lanes), 'fine_group'),
        (all(lane[6] in (0.0, -4.0) for lane in lanes), 'settled_retention'),
        (bool(int(row['complete_calibration'])), 'incomplete_calibration'),
        (bool(int(row['posterior_observation_available'])) and
         bool(int(row['posterior_updated'])), 'observation_unavailable'),
        (not int(row['use_posterior']), 'existing_posterior_policy'),
    )
    return next((reason for passed, reason in guards if not passed), None)


def proposals(rows, costs, baseline_packed):
    """Use each current likelihood once; freeze other rows to native DP lanes."""
    changed_costs, masks, reasons = [], [], []
    for ordinal, (row, lanes) in enumerate(zip(rows, costs)):
        reason = eligibility(row, lanes)
        reasons.append(reason)
        if reason is not None:
            changed_costs.append(lanes)
            masks.append(1 << ((baseline_packed >> (3 * ordinal)) & 7))
            continue
        mask, note = int(row['playable']), int(row['note'])
        likelihood = vector(row['posterior_log_likelihood'])
        feasible = [lane for lane in range(8) if mask & (1 << lane)]
        if not feasible or any(not 0 <= note - OPEN_NOTES[lane] <= 24
                               for lane in feasible):
            raise ValueError('infeasible measured fret mask')
        maximum = max(likelihood[lane] for lane in feasible)
        # Existing native fret/posterior scales; no fit to labels or sweep.
        changed_costs.append(tuple(
            (0.005 * (note - OPEN_NOTES[lane]),
             2.0 * (maximum - likelihood[lane]), 0.0, lanes[lane][3],
             0.0, 0.0, lanes[lane][6]) for lane in range(8)))
        masks.append(mask)
    return changed_costs, masks, reasons


def compare_frame(rows):
    selected = sorted((r for r in rows if int(r['observed']) and
                       not int(r['fixed_context'])), key=lambda r: int(r['ordinal']))
    if not selected:
        return {'availability': 'no_selected_rows'}
    first = selected[0]
    count = int(first['selected_count'])
    shared = ('selected_count', 'reserved_coasting', 'reserved_extras',
              'joint_strings', 'joint_cost', 'valid')
    if any(r[key] != first[key] for r in selected for key in shared):
        raise ValueError('inconsistent joint decision metadata')
    if not 1 <= count <= 8 or [int(r['ordinal']) for r in selected] != list(range(count)):
        return {'availability': 'incomplete_selected_rows'}
    masks = [int(row['playable']) for row in selected]
    reserved = int(first['reserved_coasting']) | int(first['reserved_extras'])
    if not 0 <= reserved < 256 or any(not 0 < mask < 256 for mask in masks):
        raise ValueError('invalid lane mask')
    costs = [terms(row['lane_terms']) for row in selected]
    baseline = solve(costs, masks, reserved)
    native_valid = bool(int(first['valid']))
    if (baseline is not None) != native_valid:
        return {'availability': 'native_dp_mismatch'}
    if baseline is None:
        return {'availability': 'native_dp_infeasible'}
    native_cost, native_packed = float(first['joint_cost']), int(first['joint_strings'])
    if not math.isfinite(native_cost):
        raise ValueError('nonfinite native joint cost')
    if baseline != (native_cost, native_packed) or any(
            int(row['dp_primary']) != ((native_packed >> (3 * i)) & 7)
            for i, row in enumerate(selected)):
        return {'availability': 'native_dp_mismatch'}
    alternative_costs, alternative_masks, reasons = proposals(selected, costs, native_packed)
    alternative = solve(alternative_costs, alternative_masks, reserved)
    if alternative is None:
        raise ValueError('shadow lost a feasible frozen baseline')
    return dict(availability='reconstructed', rows=selected, reasons=reasons,
                baseline_packed=native_packed, shadow_packed=alternative[1])


def score(row, before, after):
    """Outcome labels only. Rescued intermediate assignments are not new gains."""
    c = Counter(rows=1, changed=int(before != after))
    expected = int(row['expected_mask'])
    if int(row['expected_note']) and expected.bit_count() == 1:
        c['scored_single_target'] = 1
        c['baseline_dp_correct'] = int(bool(expected & (1 << before)))
        c['shadow_dp_correct'] = int(bool(expected & (1 << after)))
    if before == after:
        return c
    if not int(row['expected_note']):
        c['unlabeled_changed'] = 1
        return c
    if expected.bit_count() != 1:
        c['unknown_or_multistring_target_changed'] = 1
        return c
    c['single_target_changed'] = 1
    old_correct, new_correct = bool(expected & (1 << before)), bool(expected & (1 << after))
    c['dp_corrected'] = int(new_correct and not old_correct)
    c['dp_spoiled'] = int(old_correct and not new_correct)
    c['different_wrong_lane'] = int(not old_correct and not new_correct)
    rendered_correct = bool(int(row['rendered_mask']) & expected)
    c['render_absent_correction_opportunity'] = int(new_correct and not rendered_correct)
    c['already_rendered_correction_not_new_gain'] = int(new_correct and rendered_correct)
    c['render_present_assignment_risk'] = int(not new_correct and rendered_correct)
    c['downstream_rescued_row_put_at_risk'] = int(
        not new_correct and rendered_correct and not old_correct)
    return c


def analyze(rows, metadata):
    counts, reasons, by_note = Counter(), Counter(), defaultdict(Counter)
    samples = int(metadata['sample_count'])
    stride = int(metadata['grid_stride_samples'])
    previous, row_count, examples = -1, 0, []
    for sample, group in itertools.groupby(rows, lambda r: int(r['sample'])):
        frame = list(group)
        if (sample <= previous or sample >= samples or sample % stride != stride - 1 or
                any(int(r['tick']) * 64 - 1 != sample for r in frame)):
            raise ValueError('invalid sampled decision clock')
        previous = sample
        if len({int(r['note']) for r in frame}) != len(frame):
            raise ValueError('duplicate note within sampled decision')
        row_count += len(frame)
        counts['frames_with_rows'] += 1
        comparison = compare_frame(frame)
        availability = comparison['availability']
        counts[availability + '_frames'] += 1
        if availability != 'reconstructed':
            continue
        counts['compared_rows'] += len(comparison['rows'])
        before, after = comparison['baseline_packed'], comparison['shadow_packed']
        counts['changed_frames'] += int(before != after)
        for i, (row, reason) in enumerate(zip(comparison['rows'], comparison['reasons'])):
            reasons[reason or 'eligible'] += 1
            old, new = (before >> (3 * i)) & 7, (after >> (3 * i)) & 7
            measured = score(row, old, new)
            counts.update(measured)
            by_note[int(row['note'])].update(measured)
            if old != new and len(examples) < 12:
                examples.append(dict(sample=sample, note=int(row['note']),
                                     before_lane=old, after_lane=new,
                                     expected_mask=int(row['expected_mask']),
                                     rendered_mask=int(row['rendered_mask'])))
    if row_count != int(metadata['trace_rows']):
        raise ValueError('trace row count does not match capture report')
    counts['sampled_frames'] = int(metadata['sampled_frames'])
    if counts['sampled_frames'] != samples // stride:
        raise ValueError('incompatible complete capture grid')
    counts['frames_without_rows'] = counts['sampled_frames'] - counts['frames_with_rows']
    counts['annotated_targets'] = metadata['total']['targets']
    counts['missing_annotation_rows'] = metadata['total']['missing_assignment_row']
    return dict(counts=dict(counts), eligibility=dict(reasons), examples=examples,
                by_note={str(note): dict(c) for note, c in sorted(by_note.items())})


def run(trace, capture_report, dataset):
    source = capture_report['datasets'][dataset]
    digest = hashlib.sha256()
    with gzip.open(trace, 'rt', newline='') as handle:
        def lines():
            for line in handle:
                digest.update(line.encode('utf-8'))
                yield line
        result = analyze(csv.DictReader(lines(), delimiter='\t'), source['analysis'])
    if digest.hexdigest() != source['provenance']['trace_sha256']:
        raise ValueError('trace SHA-256 does not match capture report')
    result.update(
        schema_version=1, dataset=dataset, source_run=capture_report['run_id'],
        provenance=source['provenance'], native_control=source['control'],
        capture_binary_sha256=capture_report['binary_sha256'],
        capture_source_files_sha256=capture_report['source_files_sha256'],
        formulation='0.005*fret + 2*(max_feasible_current_ll-current_ll) + open + retention',
        interpretation={
            'result': 'frozen-state conditional shadow, not causal replay or MIDI improvement',
            'unavailable': 'missing trace rows and infeasible decisions are not missing MIDI',
            'protection': 'recorded owners/groups frozen; no relaxation of reserved lanes',
            'missing_prestate': 'selector and pending group masks are not captured before assignment',
            'new_gain': 'already-rendered corrections excluded from correction opportunities',
            'risk': 'render-present changes may lose downstream rescues; no loss magnitude inferred',
            'labels': 'only outcome scoring; no annotation-dependent proposal or eligibility',
            'production_changed': False,
        })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--capture-report', type=Path, required=True)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.trace, json.loads(args.capture_report.read_text()), args.dataset)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: result[key] for key in ('dataset', 'counts', 'eligibility')}, indent=2))


if __name__ == '__main__':
    main()
