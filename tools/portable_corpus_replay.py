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
from tools.midi_lifecycle_analysis import CONFLICT_FIELDS, analyze_trace
from tools.portable_recovery import digest
from tools.replay_corpus import DATASETS

BLOCKS = (512, 32, 1024)
MEASUREMENT_SCOPE = 'detector_and_optional_cues_without_offline_frequency_reporting'
SETTINGS = {'a4': 440, 'input-trim': -9, 'sensitivity': 60,
            'response': 75, 'max-polyphony': 5, 'max-fret': 24}
CUE_ON_FLAGS = ('--diagnostic-native-partial-cues',
                '--diagnostic-cue-free-lane-reassignment')
PREVIEW_ON_FLAGS = ('--diagnostic-projection-preview-admission',)
COLLISION_ON_FLAGS = ('--diagnostic-spectral-lane-collision',)


def now():
    return datetime.now(timezone.utc).isoformat()


def timing_gates(timing, replay, block):
    identity = (timing.get('schema') == 'm3_replay_core_timing_v1'
                and timing.get('fingerprint_identical') is True
                and timing.get('fingerprint') == replay['output']['fingerprint']
                and timing.get('block_samples') == block
                and timing.get('sample_rate') == 96000)
    uninstrumented = (timing.get('measurement_scope') == MEASUREMENT_SCOPE
                      and timing.get('timing_diagnostic_only', False) is False
                      and 'allocation_trace' not in timing and 'thread_cpu' not in timing
                      and 'stage_cpu' not in timing)
    allocations = (identity and uninstrumented and timing.get('allocation_guard') is True
                   and all(type(timing.get(key)) is int and timing[key] == 0 for key in
                           ('cpp_allocations', 'cpp_frees', 'c_allocations', 'c_frees')))
    realtime = None
    if block == 32:
        realtime = (identity and uninstrumented and all(type(timing.get(key)) is int
                                    and 0 <= timing[key] <= limit for key, limit in
                                    (('p99_ns', 166666), ('maximum_ns', 333333),
                                     ('deadline_overruns', 0))))
    return dict(timed_scored_identity=identity, zero_processing_allocations=allocations,
                timing_pass=realtime)


def validate_timing_diagnosis(timing, mode):
    cpu = timing.get('thread_cpu', {})
    if (timing.get('timing_diagnostic_only') is not True
            or cpu.get('valid') is not True
            or type(cpu.get('block_resolution_pass')) is not bool
            or len(cpu.get('phases', [])) != 32
            or sum(phase['blocks'] for phase in cpu['phases']) != timing['blocks']
            or sum(phase['wall_deadline_overruns'] for phase in cpu['phases'])
               != timing['deadline_overruns']
            or not 0 < len(cpu.get('slowest_blocks', [])) <= 16
            or cpu['slowest_blocks'][0]['wall_ns'] != timing['maximum_ns']):
        raise ValueError('Incomplete timing diagnosis: ' + mode)


def command_for(binary, corpus, name, mode, block, timing, *,
                projection_preview_admission=False, spectral_lane_collision=False,
                midi_trace=None):
    if name not in DATASETS or mode not in ('off', 'on') or block not in BLOCKS:
        raise ValueError('Unknown replay selection')
    if projection_preview_admission and spectral_lane_collision:
        raise ValueError('Select only one isolated policy')
    command = [str(binary), '--wav', str(corpus / (name + '.wav')),
               '--labels', str(corpus / (name + '.tsv')),
               '--calibration', str(corpus / 'calibration.m3cb'),
               '--spectral-shadow-templates', str(corpus / 'templates.tsv'),
               '--block', str(block), '--label-details']
    if block == 32:
        command.extend(('--diagnostic-core-timing', str(timing)))
    if midi_trace is not None:
        if block != 512:
            raise ValueError('MIDI lifecycle capture requires the untimed 512-sample replay')
        command.extend(('--midi-event-trace', str(midi_trace)))
    for key, value in SETTINGS.items():
        command.extend(('--' + key, str(value)))
    if mode == 'on':
        command.extend(COLLISION_ON_FLAGS if spectral_lane_collision else
                       PREVIEW_ON_FLAGS if projection_preview_admission else CUE_ON_FLAGS)
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-seconds', type=int, default=10800)
    policy = parser.add_mutually_exclusive_group()
    policy.add_argument('--projection-preview-admission', action='store_true',
                        help='Screen preview ownership alone instead of the frozen-cue correction')
    policy.add_argument('--spectral-lane-collision', action='store_true',
                        help='Screen collision output alone, with complete raw MIDI safety gates')
    parser.add_argument('--off-reference-report', type=Path,
                        help='Saved corpus OFF-32 references; required for the collision policy')
    parser.add_argument('--capture-midi-lifecycle', action='store_true',
                        help='Measure full detector note lifetimes on untimed 512-sample replays')
    args = parser.parse_args()
    if args.max_seconds <= 0:
        parser.error('--max-seconds must be positive')
    if args.spectral_lane_collision and args.off_reference_report is None:
        parser.error('--spectral-lane-collision requires --off-reference-report')
    capture_midi = args.capture_midi_lifecycle or args.spectral_lane_collision
    reference_rows = None
    if args.off_reference_report is not None:
        reference = json.loads(args.off_reference_report.read_text())
        reference_rows = {name: reference['datasets'][name]['runs']['off-32'] for name in DATASETS}
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
    report['on_flags'] = list(COLLISION_ON_FLAGS if args.spectral_lane_collision else
                             PREVIEW_ON_FLAGS if args.projection_preview_admission else CUE_ON_FLAGS)
    report['midi_lifecycle_capture'] = dict(enabled=capture_midi,
        block_samples=512, scope='detector transitions before host delivery',
        acceptance_target=('no increase in any raw conflict count per dataset'
                           if args.spectral_lane_collision else 'not measured'),
        alters_acceptance_gates=args.spectral_lane_collision)
    if reference_rows is not None:
        report['off_reference_report_sha256'] = digest(args.off_reference_report)
    if args.projection_preview_admission:
        report.update(schema='m3_portable_projection_preview_corpus_v1',
                      trial_revision='full_physical_assignment_context',
                      assignment_context='original selected candidates; preview filtering remains downstream')
    if args.spectral_lane_collision:
        report.update(schema='m3_portable_spectral_lane_collision_corpus_v1',
                      trial_revision='singleton_output_fallback',
                      assignment_context='ordinary physical assignment; conflicting singleton output fallback')
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
        midi_path = (args.output / (stem + '-midi.tsv')
                     if capture_midi and block == 512 else None)
        command = command_for(args.binary, args.corpus, name, mode, block, timing_path,
                              projection_preview_admission=args.projection_preview_admission,
                              spectral_lane_collision=args.spectral_lane_collision,
                              midi_trace=midi_path)
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
        if mode == 'off' and reference_rows is not None:
            reference = reference_rows[name]
            identity = all(row[key] == reference[key]
                           for key in ('output', 'exact_matches_by_string_count'))
            row['off_baseline_output_identical'] = identity
            row['off_reference_bit_identical'] = (
                identity and row['tsv_sha256'] == reference['tsv_sha256'] if block == 32 else None)
        if midi_path is not None:
            row['midi_lifecycle'] = analyze_trace(midi_path, tsv,
                include_raw_conflicts=args.spectral_lane_collision)
            row['midi_lifecycle_trace'] = dict(file=midi_path.name, sha256=digest(midi_path))
        report['datasets'].setdefault(name, {'runs': {}})['runs'][f'{mode}-{block}'] = row
        results[key] = parsed
        save()
        if mode == 'off' and reference_rows is not None and (
                not row['off_baseline_output_identical']
                or row['off_reference_bit_identical'] is False):
            raise ValueError('OFF reference differs from the saved corpus baseline: ' + stem)
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
        if args.spectral_lane_collision and block == 512:
            counts = [entry['runs'][f'{mode}-512']['midi_lifecycle']['raw_midi']['counts']
                      for mode in ('off', 'on')]
            delta = {key: counts[1][key] - counts[0][key] for key in CONFLICT_FIELDS}
            entry['raw_midi_delta'] = delta
            entry['raw_midi_no_regression'] = all(value <= 0 for value in delta.values())
            safe = safe and entry['raw_midi_no_regression']
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
        entry['native_gate_pass'] = (entry['recovery_safety_pass'] and all(
            entry['runs'][f'{mode}-32']['gates']['timing_pass'] is True
            for mode in ('off', 'on')))
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
        if args.spectral_lane_collision:
            rows = list(report['datasets'].values())
            compared = [row for row in rows if 'raw_midi_delta' in row]
            delta = {key: sum(row['raw_midi_delta'][key] for row in compared)
                     for key in CONFLICT_FIELDS}
            report['raw_midi_comparison'] = dict(datasets_compared=len(compared), delta=delta,
                no_regression=(len(compared) == len(DATASETS)
                               and all(row['raw_midi_no_regression'] for row in compared)),
                conflicts_reduced=(len(compared) == len(DATASETS)
                                   and delta['cross_pitch_on_before_release'] < 0))
            report['off_references_bit_identical'] = (
                len(rows) == len(DATASETS) and all(row['runs'].get('off-32', {}).get(
                    'off_reference_bit_identical') is True for row in rows))
            report['full_corpus_screen_pass'] = (
                report['native_gates_passed'] == len(DATASETS)
                and report['off_references_bit_identical']
                and report['raw_midi_comparison']['no_regression']
                and report['raw_midi_comparison']['conflicts_reduced'])
            report['decision'] = ('eligible for host validation' if report['full_corpus_screen_pass']
                                  else 'rejected')
        # A corpus replay cannot certify host/MIDI lifecycle or restore missing control crops.
        save()


if __name__ == '__main__':
    main()
