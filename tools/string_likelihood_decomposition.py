#!/usr/bin/env python3
"""Explain changed pairs in the rejected observation-cost shadow.

Margins favor the labeled string when positive. These are observations of
frozen intermediate decisions, not independent trials or causal MIDI gains.
The descriptor term is the likelihood residual after subtracting the exact
profile, cents and recorded weighted detuning contributions.
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

from tools.string_evidence_audit import vector
from tools.string_observation_shadow import compare_frame, terms


def pair_margins(row, expected, competitor):
    """Recover only unreserved lanes whose native profile cost was computed."""
    if not (int(row['complete_calibration']) and
            int(row['posterior_observation_available'])):
        raise ValueError('complete likelihood observation required')
    mask = int(row['playable'])
    reserved = int(row['reserved_coasting']) | int(row['reserved_extras'])
    pair = (1 << expected) | (1 << competitor)
    if expected == competitor or pair & ~mask or pair & reserved:
        raise ValueError('pair must be distinct, playable and unreserved')
    detuning_mask = int(row['posterior_detuning_valid_mask'])
    detuning = vector(row['posterior_detuning_log_likelihood'])
    if not 0 <= detuning_mask < 256 or detuning_mask & ~mask:
        raise ValueError('invalid detuning mask')
    if any(value != 0 and not detuning_mask & (1 << lane)
           for lane, value in enumerate(detuning)):
        raise ValueError('unavailable detuning has a nonzero contribution')
    if not math.isclose(sum(detuning), 0.0, abs_tol=1e-8):
        raise ValueError('detuning contributions are not centered')
    costs = terms(row['lane_terms'])
    likelihood, learned = vector(row['posterior_log_likelihood']), vector(row['learned_cents'])
    assignment_cents = float(row['assignment_cents'])
    if not math.isfinite(assignment_cents):
        raise ValueError('nonfinite assignment cents')

    def components(lane):
        # Complete calibration uses -512*(similarity-center) in lane_terms[2],
        # and +6*(similarity-center) in the current observation likelihood.
        profile = -6.0 / 512.0 * costs[lane][2]
        cents = (-0.5 * min(32.0, ((assignment_cents - learned[lane]) / 4.0) ** 2)
                 if int(row['phase_valid']) else 0.0)
        return dict(profile=profile, cents=cents, detuning=detuning[lane],
                    descriptor=likelihood[lane] - profile - cents - detuning[lane],
                    total=likelihood[lane])

    wanted, other = components(expected), components(competitor)
    return {key: wanted[key] - other[key] for key in wanted}


def analyze(rows, metadata):
    counts, sums = defaultdict(Counter), defaultdict(Counter)
    coverage, examples = Counter(), []
    previous, row_count = -1, 0
    stride, samples = int(metadata['grid_stride_samples']), int(metadata['sample_count'])
    for sample, group in itertools.groupby(rows, lambda row: int(row['sample'])):
        frame = list(group)
        if (sample <= previous or sample >= samples or sample % stride != stride - 1 or
                any(int(row['tick']) * 64 - 1 != sample for row in frame)):
            raise ValueError('invalid sampled decision clock')
        previous = sample
        if len({row['note'] for row in frame}) != len(frame):
            raise ValueError('duplicate note within sampled decision')
        row_count += len(frame)
        comparison = compare_frame(frame)
        coverage[comparison['availability']] += 1
        if comparison['availability'] != 'reconstructed':
            continue
        before, after = comparison['baseline_packed'], comparison['shadow_packed']
        for i, (row, reason) in enumerate(zip(comparison['rows'], comparison['reasons'])):
            old, new = (before >> (3 * i)) & 7, (after >> (3 * i)) & 7
            expected_mask = int(row['expected_mask'])
            if old == new or not int(row['expected_note']) or expected_mask.bit_count() != 1:
                continue
            if reason is not None:
                raise ValueError('ineligible lane changed in frozen shadow')
            expected = expected_mask.bit_length() - 1
            outcome = 'corrected' if new == expected else 'spoiled' if old == expected else 'different_wrong'
            c = counts[outcome]
            c['changed_rows'] += 1
            competitor = old if new == expected else new
            reserved = int(row['reserved_coasting']) | int(row['reserved_extras'])
            if expected_mask & reserved or expected_mask & ~int(row['playable']):
                c['expected_lane_unavailable'] += 1
                continue
            margins = pair_margins(row, expected, competitor)
            c['measured_pairs'] += 1
            dm = int(row['posterior_detuning_valid_mask'])
            c['detuning_expected_available'] += int(bool(dm & expected_mask))
            c['detuning_competitor_available'] += int(bool(dm & (1 << competitor)))
            c['detuning_both_available'] += int((dm & (expected_mask | (1 << competitor))) ==
                                                (expected_mask | (1 << competitor)))
            c['phase_valid'] += int(bool(int(row['phase_valid'])))
            for key, margin in margins.items():
                direction = 'positive' if margin > 1e-9 else 'negative' if margin < -1e-9 else 'tied'
                c[key + '_' + direction] += 1
                sums[outcome][key] += margin
            for key in ('descriptor', 'detuning', 'cents', 'profile'):
                remaining = margins['total'] - margins[key]
                c[key + '_reverses_correct_other_terms'] += int(remaining > 1e-9 and margins['total'] < -1e-9)
                c[key + '_rescues_wrong_other_terms'] += int(remaining < -1e-9 and margins['total'] > 1e-9)
            c['descriptor_detuning_reverse_profile_cents'] += int(
                margins['profile'] + margins['cents'] > 1e-9 and margins['total'] < -1e-9)
            if len(examples) < 12:
                examples.append(dict(sample=sample, note=int(row['note']), outcome=outcome,
                                     expected_lane=expected, competitor_lane=competitor,
                                     detuning_valid_mask=dm, margins=margins))
    if row_count != int(metadata['trace_rows']):
        raise ValueError('trace row count does not match capture report')
    if int(metadata['sampled_frames']) != samples // stride:
        raise ValueError('incompatible complete capture grid')
    return dict(coverage=dict(coverage), counts={key: dict(value) for key, value in counts.items()},
                mean_margin={key: {term: value / counts[key]['measured_pairs']
                                   for term, value in values.items()}
                             for key, values in sums.items()}, examples=examples)


def run(trace, report, dataset):
    source = report['datasets'][dataset]
    digest = hashlib.sha256()
    with gzip.open(trace, 'rt', newline='') as handle:
        def lines():
            for line in handle:
                digest.update(line.encode('utf-8'))
                yield line
        result = analyze(csv.DictReader(lines(), delimiter='\t'), source['analysis'])
    if digest.hexdigest() != source['provenance']['trace_sha256']:
        raise ValueError('trace SHA-256 does not match capture report')
    result.update(schema_version=1, source_run=report['run_id'], dataset=dataset,
                  provenance=source['provenance'], capture_binary_sha256=report['binary_sha256'],
                  capture_source_files_sha256=report['source_files_sha256'],
                  interpretation=__doc__, installed_changed=False)
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
    print(json.dumps({key: result[key] for key in ('coverage', 'counts', 'mean_margin')}, indent=2))


if __name__ == '__main__':
    main()
