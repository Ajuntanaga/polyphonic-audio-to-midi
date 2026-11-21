"""Compare OFF, saved current ON and a bounded-screen policy on replacement compute.

Snapshot inference, raw held-note safety and untraced native timing are separate
gates. A successful offline screen never promotes or installs the candidate.
"""
import argparse
import csv
import json
import os
import re
from pathlib import Path
import subprocess
import time

from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.midi_lifecycle_analysis import (
    CONFLICT_FIELDS, OUTPUT_SAFETY_FIELDS, raw_conflicts, read_events, summarize)
from tools.portable_assignment_trace import compress_trace_window, digest
from tools.portable_calibrated_midi_retention_trial import CONDITIONS
from tools.portable_corpus_replay import BLOCKS, SETTINGS, command_for, now, timing_gates
from tools.portable_routing_trace import outcome_window
from tools.replay_corpus import DATASETS


REFERENCE_SCHEMA = 'm3_calibrated_midi_retention_corpus_references_v1'
OFF, CURRENT, TRIAL = (mode for mode, _ in CONDITIONS)
POLICIES = {
    'upper-fretted-relief': dict(
        conditions=CONDITIONS[:2] + (('upper-fretted-relief-on', (
            '--diagnostic-spectral-lane-collision', '--diagnostic-upper-fretted-relief')),),
        require_inference=False,
        datasets=('ordinary', 'extended-middle', 'physical-long', 'extended-high',
                  'isolated-02', 'isolated-05', 'isolated-08')),
    'calibrated-midi-retention': dict(conditions=CONDITIONS, require_inference=True),
    'qualified-tier-retention': dict(
        conditions=CONDITIONS[:2] + (('qualified-tier-retention-on', (
            '--diagnostic-spectral-lane-collision', '--diagnostic-qualified-tier-retention')),),
        require_inference=False),
    'completion-midi-retention': dict(
        conditions=CONDITIONS[:2] + (('completion-midi-retention-on', (
            '--diagnostic-spectral-lane-collision', '--diagnostic-completion-midi-retention')),),
        require_inference=True),
}
LABEL_IDENTITY = ('label_index', 'midi_note', 'string_mask', 'start_sample', 'end_sample')


def verify_references(reference, manifest, corpus):
    if (reference['schema'] != REFERENCE_SCHEMA or reference['settings'] != SETTINGS
            or reference['block_samples'] != 512
            or reference['reference_flags'] != {mode: list(flags) for mode, flags in CONDITIONS[:2]}
            or set(reference['datasets']) != set(DATASETS)):
        raise ValueError('Invalid saved corpus reference selection')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if manifest['source'][key] != reference['source'][key]:
            raise ValueError('Saved corpus input provenance differs: ' + key)
    names = {'calibration.m3cb', 'templates.tsv'} | {
        name + suffix for name in DATASETS for suffix in ('.wav', '.tsv')}
    if set(manifest['files']) != names:
        raise ValueError('Manifest does not contain exactly the declared corpus inputs')
    for name in sorted(names):
        if digest(corpus / name) != manifest['files'][name]['sha256']:
            raise ValueError('Input hash mismatch: ' + name)
    return len(names)


def saved_identity(row, reference):
    return all(row[key] == reference[key] for key in (
        'output', 'exact_matches_by_string_count', 'tsv_sha256',
        'midi_trace_sha256', 'sample_count', 'sample_rate'))


def analyze_midi(trace, tsv, replay):
    with tsv.open(newline='') as stream:
        aggregate = next(csv.DictReader(stream, delimiter='\t'))
    clock = {}
    for key in ('samples', 'sample_rate', 'transitions'):
        if not aggregate[key].isascii() or not aggregate[key].isdigit():
            raise ValueError('Invalid replay sample clock or transition count')
        clock[key] = int(aggregate[key])
    if clock['sample_rate'] != 96000:
        raise ValueError('Unexpected recording sample rate')
    events = read_events(trace, sample_count=clock['samples'],
                         transition_count=clock['transitions'])
    result = summarize(events, replay['labels'], sample_count=clock['samples'],
                       sample_rate=clock['sample_rate'], include_output_safety=True,
                       include_group_coverage=True, include_pitch_set_coverage=True)
    result['raw_midi'] = raw_conflicts(events)
    return result


def compare_notes(current, trial, current_replay, trial_replay, *, require_inference=True):
    snapshot = compare_replays(current_replay, trial_replay)
    same_clock = (current['sample_count'] == trial['sample_count']
                  and current['sample_rate'] == trial['sample_rate'])
    inference = None
    if 'outcome_trace' in current and 'outcome_trace' in trial:
        inference = (
            {k: v for k, v in current['output'].items() if k != 'fingerprint'}
            == {k: v for k, v in trial['output'].items() if k != 'fingerprint'}
            and current_replay['labels'] == trial_replay['labels']
            and current['exact_matches_by_string_count'] == trial['exact_matches_by_string_count']
            and current['outcome_trace']['raw_sha256'] == trial['outcome_trace']['raw_sha256']
            and same_clock)
    before, after = current['midi_lifecycle'], trial['midi_lifecycle']
    valid = before['coverage_valid'] and after['coverage_valid']
    changed, held_delta, safety_delta = [], None, None
    if valid:
        a, b = before['labels'], after['labels']
        if (len(a) != len(b) or any(left[key] != right[key]
                for left, right in zip(a, b) for key in LABEL_IDENTITY)):
            raise ValueError('Held-label identity differs')
        for left, right in zip(a, b):
            delta = right['exact_held_samples'] - left['exact_held_samples']
            attacks = right['note_ons_inside_label'] - left['note_ons_inside_label']
            if delta or attacks:
                changed.append(dict(label_index=left['label_index'],
                    midi_note=left['midi_note'], exact_held_samples_before=left['exact_held_samples'],
                    exact_held_samples_after=right['exact_held_samples'], held_delta=delta,
                    note_ons_before=left['note_ons_inside_label'],
                    note_ons_after=right['note_ons_inside_label'], note_on_delta=attacks))
        held_delta = after['exact_held_samples'] - before['exact_held_samples']
        if before['output_safety']['valid'] and after['output_safety']['valid']:
            safety_delta = {key: after['output_safety']['counts'][key]
                            - before['output_safety']['counts'][key]
                            for key in OUTPUT_SAFETY_FIELDS}
    conflicts = {key: after['raw_midi']['counts'][key] - before['raw_midi']['counts'][key]
                 for key in CONFLICT_FIELDS}
    losses = [row for row in changed if row['held_delta'] < 0]
    improved = [row for row in changed if row['held_delta'] > 0 and row['note_on_delta'] < 0]
    safe = (valid and not losses and safety_delta is not None
            and all(value <= 0 for value in safety_delta.values())
            and all(value <= 0 for value in conflicts.values()))
    return dict(snapshot=snapshot, inference_bit_identical=inference,
        inference_identity_required=require_inference, sample_clock_identical=same_clock,
        held_pairing_valid=valid, changed_held_labels=changed, held_losses=losses,
        improved_hold_and_attack_labels=improved, exact_held_samples_delta=held_delta,
        output_safety_delta=safety_delta, raw_conflict_delta=conflicts,
        note_safety_pass=bool(snapshot['gate_pass'] and same_clock and safe
                             and (inference is True or not require_inference)))


def buffer_identity(reference, replay):
    comparison = compare_replays(reference, replay)
    return (comparison['output_bit_identical'] and not comparison['changed_labels']
            and reference['exact_matches_by_string_count'] == replay['exact_matches_by_string_count'])


def relief_counters(stderr):
    keys = ('evaluated', 'no_parent', 'related_blocked', 'applied',
            'rendered_disagreements', 'active_only', 'rendered_only')
    lines = [line.split('upper_fretted_relief ', 1)[1] for line in stderr.splitlines()
             if line.startswith('m3_replay: upper_fretted_relief ')]
    if len(lines) != 1:
        raise ValueError('Missing or duplicate relief mechanism counters')
    pairs = re.findall(r'(\w+)=(\d+)', lines[0])
    if tuple(key for key, _ in pairs) != keys:
        raise ValueError('Malformed relief mechanism counters')
    result = {key: int(value) for key, value in pairs}
    if (result['evaluated'] != result['no_parent'] + result['related_blocked'] + result['applied']
            or result['rendered_disagreements'] != result['active_only'] + result['rendered_only']):
        raise ValueError('Relief counter accounting differs')
    return result


def relief_gate(comparison, before, after):
    # Snapshot comparison already enforces every label and false-output gate.
    gained = sum(max(0, b['matched'] - a['matched'])
                 for a, b in zip(before['labels'], after['labels'])
                 if 61 <= a['midi_note'] <= 71)
    attacks = [row for row in comparison['changed_held_labels'] if row['note_on_delta'] > 0]
    return dict(gained_matched_frames_61_71=gained,
                usefulness_pass=gained >= 5000,
                retrigger_regressions=attacks, retrigger_pass=not attacks)


def run(binary, corpus, manifest_path, reference_path, output, max_seconds=10800, *,
        policy='calibrated-midi-retention'):
    if max_seconds <= 0:
        raise ValueError('max_seconds must be positive')
    selection = POLICIES[policy]
    relief = policy == 'upper-fretted-relief'
    if relief and os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Native relief screen runs only on GitHub Actions')
    datasets_to_run = selection.get('datasets', DATASETS)
    conditions = selection['conditions']
    trial = conditions[-1][0]
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    manifest = json.loads(manifest_path.read_text())
    references = json.loads(reference_path.read_text())
    report = dict(schema='m3_' + policy.replace('-', '_') + '_corpus_v1',
        policy_name=policy, inference_identity_required=selection['require_inference'], started_at=now(),
        state='running', final=False, stage='verify saved references and corpus inputs',
        source=manifest.get('source', {}), settings=SETTINGS,
        reference_manifest_sha256=digest(reference_path),
        reference_report_sha256=references['anchor_report_sha256'],
        reference_source=references['source'], input_manifest_sha256=digest(manifest_path),
        binary_sha256=digest(binary), declared_datasets=len(datasets_to_run), dataset_names=list(datasets_to_run), datasets={},
        conditions={mode: list(flags) for mode, flags in conditions},
        timing_limits=dict(block_samples=32, sample_rate=96000, p99_ns=166666,
                           maximum_ns=333333, deadline_overruns=0),
        metric_scope='Snapshot assignments, overlapping held label-samples and raw false '
            'voice-samples/onsets are separate. Gap outputs are extra notes, not missing notes.',
        installed_output_changed=False, promotion_accepted=False, live_readiness='not measured')
    deadline = time.monotonic() + max_seconds

    def save():
        report['updated_at'] = now()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        report['verified_inputs'] = verify_references(references, manifest, corpus)
        for name in datasets_to_run:
            dataset = report['datasets'][name] = dict(runs={}, buffer_parity={})
            cached = {}
            for block in BLOCKS:
                for mode, flags in conditions:
                    stem = name + '-' + mode + '-' + str(block)
                    report.update(stage='corpus replay', current_run=stem)
                    save()
                    tsv, stderr, timing_path = (output / (stem + suffix)
                                               for suffix in ('.tsv', '.stderr', '-timing.json'))
                    midi, outcome = (output / (stem + suffix + '.tsv')
                                     for suffix in ('-midi', '-outcome'))
                    command = command_for(binary, corpus, name, 'off', block, timing_path,
                                          midi_trace=midi if block == 512 else None)
                    command.extend(flags)
                    if block == 512 and mode != OFF and not relief:
                        command.extend(('--outcome-trace', str(outcome)))
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Corpus wall-clock budget exhausted')
                    started = time.monotonic()
                    with tsv.open('w') as out, stderr.open('w') as err:
                        subprocess.run(command, stdout=out, stderr=err,
                                       timeout=min(1800, remaining), check=True)
                    replay = read_replay(tsv)
                    row = dict(elapsed_seconds=time.monotonic() - started,
                        output=replay['output'],
                        exact_matches_by_string_count=replay['exact_matches_by_string_count'],
                        tsv_sha256=digest(tsv), command=command)
                    dataset['runs'][mode + '-' + str(block)] = row
                    if relief and mode == trial:
                        row['upper_relief_counters'] = relief_counters(stderr.read_text())
                    if block == 512:
                        lifecycle = analyze_midi(midi, tsv, replay)
                        row.update(midi_lifecycle=lifecycle, sample_count=lifecycle['sample_count'],
                                   sample_rate=lifecycle['sample_rate'])
                        row['midi_trace'] = compress_trace_window(midi, start=0, end=row['sample_count'])
                        row['midi_trace_sha256'] = row['midi_trace']['raw_sha256']
                        midi.unlink()
                        if mode != OFF and not relief:
                            outcome_window(outcome, row['sample_count'], 0, 0)
                            row['outcome_trace'] = compress_trace_window(outcome, start=0,
                                                                       end=row['sample_count'])
                            outcome.unlink()
                        if mode in (OFF, CURRENT):
                            row['saved_reference_bit_identical'] = saved_identity(
                                row, references['datasets'][name][mode])
                            if not row['saved_reference_bit_identical']:
                                raise ValueError('Saved reference identity drift: ' + stem)
                        cached[mode] = replay
                    else:
                        dataset['buffer_parity'][mode + '-' + str(block)] = buffer_identity(
                            cached[mode], replay)
                        if block == 32:
                            row['timing'] = json.loads(timing_path.read_text())
                            row['gates'] = timing_gates(row['timing'], replay, block)
                    save()
                if block == 512:
                    dataset['comparison'] = compare_notes(dataset['runs'][CURRENT + '-512'],
                        dataset['runs'][trial + '-512'], cached[CURRENT], cached[trial],
                        require_inference=selection['require_inference'])
                    dataset['snapshot_vs_off'] = compare_replays(cached[OFF], cached[trial])
                    dataset['note_safety_pass'] = (dataset['comparison']['note_safety_pass']
                                                   and dataset['snapshot_vs_off']['gate_pass'])
                    if relief:
                        dataset['relief_gate'] = relief_gate(dataset['comparison'], cached[CURRENT], cached[trial])
                        current_holds = dataset['runs'][CURRENT + '-512']['midi_lifecycle']['labels']
                        trial_holds = dataset['runs'][trial + '-512']['midi_lifecycle']['labels']
                        dataset['relief_gate']['longest_hold_losses'] = [
                            a['label_index'] for a, b in zip(current_holds, trial_holds)
                            if b['longest_exact_hold_samples'] < a['longest_exact_hold_samples']]
                        dataset['note_safety_pass'] &= (dataset['relief_gate']['retrigger_pass']
                            and not dataset['relief_gate']['longest_hold_losses'])
                    save()
                    if not dataset['note_safety_pass']:
                        report.update(state='rejected', stage='stopped at note safety regression')
                        break
            if report['state'] == 'rejected':
                break
            dataset['buffer_pass'] = (len(dataset['buffer_parity']) == 6
                                      and all(dataset['buffer_parity'].values()))
            dataset['native_gate_pass'] = all(all(dataset['runs'][mode + '-32']['gates'].values())
                                              for mode, _ in conditions)
            save()
            if not dataset['buffer_pass']:
                report.update(state='rejected', stage='stopped at buffer identity regression')
                break
        else:
            report.update(state='completed', stage='final corpus screen')
    except Exception as error:
        report.update(state='failed', stage='failed', error=str(error), error_type=type(error).__name__)
        stem = report.get('current_run')
        if stem and (output / (stem + '.stderr')).exists():
            report['failure_stderr'] = stem + '.stderr'
            report['failure_stderr_tail'] = (output / (stem + '.stderr')).read_text()[-2048:]
        raise
    finally:
        datasets = list(report['datasets'].values())
        complete = report['state'] == 'completed' and len(datasets) == len(datasets_to_run)
        report['note_safety_datasets_passed'] = sum(d.get('note_safety_pass', False) for d in datasets)
        report['buffer_datasets_passed'] = sum(d.get('buffer_pass', False) for d in datasets)
        report['native_datasets_passed'] = sum(d.get('native_gate_pass', False) for d in datasets)
        report['native_datasets_passed_by_mode'] = {
            mode: sum(bool(d['runs'].get(mode + '-32', {}).get('gates'))
                      and all(d['runs'][mode + '-32']['gates'].values()) for d in datasets)
            for mode, _ in conditions}
        report['improved_hold_and_attack_labels'] = sum(len(d.get('comparison', {}).get(
            'improved_hold_and_attack_labels', [])) for d in datasets)
        report['reference_identity_pass'] = complete and all(
            d['runs'][mode + '-512'].get('saved_reference_bit_identical', False)
            for d in datasets for mode in (OFF, CURRENT))
        target_improved = None
        if policy in ('qualified-tier-retention', 'completion-midi-retention'):
            target_improved = any(row['label_index'] == 3 and row['midi_note'] == 40
                for row in report['datasets'].get('physical-long', {}).get('comparison', {}).get(
                    'improved_hold_and_attack_labels', []))
        report['required_target_hold_and_attack_improved'] = target_improved
        report['corpus_note_safety_pass'] = bool(complete and report['reference_identity_pass']
            and report['note_safety_datasets_passed'] == len(datasets_to_run)
            and (report['datasets'].get('ordinary', {}).get('relief_gate', {}).get('usefulness_pass', False)
                 if relief else report['improved_hold_and_attack_labels'] > 0)
            and target_improved is not False)
        report['full_corpus_screen_pass'] = bool(report['corpus_note_safety_pass']
            and report['buffer_datasets_passed'] == len(datasets_to_run)
            and report['native_datasets_passed'] == len(datasets_to_run))
        if relief:
            report['bounded_screen_pass'] = report.pop('full_corpus_screen_pass')
        passed = report.get('bounded_screen_pass', report.get('full_corpus_screen_pass', False))
        report['decision'] = (('bounded screen passed; no promotion or installed change' if relief
                               else 'eligible for external host validation; not promotion')
            if passed else 'rejected or incomplete; inspect separate gates')
        report.update(final=True, finished_at=now())
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('binary', 'corpus', 'manifest', 'references', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--max-seconds', type=int, default=10800)
    parser.add_argument('--policy', choices=POLICIES, default='calibrated-midi-retention')
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.references, args.output, args.max_seconds,
        policy=args.policy)


if __name__ == '__main__':
    main()
