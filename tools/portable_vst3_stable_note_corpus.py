"""Paired full-corpus component screen. No promotion or external-host claim."""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess

from tools.portable_calibrated_midi_retention_corpus import verify_references
from tools.portable_midi_ledger_replay import digest
from tools.portable_vst3_corpus_replay import SETTINGS, assess, read_callbacks
from tools.portable_vst3_process_timing import assess_measurement
from tools.replay_corpus import DATASETS
from tools.vst3_stable_note_corpus_gate import compare_component_pitch


COMPONENT_SCHEMA = 'm3_batch_cell_vst3_references_v1'
INPUT_IDENTITY = ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256')
MODES = ('per_voice', 'stable_note')
PASSES = ((512, False), (32, False), (32, True), (1024, False))


def component_state(native):
    # assess() independently checks format, block size and exact block count.
    # Timing and the new execution switch are the only other differing fields.
    omitted = {'sample_bits', 'block_samples', 'blocks', 'process_measurement', 'batch_cell_update'}
    return {key: value for key, value in native.items() if key not in omitted}


def component_reference_from_report(report, report_sha256):
    if (report.get('schema') != 'm3_vst3_stable_note_corpus_v1'
            or report.get('state') != 'completed' or report.get('final') is not True
            or report.get('scope', 'full corpus') != 'full corpus' or report.get('settings') != SETTINGS
            or set(report['datasets']) != set(DATASETS)
            or not re.fullmatch('[0-9a-f]{64}', report_sha256)):
        raise ValueError('Incomplete saved component report')
    expected_names = {f'{mode}-{bits}-{block}-' + ('timed' if timed else 'plain')
                      for mode in MODES for bits in (32, 64) for block, timed in PASSES}
    reference = dict(schema=COMPONENT_SCHEMA, source=report['source'],
        source_report_sha256=report_sha256, settings=SETTINGS, datasets={})
    for dataset, row in report['datasets'].items():
        if set(row['runs']) != expected_names:
            raise ValueError('Incomplete saved component matrix')
        modes = {}
        for mode in MODES:
            saved = row['runs'][f'{mode}-32-512-plain']
            state = component_state(saved['native'])
            sha = saved['trace']['raw_sha256']
            for name, item in row['runs'].items():
                if not name.startswith(mode + '-'):
                    continue
                if (item['native'].get('batch_cell_update', False) is not False
                        or component_state(item['native']) != state
                        or item['trace']['raw_sha256'] != sha):
                    raise ValueError('Saved component outcomes differ across the matrix')
            modes[mode] = dict(state=state, callbacks_sha256=sha)
        reference['datasets'][dataset] = dict(clock=row['clock'], modes=modes)
    return reference


def verify_component_reference(reference, manifest, replay_reference):
    if (reference.get('schema') != COMPONENT_SCHEMA or reference.get('settings') != SETTINGS
            or set(reference['datasets']) != set(DATASETS)
            or any(reference['source'][key] != manifest['source'][key] for key in INPUT_IDENTITY)
            or not re.fullmatch('[0-9a-f]{64}', reference['source_report_sha256'])):
        raise ValueError('Component reference provenance differs')
    for dataset, row in reference['datasets'].items():
        clock = {key: replay_reference['datasets'][dataset]['current-on'][key]
                 for key in ('sample_count', 'sample_rate')}
        if row['clock'] != clock or set(row['modes']) != set(MODES):
            raise ValueError('Component reference clock or modes differ')
        for mode, item in row['modes'].items():
            if (not re.fullmatch('[0-9a-f]{64}', item['callbacks_sha256'])
                    or any(item['state'][key] != value for key, value in clock.items())
                    or item['state']['stable_note_identity'] is not (mode == 'stable_note')):
                raise ValueError('Invalid component reference outcome')


def read_labels(path, samples):
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    labels = []
    for index, row in enumerate(rows):
        label = {key: int(row[key]) for key in ('start_sample', 'end_sample', 'midi_note', 'string_mask')}
        if not (0 <= label['start_sample'] < label['end_sample'] <= samples
                and 0 <= label['midi_note'] <= 127 and 0 <= label['string_mask'] < 256):
            raise ValueError(f'{path}: row {index + 2}: invalid annotation bounds or pitch/string identity: {label}')
        # Zero means unknown string identity; pitch-level comparisons remain valid.
        labels.append(dict(label_index=index, **label))
    if not labels:
        raise ValueError('Empty annotation set')
    return labels


def run(args):
    batch = getattr(args, 'batch_cell_update', False)
    component_path = getattr(args, 'component_reference', None)
    if batch != (component_path is not None):
        raise ValueError('Batch execution requires the saved component reference and vice versa')
    requested = getattr(args, 'datasets', None)
    selected = list(DATASETS) if requested is None else list(requested)
    if not selected or len(set(selected)) != len(selected) or any(name not in DATASETS for name in selected):
        raise ValueError('Dataset selection must contain unique known corpus names')
    diagnostic = requested is not None
    captured = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True)
    if captured.strip() != args.source_sha:
        raise ValueError('Harness source differs')
    manifest = json.loads(args.manifest.read_text())
    if manifest['source']['commit'] != args.source_sha:
        raise ValueError('Manifest source differs')
    reference = json.loads(args.reference.read_text())
    verified_count = verify_references(reference, manifest, args.corpus)
    component_reference = None
    if component_path is not None:
        component_reference = json.loads(component_path.read_text())
        verify_component_reference(component_reference, manifest, reference)
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_vst3_stable_note_corpus_v1', state='running', final=False,
        source=manifest['source'], settings=SETTINGS, datasets={},
        scope='bounded diagnostic' if diagnostic else 'full corpus', selected_datasets=selected,
        verified_input_files=verified_count, manifest_sha256=digest(args.manifest),
        reference_sha256=digest(args.reference), binary_sha256=digest(args.binary),
        installed_output_changed=False, promotion_accepted=False,
        acoustic_repluck_preservation='not measured', live_readiness='not measured',
        frozen_off_replay_identity='not measured', physical_string_assignment='not measured',
        interpretation=__doc__)
    if batch:
        report.update(schema='m3_vst3_batch_cell_corpus_v1', batch_cell_update=True,
            component_reference_sha256=digest(component_path),
            component_reference_source=component_reference['source'],
            component_reference_report_sha256=component_reference['source_report_sha256'])

    def save():
        report['observed_at'] = datetime.now(timezone.utc).isoformat()
        temp = args.output / 'report.json.tmp'
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(args.output / 'report.json')

    save()
    try:
        inputs = {}
        for dataset in selected:
            report['stage'] = dataset + '/annotation-preflight'
            save()
            clock = {key: reference['datasets'][dataset]['current-on'][key]
                     for key in ('sample_count', 'sample_rate')}
            if clock['sample_rate'] != 96000 or type(clock['sample_count']) is not int or clock['sample_count'] <= 0:
                raise ValueError('Invalid fixed-budget recording clock')
            labels = read_labels(args.corpus / (dataset + '.tsv'), clock['sample_count'])
            inputs[dataset] = (clock, labels)
        report['annotation_preflight_passed'] = True
        save()
        for dataset, (clock, labels) in inputs.items():
            row = dict(clock=clock, runs={}, comparisons={})
            report['datasets'][dataset] = row
            canonical = {}
            for bits in (32, 64):
                for stable in (False, True):
                    mode = 'stable_note' if stable else 'per_voice'
                    for block, timed in PASSES:
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
                        if batch:
                            command += ['--batch-cell-update', '1']
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
                        saved_identity = {}
                        if batch:
                            saved = component_reference['datasets'][dataset]['modes'][mode]
                            saved_identity = dict(batch_execution_enabled=native.get('batch_cell_update') is True,
                                saved_component_callbacks_identical=raw_sha == saved['callbacks_sha256'],
                                saved_component_outcome_identical=component_state(native) == saved['state'])
                            assessment['gates'].update(saved_identity)
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
                        if not all(saved_identity.values()):
                            raise ValueError(f'{dataset}/{name}: saved component identity failed: {saved_identity}')
            row['comparisons'] = compare_component_pitch(canonical['per_voice']['events'],
                canonical['stable_note']['events'], labels, clock['sample_count'])
            row['detector_transition_count_identical'] = canonical['per_voice']['transitions'] == canonical['stable_note']['transitions']
            row['gate_pass'] = (row['comparisons']['gate_pass'] and row['detector_transition_count_identical']
                and all(item['gate_pass'] for item in row['runs'].values()))
            save()
        passed = set(report['datasets']) == set(selected) and all(row['gate_pass'] for row in report['datasets'].values())
        report.update(state='completed', final=True, screen_gate_pass=passed,
            corpus_gate_pass=None if diagnostic else passed,
            decision=('diagnostic passed; no corpus verdict' if diagnostic else 'eligible for further validation') if passed else 'rejected',
            stage='diagnostic complete' if diagnostic else 'corpus complete')
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
    parser.add_argument('--batch-cell-update', action='store_true',
                        help='Test-only batched arithmetic; requires a pinned component reference')
    parser.add_argument('--component-reference', type=Path)
    parser.add_argument('--datasets', nargs='+', choices=tuple(DATASETS),
                        help='Bounded diagnostic only; never produces a full-corpus verdict')
    report = run(parser.parse_args())
    return 0 if report['screen_gate_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
