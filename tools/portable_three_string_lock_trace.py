"""Trace the initial physical-long three-string delay without changing policy.

The fixed window follows a measured raw-MIDI delay in a completed corpus replay.
It is an annotation-relative diagnostic, not a physical onset or latency test.
All native execution belongs on the offloaded worker.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from tools.portable_assignment_trace import profile_addition_summary
from tools.portable_corpus_replay import SETTINGS
from tools.portable_pending_string_trace import run as capture


DATASET = 'physical-long'
CASE = dict(label_index=3, midi_note=40, string_mask=7,
            start_sample=2932608, end_sample=5452800)
WINDOW = (2932544, 3453312)
CONDITIONS = (('current-on', ('--diagnostic-spectral-lane-collision',)),)
REFERENCE_SCHEMA = 'm3_three_string_lock_references_v1'
INPUT_NAMES = (DATASET + '.wav', DATASET + '.tsv', 'calibration.m3cb', 'templates.tsv')
INTERPRETATION = (
    'Unchanged current-ON diagnostic. Exact masks mean all intended strings and no extra '
    'strings for this pitch. Missing observer values are unobserved, not zero. Times are '
    'relative to an annotation, not measured physical string onsets. Earlier state may '
    'predate the window. Stage order alone does not establish cause. Raw detector MIDI '
    'is not external host delivery; no native timing or live acceptance is established.')


def validate_reference(reference, manifest):
    if (reference['schema'] != REFERENCE_SCHEMA or reference['dataset'] != DATASET
            or reference['settings'] != SETTINGS or reference['case'] != CASE
            or reference['window'] != list(WINDOW) or reference['block_samples'] != 512
            or reference['conditions'] != {name: list(flags) for name, flags in CONDITIONS}
            or set(reference['replay_references']) != {'current-on'}):
        raise ValueError('Wrong fixed three-string reference selection')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if reference['source'][key] != manifest['source'][key]:
            raise ValueError('Saved input provenance differs: ' + key)
    for name in INPUT_NAMES:
        if reference['inputs'][name] != manifest['files'][name]:
            raise ValueError('Saved input identity differs: ' + name)
    row = reference['replay_references']['current-on']
    for key in ('tsv_sha256', 'midi_sha256', 'outcome_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', row.get(key, '')):
            raise ValueError('A saved complete digest is required: ' + key)
    held = row['held_labels'][str(CASE['label_index'])]
    if (row['sample_count'] != 5646848 or row['sample_rate'] != 96000
            or any(held[key] != value for key, value in CASE.items())
            or held['first_exact_hold_delay_samples'] != 520639
            or not WINDOW[0] <= CASE['start_sample'] + held['first_exact_hold_delay_samples'] < WINDOW[1]):
        raise ValueError('Saved annotation, sample clock or first exact hold changed')


def chronology(assignments, frames, label):
    """Summarize already clock/peer-validated observations, retaining unknowns.

    Keep stage milestones and compact transitions in the small report. Complete
    candidate/assignment observations remain in the bounded compressed evidence.
    """
    by_sample = defaultdict(list)
    for row in assignments:
        if int(row['observed']):
            by_sample[int(row['sample'])].append(row)
    expected = label['string_mask']
    stages, masks, observations, transitions = {}, defaultdict(Counter), {}, []
    previous = None
    in_label_count = 0
    targets = []
    for frame in frames:
        sample = frame['sample']
        in_label = label['start_sample'] <= sample < label['end_sample']
        in_label_count += in_label
        peers = by_sample.get(sample, [])
        target = next((row for row in peers if int(row['note']) == label['midi_note']), None)
        if target is not None:
            targets.append(target)
        state = frame['candidate_state']
        routing = frame['routing']
        route_observed = bool(routing['render_observed'] or routing['continuity_observed'])
        render_observed = target is not None and bool(int(target['render_observed']))
        values = dict(
            candidate_selected=state is not None and state['selection'] == 4,
            candidate_active=state is not None and bool(state['active']),
            fine_valid=None if state is None else bool(state['fine_valid']),
            fine_exact_mask=None if state is None else bool(state['fine_valid']) and state['fine_mask'] == expected,
            committed_exact_mask=None if state is None else state['committed_mask'] == expected,
            assignment_final_exact_mask=None if target is None else bool(int(target['valid'])) and int(target['final_mask']) == expected,
            assignment_rendered_exact_mask=None if not render_observed else int(target['rendered_mask']) == expected,
            route_midi_exact_mask=None if not route_observed else routing['midi_after'] == expected,
            snapshot_exact_label_match=None if not in_label else label['label_index'] in frame['matched_labels'])
        milestone = False
        for name, value in values.items():
            entry = stages.setdefault(name, dict(true=0, false=0, unobserved=0,
                label_true=0, label_false=0, label_unobserved=0,
                first_in_window=None, first_in_label=None))
            category = 'unobserved' if value is None else 'true' if value else 'false'
            entry[category] += 1
            if in_label:
                entry['label_' + category] += 1
            if value:
                when = dict(sample=sample, offset_from_label_start=sample-label['start_sample'])
                if entry['first_in_window'] is None:
                    entry['first_in_window'] = when
                    milestone = True
                if in_label and entry['first_in_label'] is None:
                    entry['first_in_label'] = when
                    milestone = True
        signature = tuple(values.values())
        if signature != previous:
            transitions.append(dict(sample=sample, offset_from_label_start=sample-label['start_sample'],
                                    stages=values))
        previous = signature
        for name in ('fine_mask', 'committed_mask', 'assigned_mask'):
            masks[name][str(state[name]) if state is not None else 'unobserved'] += 1
        for name in ('final_mask', 'rendered_mask', 'group_proposal', 'group_after'):
            observed = target is not None and (name == 'final_mask' or render_observed)
            masks['assignment_' + name][target[name] if observed else 'unobserved'] += 1
        masks['route_midi_mask'][str(routing['midi_after']) if route_observed else 'unobserved'] += 1
        if milestone:
            # Full target terms and all peers are in the bulk trace; retain the
            # stage fields that explain each milestone in this small report.
            observations[str(sample)] = dict(frame=frame, assignment=None if target is None else {
                key: target[key] for key in ('valid', 'prior_active', 'prior_primary', 'dp_primary',
                    'final_mask', 'rendered_mask', 'group_before', 'group_proposal', 'group_after',
                    'fine_valid', 'fine_mask', 'fine_pending_mask', 'profile_fit_observed',
                    'profile_primary_error', 'profile_mixture_error', 'profile_first_pass_reasons',
                    'profile_first_pass_alpha', 'profile_first_pass_errors')},
                peers=[{key: row[key] for key in ('note', 'ordinal', 'prior_active', 'prior_midi',
                    'playable', 'dp_primary', 'final_mask', 'valid')} for row in peers])
    if not frames or not in_label_count:
        raise ValueError('No observations inside the selected label')
    return dict(window_frames=len(frames), label_frames=in_label_count, stages=stages,
        mask_histograms={name: dict(counts) for name, counts in masks.items()},
        milestone_observations=observations, transition_count=len(transitions),
        first_transitions=transitions[:32], profile_first_addition=profile_addition_summary(targets),
        interpretation=INTERPRETATION)


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    validate_reference(json.loads(reference_path.read_text()), json.loads(manifest_path.read_text()))
    return capture(binary, corpus, manifest_path, reference_path, output,
        timeout=timeout, dataset=DATASET, cases=(CASE,), conditions=CONDITIONS,
        window=lambda label: WINDOW, diagnose=chronology,
        schema='m3_three_string_lock_trace_v1', interpretation=INTERPRETATION)


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
