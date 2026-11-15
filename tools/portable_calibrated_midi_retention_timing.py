"""Diagnose isolated-05 wall/CPU timing against the completed three-mode corpus.

This fixed, bounded diagnostic never replaces uninstrumented acceptance evidence.
It checks scored TSV identity; emitted MIDI lifecycle is not remeasured here.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_allocation_trace import reference_identity
from tools.portable_assignment_trace import digest, verify_inputs
from tools.portable_calibrated_midi_retention_trial import CONDITIONS
from tools.portable_corpus_replay import (
    MEASUREMENT_SCOPE, SETTINGS, command_for, now, timing_gates, validate_timing_diagnosis)


DATASET = 'isolated-05'
REFERENCE_SCHEMA = 'm3_calibrated_midi_retention_timing_references_v1'


def validate_reference(reference, manifest):
    if (reference['schema'] != REFERENCE_SCHEMA or reference['dataset'] != DATASET
            or reference['block_samples'] != 32 or reference['settings'] != SETTINGS
            or reference['conditions'] != {mode: list(flags) for mode, flags in CONDITIONS}
            or set(reference['runs']) != {mode for mode, _ in CONDITIONS}):
        raise ValueError('Wrong fixed timing reference selection')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if reference['source'][key] != manifest['source'][key]:
            raise ValueError('Saved input provenance differs: ' + key)
    for mode, _ in CONDITIONS:
        row = reference['runs'][mode]
        timing = row['timing']
        if (timing.get('timing_diagnostic_only', False) is not False
                or any(key in timing for key in ('allocation_trace', 'thread_cpu', 'stage_cpu'))
                or timing.get('measurement_scope') != MEASUREMENT_SCOPE
                or not timing_gates(timing, row, 32)['timed_scored_identity']):
            raise ValueError('Reference is not the saved uninstrumented timing: ' + mode)


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    report = dict(schema='m3_calibrated_midi_retention_timing_v1', started_at=now(),
        state='running', final=False, stage='verify saved references and inputs',
        dataset=DATASET, block_samples=32, settings=SETTINGS, runs={},
        conditions={mode: list(flags) for mode, flags in CONDITIONS},
        diagnostic_only=True, collection_pass=False, native_gate_pass=False,
        promotion_accepted=False, installed_output_changed=False,
        acceptance='not evaluated: diagnostic timing', live_readiness='not measured',
        midi_lifecycle='not remeasured; retain separate completed corpus evidence',
        timing_limits=dict(p99_ns=166666, maximum_ns=333333, deadline_overruns=0),
        interpretation='Thread CPU brackets include clock overhead. Wall-minus-CPU is '
            'diagnostic evidence, not proof of scheduler cause. A nonrecurring spike '
            'does not clear the saved uninstrumented failure.')

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
        verify_inputs(corpus, manifest, DATASET)
        report.update(source=manifest['source'], verified_inputs=4,
            input_manifest_sha256=digest(manifest_path), binary_sha256=digest(binary),
            reference_manifest_sha256=digest(reference_path),
            reference_source=reference['source'],
            reference_report_sha256=reference['anchor_report_sha256'])
        for mode, flags in CONDITIONS:
            report['stage'] = mode + ' block-32 thread CPU diagnosis'
            save()
            stem = DATASET + '-' + mode + '-32'
            tsv, timing_path, stderr = (output / (stem + suffix)
                                      for suffix in ('.tsv', '-timing.json', '.stderr'))
            command = command_for(binary, corpus, DATASET, 'off', 32, timing_path.resolve())
            command.extend(flags)
            command.append('--diagnostic-thread-cpu')
            started = time.monotonic()
            with tsv.open('x') as out, stderr.open('x') as err:
                subprocess.run(command, stdout=out, stderr=err, timeout=timeout, check=True)
            replay = read_replay(tsv)
            timing = json.loads(timing_path.read_text())
            tsv_hash = digest(tsv)
            row = dict(command=command, elapsed_seconds=time.monotonic() - started,
                output=replay['output'],
                exact_matches_by_string_count=replay['exact_matches_by_string_count'],
                tsv_sha256=tsv_hash, timing=timing,
                recorded_reference_bit_identical=reference_identity(
                    reference['runs'][mode], replay, tsv_hash),
                measurement_scope_verified=timing.get('measurement_scope') == MEASUREMENT_SCOPE,
                gates=timing_gates(timing, replay, 32),
                saved_uninstrumented_timing=reference['runs'][mode]['timing'])
            report['runs'][mode] = row
            save()
            if not (row['recorded_reference_bit_identical'] and row['measurement_scope_verified']
                    and row['gates']['timed_scored_identity']):
                raise ValueError('Scored output identity or measurement scope failed: ' + mode)
            validate_timing_diagnosis(timing, mode)
        report.update(state='completed', stage='three-mode diagnosis collected',
            collection_pass=True, cpu_block_statistics_usable=all(
                row['timing']['thread_cpu']['block_resolution_pass']
                for row in report['runs'].values()))
        return True
    except Exception as error:
        report.update(state='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report.update(final=True, finished_at=now())
        save()


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
