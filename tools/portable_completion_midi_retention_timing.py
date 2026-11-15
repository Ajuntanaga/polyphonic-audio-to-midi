"""Locate slow blocks in the three failed completion-retention trial datasets.

Nine fixed OFF/current/trial replays reuse the existing thread CPU diagnostic.
Stage mode retains four recorded overrun positions in three fixed replays.
Instrumented timing is diagnostic only and cannot replace the rejected corpus.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_allocation_trace import reference_identity
from tools.portable_assignment_trace import digest, verify_inputs
from tools.portable_calibrated_midi_retention_corpus import POLICIES
from tools.portable_controlled_replay import validate_stage_controls
from tools.portable_corpus_replay import (
    MEASUREMENT_SCOPE, SETTINGS, command_for, now, timing_gates, validate_timing_diagnosis)


DATASETS = ('ordinary', 'physical-long', 'extended-high')
CONDITIONS = POLICIES['completion-midi-retention']['conditions']
REFERENCE_SCHEMA = 'm3_completion_midi_retention_timing_references_v1'
STAGE_CONTROLS = {
    ('ordinary', 'current-on'): (1172736,),
    ('ordinary', 'completion-midi-retention-on'): (7664256, 7671744),
    ('physical-long', 'completion-midi-retention-on'): (3512640,),
}
STAGE_ANCHOR = dict(run_id=43774069298,
    report_sha256='26ae426ab28abb765c332d99c70aaf503c798dce89cd69df55c0d499cf19eb38')


def validate_reference(reference, manifest):
    if (reference['schema'] != REFERENCE_SCHEMA or reference['block_samples'] != 32
            or reference['settings'] != SETTINGS
            or reference['conditions'] != {mode: list(flags) for mode, flags in CONDITIONS}
            or set(reference['datasets']) != set(DATASETS)):
        raise ValueError('Wrong fixed completion timing reference selection')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if reference['source'][key] != manifest['source'][key]:
            raise ValueError('Saved input provenance differs: ' + key)
    for dataset in DATASETS:
        runs = reference['datasets'][dataset]
        if set(runs) != {mode for mode, _ in CONDITIONS}:
            raise ValueError('Wrong saved modes: ' + dataset)
        for mode, _ in CONDITIONS:
            row = runs[mode]
            timing = row['timing']
            if (timing.get('timing_diagnostic_only', False) is not False
                    or any(key in timing for key in ('allocation_trace', 'thread_cpu', 'stage_cpu'))
                    or timing.get('measurement_scope') != MEASUREMENT_SCOPE
                    or not timing_gates(timing, row, 32)['timed_scored_identity']):
                raise ValueError('Reference is not saved uninstrumented timing: ' + dataset + '/' + mode)


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900,
        stage_diagnosis=False):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    selected = (tuple(STAGE_CONTROLS) if stage_diagnosis else
                tuple((ds, mode) for ds in DATASETS for mode, _ in CONDITIONS))
    datasets = tuple(dict.fromkeys(ds for ds, _ in selected))
    report = dict(schema=('m3_completion_midi_retention_stages_v1' if stage_diagnosis
                         else 'm3_completion_midi_retention_timing_v1'), started_at=now(),
        state='running', final=False, stage='verify saved references and inputs',
        declared_datasets=list(datasets), datasets={}, block_samples=32, settings=SETTINGS,
        conditions={mode: list(flags) for mode, flags in CONDITIONS},
        diagnostic_only=True, collection_pass=False, native_gate_pass=False,
        promotion_accepted=False, installed_output_changed=False,
        acceptance='not evaluated: diagnostic timing', live_readiness='not measured',
        midi_lifecycle='not remeasured; retain separate completed corpus evidence',
        timing_limits=dict(p99_ns=166666, maximum_ns=333333, deadline_overruns=0),
        interpretation='Thread CPU brackets include clock overhead. Wall-minus-CPU is '
            'diagnostic evidence, not proof of scheduler cause. Nonrecurrence does '
            'not clear the saved uninstrumented failures.')
    if stage_diagnosis:
        report.update(stage_anchor=STAGE_ANCHOR, declared_cases=[dict(dataset=ds, mode=mode,
            end_samples=list(STAGE_CONTROLS[ds, mode])) for ds, mode in selected],
            interpretation=report['interpretation'] +
                ' Stage clocks add overhead; these results cannot establish native timing acceptance.')

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
        for dataset in datasets:
            verify_inputs(corpus, manifest, dataset)
        report.update(source=manifest['source'], verified_inputs=2 + 2 * len(datasets),
            input_manifest_sha256=digest(manifest_path), binary_sha256=digest(binary),
            reference_manifest_sha256=digest(reference_path),
            reference_source=reference['source'],
            reference_report_sha256=reference['anchor_report_sha256'])
        for dataset in datasets:
            runs = report['datasets'][dataset] = {}
            for mode, flags in CONDITIONS:
                if (dataset, mode) not in selected:
                    continue
                report['stage'] = dataset + '/' + mode + ' block-32 thread CPU diagnosis'
                save()
                stem = dataset + '-' + mode + '-32'
                tsv, timing_path, stderr = (output / (stem + suffix)
                    for suffix in ('.tsv', '-timing.json', '.stderr'))
                command = command_for(binary, corpus, dataset, 'off', 32, timing_path.resolve())
                command.extend(flags)
                command.append('--diagnostic-thread-cpu')
                if stage_diagnosis:
                    for sample in STAGE_CONTROLS[dataset, mode]:
                        command.extend(('--diagnostic-stage-end-sample', str(sample)))
                started = time.monotonic()
                with tsv.open('x') as out, stderr.open('x') as err:
                    subprocess.run(command, stdout=out, stderr=err, timeout=timeout, check=True)
                replay = read_replay(tsv)
                timing = json.loads(timing_path.read_text())
                tsv_hash = digest(tsv)
                saved = reference['datasets'][dataset][mode]
                row = dict(command=command, elapsed_seconds=time.monotonic() - started,
                    output=replay['output'],
                    exact_matches_by_string_count=replay['exact_matches_by_string_count'],
                    tsv_sha256=tsv_hash, timing=timing,
                    recorded_reference_bit_identical=reference_identity(saved, replay, tsv_hash),
                    measurement_scope_verified=timing.get('measurement_scope') == MEASUREMENT_SCOPE,
                    gates=timing_gates(timing, replay, 32),
                    saved_uninstrumented_timing=saved['timing'])
                runs[mode] = row
                save()
                if not (row['recorded_reference_bit_identical'] and row['measurement_scope_verified']
                        and row['gates']['timed_scored_identity']
                        and timing['blocks'] == saved['timing']['blocks']):
                    raise ValueError('Scored output, block count or measurement scope changed: ' + stem)
                validate_timing_diagnosis(timing, stem)
                if stage_diagnosis:
                    validate_stage_controls(timing, STAGE_CONTROLS[dataset, mode], stem)
                    row['stage_controls_verified'] = True
                for block in timing['thread_cpu']['slowest_blocks']:
                    if (type(block.get('end_sample')) is not int
                            or not 0 < block['end_sample'] <= timing['blocks'] * 32
                            or any(type(block.get(k)) is not int or block[k] < 0
                                   for k in ('wall_ns', 'cpu_ns'))):
                        raise ValueError('Missing slow-block sample/clock evidence: ' + stem)
        report.update(state='completed', stage=(
            'three fixed stage replays and four controls collected' if stage_diagnosis
            else 'nine fixed diagnostic replays collected'),
            collection_pass=True, cpu_block_statistics_usable=all(
                row['timing']['thread_cpu']['block_resolution_pass']
                for runs in report['datasets'].values() for row in runs.values()))
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
    parser.add_argument('--stage-diagnosis', action='store_true')
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds, stage_diagnosis=args.stage_diagnosis)


if __name__ == '__main__':
    main()
