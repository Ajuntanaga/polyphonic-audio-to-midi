"""Screen a sample-observation optimization against a fixed build on one runner.

Six replays alternate baseline/candidate order across three fixed cases. This is
a usefulness screen with thread CPU clock overhead, not native acceptance.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_allocation_trace import reference_identity
from tools.portable_assignment_trace import digest, verify_inputs
from tools.portable_completion_midi_retention_timing import CONDITIONS, validate_reference
from tools.portable_corpus_replay import (
    MEASUREMENT_SCOPE, SETTINGS, command_for, now, timing_gates, validate_timing_diagnosis)


BASELINE_COMMIT = '072d1e5f721cd24dc6fcdd5c210838f8685366ed'
CASES = (('ordinary', 'current-on'),
         ('ordinary', 'completion-midi-retention-on'),
         ('physical-long', 'completion-midi-retention-on'))
MINIMUM_CPU_REDUCTION_PERCENT = 2


def validate_observation(timing, replay, saved, tsv_hash):
    if not (reference_identity(saved, replay, tsv_hash)
            and timing.get('measurement_scope') == MEASUREMENT_SCOPE
            and timing_gates(timing, replay, 32)['timed_scored_identity']
            and timing['blocks'] == saved['timing']['blocks']):
        raise ValueError('Scored identity, block count or timing scope changed')
    validate_timing_diagnosis(timing, 'sample-observation comparison')
    cpu = timing['thread_cpu']
    if (cpu['block_resolution_pass'] is not True
            or any(key in timing for key in ('stage_cpu', 'allocation_trace'))
            or timing.get('allocation_guard') is not True
            or any(type(timing.get(key)) is not int or timing[key] != 0 for key in
                   ('cpp_allocations', 'cpp_frees', 'c_allocations', 'c_frees'))):
        raise ValueError('Usable CPU timing without stage probes and zero allocations required')
    for clock in (timing, cpu):
        if (any(type(clock.get(key)) is not int or clock[key] < 0 for key in
                ('total_ns', 'p99_ns', 'maximum_ns', 'deadline_overruns'))
                or clock['total_ns'] == 0 or clock['p99_ns'] > clock['maximum_ns']):
            raise ValueError('Invalid wall or CPU timing totals')


def run(baseline_binary, candidate_binary, corpus, manifest_path, reference_path,
        output, *, timeout=900):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    binaries = dict(baseline=baseline_binary.resolve(), candidate=candidate_binary.resolve())
    if binaries['baseline'] == binaries['candidate']:
        raise ValueError('Baseline and candidate must be separate builds')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_sample_observation_comparison_v1', started_at=now(),
        state='running', final=False, stage='verify inputs and fixed references',
        baseline_commit=BASELINE_COMMIT, settings=SETTINGS, block_samples=32,
        declared_cases=[dict(dataset=ds, mode=mode) for ds, mode in CASES],
        cases=[], diagnostic_only=True, collection_pass=False, usefulness_screen_pass=False,
        native_gate_pass=False, promotion_accepted=False, installed_output_changed=False,
        minimum_cpu_reduction_percent=MINIMUM_CPU_REDUCTION_PERCENT,
        screening_rule='CPU total at least 2% lower and CPU p99 no higher in every pair',
        interpretation='One same-runner pair per case, alternating execution order. '
            'Thread CPU brackets include clock overhead. A screen pass justifies '
            'uninstrumented corpus validation; it does not clear earlier timing failures '
            'or establish note-quality gains or live readiness.')

    def save():
        report['updated_at'] = now()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        reference = json.loads(reference_path.read_text())
        validate_reference(reference, manifest)
        datasets = tuple(dict.fromkeys(ds for ds, _ in CASES))
        for dataset in datasets:
            verify_inputs(corpus, manifest, dataset)
        report.update(source=manifest['source'], verified_inputs=2 + 2 * len(datasets),
            binary_sha256={name: digest(path) for name, path in binaries.items()},
            input_manifest_sha256=digest(manifest_path),
            reference_manifest_sha256=digest(reference_path),
            reference_report_sha256=reference['anchor_report_sha256'])
        for index, (dataset, mode) in enumerate(CASES):
            order = ('baseline', 'candidate') if index % 2 == 0 else ('candidate', 'baseline')
            case = dict(dataset=dataset, mode=mode, execution_order=list(order), runs={})
            report['cases'].append(case)
            saved = reference['datasets'][dataset][mode]
            for name in order:
                stem = dataset + '-' + mode + '-' + name
                report['stage'] = stem
                save()
                tsv, timing_path, stderr = (output / (stem + suffix)
                    for suffix in ('.tsv', '-timing.json', '.stderr'))
                command = command_for(binaries[name], corpus.resolve(), dataset, 'off', 32,
                                      timing_path.resolve())
                command.extend(dict(CONDITIONS)[mode])
                command.append('--diagnostic-thread-cpu')
                started = time.monotonic()
                with tsv.open('x') as out, stderr.open('x') as err:
                    subprocess.run(command, stdout=out, stderr=err, timeout=timeout, check=True)
                replay = read_replay(tsv)
                timing = json.loads(timing_path.read_text())
                tsv_hash = digest(tsv)
                row = dict(command=command, elapsed_seconds=time.monotonic() - started,
                    output=replay['output'], tsv_sha256=tsv_hash, timing=timing,
                    observation_verified=False)
                case['runs'][name] = row
                save()
                validate_observation(timing, replay, saved, tsv_hash)
                row['observation_verified'] = True
                row['recorded_reference_bit_identical'] = True
            before = case['runs']['baseline']['timing']['thread_cpu']
            after = case['runs']['candidate']['timing']['thread_cpu']
            case.update(cpu_total_reduction_percent=100 * (before['total_ns'] - after['total_ns'])
                        / before['total_ns'], cpu_p99_delta_ns=after['p99_ns'] - before['p99_ns'],
                usefulness_screen_pass=(100 * after['total_ns'] <=
                    (100 - MINIMUM_CPU_REDUCTION_PERCENT) * before['total_ns']
                    and after['p99_ns'] <= before['p99_ns']))
            save()
        report.update(state='completed', stage='six fixed replays collected', collection_pass=True,
            usefulness_screen_pass=all(case['usefulness_screen_pass'] for case in report['cases']))
        return report['usefulness_screen_pass']
    except Exception as error:
        report.update(state='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report.update(final=True, finished_at=now())
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-binary', 'candidate-binary', 'corpus', 'manifest',
                 'reference-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    run(args.baseline_binary, args.candidate_binary, args.corpus, args.manifest,
        args.reference_report, args.output, timeout=args.replay_timeout_seconds)


if __name__ == '__main__':
    main()
