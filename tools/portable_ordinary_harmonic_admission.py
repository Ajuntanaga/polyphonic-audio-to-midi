"""One ordinary-corpus admission screen; recorded audio and native work run on GHA.

Generate past-only cues from a separately frozen current-detector shadow. This
tests an offline admission hypothesis, not a native feedback implementation.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

import numpy as np
from scipy.io import wavfile

from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.harmonic_admission_cues import CONFIG, generate
from tools.portable_assignment_trace import compress_trace_window, digest
from tools.portable_calibrated_midi_retention_corpus import (
    analyze_midi, compare_notes, saved_identity)
from tools.portable_corpus_replay import SETTINGS, command_for, now


OFF, CURRENT, TRIAL = 'reference-off', 'current-on', 'harmonic-admission-on'
COLLISION = '--diagnostic-spectral-lane-collision'
REFERENCE_FLAGS = {OFF: [], CURRENT: [COLLISION]}
REFERENCE_SCHEMA = 'm3_ordinary_harmonic_admission_references_v1'
RATE, SAMPLES = 96000, 10689600
INPUTS = {'ordinary.wav', 'ordinary.tsv', 'calibration.m3cb', 'templates.tsv'}
TARGET = dict(label_index=10, midi_note=75, string_mask=128,
              start_sample=163306, end_sample=235200)


def verify_references(reference, manifest, corpus):
    if (reference['schema'] != REFERENCE_SCHEMA or reference['dataset'] != 'ordinary'
            or reference['settings'] != SETTINGS or reference['block_samples'] != 512
            or reference['reference_flags'] != REFERENCE_FLAGS
            or reference['config'] != CONFIG or reference['target'] != TARGET
            or set(reference['inputs']) != INPUTS
            or set(reference['runs']) != {OFF, CURRENT}):
        raise ValueError('Invalid frozen harmonic-admission reference selection')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if manifest['source'][key] != reference['source'][key]:
            raise ValueError('Saved input provenance differs: ' + key)
    for name in sorted(INPUTS):
        spec = reference['inputs'][name]
        if (manifest['files'][name]['sha256'] != spec['sha256']
                or (corpus / name).stat().st_size != spec['bytes']
                or digest(corpus / name) != spec['sha256']):
            raise ValueError('Saved input identity differs: ' + name)
    for row in reference['runs'].values():
        if (row['sample_count'], row['sample_rate']) != (SAMPLES, RATE):
            raise ValueError('Saved ordinary sample clock differs')
    return len(INPUTS)


def load_audio(path):
    rate, audio = wavfile.read(path, mmap=True)
    if rate != RATE or audio.ndim != 1 or len(audio) != SAMPLES or audio.dtype != np.int16:
        raise ValueError('Expected complete ordinary PCM16 mono 96kHz recording')
    return audio


def target_result(current, trial, current_replay, trial_replay):
    result = {}
    for name, row, replay in (('before', current, current_replay), ('after', trial, trial_replay)):
        held = [label for label in row['midi_lifecycle']['labels']
                if label['label_index'] == TARGET['label_index']]
        snapshots = [label for label in replay['labels']
                     if label['label_index'] == TARGET['label_index']]
        if (len(held) != 1 or len(snapshots) != 1
                or any(held[0][key] != value or snapshots[0][key] != value
                       for key, value in TARGET.items())):
            raise ValueError('Missing-note target identity differs')
        result[name] = dict(held[0], snapshot_matched=snapshots[0]['matched'],
                            snapshot_labeled=snapshots[0]['labeled'])
    before, after = result['before'], result['after']
    if before['exact_held_samples'] != 0 or before['note_ons_inside_label'] != 0:
        raise ValueError('Missing-note baseline no longer matches the declared target')
    result['improved'] = bool(after['exact_held_samples'] > 0
        and after['note_ons_inside_label'] > 0
        and after['snapshot_matched'] > before['snapshot_matched'])
    return result


def run(binary, corpus, manifest_path, reference_path, output, max_seconds=2400):
    if max_seconds <= 0:
        raise ValueError('max_seconds must be positive')
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    manifest = json.loads(manifest_path.read_text())
    references = json.loads(reference_path.read_text())
    report = dict(schema='m3_ordinary_harmonic_admission_v1', started_at=now(),
        state='running', final=False, stage='verify frozen inputs and references',
        source=manifest.get('source', {}), reference_source=references['source'],
        reference_manifest_sha256=digest(reference_path),
        input_manifest_sha256=digest(manifest_path), binary_sha256=digest(binary),
        dataset='ordinary', settings=SETTINGS, block_samples=512, config=CONFIG,
        target=TARGET, runs={}, installed_output_changed=False, promotion_accepted=False,
        native_timing='not measured', allocations='not measured',
        buffer_identity='not measured', live_readiness='not measured',
        metric_scope='Snapshot assignments, overlapping held label-samples and false '
            'voice-samples/onsets are separate. Gap outputs are extra notes, not missing notes.',
        limitations='Offline frozen-shadow cues do not establish a native feedback path or '
            'real-time cost. Conditional prediction contributions can still explain model '
            'mismatch rather than independent notes. The prediction-gain guard excludes '
            'numerical roundoff; it is not an audibility or noise threshold. Labels are '
            'used only after cue generation for scoring.')
    deadline = time.monotonic() + max_seconds
    cue_path = output / 'ordinary-harmonic-admission-cues.tsv'
    evidence_path = output / 'ordinary-harmonic-admission-evidence.jsonl.gz'
    conditions = ((OFF, ()), (CURRENT, (COLLISION,)), (TRIAL, (COLLISION,
        '--candidate-rescue-score-ratio', str(CONFIG['score_ratio']),
        '--candidate-rescue-fundamental-ratio', str(CONFIG['fundamental_ratio']),
        '--candidate-rescue-harmonic-cues', str(cue_path.resolve()))))
    report['conditions'] = {mode: list(flags) for mode, flags in conditions}

    def save():
        report['updated_at'] = now()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        temporary.replace(output / 'report.json')

    save()
    cached = {}
    try:
        report['verified_inputs'] = verify_references(references, manifest, corpus)
        for mode, flags in conditions:
            stem = 'ordinary-' + mode + '-512'
            report.update(stage='bounded replay', current_run=stem)
            save()
            tsv, stderr, timing = (output / (stem + suffix)
                                  for suffix in ('.tsv', '.stderr', '-timing.json'))
            midi, outcome = (output / (stem + suffix + '.tsv')
                             for suffix in ('-midi', '-outcome'))
            command = command_for(binary, corpus, 'ordinary', 'off', 512, timing, midi_trace=midi)
            command.extend(flags)
            if mode == CURRENT:
                command.extend(('--outcome-trace', str(outcome)))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Bounded screen wall-clock budget exhausted')
            started = time.monotonic()
            with tsv.open('w') as out, stderr.open('w') as err:
                subprocess.run(command, stdout=out, stderr=err,
                               timeout=min(900, remaining), check=True)
            replay = read_replay(tsv)
            lifecycle = analyze_midi(midi, tsv, replay)
            row = dict(elapsed_seconds=time.monotonic() - started, output=replay['output'],
                exact_matches_by_string_count=replay['exact_matches_by_string_count'],
                tsv_sha256=digest(tsv), command=command, midi_lifecycle=lifecycle,
                sample_count=lifecycle['sample_count'], sample_rate=lifecycle['sample_rate'])
            report['runs'][mode] = row
            row['midi_trace'] = compress_trace_window(midi, start=0, end=row['sample_count'])
            row['midi_trace_sha256'] = row['midi_trace']['raw_sha256']
            midi.unlink()
            if mode in REFERENCE_FLAGS:
                row['saved_reference_bit_identical'] = saved_identity(row, references['runs'][mode])
                if not row['saved_reference_bit_identical']:
                    raise ValueError('Saved reference identity drift: ' + mode)
            cached[mode] = replay
            save()
            if mode == CURRENT:
                row['outcome_sha256'] = digest(outcome)
                row['saved_outcome_bit_identical'] = (
                    row['outcome_sha256'] == references['current_outcome_sha256'])
                if not row['saved_outcome_bit_identical']:
                    raise ValueError('Saved current outcome identity drift')
                report.update(stage='generate past-only frozen-shadow cues')
                save()
                started = time.monotonic()
                cue_summary = generate(load_audio(corpus / 'ordinary.wav'), outcome,
                                       cue_path, evidence_path, deadline)
                cue_summary.update(elapsed_seconds=time.monotonic() - started,
                    complete=True, cue_sha256=digest(cue_path), cue_bytes=cue_path.stat().st_size,
                    evidence_sha256=digest(evidence_path), evidence_bytes=evidence_path.stat().st_size)
                report['cue_generation'] = cue_summary
                row['outcome_trace'] = compress_trace_window(outcome, start=0, end=row['sample_count'])
                outcome.unlink()
                save()
        report['comparison'] = compare_notes(report['runs'][CURRENT], report['runs'][TRIAL],
            cached[CURRENT], cached[TRIAL], require_inference=False)
        report['snapshot_vs_off'] = compare_replays(cached[OFF], cached[TRIAL])
        report['note_safety_pass'] = bool(report['comparison']['note_safety_pass']
                                        and report['snapshot_vs_off']['gate_pass'])
        report['target_result'] = target_result(report['runs'][CURRENT], report['runs'][TRIAL],
                                               cached[CURRENT], cached[TRIAL])
        passed = report['note_safety_pass'] and report['target_result']['improved']
        report.update(state='completed' if passed else 'rejected', stage='final bounded screen')
    except Exception as error:
        report.update(state='failed', stage='failed', error=str(error), error_type=type(error).__name__)
        stem = report.get('current_run')
        if stem and (output / (stem + '.stderr')).exists():
            report['failure_stderr'] = stem + '.stderr'
            report['failure_stderr_tail'] = (output / (stem + '.stderr')).read_text()[-2048:]
        raise
    finally:
        report['reference_identity_pass'] = all(report['runs'].get(mode, {}).get(
            'saved_reference_bit_identical', False) for mode in REFERENCE_FLAGS) and bool(
                report['runs'].get(CURRENT, {}).get('saved_outcome_bit_identical', False))
        report['bounded_screen_pass'] = bool(report['state'] == 'completed'
            and report['reference_identity_pass'] and report.get('cue_generation', {}).get('complete'))
        report['decision'] = ('offline screen passed; native implementation and corpus safety remain'
            if report['bounded_screen_pass'] else 'rejected or incomplete; do not widen this policy')
        report.update(final=True, finished_at=now())
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('binary', 'corpus', 'manifest', 'references', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--max-seconds', type=int, default=2400)
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.references, args.output, args.max_seconds)


if __name__ == '__main__':
    main()
