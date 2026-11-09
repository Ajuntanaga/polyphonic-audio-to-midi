"""Reconstruct held-out controls and compare native cues on the private GitHub worker.

Input hashes can restore historical audio identity. New OFF/ON results cannot
restore the missing historical binary, or establish installed/live acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from tools.controlled_descriptor_overlap import controlled_mixtures, read_float_wave, write_float_wave
from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.portable_corpus_replay import (
    BLOCKS, MEASUREMENT_SCOPE, SETTINGS, now, timing_gates, validate_timing_diagnosis)
from tools.portable_recovery import digest


def prepare_cases(corpus, manifest, reference_path, output):
    import numpy as np
    reference = json.loads(reference_path.read_text())
    expected = {name + '.wav': item['wave_sha256']
                for name, item in reference['components'].items()}
    expected['calibration.m3cb'] = reference['calibration_sha256']
    if (manifest.get('reference_sha256') != digest(reference_path)
            or manifest.get('corpus_id') != reference['corpus_id']
            or set(manifest['files']) != set(expected)):
        raise ValueError('Controlled input manifest differs')
    for name, sha in expected.items():
        if manifest['files'][name]['sha256'] != sha or digest(corpus / name) != sha:
            raise ValueError('Historical input hash differs: ' + name)
    components = {}
    for name, identity in reference['components'].items():
        rate, values = read_float_wave(corpus / (name + '.wav'))
        if (rate != 96000 or rate != identity['sample_rate']
                or len(values) != identity['sample_count']
                or hashlib.sha256(values.tobytes()).hexdigest() != identity['samples_sha256']):
            raise ValueError('Historical component differs: ' + name)
        components[name] = values.astype(np.float64)
    prefix, suffix = reference['prefix_samples'], reference['suffix_samples']
    mixtures = controlled_mixtures(components['target'],
        {name: components[name] for name in ('octave', 'nearby')}, prefix=prefix, suffix=suffix)
    cases = {}
    for name, item in mixtures.items():
        meta = item['metadata']
        cases[name] = item['audio'], True, meta['interferer']
        if meta['interferer'] is not None:
            added = components[meta['interferer']] * meta['interferer_scale'] * meta['common_gain']
            cases[name + '_source_only'] = (np.pad(np.asarray(added, dtype='<f4'),
                (prefix, suffix)), False, meta['interferer'])
    cases['silence'] = np.zeros(prefix + len(components['target']) + suffix, dtype='<f4'), False, None
    if set(cases) != set(reference['cases']):
        raise ValueError('Historical case coverage differs')
    output.mkdir(exist_ok=False)
    rows = {}
    for name, (values, has_target, added) in cases.items():
        saved = reference['cases'][name]
        samples_hash = hashlib.sha256(values.tobytes()).hexdigest()
        if (saved['sample_rate'] != 96000 or len(values) != saved['sample_count']
                or samples_hash != saved['audio_sha256']):
            raise ValueError('Historical mixture samples differ: ' + name)
        identities = []
        for component in (['target'] if has_target else []) + ([added] if added else []):
            item = reference['components'][component]
            identities.append(dict(start_sample=prefix, end_sample=prefix + item['sample_count'],
                midi_note=item['midi_note'], string_mask=item['string_mask'],
                calibration_pass=reference['calibration_pass']))
        fields = ('start_sample', 'end_sample', 'midi_note', 'string_mask', 'calibration_pass')
        labels = '\t'.join(fields) + '\n' + ''.join(
            '\t'.join(str(row[key]) for key in fields) + '\n' for row in identities)
        wav, tsv = output / (name + '.wav'), output / (name + '.tsv')
        write_float_wave(wav, 96000, values)
        tsv.write_text(labels)
        rows[name] = dict(has_target=has_target, labels=identities, sample_count=len(values),
            samples_sha256=samples_hash, wav_sha256=digest(wav), labels_sha256=digest(tsv))
    return rows


def validate_labels(parsed, expected):
    if len(parsed['labels']) != len(expected):
        raise ValueError('Replay label coverage differs')
    for actual, wanted in zip(parsed['labels'], expected):
        if any(actual[key] != value for key, value in wanted.items()) or actual['labeled'] <= 0:
            raise ValueError('Replay label identity or denominator differs')


def accuracy_screen(datasets):
    safe = all(row['comparisons']['512']['gate_pass'] for row in datasets.values())
    target = datasets['nearby_0dB']['runs']
    before, after = target['off-512']['target'], target['on-512']['target']
    gain = after['matched'] - before['matched']
    return dict(no_label_or_error_regression=safe, nearby_target_gain=gain,
                target_before=before, target_after=after, pass_screen=safe and gain > 0)


def replay_command(binary, corpus, cases, name, mode, block, timing_path):
    command = [str(binary), '--wav', str(cases / (name + '.wav')),
        '--labels', str(cases / (name + '.tsv')),
        '--calibration', str(corpus / 'calibration.m3cb'), '--block', str(block), '--label-details']
    for key, value in SETTINGS.items():
        command.extend(('--' + key, str(value)))
    if mode == 'on':
        command.extend(('--diagnostic-native-partial-cues', '--diagnostic-cue-free-lane-reassignment'))
    if block == 32:
        command.extend(('--diagnostic-core-timing', str(timing_path)))
    return command


def run_timing_diagnosis(binary, corpus, manifest_path, reference_path, baseline_path,
                         output, max_seconds):
    """Diagnose the failed octave pair, preserving its saved full replay hashes."""
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus, output = binary.resolve(), corpus.resolve(), output.resolve()
    name = 'octave_0dB'
    report = dict(schema='m3_controlled_timing_diagnosis_v1', started_at=now(),
        state='running', final=False, stage='verify held-out pair', control=name,
        block_samples=32, settings=SETTINGS, runs={}, diagnostic_only=True,
        spectral_templates='disabled, matching historical controls',
        collection_pass=False, native_gate_pass=False, allocation_and_output_pass=False,
        installed_output_changed=False, promotion_accepted=False, live_readiness='not measured',
        acceptance='not evaluated: diagnostic timing', max_seconds=min(max_seconds, 360),
        limits=['CPU instrumentation cannot replace the earlier failed native timing gate.',
                'Only this held-out OFF/ON pair is measured; no corpus or live-host acceptance.'])
    deadline = time.monotonic() + report['max_seconds']

    def save():
        report['updated_at'] = now()
        temp = output / 'report.json.tmp'
        temp.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        temp.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        baseline = json.loads(baseline_path.read_text())
        if (baseline.get('schema') != 'm3_github_heldout_control_result_v1'
                or baseline.get('final') is not True or baseline.get('collection_pass') is not True
                or baseline.get('settings') != SETTINGS
                or baseline.get('spectral_templates') != report['spectral_templates']
                or baseline.get('reference_sha256') != digest(reference_path)):
            raise ValueError('Held-out timing reference settings or input identity differ')
        reference = baseline['controls'][name]
        if (not all(reference.get('replay_sha256', {}).get(mode + '-32') for mode in ('off', 'on'))
                or not all(key in reference for key in ('baseline_off', 'current_on'))):
            raise ValueError('Missing paired block-32 references: ' + name)
        report.update(source=manifest.get('source', {}), input_manifest_sha256=digest(manifest_path),
            reference_sha256=digest(reference_path), binary_sha256=digest(binary),
            baseline_report_sha256=digest(baseline_path), baseline_source=baseline['source'],
            baseline_timing=reference['timing'], timing_limits=baseline['timing_limits'])
        report['inputs'] = prepare_cases(corpus, manifest, reference_path, output / 'cases')
        report['verified_inputs'] = len(manifest['files'])
        results = {}
        for mode, output_key in (('off', 'baseline_off'), ('on', 'current_on')):
            stem = f'{name}-{mode}-32'
            report.update(stage=stem, current_stderr_file=stem + '.stderr')
            save()
            print(stem, flush=True)
            tsv, timing_path = output / (stem + '.tsv'), output / (stem + '-timing.json')
            command = replay_command(binary, corpus, output / 'cases', name, mode, 32, timing_path)
            command.append('--diagnostic-thread-cpu')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Controlled timing diagnosis budget exhausted')
            started = time.monotonic()
            with tsv.open('x') as stdout, (output / (stem + '.stderr')).open('x') as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=min(180, remaining))
            parsed = read_replay(tsv)
            validate_labels(parsed, report['inputs'][name]['labels'])
            timing, tsv_hash = json.loads(timing_path.read_text()), digest(tsv)
            row = dict(command=command, output=parsed['output'], labels=parsed['labels'],
                tsv_sha256=tsv_hash, elapsed_seconds=time.monotonic() - started, timing=timing,
                recorded_reference_bit_identical=(tsv_hash == reference['replay_sha256'][mode + '-32']
                                                  and parsed['output'] == reference[output_key]),
                measurement_scope_verified=timing.get('measurement_scope') == MEASUREMENT_SCOPE,
                gates=timing_gates(timing, parsed, 32))
            report['runs'][mode] = row
            results[mode] = parsed
            save()
            if not (row['recorded_reference_bit_identical'] and row['measurement_scope_verified']
                    and row['gates']['timed_scored_identity']):
                raise ValueError('Output identity or measurement scope failed: ' + mode)
            validate_timing_diagnosis(timing, mode)
        report['comparison'] = compare_replays(results['off'], results['on'])
        report.update(state='completed', final=True, stage='held-out timing diagnosis collected',
            collection_pass=report['comparison']['gate_pass'],
            cpu_block_statistics_usable=all(row['timing']['thread_cpu']['block_resolution_pass']
                                            for row in report['runs'].values()))
        return report['collection_pass']
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()


def run(binary, corpus, manifest_path, reference_path, output, max_seconds):
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus, output = binary.resolve(), corpus.resolve(), output.resolve()
    report = dict(schema='m3_portable_controlled_replay_v1', started_at=now(),
        state='running', final=False, stage='verify held-out inputs', datasets={},
        settings=SETTINGS, spectral_templates='disabled, matching historical controls',
        provenance='Historical input hashes; new paired native OFF/ON references. '
                   'Historical baseline binary and frozen feature sidecars are not recovered.',
        installed_output_changed=False, promotion_accepted=False, live_readiness='not measured',
        timing_limits=dict(p99_ns=166666, maximum_ns=333333, deadline_overruns=0),
        limits=['Independent plucks from the same recording session, not new-session coverage.',
                'This narrow control screen does not replace corpus, host or MIDI lifecycle gates.'])
    deadline = time.monotonic() + max_seconds
    results = {}

    def save():
        report['updated_at'] = now()
        temp = output / 'report.json.tmp'
        temp.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        temp.replace(output / 'report.json')

    def replay(name, mode, block):
        stem = f'{name}-{mode}-{block}'
        report['stage'] = stem
        report['current_stderr_file'] = stem + '.stderr'
        save()
        print(stem, flush=True)
        tsv, timing_path = output / (stem + '.tsv'), output / (stem + '-timing.json')
        command = replay_command(binary, corpus, output / 'cases', name, mode, block, timing_path)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Controlled replay budget exhausted')
        started = time.monotonic()
        with tsv.open('x') as stdout, (output / (stem + '.stderr')).open('x') as stderr:
            subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=min(180, remaining))
        parsed = read_replay(tsv)
        validate_labels(parsed, report['inputs'][name]['labels'])
        row = dict(command=command, output=parsed['output'], labels=parsed['labels'],
            tsv_sha256=digest(tsv), elapsed_seconds=time.monotonic() - started)
        if report['inputs'][name]['has_target']:
            row['target'] = parsed['labels'][0]
        if block == 32:
            row['timing'] = json.loads(timing_path.read_text())
            row['gates'] = timing_gates(row['timing'], parsed, block)
        entry = report['datasets'].setdefault(name, dict(runs={}, comparisons={}, buffer_parity={}))
        entry['runs'][f'{mode}-{block}'] = row
        results[name, mode, block] = parsed
        save()
        if block == 32 and not row['gates']['timed_scored_identity']:
            raise ValueError('Timed/scored identity failed: ' + stem)
        return parsed

    def pair(name, block):
        before, after = replay(name, 'off', block), replay(name, 'on', block)
        report['datasets'][name]['comparisons'][str(block)] = compare_replays(before, after)
        save()

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        report.update(source=manifest.get('source', {}), input_manifest_sha256=digest(manifest_path),
            reference_sha256=digest(reference_path), binary_sha256=digest(binary))
        report['inputs'] = prepare_cases(corpus, manifest, reference_path, output / 'cases')
        report['verified_inputs'] = len(manifest['files'])
        for name in report['inputs']:
            pair(name, 512)
        report['accuracy_screen'] = accuracy_screen(report['datasets'])
        report['control_gate_pass'] = False
        if report['accuracy_screen']['pass_screen']:
            for name, entry in report['datasets'].items():
                for block in BLOCKS[1:]:
                    pair(name, block)
                    for mode in ('off', 'on'):
                        check = compare_replays(results[name, mode, 512], results[name, mode, block])
                        entry['buffer_parity'][f'{mode}-{block}'] = (
                            check['output_bit_identical'] and not check['changed_labels'])
                entry['native_gate_pass'] = (all(row['gate_pass'] for row in entry['comparisons'].values())
                    and len(entry['buffer_parity']) == 4 and all(entry['buffer_parity'].values())
                    and all(entry['runs'][mode + '-32']['gates']['zero_processing_allocations']
                            and entry['runs'][mode + '-32']['gates']['timing_pass']
                            for mode in ('off', 'on')))
                save()
            report['control_gate_pass'] = all(row['native_gate_pass'] for row in report['datasets'].values())
        else:
            report['buffer_timing_stage'] = 'not measured: no safe target gain at block 512'
        report.update(state='completed', final=True, stage='held-out control collection finished',
            collection_pass=True, acceptance='passed this control screen only' if report['control_gate_pass']
            else 'rejected by controlled gain, safety or native gates')
        return report['control_gate_pass']
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--timing-reference-report', type=Path,
                        help='Diagnose only the saved octave OFF/ON pair; cannot pass native acceptance')
    parser.add_argument('--max-seconds', type=int, default=2400)
    args = parser.parse_args()
    if args.max_seconds <= 0:
        parser.error('--max-seconds must be positive')
    if args.timing_reference_report:
        passed = run_timing_diagnosis(args.binary, args.corpus, args.manifest, args.reference,
                                     args.timing_reference_report, args.output, args.max_seconds)
    else:
        passed = run(args.binary, args.corpus, args.manifest, args.reference, args.output, args.max_seconds)
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
