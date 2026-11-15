"""Bounded note-safety screen for a default-off physical three-string trial.

Native work runs on replacement compute. Stop after physical-long if the target
hold does not improve safely; do not spend the rest of the budget on parity.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.portable_assignment_trace import compress_trace_window, digest
from tools.portable_calibrated_midi_retention_corpus import (
    analyze_midi, compare_notes, saved_identity, verify_references)
from tools.portable_corpus_replay import SETTINGS, command_for, now


OFF, CURRENT, TRIAL = 'reference-off', 'current-on', 'suppressed-adjacent-admission-on'
FLAG = '--diagnostic-suppressed-adjacent-admission'
COLLISION = '--diagnostic-spectral-lane-collision'
CONDITIONS = ((OFF, ()), (CURRENT, (COLLISION,)), (TRIAL, (COLLISION, FLAG)))
SCREEN_DATASETS = ('physical-long', 'ordinary', 'constructed', 'synthetic-four')
TARGET = dict(label_index=3, midi_note=40, string_mask=7,
              start_sample=2932608, end_sample=5452800)
POLICIES = {
    'suppressed-adjacent-admission': dict(mode=TRIAL, flag=FLAG,
        schema='m3_suppressed_adjacent_admission_trial_v1',
        description='Default-off raw-admission veto only for an already active spectrally '
            'suppressed singleton without current direct/local/M3 evidence, whose settled '
            'phase stays in a supported adjacent active MIDI peer cell for 160 ms. '
            'Preserve existing physical/MIDI release paths; no note or label exception.'),
    'fine-subset-consensus': dict(mode='fine-subset-consensus-on',
        flag='--diagnostic-fine-subset-consensus', schema='m3_fine_subset_consensus_trial_v1',
        description='Default-off initial fine acquisition only: carry pending inclusion '
            'count when a qualified group strictly shrinks, retains the established '
            'singleton, and has current connected beat support no weaker than the old '
            'full-mask minimum. Keep the existing beat EMA, consensus duration and '
            'ownership guards. Historical subset-fit coherence is not measured.'),
    'qualified-tier-retention': dict(mode='qualified-tier-retention-on',
        flag='--diagnostic-qualified-tier-retention', schema='m3_qualified_tier_retention_trial_v1',
        description='Default-off inference correction: apply a freshly qualified '
            'bounded spectral-tier completion even when it equals the current group. '
            'Equality alone cannot preserve a lane. Keep the existing spectral, beat, '
            'energy, primary, ownership and capacity guards; no new delay or threshold.')}


def target_hold(current, trial):
    result = {}
    for name, row in (('before', current), ('after', trial)):
        labels = [label for label in row['midi_lifecycle']['labels']
                  if label['label_index'] == TARGET['label_index']]
        if len(labels) != 1 or any(labels[0][key] != value for key, value in TARGET.items()):
            raise ValueError('Physical three-string target identity differs')
        result[name] = labels[0]
    before, after = result['before'], result['after']
    result['improved'] = (after['exact_held_samples'] > before['exact_held_samples']
                         and after['note_ons_inside_label'] < before['note_ons_inside_label'])
    return result


def run(binary, corpus, manifest_path, reference_path, output, max_seconds=2400,
        policy='suppressed-adjacent-admission'):
    if max_seconds <= 0:
        raise ValueError('max_seconds must be positive')
    selection = POLICIES[policy]
    trial_mode = selection['mode']
    conditions = ((OFF, ()), (CURRENT, (COLLISION,)),
                  (trial_mode, (COLLISION, selection['flag'])))
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    manifest = json.loads(manifest_path.read_text())
    references = json.loads(reference_path.read_text())
    report = dict(schema=selection['schema'], started_at=now(),
        state='running', final=False, stage='verify saved references and inputs',
        source=manifest.get('source', {}), settings=SETTINGS, block_samples=512,
        reference_manifest_sha256=digest(reference_path),
        reference_report_sha256=references['anchor_report_sha256'],
        reference_source=references['source'], input_manifest_sha256=digest(manifest_path),
        binary_sha256=digest(binary), declared_datasets=list(SCREEN_DATASETS), datasets={},
        conditions={mode: list(flags) for mode, flags in conditions}, target=TARGET,
        policy=selection['description'], policy_name=policy,
        metric_scope='Snapshot assignments, overlapping held label-samples and false '
            'voice-samples/onsets are separate. Gap outputs are extra notes, not missing notes.',
        installed_output_changed=False, promotion_accepted=False,
        buffer_identity='not measured', native_timing='not measured',
        allocations='not measured', live_readiness='not measured')
    deadline = time.monotonic() + max_seconds

    def save():
        report['updated_at'] = now()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        report['verified_inputs'] = verify_references(references, manifest, corpus)
        for name in SCREEN_DATASETS:
            dataset = report['datasets'][name] = dict(runs={})
            cached = {}
            for mode, flags in conditions:
                stem = name + '-' + mode + '-512'
                report.update(stage='bounded replay', current_run=stem)
                save()
                tsv, stderr, timing = (output / (stem + suffix)
                                      for suffix in ('.tsv', '.stderr', '-timing.json'))
                midi = output / (stem + '-midi.tsv')
                command = command_for(binary, corpus, name, 'off', 512, timing, midi_trace=midi)
                command.extend(flags)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Bounded screen wall-clock budget exhausted')
                started = time.monotonic()
                with tsv.open('w') as out, stderr.open('w') as err:
                    subprocess.run(command, stdout=out, stderr=err,
                                   timeout=min(900, remaining), check=True)
                replay = read_replay(tsv)
                lifecycle = analyze_midi(midi, tsv, replay)
                row = dict(elapsed_seconds=time.monotonic() - started,
                    output=replay['output'], exact_matches_by_string_count=replay['exact_matches_by_string_count'],
                    tsv_sha256=digest(tsv), command=command, midi_lifecycle=lifecycle,
                    sample_count=lifecycle['sample_count'], sample_rate=lifecycle['sample_rate'])
                dataset['runs'][mode] = row
                row['midi_trace'] = compress_trace_window(midi, start=0, end=row['sample_count'])
                row['midi_trace_sha256'] = row['midi_trace']['raw_sha256']
                midi.unlink()
                if mode in (OFF, CURRENT):
                    row['saved_reference_bit_identical'] = saved_identity(
                        row, references['datasets'][name][mode])
                    if not row['saved_reference_bit_identical']:
                        raise ValueError('Saved reference identity drift: ' + stem)
                cached[mode] = replay
                save()
            dataset['comparison'] = compare_notes(dataset['runs'][CURRENT], dataset['runs'][trial_mode],
                cached[CURRENT], cached[trial_mode], require_inference=False)
            dataset['snapshot_vs_off'] = compare_replays(cached[OFF], cached[trial_mode])
            dataset['note_safety_pass'] = bool(dataset['comparison']['note_safety_pass']
                                              and dataset['snapshot_vs_off']['gate_pass'])
            if name == 'physical-long':
                report['target_hold'] = target_hold(dataset['runs'][CURRENT], dataset['runs'][trial_mode])
            save()
            if not dataset['note_safety_pass']:
                report.update(state='rejected', stage='stopped at note safety regression')
                break
            if name == 'physical-long' and not report['target_hold']['improved']:
                report.update(state='rejected', stage='stopped without target hold and attack improvement')
                break
        else:
            report.update(state='completed', stage='final bounded screen')
    except Exception as error:
        report.update(state='failed', stage='failed', error=str(error), error_type=type(error).__name__)
        stem = report.get('current_run')
        if stem and (output / (stem + '.stderr')).exists():
            report['failure_stderr'] = stem + '.stderr'
            report['failure_stderr_tail'] = (output / (stem + '.stderr')).read_text()[-2048:]
        raise
    finally:
        rows = list(report['datasets'].values())
        complete = report['state'] == 'completed' and len(rows) == len(SCREEN_DATASETS)
        report['note_safety_datasets_passed'] = sum(row.get('note_safety_pass', False) for row in rows)
        report['completed_datasets'] = sum('comparison' in row for row in rows)
        report['reference_identity_pass'] = bool(rows) and all(
            row['runs'].get(mode, {}).get('saved_reference_bit_identical', False)
            for row in rows for mode in (OFF, CURRENT))
        report['bounded_screen_pass'] = bool(complete and report['reference_identity_pass']
            and report['note_safety_datasets_passed'] == len(SCREEN_DATASETS)
            and report.get('target_hold', {}).get('improved', False))
        report['decision'] = ('eligible for full corpus and native safety checks; not promotion'
            if report['bounded_screen_pass'] else 'rejected or incomplete; inspect separate gates')
        report.update(final=True, finished_at=now())
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('binary', 'corpus', 'manifest', 'references', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--max-seconds', type=int, default=2400)
    parser.add_argument('--policy', choices=tuple(POLICIES), default='suppressed-adjacent-admission')
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.references, args.output,
        args.max_seconds, args.policy)


if __name__ == '__main__':
    main()
