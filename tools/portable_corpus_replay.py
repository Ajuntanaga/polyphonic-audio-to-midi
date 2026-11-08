"""Recreate lost OFF/ON references on replacement compute, without Modal.

These are new measurements, not proof of identity with unavailable old artifacts.
Timing failures never permit promotion, but do not prevent reference recovery.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from tools.frozen_cue_corpus_gate import read_replay, compare_replays
from tools.portable_recovery import digest
from tools.replay_corpus import DATASETS

BLOCKS = (512, 32, 1024)
SETTINGS = {'a4': 440, 'input-trim': -9, 'sensitivity': 60,
            'response': 75, 'max-polyphony': 5, 'max-fret': 24}


def now():
    return datetime.now(timezone.utc).isoformat()


def timing_gates(timing, replay, block):
    identity = (timing.get('schema') == 'm3_replay_core_timing_v1'
                and timing.get('fingerprint_identical') is True
                and timing.get('fingerprint') == replay['output']['fingerprint']
                and timing.get('block_samples') == block
                and timing.get('sample_rate') == 96000)
    allocations = (identity and timing.get('allocation_guard') is True
                   and all(type(timing.get(key)) is int and timing[key] == 0 for key in
                           ('cpp_allocations', 'cpp_frees', 'c_allocations', 'c_frees')))
    realtime = None
    if block == 32:
        realtime = (identity and all(type(timing.get(key)) is int
                                    and 0 <= timing[key] <= limit for key, limit in
                                    (('p99_ns', 166666), ('maximum_ns', 333333),
                                     ('deadline_overruns', 0))))
    return dict(timed_scored_identity=identity, zero_processing_allocations=allocations,
                timing_pass=realtime)


def command_for(binary, corpus, name, mode, block, timing):
    if name not in DATASETS or mode not in ('off', 'on') or block not in BLOCKS:
        raise ValueError('Unknown replay selection')
    command = [str(binary), '--wav', str(corpus / (name + '.wav')),
               '--labels', str(corpus / (name + '.tsv')),
               '--calibration', str(corpus / 'calibration.m3cb'),
               '--spectral-shadow-templates', str(corpus / 'templates.tsv'),
               '--block', str(block), '--label-details']
    if block == 32:
        command.extend(('--diagnostic-core-timing', str(timing)))
    for key, value in SETTINGS.items():
        command.extend(('--' + key, str(value)))
    if mode == 'on':
        command.extend(('--diagnostic-native-partial-cues',
                        '--diagnostic-cue-free-lane-reassignment'))
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-seconds', type=int, default=10800)
    args = parser.parse_args()
    if args.max_seconds <= 0:
        parser.error('--max-seconds must be positive')
    # Exclusive directory: never overwrite a prior measurement.
    args.output.mkdir(parents=True, exist_ok=False)
    args.binary, args.corpus = args.binary.resolve(), args.corpus.resolve()
    manifest = json.loads(args.manifest.read_text())
    names = {'calibration.m3cb', 'templates.tsv'} | {
        name + suffix for name in DATASETS for suffix in ('.wav', '.tsv')}
    if set(manifest['files']) != names:
        raise ValueError('Recovery manifest does not contain exactly the declared inputs')
    for name in sorted(names):
        if digest(args.corpus / name) != manifest['files'][name]['sha256']:
            raise ValueError('Uploaded input hash mismatch: ' + name)
    report = dict(schema='m3_portable_corpus_recovery_v1', started_at=now(),
                  state='running', final=False, stage='OFF reference recovery',
                  provenance='New references; historical Modal identity is not verified',
                  installed_output_changed=False, source=manifest.get('source', {}),
                  input_manifest_sha256=digest(args.manifest), verified_inputs=len(names),
                  binary_sha256=digest(args.binary), settings=SETTINGS,
                  timing_limits=dict(block_samples=32, sample_rate=96000,
                                     p99_ns=166666, maximum_ns=333333, deadline_overruns=0),
                  datasets={}, promotion_accepted=False, live_readiness='not measured')
    deadline = time.monotonic() + args.max_seconds
    results = {}

    def save():
        report['updated_at'] = now()
        temporary = args.output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(args.output / 'report.json')

    def replay(name, mode, block):
        key = (name, mode, block)
        if key in results:
            return results[key]
        report['stage'] = f'{name}: {mode}, block {block}'
        report['current_run'] = dict(dataset=name, mode=mode, block=block,
                                     stderr_file=f'{name}-{mode}-{block}.stderr')
        save()
        print(report['stage'], flush=True)
        stem = f'{name}-{mode}-{block}'
        tsv = args.output / (stem + '.tsv')
        timing_path = args.output / (stem + '-timing.json')
        command = command_for(args.binary, args.corpus, name, mode, block, timing_path)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Recovery wall-time budget exhausted')
        started = time.monotonic()
        with tsv.open('x') as output, (args.output / (stem + '.stderr')).open('x') as error:
            subprocess.run(command, stdout=output, stderr=error, check=True,
                           timeout=min(1800, remaining))
        parsed = read_replay(tsv)
        timing = json.loads(timing_path.read_text()) if block == 32 else None
        gates = timing_gates(timing, parsed, block) if timing is not None else dict(
            timed_scored_identity=None, zero_processing_allocations=None, timing_pass=None)
        row = dict(command=command, elapsed_seconds=time.monotonic() - started,
                   output=parsed['output'], exact_matches_by_string_count=parsed['exact_matches_by_string_count'],
                   tsv_sha256=digest(tsv), timing=timing, gates=gates)
        report['datasets'].setdefault(name, {'runs': {}})['runs'][f'{mode}-{block}'] = row
        results[key] = parsed
        save()
        if block == 32 and not gates['timed_scored_identity']:
            raise ValueError('Timed/scored replay identity failed: ' + stem)
        return parsed

    def pair(name, block):
        off, on = replay(name, 'off', block), replay(name, 'on', block)
        comparison = compare_replays(off, on)
        entry = report['datasets'][name]
        entry.setdefault('comparisons', {})[str(block)] = comparison
        safe = comparison['gate_pass'] and (block != 32 or all(
            entry['runs'][f'{mode}-{block}']['gates']['zero_processing_allocations']
            for mode in ('off', 'on')))
        save()
        return safe

    def check_dataset(name):
        safe = True
        for block in BLOCKS:
            safe = pair(name, block) and safe
            if not safe:
                break
        entry = report['datasets'][name]
        parity = {}
        for mode in ('off', 'on'):
            for block in BLOCKS[1:]:
                if (name, mode, block) in results:
                    comparison = compare_replays(results[name, mode, 512], results[name, mode, block])
                    parity[f'{mode}-{block}'] = (comparison['output_bit_identical']
                                               and not comparison['changed_labels'])
        entry['buffer_parity'] = parity
        entry['recovery_safety_pass'] = safe and len(parity) == 4 and all(parity.values())
        entry['native_gate_pass'] = (entry['recovery_safety_pass'] and
                                    entry['runs']['on-32']['gates']['timing_pass'] is True)
        save()
        return entry['recovery_safety_pass']

    save()
    try:
        # Recover every OFF reference even if the first correction screen later fails.
        for name in DATASETS:
            replay(name, 'off', 512)
        if check_dataset('physical-long'):
            for name in DATASETS:
                if name != 'physical-long' and not check_dataset(name):
                    report['stopped_on_regression'] = name
                    break
        else:
            report['stopped_on_regression'] = 'physical-long'
        report.update(state='completed', final=True, stage='reference recovery finished')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        failure = dict(report.get('current_run', {}),
                       returncode=getattr(error, 'returncode', None),
                       timed_out=isinstance(error, (TimeoutError, subprocess.TimeoutExpired)))
        stderr = args.output / failure.get('stderr_file', '')
        if stderr.is_file():
            with stderr.open('rb') as stream:
                stream.seek(max(0, stderr.stat().st_size - 2048))
                failure['stderr_tail'] = stream.read(2048).decode('utf-8', errors='replace')
        report['failure'] = failure
        raise
    finally:
        report['off_references'] = sum('off-512' in row['runs'] for row in report['datasets'].values())
        report['on_references'] = sum('on-512' in row['runs'] for row in report['datasets'].values())
        report['native_gates_passed'] = sum(row.get('native_gate_pass', False)
                                            for row in report['datasets'].values())
        report['declared_datasets'] = len(DATASETS)
        # A corpus replay cannot certify host/MIDI lifecycle or restore missing control crops.
        save()


if __name__ == '__main__':
    main()
