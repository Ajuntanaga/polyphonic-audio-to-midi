"""Paired full-corpus component screen. No promotion or external-host claim."""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import subprocess

from tools.portable_calibrated_midi_retention_corpus import verify_references
from tools.portable_midi_ledger_replay import digest
from tools.portable_vst3_corpus_replay import SETTINGS, assess, read_callbacks
from tools.portable_vst3_process_timing import assess_measurement
from tools.replay_corpus import DATASETS
from tools.vst3_stable_note_corpus_gate import compare_component_pitch


def read_labels(path, samples):
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    labels = []
    for index, row in enumerate(rows):
        label = {key: int(row[key]) for key in ('start_sample', 'end_sample', 'midi_note', 'string_mask')}
        if not (0 <= label['start_sample'] < label['end_sample'] <= samples
                and 0 <= label['midi_note'] <= 127 and 0 < label['string_mask'] < 256):
            raise ValueError('Invalid annotation bounds or pitch/string identity')
        labels.append(dict(label_index=index, **label))
    if not labels:
        raise ValueError('Empty annotation set')
    return labels


def run(args):
    captured = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True)
    if captured.strip() != args.source_sha:
        raise ValueError('Harness source differs')
    manifest = json.loads(args.manifest.read_text())
    if manifest['source']['commit'] != args.source_sha:
        raise ValueError('Manifest source differs')
    reference = json.loads(args.reference.read_text())
    verified_count = verify_references(reference, manifest, args.corpus)
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_vst3_stable_note_corpus_v1', state='running', final=False,
        source=manifest['source'], settings=SETTINGS, datasets={},
        verified_input_files=verified_count, manifest_sha256=digest(args.manifest),
        reference_sha256=digest(args.reference), binary_sha256=digest(args.binary),
        installed_output_changed=False, promotion_accepted=False,
        acoustic_repluck_preservation='not measured', live_readiness='not measured',
        frozen_off_replay_identity='not measured', physical_string_assignment='not measured',
        interpretation=__doc__)

    def save():
        report['observed_at'] = datetime.now(timezone.utc).isoformat()
        temp = args.output / 'report.json.tmp'
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(args.output / 'report.json')

    save()
    try:
        for dataset in DATASETS:
            clock = {key: reference['datasets'][dataset]['current-on'][key]
                     for key in ('sample_count', 'sample_rate')}
            if clock['sample_rate'] != 96000 or type(clock['sample_count']) is not int or clock['sample_count'] <= 0:
                raise ValueError('Invalid fixed-budget recording clock')
            labels = read_labels(args.corpus / (dataset + '.tsv'), clock['sample_count'])
            row = dict(clock=clock, runs={}, comparisons={})
            report['datasets'][dataset] = row
            canonical = {}
            for bits in (32, 64):
                for stable in (False, True):
                    mode = 'stable_note' if stable else 'per_voice'
                    for block, timed in ((512, False), (32, False), (32, True), (1024, False)):
                        name = f'{mode}-{bits}-{block}-' + ('timed' if timed else 'plain')
                        report['stage'] = dataset + '/' + name
                        directory = args.output / dataset / name
                        directory.mkdir(parents=True)
                        trace = directory / 'callbacks.tsv'
                        command = [str(args.binary.resolve()), '--wav', str((args.corpus / (dataset + '.wav')).resolve()),
                            '--calibration', str((args.corpus / 'calibration.m3cb').resolve()),
                            '--events', str(trace.resolve()), '--sample-bits', str(bits), '--trial', '1',
                            '--stable-note-identity', str(int(stable)), '--block', str(block)]
                        if timed:
                            command += ['--measure-process', '1']
                        save()
                        with (directory / 'native.json').open('x') as out, (directory / 'native.stderr').open('x') as err:
                            result = subprocess.run(command, stdout=out, stderr=err, timeout=900, check=False)
                        if result.returncode:
                            raise RuntimeError(f'{dataset}/{name}: native exit {result.returncode}')
                        native = json.loads((directory / 'native.json').read_text())
                        callbacks = read_callbacks(trace, sample_count=clock['sample_count'],
                            expected_count=native['accepted_events'], include_events=True)
                        events = callbacks.pop('events')
                        assessment = assess(native, callbacks, clock=clock, sample_bits=bits,
                            trial=True, stable_note_identity=stable, block_samples=block)
                        raw_sha = digest(trace)
                        if mode not in canonical:
                            canonical[mode] = dict(events=events, sha256=raw_sha,
                                transitions=native['detector_transitions'], transfers=native['transferred_pairs'])
                        baseline = canonical[mode]
                        assessment['gates'].update(
                            buffer_and_format_callbacks_identical=raw_sha == baseline['sha256'],
                            buffer_and_format_transfers_identical=native['transferred_pairs'] == baseline['transfers'],
                            buffer_and_format_detector_count_identical=native['detector_transitions'] == baseline['transitions'],
                            completion_retention_disabled=native.get('completion_midi_retention') is False)
                        if timed:
                            plain = row['runs'][f'{mode}-{bits}-32-plain']
                            measurement = assess_measurement(native, plain['native'], trace_sha=raw_sha,
                                untimed_trace_sha=plain['trace']['raw_sha256'])
                            assessment['gates'].update(measurement['gates'])
                        elif native.get('process_measurement') is not None:
                            raise ValueError('Unexpected timing in plain reference')
                        assessment['gate_pass'] = all(assessment['gates'].values())
                        compressed = trace.with_suffix('.tsv.gz')
                        with trace.open('rb') as src, compressed.open('xb') as out:
                            with gzip.GzipFile(fileobj=out, mode='wb', filename='', mtime=0) as archive:
                                shutil.copyfileobj(src, archive)
                        trace.unlink()
                        row['runs'][name] = dict(native=native, callbacks=callbacks, **assessment,
                            trace=dict(raw_sha256=raw_sha, sha256=digest(compressed),
                                file=str(compressed.relative_to(args.output)), bytes=compressed.stat().st_size))
                        save()
            row['comparisons'] = compare_component_pitch(canonical['per_voice']['events'],
                canonical['stable_note']['events'], labels, clock['sample_count'])
            row['detector_transition_count_identical'] = canonical['per_voice']['transitions'] == canonical['stable_note']['transitions']
            row['gate_pass'] = (row['comparisons']['gate_pass'] and row['detector_transition_count_identical']
                and all(item['gate_pass'] for item in row['runs'].values()))
            save()
        passed = set(report['datasets']) == set(DATASETS) and all(row['gate_pass'] for row in report['datasets'].values())
        report.update(state='completed', final=True, corpus_gate_pass=passed,
            decision='eligible for further validation' if passed else 'rejected', stage='corpus complete')
    except Exception as error:
        report.update(state='error', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    report = run(parser.parse_args())
    return 0 if report['corpus_gate_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
