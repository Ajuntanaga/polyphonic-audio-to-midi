"""One fixed, same-binary exact-cell sharing screen; native execution is remote.

Six trace-free timing runs and six untimed MIDI companions use three fixed
cases, alternating arm order. Identity and CPU usefulness are separate from
full-corpus native acceptance and live-host readiness.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_allocation_trace import reference_identity
from tools.portable_assignment_trace import digest, verify_inputs
from tools.portable_completion_midi_retention_timing import CONDITIONS, validate_reference
from tools.portable_corpus_replay import SETTINGS, command_for, now
from tools.portable_sample_observation_comparison import (
    CASES, MINIMUM_CPU_REDUCTION_PERCENT, validate_observation)

FLAG = '--diagnostic-exact-cell-sharing'
COMPANION_REFERENCE_SCHEMA = 'm3_exact_cell_sharing_companion_references_v1'
CELL_LINE = re.compile(
    r'^m3_replay: exact_cell_sharing enabled=([01]) unique=(\d+) duplicates=(\d+)$',
    re.MULTILINE)
MIDI_LINE = re.compile(
    r'^m3_replay: midi_event_trace rows=(\d+) cap=(\d+) truncated=([01])$',
    re.MULTILINE)


def cell_counts(stderr, enabled):
    matches = CELL_LINE.findall(stderr)
    if len(matches) != 1:
        raise ValueError('Exactly one cell-sharing summary required')
    actual, unique, duplicates = map(int, matches[0])
    if actual != int(enabled) or unique <= 0 or duplicates <= 0:
        raise ValueError('Wrong sharing mode or no duplicate cells exercised')
    return dict(unique=unique, duplicates=duplicates)


def midi_capture(stderr, path):
    matches = MIDI_LINE.findall(stderr)
    if len(matches) != 1:
        raise ValueError('Exactly one MIDI capture summary required')
    rows, cap, truncated = map(int, matches[0])
    if truncated or not 0 < rows <= cap or path.stat().st_size == 0:
        raise ValueError('Complete nonempty MIDI capture required')
    return dict(rows=rows, cap=cap, truncated=False, sha256=digest(path))


def validate_companion_reference(reference, timing_reference):
    expected = {}
    for dataset, mode in CASES:
        expected.setdefault(dataset, set()).add(mode)
    if (reference['schema'] != COMPANION_REFERENCE_SCHEMA
            or reference['block_samples'] != 512
            or reference['settings'] != SETTINGS
            or reference['conditions'] != {mode: list(flags) for mode, flags in CONDITIONS}
            or set(reference['datasets']) != set(expected)):
        raise ValueError('Wrong fixed block-512 companion reference selection')
    if (reference['source'] != timing_reference['source']
            or reference['anchor_report_sha256'] != timing_reference['anchor_report_sha256']):
        raise ValueError('Timing and companion reference provenance differs')
    for dataset, modes in expected.items():
        runs = reference['datasets'][dataset]
        if set(runs) != modes:
            raise ValueError('Wrong saved companion modes: ' + dataset)
        for mode in modes:
            row = runs[mode]
            if (not re.fullmatch(r'[0-9a-f]{64}', row.get('tsv_sha256', ''))
                    or not isinstance(row.get('output'), dict)
                    or not isinstance(row.get('exact_matches_by_string_count'), dict)):
                raise ValueError('Incomplete companion snapshot reference: ' + dataset + '/' + mode)


def run(binary, corpus, manifest_path, reference_path, companion_reference_path,
        output, *, timeout=900):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    output.mkdir(parents=True, exist_ok=False)
    small, bulk = output / 'report', output / 'bulk'
    small.mkdir()
    bulk.mkdir()
    binary, corpus = binary.resolve(), corpus.resolve()
    report = dict(schema='m3_exact_cell_sharing_v1', started_at=now(), state='running',
        final=False, stage='verify inputs and references', settings=SETTINGS,
        flag=FLAG, timing_block_samples=32, midi_companion_block_samples=512,
        declared_cases=[dict(dataset=ds, mode=mode) for ds, mode in CASES], cases=[],
        execution_order=[], diagnostic_only=True, collection_pass=False,
        usefulness_screen_pass=False, native_gate_pass=False, promotion_accepted=False,
        installed_output_changed=False, minimum_cpu_reduction_percent=MINIMUM_CPU_REDUCTION_PERCENT,
        screening_rule='Every pair: identical snapshots and MIDI, zero allocations, '
            'usable CPU clock, CPU total at least 2% lower and CPU p99 no higher',
        interpretation='One same-binary pair per case, alternating order. Thread CPU '
            'brackets include clock overhead. Raw MIDI uses separate untimed companions. '
            'A useful result warrants uninstrumented corpus validation; it cannot clear '
            'prior native/host timing failures or establish note gains or live readiness.')

    def save():
        report['updated_at'] = now()
        temporary = small / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(small / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        reference = json.loads(reference_path.read_text())
        companion_reference = json.loads(companion_reference_path.read_text())
        validate_reference(reference, manifest)
        validate_companion_reference(companion_reference, reference)
        datasets = tuple(dict.fromkeys(ds for ds, _ in CASES))
        for dataset in datasets:
            verify_inputs(corpus, manifest, dataset)
        report.update(source=manifest['source'], binary_sha256=digest(binary),
            verified_inputs=2 + 2 * len(datasets),
            input_manifest_sha256=digest(manifest_path),
            reference_manifest_sha256=digest(reference_path),
            companion_reference_manifest_sha256=digest(companion_reference_path),
            reference_source=reference['source'],
            reference_report_sha256=reference['anchor_report_sha256'])
        # All timing runs finish before any MIDI trace is written.
        for index, (dataset, mode) in enumerate(CASES):
            order = ('off', 'on') if index % 2 == 0 else ('on', 'off')
            case = dict(dataset=dataset, mode=mode, arm_order=list(order),
                        timing_runs={}, midi_companions={})
            report['cases'].append(case)
        for phase, block in (('timing_runs', 32), ('midi_companions', 512)):
            phase_reference = reference if block == 32 else companion_reference
            for case in report['cases']:
                dataset, mode = case['dataset'], case['mode']
                saved = phase_reference['datasets'][dataset][mode]
                for arm in case['arm_order']:
                    stem = f'{dataset}-{mode}-{arm}-{block}'
                    tsv, midi = (bulk / (stem + suffix) for suffix in ('.tsv', '-midi.tsv'))
                    timing_path, stderr_path = (small / (stem + suffix)
                        for suffix in ('-timing.json', '.stderr'))
                    command = command_for(binary, corpus, dataset, 'off', block,
                        timing_path.resolve(), midi_trace=midi.resolve() if block == 512 else None)
                    command.extend(dict(CONDITIONS)[mode])
                    if block == 32:
                        command.append('--diagnostic-thread-cpu')
                    if arm == 'on':
                        command.append(FLAG)
                    row = dict(command=command, observation_verified=False)
                    case[phase][arm] = row
                    report['stage'] = stem
                    report['execution_order'].append(stem)
                    save()
                    started = time.monotonic()
                    # Capture both streams before parsing; never retry a failed replay.
                    with tsv.open('x') as out, stderr_path.open('x') as err:
                        subprocess.run(command, stdout=out, stderr=err, timeout=timeout, check=True)
                    row['elapsed_seconds'] = time.monotonic() - started
                    replay, tsv_hash = read_replay(tsv), digest(tsv)
                    stderr = stderr_path.read_text()
                    row.update(output=replay['output'], tsv_sha256=tsv_hash,
                               stderr_sha256=digest(stderr_path))
                    if block == 32:
                        timing = json.loads(timing_path.read_text())
                        row['timing'] = timing
                        save()
                        validate_observation(timing, replay, saved, tsv_hash)
                        row['cell_counts'] = cell_counts(stderr, arm == 'on')
                    else:
                        if not reference_identity(saved, replay, tsv_hash):
                            raise ValueError('Untimed companion snapshot differs from saved reference')
                        row['midi'] = midi_capture(stderr, midi)
                    row.update(observation_verified=True, recorded_reference_bit_identical=True)
                    save()
                before, after = (case[phase][arm] for arm in ('off', 'on'))
                if before['tsv_sha256'] != after['tsv_sha256']:
                    raise ValueError('Paired snapshot identity failed')
                if block == 32:
                    if before['cell_counts'] != after['cell_counts']:
                        raise ValueError('Paired cell map counts differ')
                    old, new = before['timing']['thread_cpu'], after['timing']['thread_cpu']
                    case.update(cpu_total_reduction_percent=
                        100 * (old['total_ns'] - new['total_ns']) / old['total_ns'],
                        cpu_p99_delta_ns=new['p99_ns'] - old['p99_ns'],
                        cpu_useful=(100 * new['total_ns'] <=
                            (100 - MINIMUM_CPU_REDUCTION_PERCENT) * old['total_ns']
                            and new['p99_ns'] <= old['p99_ns']))
                else:
                    if before['midi'] != after['midi']:
                        raise ValueError('Paired raw MIDI identity failed')
                    case['raw_midi_bit_identical'] = True
                save()
        report.update(state='completed', stage='six timing runs and six MIDI companions collected',
            collection_pass=True, usefulness_screen_pass=all(c['cpu_useful'] for c in report['cases']))
        return report['usefulness_screen_pass']
    except Exception as error:
        report.update(state='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report.update(final=True, finished_at=now())
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference-report',
                 'companion-reference-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.reference_report,
        args.companion_reference_report, args.output, timeout=args.replay_timeout_seconds)


if __name__ == '__main__':
    main()
