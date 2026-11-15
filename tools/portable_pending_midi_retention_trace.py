"""Capture the two missing current-ON cost windows from the rejected MIDI trial.

All native execution stays on GitHub. Frozen omission at saved loss starts is
diagnostic arithmetic, not a replacement policy or a held-note improvement.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from tools.assignment_cost_analysis import INTEGER_FIELDS, solve
from tools.portable_pending_string_trace import run as capture
from tools.portable_pending_string_trial import CONDITIONS


CASES = (
    dict(label_index=200, midi_note=50, string_mask=8, start_sample=3590630, end_sample=3662400),
    dict(label_index=279, midi_note=47, string_mask=2, start_sample=5059430, end_sample=5131200))
# Measured loss starts in run 43707756793. These select diagnostic observations
# only; no annotation or sample number enters the native detector.
ANCHORS = {
    200: dict(peer=32, retained_lane=0, samples=(3594751,)),
    279: dict(peer=33, retained_lane=0,
              samples=(5107455, 5107839, 5118463, 5121279, 5124415, 5128831))}


def window_for(label):
    return max(0, label['start_sample'] // 64 * 64 - 96000), (label['end_sample'] // 64 + 10) * 64


def compare_anchors(raw_rows, frames, label):
    """Called after the shared analyzer verifies complete peers and native DP.

Keep original ordinals when removing a row: the packed tie break still uses
the original bit positions. All costs and reserved masks remain frozen.
"""
    selection = ANCHORS[label['label_index']]
    samples = set(selection['samples'])
    groups = defaultdict(list)
    for raw in raw_rows:
        if int(raw['sample']) not in samples or not int(raw['observed']):
            continue
        row = {key: int(raw[key]) for key in INTEGER_FIELDS}
        for key in ('allocation_preview', 'prior_attack_ticks', 'attack_required'):
            row[key] = int(raw[key])
        row['terms'] = [[float(term) for term in lane.split(':')]
                        for lane in raw['lane_terms'].split(',')]
        row['joint_cost'] = float(raw['joint_cost'])
        groups[row['sample']].append(row)
    states = {frame['sample']: frame['candidate_state'] for frame in frames}
    observations = []
    for sample in selection['samples']:
        rows = sorted(groups.get(sample, []), key=lambda row: row['ordinal'])
        target = next((row for row in rows if row['note'] == label['midi_note']), None)
        peer = next((row for row in rows if row['note'] == selection['peer']), None)
        state = states.get(sample)
        if target is None or peer is None or state is None:
            raise ValueError(f'Missing target, peer or outcome at loss anchor {sample}')
        retained_lane = selection['retained_lane']
        if (peer['prior_active'] or peer['prior_midi'] or peer['allocation_preview'] or
                peer['playable'] != 1 << retained_lane or
                not 0 <= peer['prior_attack_ticks'] + 1 < peer['attack_required']):
            raise ValueError(f'Peer is not an inactive unready singleton at {sample}')
        original = solve(rows)
        if original != (target['joint_cost'], target['joint_strings']):
            raise ValueError(f'Original optimum changed at loss anchor {sample}')
        remaining = [row for row in rows if row is not peer]
        omitted = solve(remaining)
        constrained = solve(remaining, pin=(target['note'], retained_lane))

        def solution(value):
            return None if value is None else dict(cost=value[0], packed=value[1],
                target_lane=(value[1] >> (target['ordinal'] * 3)) & 7)

        observations.append(dict(sample=sample, target_note=target['note'],
            target_ordinal=target['ordinal'], prior_physical_mask=target['prior_mask'],
            prior_midi_mask=target['prior_midi'], final_physical_mask=target['final_mask'],
            best_string=state['best_string'], calibration_mask=state['cal_mask'],
            retained_lane=retained_lane, omitted_peer={key: peer[key] for key in
                ('note', 'ordinal', 'prior_active', 'prior_midi', 'playable',
                 'prior_attack_ticks', 'attack_required')},
            original=solution(original), omitted=solution(omitted),
            omitted_pinned_to_retained=solution(constrained)))
    return dict(expected_anchors=len(selection['samples']), observed_anchors=len(observations),
        observations=observations, interpretation='All other recorded terms, reservations and '
        'original ordinals remain fixed. This arithmetic does not simulate later history, '
        'validate a runtime rule, or measure new note gains.')


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    reference = json.loads(reference_path.read_text())['replay_references']['current-on']
    if 'outcome_sha256' not in reference:
        raise ValueError('A saved complete outcome digest is required')
    return capture(binary, corpus, manifest_path, reference_path, output,
        timeout=timeout, cases=CASES, conditions=CONDITIONS[1:2], window=window_for,
        diagnose=compare_anchors, schema='m3_pending_midi_retention_trace_v1')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    if args.replay_timeout_seconds <= 0:
        parser.error('--replay-timeout-seconds must be positive')
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds)


if __name__ == '__main__':
    main()
