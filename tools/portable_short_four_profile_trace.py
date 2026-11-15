"""Observe the existing early harmonic-profile route on one short four-string group.

One unchanged current-ON replay; no admission policy or threshold is changed.
Native execution belongs on the GitHub worker, using the existing input bundle.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from tools.portable_assignment_trace import profile_addition_summary
from tools.portable_corpus_replay import SETTINGS
from tools.portable_pending_string_trace import run as capture


DATASET = 'synthetic-four'
CASE = dict(label_index=36, midi_note=53, string_mask=8,
            start_sample=2073693, end_sample=2294400)
GROUP = dict(label_indices=[36, 37, 38, 39], string_masks=[8, 4, 2, 1],
             midi_note=53, string_mask=15, start_sample=2073693, end_sample=2294400)
WINDOW = (2073408, 2294400)
CONDITIONS = (('current-on', ('--diagnostic-spectral-lane-collision',)),)
REFERENCE_SCHEMA = 'm3_short_four_profile_references_v1'
INPUT_NAMES = (DATASET + '.wav', DATASET + '.tsv', 'calibration.m3cb', 'templates.tsv')
INTERPRETATION = (
    'Label36 is a singleton annotation (mask8); labels36-39 together expect mask15. '
    'Exact group masks require every intended string and no extra string for note53. '
    'All-label snapshot matches count expected assignments found, with false outputs separate. '
    'Unobserved values are not zero. Profile-fit absence does not name the failed prerequisite. '
    'First-addition reasons describe only the first greedy pass; accepted is not final group '
    'admission, and later veto reasons are not fully observed. These are fits to one aggregate '
    'harmonic observation, not independent string evidence. No note gain, timing, safe new '
    'admission or external host delivery is established by this unchanged-output trace.')


def validate_reference(reference, manifest):
    if (reference['schema'] != REFERENCE_SCHEMA or reference['dataset'] != DATASET
            or reference['case'] != CASE or reference['group'] != GROUP
            or reference['window'] != list(WINDOW) or reference['block_samples'] != 512
            or reference['settings'] != SETTINGS
            or reference['conditions'] != {name: list(flags) for name, flags in CONDITIONS}
            or set(reference['replay_references']) != {'current-on'}):
        raise ValueError('Wrong fixed short-four reference selection')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if reference['source'][key] != manifest['source'][key]:
            raise ValueError('Saved input provenance differs: ' + key)
    for name in INPUT_NAMES:
        if reference['inputs'][name] != manifest['files'][name]:
            raise ValueError('Saved input identity differs: ' + name)
    saved = reference['replay_references']['current-on']
    for key in ('tsv_sha256', 'midi_sha256', 'outcome_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', saved.get(key, '')):
            raise ValueError('A saved complete digest is required: ' + key)
    if saved['sample_count'] != 5529600 or saved['sample_rate'] != 96000:
        raise ValueError('Saved sample clock differs')
    for index, mask in zip(GROUP['label_indices'], GROUP['string_masks']):
        expected = dict(CASE, label_index=index, string_mask=mask)
        if any(saved['held_labels'][str(index)][key] != value for key, value in expected.items()):
            raise ValueError('Saved group annotation differs')


def chronology(assignments, frames, label):
    """Summarize observed profile decisions; retain full joint rows in bulk evidence."""
    if label != CASE:
        raise ValueError('Wrong singleton anchor for four-string group')
    by_sample = {int(row['sample']): row for row in assignments
                 if int(row['observed']) and int(row['note']) == CASE['midi_note']}
    profiles, counts, histograms, first_contexts = [], Counter(), {}, []
    seen_contexts = set()
    for frame in frames:
        sample = frame['sample']
        if not CASE['start_sample'] <= sample < CASE['end_sample']:
            continue
        counts['label_frames'] += 1
        target = by_sample.get(sample)
        render = target is not None and bool(int(target['render_observed']))
        state, route = frame['candidate_state'], frame['routing']
        route_seen = bool(route['render_observed'] or route['continuity_observed'])
        masks = dict(
            fine=None if state is None else state['fine_mask'],
            committed=None if state is None else state['committed_mask'],
            final=None if target is None or not int(target['valid']) else int(target['final_mask']),
            proposed=None if not render else int(target['group_proposal']),
            rendered=None if not render else int(target['rendered_mask']),
            midi=None if not route_seen else route['midi_after'])
        for name, mask in masks.items():
            histograms.setdefault(name, Counter())[str(mask) if mask is not None else 'unobserved'] += 1
        counts['all_group_labels_matched'] += set(GROUP['label_indices']).issubset(frame['matched_labels'])
        profile = None if not render else bool(int(target['profile_fit_observed']))
        counts['profile_' + ('unobserved' if profile is None else 'fit' if profile else 'not_fit')] += 1
        if profile:
            profiles.append(target)
            counts['profile_long_memory' if int(target['profile_uses_long_memory']) else 'profile_short_memory'] += 1
        # A compact example for each observed prerequisite/first-pass disposition.
        # Bulk traces retain every tick and every competing pitch, without this cap.
        keys = ('candidate_age_ticks', 'playable', 'dp_primary', 'prior_midi', 'group_before',
                'group_proposal', 'group_after', 'beat_valid', 'fine_valid', 'fine_mask',
                'profile_fit_observed', 'profile_uses_long_memory', 'profile_first_pass_reasons')
        context = None if not render else {key: target[key] for key in keys}
        signature = None if context is None else tuple(value for key, value in context.items()
                                                       if key != 'candidate_age_ticks')
        if signature not in seen_contexts:
            seen_contexts.add(signature)
            if len(first_contexts) < 32:
                first_contexts.append(dict(sample=sample, offset_from_group_start=sample-CASE['start_sample'],
                    masks=masks, profile_context=context))
    if not counts['label_frames']:
        raise ValueError('No frames inside the selected group')
    return dict(group=GROUP, singleton_anchor=CASE, window_frames=len(frames), counts=dict(counts),
        mask_histograms={key: dict(value) for key, value in histograms.items()},
        profile_first_addition=profile_addition_summary(profiles),
        observed_context_count=len(seen_contexts), first_contexts=first_contexts,
        interpretation=INTERPRETATION)


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    validate_reference(json.loads(reference_path.read_text()), json.loads(manifest_path.read_text()))
    return capture(binary, corpus, manifest_path, reference_path, output,
        timeout=timeout, dataset=DATASET, cases=(CASE,), conditions=CONDITIONS,
        window=lambda label: WINDOW, diagnose=chronology,
        schema='m3_short_four_profile_trace_v1', interpretation=INTERPRETATION)


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
