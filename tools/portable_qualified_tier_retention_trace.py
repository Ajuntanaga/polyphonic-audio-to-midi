"""Observe the first extended-middle divergence of the rejected retention rule.

Only the GitHub worker runs these two native replays. Both saved complete scored,
MIDI and outcome streams must be reproduced before interpreting the bounded trace.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from tools.portable_corpus_replay import SETTINGS
from tools.portable_pending_string_trace import run as capture


DATASET = 'extended-middle'
CASE = dict(label_index=1, midi_note=52, string_mask=40,
            start_sample=393600, end_sample=739200)
WINDOW = (461568, 462336)
ANCHORS = (461823, 461887)
INPUT_NAMES = (DATASET + '.wav', DATASET + '.tsv', 'calibration.m3cb', 'templates.tsv')
CONDITIONS = (
    ('current-on', ('--diagnostic-spectral-lane-collision',)),
    ('qualified-tier-retention-on', ('--diagnostic-spectral-lane-collision',
                                     '--diagnostic-qualified-tier-retention')))
REFERENCE_SCHEMA = 'm3_qualified_tier_retention_trace_references_v1'
INTERPRETATION = (
    'Paired observation of unchanged current and rejected retention policies. '
    'Each complete scored TSV, raw MIDI and outcome stream must match its saved '
    'corpus reference. The first changed snapshot is461823; the first lost raw '
    'hold starts461887. These clocks are distinct. Named fine-group disposition, '
    'DP primary and group origin describe observed decisions, not a safe replacement '
    'predicate. No DSP policy, timing, allocation or host acceptance is changed or measured.')


def validate_reference(reference, manifest):
    if (reference['schema'] != REFERENCE_SCHEMA or reference['dataset'] != DATASET
            or reference['settings'] != SETTINGS or reference['case'] != CASE
            or reference['window'] != list(WINDOW) or reference['block_samples'] != 512
            or reference['conditions'] != {name: list(flags) for name, flags in CONDITIONS}
            or set(reference['replay_references']) != {name for name, _ in CONDITIONS}):
        raise ValueError('Wrong fixed paired retention reference selection')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if reference['source'][key] != manifest['source'][key]:
            raise ValueError('Saved input provenance differs: ' + key)
    for name in INPUT_NAMES:
        if reference['inputs'][name] != manifest['files'][name]:
            raise ValueError('Saved input identity differs: ' + name)
    for policy, _ in CONDITIONS:
        row = reference['replay_references'][policy]
        for key in ('tsv_sha256', 'midi_sha256', 'outcome_sha256'):
            if not re.fullmatch('[0-9a-f]{64}', row.get(key, '')):
                raise ValueError('A saved complete digest is required: ' + key)
        held = row['held_labels'][str(CASE['label_index'])]
        if (row['sample_count'] != 2241600 or row['sample_rate'] != 96000
                or any(held[key] != value for key, value in CASE.items())
                or held['first_exact_hold_delay_samples'] != 5311):
            raise ValueError('Saved annotation, sample clock or first exact hold changed')


def diagnose(assignments, frames, label):
    """Retain all twelve joint decisions, including the prior tick at each anchor."""
    by_sample = defaultdict(list)
    for row in assignments:
        if int(row['observed']):
            by_sample[int(row['sample'])].append(row)
    ticks, dispositions, primary_counts = [], Counter(), Counter()
    observed_notes = None
    for frame in frames:
        fine, peers = frame['fine_group'], frame['admission_peers']
        if fine is None or not fine['ownership_observed'] or not fine['fine_group_evaluated']:
            raise ValueError('Missing fine group stage observation')
        if peers is None or label['midi_note'] not in peers:
            raise ValueError('Missing target admission observation')
        if observed_notes is not None and set(peers) != observed_notes:
            raise ValueError('Incomplete admission peer coverage')
        observed_notes = set(peers)
        selected = by_sample[frame['sample']]
        targets = [row for row in selected if int(row['note']) == label['midi_note']]
        if len(targets) != 1 or any(int(row['note']) not in peers for row in selected):
            raise ValueError('Missing or duplicate target assignment')
        target = targets[0]
        # Require these fields; older cost-only traces cannot answer this question.
        group = {key: int(target[key]) for key in ('dp_primary', 'group_before',
            'group_proposal', 'group_origin', 'group_transition', 'group_after')}
        dispositions.update((fine['disposition'],))
        primary_counts.update((str(group['dp_primary']),))
        ticks.append(dict(sample=frame['sample'], fine_group=fine,
            routing=frame['routing'], tracking=frame['tracking'], group=group,
            complete_admission_peers=peers, complete_selected_assignments=selected))
    by_tick = {row['sample']: i for i, row in enumerate(ticks)}
    if any(sample not in by_tick or by_tick[sample] == 0 for sample in ANCHORS):
        raise ValueError('Missing saved event anchors or preceding observation')
    return dict(window_frames=len(ticks), observed_notes=sorted(observed_notes),
        fine_group_dispositions=dict(dispositions), dp_primary_counts=dict(primary_counts),
        anchors={str(sample): dict(prior=ticks[by_tick[sample]-1],
                                  current=ticks[by_tick[sample]]) for sample in ANCHORS},
        ticks=ticks, interpretation=INTERPRETATION)


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    validate_reference(json.loads(reference_path.read_text()), json.loads(manifest_path.read_text()))
    return capture(binary, corpus, manifest_path, reference_path, output,
        timeout=timeout, dataset=DATASET, cases=(CASE,), conditions=CONDITIONS,
        window=lambda label: WINDOW, diagnose=diagnose,
        schema='m3_qualified_tier_retention_trace_v1', interpretation=INTERPRETATION)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds)


if __name__ == '__main__':
    main()
