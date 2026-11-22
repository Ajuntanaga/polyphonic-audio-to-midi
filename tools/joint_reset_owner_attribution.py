"""Describe saved MIDI ownership around wholly missed joint-reset labels.

No audio, replay, candidate-state inference, policy simulation or gate change.
Run from the repository: python3 -m tools.joint_reset_owner_attribution --out PATH
"""
import argparse
import hashlib
import json
from bisect import bisect_right
from itertools import groupby
from pathlib import Path

from tools.midi_lifecycle_analysis import raw_conflicts, read_events


REPORT_SHA = '3bedd04bd9b1cccc60faed718fcbdbf15e855d86a8d968b6aeb6fe3237773b8a'
ROOT = Path('build/github-results/joint-rapid-reset-45075475603')


def merge(intervals):
    result = []
    for left, right in sorted(intervals):
        if right <= left:
            continue
        if result and left <= result[-1][1]:
            result[-1][1] = max(right, result[-1][1])
        else:
            result.append([left, right])
    return result


def clip(intervals, left, right):
    return merge((max(a, left), min(b, right)) for a, b in intervals
                 if a < right and b > left)


def timeline(events, horizon):
    """All same-sample transitions are applied before the next interval."""
    active, result, previous = {}, [], 0
    for sample, group in groupby(events, key=lambda event: event['sample']):
        if sample > previous:
            result.append((previous, sample, tuple(sorted(active.items()))))
        for event in group:
            lane, note = event['voice_id'], event['note']
            if event['kind'] == 'on':
                if lane in active:
                    raise ValueError('Raw owner overwritten')
                active[lane] = note
            else:
                if active.pop(lane, None) != note:
                    raise ValueError('Unpaired raw release')
        previous = sample
    if previous < horizon:
        result.append((previous, horizon, tuple(sorted(active.items()))))
    return result


def pitch_intervals(rows):
    by_note = {}
    for left, right, owners in rows:
        for note in {note for _, note in owners}:
            by_note.setdefault(note, []).append((left, right))
    return {note: merge(spans) for note, spans in by_note.items()}


def metrics(spans, label):
    left, right = label['start_sample'], label['end_sample']
    pieces = clip(spans, left, right)
    return dict(present_samples=sum(b-a for a, b in pieces),
                longest_present_samples=max((b-a for a, b in pieces), default=0),
                present_segments=len(pieces),
                first_present_delay_samples=pieces[0][0]-left if pieces else None)


def describe(rows, pitches, label):
    note = label['midi_note']
    start, end = label['start_sample'], label['end_sample']
    spans = pitches.get(note, [])
    endings = [b for _, b in spans if b <= start]
    anchor = max(endings) if endings else 0
    starts = [a for a, _ in spans if a >= start]
    boundaries = [row[0] for row in rows]

    def owners_at(sample):
        i = bisect_right(boundaries, sample)-1
        return rows[i][2] if i >= 0 and sample < rows[i][1] else ()

    empty = merge((a, b) for a, b, owners in rows if not owners)
    other_counts = [sum(other != note for _, other in owners)
                    for a, b, owners in rows if a < end and b > start]
    empty_label = clip(empty, start, end)
    empty_since = clip(empty, anchor, end)
    return dict(
        target_metrics=metrics(spans, label),
        target_present_at_label_start=any(a <= start < b for a, b in spans),
        last_target_disappearance_sample=max(endings) if endings else None,
        analysis_start_sample=anchor,
        next_target_appearance_sample=min(starts) if starts else None,
        owners_after_anchor=[dict(voice_id=lane, note=n) for lane, n in owners_at(anchor)],
        owners_at_label_start=[dict(voice_id=lane, note=n) for lane, n in owners_at(start)],
        minimum_other_owner_count_during_label=min(other_counts, default=0),
        empty_output_intervals_since_anchor=empty_since,
        empty_output_samples_since_anchor=sum(b-a for a, b in empty_since),
        empty_output_intervals_during_label=empty_label,
        empty_output_samples_during_label=sum(b-a for a, b in empty_label),
        uninterrupted_rendered_ownership_since_anchor=not empty_since,
    )


def analyze(root=ROOT):
    report_path = root/'report/joint-rapid-reset/report/report.json'
    raw = report_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REPORT_SHA:
        raise ValueError('Report pin mismatch')
    report = json.loads(raw)
    result = dict(schema='m3_joint_reset_owner_attribution_v1', run_id=45075475603,
                  report_sha256=REPORT_SHA, datasets={})
    for dataset, data in report['datasets'].items():
        arms, inputs, identities = {}, {}, {}
        for arm in ('current', 'trial'):
            stem = f'{dataset}-{arm}-512'
            path = root/'owner-evidence'/f'{stem}-midi.tsv'
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            run = data['runs'][stem]
            if digest != run['midi_sha256']:
                raise ValueError('Raw event pin mismatch: '+stem)
            pitch = data['arms'][arm]['pitch']
            events = read_events(path, sample_count=pitch['sample_count'],
                                 transition_count=run['raw_audit']['raw_transitions'])
            conflicts = raw_conflicts(events)
            if any(conflicts['counts'].values()):
                raise ValueError('Conflicting raw event ownership: '+stem)
            rows = timeline(events, pitch['sample_count'])
            pitches = pitch_intervals(rows)
            checked = 0
            for label in pitch['labels']:
                actual = metrics(pitches.get(label['midi_note'], []), label)
                expected = {key: label[key] for key in actual}
                if actual != expected:
                    raise ValueError(f'Label identity mismatch: {stem} {label["label_index"]}: {actual} != {expected}')
                checked += 1
            arms[arm] = (rows, pitches, pitch)
            inputs[arm] = dict(path=str(path), sha256=digest, events=len(events))
            identities[arm] = dict(labels=checked, compared_fields=4, mismatches=0,
                                   raw_conflict_counts=conflicts['counts'])
        before = {x['label_index']: x for x in arms['current'][2]['labels']}
        after = {x['label_index']: x for x in arms['trial'][2]['labels']}
        if set(before) != set(after):
            raise ValueError('Label set mismatch')
        selected = [i for i, label in before.items()
                    if label['present_samples'] > 0 and after[i]['present_samples'] == 0]
        targets = []
        for i in selected:
            label = before[i]
            for key in ('midi_note', 'start_sample', 'end_sample'):
                if label[key] != after[i][key]:
                    raise ValueError('Label geometry changed')
            targets.append(dict(label_index=i, midi_note=label['midi_note'],
                                start_sample=label['start_sample'], end_sample=label['end_sample'],
                                arms={arm: describe(arms[arm][0], arms[arm][1], label)
                                      for arm in ('current', 'trial')}))
        result['datasets'][dataset] = dict(
            sample_rate=arms['current'][2]['sample_rate'], inputs=inputs,
            label_identity=identities, newly_wholly_missed_labels=selected, targets=targets,
            uninterrupted_trial_ownership_since_target_disappearance=sum(
                t['arms']['trial']['uninterrupted_rendered_ownership_since_anchor'] for t in targets))
    result['interpretation'] = (
        'Raw MIDI ownership is not complete candidate activity or signal history. '
        'An empty owner interval is only a reset opportunity, not proof; continued '
        'owners contradict only the simple last-rendered-owner explanation. '
        'Diagnostic releases are not separately marked. No policy or acceptance claim.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.root)
    with args.out.open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps({name: dict(labels=data['newly_wholly_missed_labels'],
                               uninterrupted_trial_owner_cases=data['uninterrupted_trial_ownership_since_target_disappearance'])
                      for name, data in result['datasets'].items()}, indent=2))


if __name__ == '__main__':
    main()
