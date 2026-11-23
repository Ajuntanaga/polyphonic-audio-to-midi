"""Frozen full-corpus identity and deadline check; native execution is remote.

Compare 126 snapshots and 42 complete MIDI captures with saved references.
Measure 42 uninstrumented block-32 runs. No baseline rerun, policy sweep,
retry, installation or promotion is performed by this runner.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_allocation_trace import reference_identity
from tools.portable_assignment_trace import digest
from tools.portable_batch_cell_update import FLAG, cell_counts
from tools.portable_calibrated_midi_retention_corpus import buffer_identity
from tools.portable_corpus_replay import (
    BLOCKS, MEASUREMENT_SCOPE, SETTINGS, command_for, now, timing_gates)
from tools.portable_exact_cell_sharing import midi_capture
from tools.replay_corpus import DATASETS

SCHEMA = 'm3_batch_cell_corpus_v1'
REFERENCE_SCHEMA = 'm3_batch_cell_corpus_references_v1'
ANCHOR_SHA256 = '78c405a8e8845171b49b8240ff6ec91efbc0e62ef18005ad4d920b12d6bea45d'
ANCHOR_COMMIT = '83c51e3b257f57e9af75293d3a765c6bae677e5b'
INPUT_SHA256 = 'adf6e36f2883538cfa3b0500ca0d936ed64fc6a1e12aeae3bd89e40dbf7c4254'
MANIFEST_SHA256 = '0d78b2e03ba9c14ee391bd5b1b70b45b93cafc8d3d9e2591e3eac58e6aa0bb2c'
CONDITIONS = {
    'reference-off': [],
    'current-on': ['--diagnostic-spectral-lane-collision'],
    'completion-midi-retention-on': ['--diagnostic-spectral-lane-collision',
                                    '--diagnostic-completion-midi-retention'],
}


def validate_reference(reference, manifest):
    if (reference['schema'] != REFERENCE_SCHEMA
            or reference['anchor_report_sha256'] != ANCHOR_SHA256
            or reference['settings'] != SETTINGS
            or reference['conditions'] != CONDITIONS
            or reference['blocks'] != list(BLOCKS)
            or set(reference['datasets']) != set(DATASETS)
            or reference['source']['commit'] != ANCHOR_COMMIT
            or str(reference['source']['run_id']) != '43756240245'):
        raise ValueError('Wrong frozen full-corpus reference selection')
    for source in (reference['source'], manifest['source']):
        if (source['repository'] != 'Ajuntanaga/polyphonic-audio-to-midi'
                or source['worker_repository'] != 'Ajuntanaga/m3-offload'
                or source['provider'] != 'github-actions'
                or not re.fullmatch(r'[0-9a-f]{40}', source['commit'])
                or source['input_release'] != 'corpus-20261108'
                or source['input_bundle_sha256'] != INPUT_SHA256
                or source['original_input_manifest_sha256'] != MANIFEST_SHA256):
            raise ValueError('Wrong input or execution provenance')
    expected = {f'{mode}-{block}' for mode in CONDITIONS for block in BLOCKS}
    for name in DATASETS:
        rows = reference['datasets'][name]
        if set(rows) != expected:
            raise ValueError('Incomplete fixed reference modes: ' + name)
        for key, row in rows.items():
            if (not re.fullmatch(r'[0-9a-f]{64}', row.get('tsv_sha256', ''))
                    or not isinstance(row.get('output'), dict)
                    or not isinstance(row.get('exact_matches_by_string_count'), dict)):
                raise ValueError('Incomplete snapshot reference: ' + name + '/' + key)
            if key.endswith('-512') and (
                    not re.fullmatch(r'[0-9a-f]{64}', row.get('midi_sha256', ''))
                    or type(row.get('midi_rows')) is not int or row['midi_rows'] <= 0
                    or type(row.get('sample_count')) is not int or row['sample_count'] <= 0
                    or row.get('sample_rate') != 96000):
                raise ValueError('Incomplete full-recording MIDI reference: ' + name + '/' + key)


def summarize(datasets):
    rows = [row for dataset in datasets.values() for row in dataset['runs'].values()]
    timing = [row for row in rows if 'gates' in row]
    counts = dict(
        snapshot_identities=sum(row.get('recorded_reference_bit_identical') is True for row in rows),
        midi_identities=sum(row.get('raw_midi_bit_identical') is True for row in rows),
        buffer_identities=sum(row.get('buffer_bit_identical') is True for row in rows),
        zero_allocation_runs=sum(row['gates']['zero_processing_allocations'] is True for row in timing),
        timing_runs_passed=sum(row['gates']['timing_pass'] is True for row in timing),
        timed_identity_runs=sum(row['gates']['timed_scored_identity'] is True for row in timing))
    counts['full_corpus_pass'] = counts == dict(snapshot_identities=126,
        midi_identities=42, buffer_identities=84, zero_allocation_runs=42,
        timing_runs_passed=42, timed_identity_runs=42)
    return counts


def run(binary, corpus, manifest_path, reference_path, output, *,
        timeout=900, max_seconds=9000):
    if timeout <= 0 or max_seconds <= 0:
        raise ValueError('Positive replay and total budgets required')
    output.mkdir(parents=True, exist_ok=False)
    small, bulk = output / 'report', output / 'bulk'
    small.mkdir()
    bulk.mkdir()
    binary, corpus = binary.resolve(), corpus.resolve()
    deadline = time.monotonic() + max_seconds
    report = dict(schema=SCHEMA, started_at=now(), state='running', final=False,
        stage='verify inputs and frozen references', settings=SETTINGS, conditions=CONDITIONS,
        flag=FLAG, blocks=list(BLOCKS), declared_datasets=list(DATASETS), datasets={},
        execution_order=[], collection_pass=False, full_corpus_pass=False,
        native_gate_pass=False, promotion_accepted=False, installed_output_changed=False,
        live_readiness='not measured', timing_limits=dict(p99_ns=166666,
            maximum_ns=333333, deadline_overruns=0, block_samples=32, sample_rate=96000),
        interpretation='Exact saved snapshots and raw MIDI preserve recorded behavior. '
            'Uninstrumented offline core timing is separate from host/device delivery '
            'and acoustic re-pluck preservation. No installed change or note gain.')

    def save():
        report['updated_at'] = now()
        temporary = small / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(small / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        reference = json.loads(reference_path.read_text())
        validate_reference(reference, manifest)
        names = {'calibration.m3cb', 'templates.tsv'} | {
            name + suffix for name in DATASETS for suffix in ('.wav', '.tsv')}
        if set(manifest['files']) != names:
            raise ValueError('Exactly the 30 frozen input files are required')
        for name in sorted(names):
            if digest(corpus / name) != manifest['files'][name]['sha256']:
                raise ValueError('Input identity failed: ' + name)
        report.update(source=manifest['source'], verified_inputs=len(names),
            binary_sha256=digest(binary), input_manifest_sha256=digest(manifest_path),
            reference_manifest_sha256=digest(reference_path), reference_source=reference['source'],
            reference_report_sha256=reference['anchor_report_sha256'])
        for dataset in DATASETS:
            result = report['datasets'][dataset] = dict(runs={})
            baselines = {}
            for block in BLOCKS:
                for mode, flags in CONDITIONS.items():
                    key, stem = f'{mode}-{block}', f'{dataset}-{mode}-{block}'
                    tsv, midi = (bulk / (stem + suffix) for suffix in ('.tsv', '-midi.tsv'))
                    timing_path, stderr_path = (small / (stem + suffix)
                        for suffix in ('-timing.json', '.stderr'))
                    command = command_for(binary, corpus, dataset, 'off', block,
                        timing_path.resolve(), midi_trace=midi.resolve() if block == 512 else None)
                    command.extend(flags + [FLAG])
                    row = result['runs'][key] = dict(command=command)
                    report['stage'] = stem
                    report['execution_order'].append(stem)
                    save()
                    print(stem, flush=True)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Total corpus budget exhausted; no retry')
                    started = time.monotonic()
                    # Save streams before any parsing. A replay is attempted only once.
                    with tsv.open('x') as out, stderr_path.open('x') as err:
                        subprocess.run(command, stdout=out, stderr=err,
                            timeout=min(timeout, remaining), check=True)
                    row['elapsed_seconds'] = time.monotonic() - started
                    replay, tsv_hash = read_replay(tsv), digest(tsv)
                    stderr = stderr_path.read_text()
                    row.update(output=replay['output'],
                        exact_matches_by_string_count=replay['exact_matches_by_string_count'],
                        tsv_sha256=tsv_hash, stderr_sha256=digest(stderr_path),
                        cell_counts=cell_counts(stderr, True))
                    saved = reference['datasets'][dataset][key]
                    row['recorded_reference_bit_identical'] = reference_identity(saved, replay, tsv_hash)
                    save()
                    if not row['recorded_reference_bit_identical']:
                        raise ValueError('Saved snapshot identity failed: ' + stem)
                    if block == 512:
                        baselines[mode] = replay
                        row['midi'] = midi_capture(stderr, midi)
                        row['raw_midi_bit_identical'] = (
                            row['midi']['sha256'] == saved['midi_sha256']
                            and row['midi']['rows'] == saved['midi_rows'])
                        row.update(sample_count=saved['sample_count'], sample_rate=saved['sample_rate'])
                        save()
                        if not row['raw_midi_bit_identical']:
                            raise ValueError('Saved raw MIDI identity failed: ' + stem)
                    else:
                        row['buffer_bit_identical'] = buffer_identity(baselines[mode], replay)
                        if not row['buffer_bit_identical']:
                            raise ValueError('Buffer identity failed: ' + stem)
                    if block == 32:
                        timing = row['timing'] = json.loads(timing_path.read_text())
                        row['gates'] = timing_gates(timing, replay, block)
                        if (not row['gates']['timed_scored_identity']
                                or timing.get('measurement_scope') != MEASUREMENT_SCOPE
                                or timing.get('timing_diagnostic_only', False) is not False
                                or any(k in timing for k in ('thread_cpu', 'stage_cpu', 'allocation_trace'))):
                            raise ValueError('Uninstrumented scored timing required: ' + stem)
                    report.update(summarize(report['datasets']))
                    save()
        report.update(summarize(report['datasets']))
        report.update(state='completed', stage='126 fixed replays collected', collection_pass=True,
            native_gate_pass=report['full_corpus_pass'],
            decision='offline corpus passed' if report['full_corpus_pass'] else 'offline corpus rejected')
        return report['full_corpus_pass']
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
    parser.add_argument('--max-seconds', type=int, default=9000)
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds, max_seconds=args.max_seconds)


if __name__ == '__main__':
    main()
