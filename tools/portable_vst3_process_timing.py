"""Bounded ordinary-recording VST3 timing/allocation and buffer-identity screen.

Measures the instrumented component with an accepting fixed test event list,
including its diagnostic work. This is not external-host timing or live readiness.
"""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import subprocess

from tools.portable_midi_ledger_replay import digest
from tools.portable_vst3_corpus_replay import SETTINGS, assess, read_callbacks
from tools.portable_vst3_completion_midi_replay import compare_callbacks
from tools.portable_vst3_stable_note_replay import MODES, verify_inputs, stage_references

SCOPE = 'instrumented_vst3_process_with_accepting_test_sink'


def assess_measurement(native, untimed, *, trace_sha, untimed_trace_sha):
    timing = native.get('process_measurement')
    if (not isinstance(timing, dict) or timing.get('scope') != SCOPE
            or timing.get('clock') != 'steady_clock'
            or timing.get('cold_blocks_included') is not True
            or timing.get('allocation_guard') is not True
            or native.get('block_samples') != 32 or native.get('sample_rate') != 96000):
        raise ValueError('Timing scope, clock, guards or fixed acceptance clock differs')
    keys = ('blocks', 'p99_ns', 'max_ns', 'deadline_overruns',
            'cpp_allocations', 'cpp_frees', 'c_allocations', 'c_frees')
    if (any(type(timing.get(key)) is not int or timing[key] < 0 for key in keys)
            or timing['blocks'] != native['blocks'] or timing['blocks'] == 0
            or timing['p99_ns'] > timing['max_ns']
            or timing['deadline_overruns'] > timing['blocks']):
        raise ValueError('Invalid or incomplete process measurement')
    measured_state = {k: v for k, v in native.items() if k != 'process_measurement'}
    reference_state = {k: v for k, v in untimed.items() if k != 'process_measurement'}
    if untimed.get('process_measurement') is not None:
        raise ValueError('Timing reference must be untimed')
    gates = dict(timed_output_identical=trace_sha == untimed_trace_sha,
        timed_state_identical=measured_state == reference_state,
        p99_within_half_budget=timing['p99_ns'] <= 166666,
        maximum_within_deadline=timing['max_ns'] <= 333333,
        no_deadline_overruns=timing['deadline_overruns'] == 0,
        no_processing_allocations=all(timing[key] == 0 for key in keys[4:]))
    return dict(gates=gates, gate_pass=all(gates.values()))


def run(args):
    captured_source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True)
    source = captured_source.strip()
    if source != args.source_sha:
        raise ValueError('Harness source differs')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_vst3_process_timing_v1', state='running', final=False,
        source_commit=source, dataset='ordinary', settings=SETTINGS, runs={},
        promotion_accepted=False, installed_output_changed=False,
        live_readiness='not measured', wider_corpus='not measured',
        interpretation=__doc__)

    def save():
        report['observed_at'] = datetime.now(timezone.utc).isoformat()
        temporary = args.output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(args.output / 'report.json')

    save()
    try:
        manifest = json.loads(args.manifest.read_text())
        reference = json.loads(args.reference.read_text())
        inputs, clock = verify_inputs(args.corpus, manifest, reference, source)
        if clock['sample_rate'] != 96000:
            raise ValueError('Fixed acceptance budget requires 96 kHz')
        expected = stage_references(reference, args.evidence_archive, args.output / 'saved-callbacks')
        report.update(source=manifest['source'], verified_input_sha256=inputs,
            recording_clock=clock, reference_sha256=digest(args.reference),
            reference_artifact=reference['artifact'], binary_sha256=digest(args.binary))
        for bits in (32, 64):
            for mode in MODES:
                stable = mode == 'stable_note'
                for block, timed in ((512, False), (32, False), (32, True), (1024, False)):
                    name = f'{mode}-{bits}-{block}-' + ('timed' if timed else 'plain')
                    directory = args.output / name
                    directory.mkdir()
                    trace = directory / 'callbacks.tsv'
                    command = [str(args.binary.resolve()), '--wav', str((args.corpus / 'ordinary.wav').resolve()),
                        '--calibration', str((args.corpus / 'calibration.m3cb').resolve()),
                        '--events', str(trace.resolve()), '--sample-bits', str(bits), '--trial', '1',
                        '--stable-note-identity', str(int(stable)), '--block', str(block)]
                    if timed:
                        command += ['--measure-process', '1']
                    report['stage'] = name
                    save()
                    with (directory / 'native.json').open('x') as out, (directory / 'native.stderr').open('x') as err:
                        completed = subprocess.run(command, stdout=out, stderr=err, timeout=900, check=False)
                    if completed.returncode:
                        raise RuntimeError(f'{name}: native exit {completed.returncode}')
                    native = json.loads((directory / 'native.json').read_text())
                    callbacks = read_callbacks(trace, sample_count=clock['sample_count'],
                        expected_count=native['accepted_events'], include_events=True)
                    assessed = assess(native, callbacks, clock=clock, sample_bits=bits,
                        trial=True, stable_note_identity=stable, block_samples=block)
                    comparison = compare_callbacks(callbacks['events'], expected[mode])
                    assessed['gates'].update(exact_saved_callbacks=comparison['exact_saved_midi_match'],
                        exact_saved_transfers=native['transferred_pairs'] == reference['runs'][mode]['transferred_pairs'],
                        retention_disabled=native.get('completion_midi_retention') is False)
                    raw_sha = digest(trace)
                    if timed:
                        plain = report['runs'][f'{mode}-{bits}-32-plain']
                        measurement = assess_measurement(native, plain['native'], trace_sha=raw_sha,
                            untimed_trace_sha=plain['trace']['raw_sha256'])
                        assessed['gates'].update(measurement['gates'])
                    elif native.get('process_measurement') is not None:
                        raise ValueError('Untimed pass unexpectedly measured')
                    assessed['gate_pass'] = all(assessed['gates'].values())
                    callbacks.pop('events')
                    compressed = trace.with_suffix('.tsv.gz')
                    with trace.open('rb') as raw, compressed.open('xb') as out:
                        with gzip.GzipFile(fileobj=out, mode='wb', filename='', mtime=0) as archive:
                            shutil.copyfileobj(raw, archive)
                    trace.unlink()
                    report['runs'][name] = dict(native=native, callbacks=callbacks, comparison=comparison,
                        **assessed, trace=dict(file=f'{name}/{compressed.name}', raw_sha256=raw_sha,
                            sha256=digest(compressed), bytes=compressed.stat().st_size))
                    save()
        passed = all(row['gate_pass'] for row in report['runs'].values())
        report.update(state='completed', final=True, stage='bounded process screen complete',
            process_gate_pass=passed, decision='bounded process gate passed' if passed else 'rejected')
    except Exception as error:
        report.update(state='error', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference', 'evidence-archive', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    report = run(parser.parse_args())
    print(json.dumps({key: report[key] for key in ('state', 'process_gate_pass', 'decision')}))
    return 0 if report['process_gate_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
