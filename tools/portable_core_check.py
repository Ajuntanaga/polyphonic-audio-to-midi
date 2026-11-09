"""Check physical-long OFF/ON core processing after removing observer bookkeeping.

Runs only on the private GitHub worker. Full recorded output must be unchanged.
Completion is separate from timing acceptance and does not establish live readiness.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from tools.frozen_cue_corpus_gate import read_replay, compare_replays
from tools.portable_allocation_trace import reference_identity
from tools.portable_assignment_trace import digest, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for, timing_gates


MEASUREMENT_SCOPE = 'detector_and_optional_cues_without_offline_frequency_observer'


def run(binary, corpus, manifest_path, reference_path, output, timeout):
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    report = dict(schema='m3_core_check_v1', state='running', final=False,
                  stage='verify inputs', dataset='physical-long', block_samples=32,
                  installed_output_changed=False, promotion_accepted=False,
                  live_readiness='not measured', settings=SETTINGS, runs={},
                  measurement_change='Offline frequency observer detached after scoring. '
                  'Earlier allocation/timing results included its bookkeeping; '
                  'this is a measurement correction, not a production speed gain.')

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        verify_inputs(corpus, manifest, 'physical-long')
        reference_report = json.loads(reference_path.read_text())
        if reference_report['settings'] != SETTINGS:
            raise ValueError('Reference settings differ')
        references = reference_report['datasets']['physical-long']['runs']
        report.update(source=manifest.get('source', {}), verified_inputs=4,
                      input_manifest_sha256=digest(manifest_path), binary_sha256=digest(binary),
                      baseline_report_sha256=digest(reference_path),
                      baseline_source=reference_report['source'],
                      timing_limits=dict(p99_ns=166666, maximum_ns=333333, deadline_overruns=0))
        results = {}
        for mode in ('off', 'on'):
            report['stage'] = f'{mode.upper()} core check'
            save()
            stem = f'physical-long-{mode}-32'
            tsv = output / (stem + '.tsv')
            timing_path = output / (stem + '-timing.json')
            command = command_for(binary, corpus, 'physical-long', mode, 32, timing_path.resolve())
            started = time.monotonic()
            with tsv.open('x') as stdout, (output / (stem + '.stderr')).open('x') as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, timeout=timeout, check=True)
            parsed = read_replay(tsv)
            timing = json.loads(timing_path.read_text())
            tsv_hash = digest(tsv)
            row = dict(command=command, elapsed_seconds=time.monotonic() - started,
                       output=parsed['output'],
                       exact_matches_by_string_count=parsed['exact_matches_by_string_count'],
                       tsv_sha256=tsv_hash, timing=timing,
                       recorded_reference_bit_identical=reference_identity(
                           references[mode + '-32'], parsed, tsv_hash),
                       measurement_scope_verified=timing.get('measurement_scope') == MEASUREMENT_SCOPE,
                       gates=timing_gates(timing, parsed, 32))
            report['runs'][mode] = row
            results[mode] = parsed
            save()
            if not (row['recorded_reference_bit_identical'] and row['measurement_scope_verified']
                    and row['gates']['timed_scored_identity']):
                raise ValueError('Output identity or measurement scope failed: ' + mode)
        report['comparison'] = compare_replays(results['off'], results['on'])
        report['allocation_and_output_pass'] = (report['comparison']['gate_pass'] and all(
            row['gates']['zero_processing_allocations'] for row in report['runs'].values()))
        report['native_gate_pass'] = (report['allocation_and_output_pass'] and all(
            row['gates']['timing_pass'] for row in report['runs'].values()))
        report.update(state='completed', final=True, stage='paired core check collected',
                      acceptance='accepted for this core check' if report['native_gate_pass']
                      else 'rejected by core processing gates')
        return report['native_gate_pass']
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    if args.replay_timeout_seconds <= 0:
        parser.error('--replay-timeout-seconds must be positive')
    passed = run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
                 args.replay_timeout_seconds)
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
