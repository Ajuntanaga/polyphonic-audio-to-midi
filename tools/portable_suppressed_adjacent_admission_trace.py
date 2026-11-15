"""Observe the two saved policies around six extra raw note-52 lane switches.

Only the offloaded worker runs the native replay. This changes no DSP policy.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from tools.portable_corpus_replay import SETTINGS
from tools.portable_pending_string_trace import run as capture
from tools.portable_three_string_lock_trace import CASE, DATASET, INPUT_NAMES


WINDOW = (3409856, 3453312)
CONDITIONS = (
    ('current-on', ('--diagnostic-spectral-lane-collision',)),
    ('suppressed-adjacent-admission-on', ('--diagnostic-spectral-lane-collision',
                                       '--diagnostic-suppressed-adjacent-admission')))
ANCHORS = (3409919, 3424639, 3424703, 3425791, 3430079, 3430399,
           3431295, 3431551, 3439551, 3439679, 3453183, 3453247)
WATCHED = (39, 40, 52)
REFERENCE_SCHEMA = 'm3_suppressed_adjacent_admission_trace_references_v1'
INTERPRETATION = (
    'Paired observation of the unchanged current and rejected admission policies. '
    'Complete scored output and raw MIDI must match each saved reference; current-ON '
    'also preserves its saved complete outcome. A prior complete outcome for the '
    'rejected trial was not measured. Admission and complete selected-peer costs '
    'are observations, not proof of a sufficient replacement rule. Raw MIDI is not '
    'host delivery. No timing, allocation or live acceptance is measured here.')


def validate_reference(reference, manifest):
    if (reference['schema'] != REFERENCE_SCHEMA or reference['dataset'] != DATASET
            or reference['settings'] != SETTINGS or reference['case'] != CASE
            or reference['window'] != list(WINDOW) or reference['block_samples'] != 512
            or reference['conditions'] != {name: list(flags) for name, flags in CONDITIONS}
            or set(reference['replay_references']) != {name for name, _ in CONDITIONS}):
        raise ValueError('Wrong fixed paired admission reference selection')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if reference['source'][key] != manifest['source'][key]:
            raise ValueError('Saved input provenance differs: ' + key)
    for name in INPUT_NAMES:
        if reference['inputs'][name] != manifest['files'][name]:
            raise ValueError('Saved input identity differs: ' + name)
    for policy, _ in CONDITIONS:
        row = reference['replay_references'][policy]
        keys = ('tsv_sha256', 'midi_sha256') + (('outcome_sha256',) if policy == 'current-on' else ())
        for key in keys:
            if not re.fullmatch('[0-9a-f]{64}', row.get(key, '')):
                raise ValueError('A saved complete digest is required: ' + key)
        held = row['held_labels'][str(CASE['label_index'])]
        if (row['sample_count'] != 5646848 or row['sample_rate'] != 96000
                or any(held[key] != value for key, value in CASE.items())
                or held['first_exact_hold_delay_samples'] != 520639):
            raise ValueError('Saved annotation, sample clock or first exact hold changed')


def diagnose(assignments, frames, label):
    """Retain complete joint terms at anchors and stage counts across the window."""
    by_sample = defaultdict(list)
    for row in assignments:
        if int(row['observed']):
            by_sample[int(row['sample'])].append(row)
    counts = {str(note): Counter() for note in WATCHED}
    previous, observed_notes, changes, anchors = None, None, [], {}
    for frame in frames:
        peers = frame['admission_peers']
        if peers is None or not set(WATCHED) <= set(peers):
            raise ValueError('Missing watched admission observations')
        if observed_notes is not None and set(peers) != observed_notes:
            raise ValueError('Incomplete admission peer coverage')
        observed_notes = set(peers)
        selected = by_sample[frame['sample']]
        if any(int(row['note']) not in peers for row in selected):
            raise ValueError('Selected assignment peer lacks admission observation')
        for note in WATCHED:
            row = peers[note]
            counts[str(note)].update(frames=1, qualifies=row['qualifies'],
                filtered=row['raw_before'] and not row['raw_after'],
                selected=row['selection'] == 4,
                prior_active=row['prior_active'], post_active=row['post_active'],
                prior_suppressed=row['prior_suppressed'],
                post_suppressed=row['post_suppressed'],
                midi_owned=bool(row['post_midi']))
        signature = tuple(tuple(peers[note][key] for key in ('raw_after', 'qualifies',
            'selection', 'prior_suppressed', 'post_suppressed', 'post_assigned', 'post_midi'))
            for note in WATCHED)
        if previous is None or signature != previous[1]:
            changes.append(dict(sample=frame['sample'],
                                peers={str(note): peers[note] for note in WATCHED}))
        if frame['sample'] in ANCHORS:
            anchors[str(frame['sample'])] = dict(
                prior=None if previous is None else previous[0],
                current=dict(sample=frame['sample'],
                    peers={str(note): peers[note] for note in WATCHED},
                    complete_selected_assignments=selected))
        previous = (dict(sample=frame['sample'],
                         peers={str(note): peers[note] for note in WATCHED},
                         complete_selected_assignments=selected), signature)
    if set(map(int, anchors)) != set(ANCHORS):
        raise ValueError('Missing saved event anchors')
    return dict(window_frames=len(frames), observed_notes=sorted(observed_notes),
        counts={note: dict(value) for note, value in counts.items()},
        state_change_count=len(changes), first_state_changes=changes[:20],
        anchors=anchors, interpretation=INTERPRETATION)


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    validate_reference(json.loads(reference_path.read_text()), json.loads(manifest_path.read_text()))
    return capture(binary, corpus, manifest_path, reference_path, output,
        timeout=timeout, dataset=DATASET, cases=(CASE,), conditions=CONDITIONS,
        window=lambda label: WINDOW, diagnose=diagnose,
        schema='m3_suppressed_adjacent_admission_trace_v1', interpretation=INTERPRETATION)


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
