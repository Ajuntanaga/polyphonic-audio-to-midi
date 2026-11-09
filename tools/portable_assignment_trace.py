"""Trace one OFF recording on a cloud runner against a fresh untraced reference.

Inputs and output carry their own provenance; installed scores never change.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read_rows(path):
    csv.field_size_limit(8 * 1024 * 1024)
    with path.open(newline='') as stream:
        return list(csv.DictReader((line for line in stream if not line.startswith('#')),
                                   delimiter='\t'))


def assignment_summary(rows, *, note, start, end, expected_mask):
    selected = [row for row in rows if int(row['note']) == note
                and start <= int(row['sample']) < end]
    if any(int(row['expected_note']) != 1 or int(row['expected_mask']) != expected_mask
           for row in selected):
        raise ValueError('Assignment trace disagrees with label identity')
    fields = ('observed', 'valid', 'complete_calibration', 'playable',
              'prior_primary', 'dp_primary', 'final_primary', 'final_mask',
              'rendered_mask', 'midi_mask', 'group_after', 'primary_only_render',
              'use_posterior', 'posterior_observation_available', 'posterior_updated',
              'profile_fit_observed', 'profile_uses_long_memory')
    counts = {key: dict(Counter(row[key] for row in selected)) for key in fields}
    masks = [int(row['rendered_mask']) for row in selected]
    return dict(sampled_rows=len(selected), expected_mask=expected_mask,
                distributions=counts,
                exact_rendered_rows=sum(mask == expected_mask for mask in masks),
                missing_expected_lane_rows={str(lane): sum(not mask & (1 << lane) for mask in masks)
                                            for lane in range(8) if expected_mask & (1 << lane)},
                extra_lane_rows={str(lane): sum(bool(mask & (1 << lane)) for mask in masks)
                                 for lane in range(8) if not expected_mask & (1 << lane)},
                interpretation='Sampled assignment rows only, not labeled-frame match scores. '
                               'Missing rows are analyzed separately by candidate disposition.')


def verify_inputs(corpus, manifest, name):
    for filename in (name + '.wav', name + '.tsv', 'calibration.m3cb', 'templates.tsv'):
        if digest(corpus / filename) != manifest['files'][filename]['sha256']:
            raise ValueError('Input identity failed: ' + filename)


def trace_bounds(labels, sample_count, sample_rate):
    # The native candidate trace defaults to twenty seconds and caps at 90,000
    # ticks. Cover every requested label explicitly, including boundary ticks.
    start = max(0, min(label['start_sample'] for label in labels) - 64)
    end = min(sample_count, max(label['end_sample'] for label in labels) + 64)
    if (end - start + 63) // 64 + 1 > 90000:
        raise ValueError('Requested labels exceed the candidate trace frame limit')
    return start / sample_rate, end / sample_rate


def run(binary, corpus, manifest_path, output, *, dataset, note, timeout):
    from tools.frozen_cue_corpus_gate import compare_replays, read_replay
    from tools.portable_corpus_replay import SETTINGS, command_for
    from tools.selection_trace_diagnosis import summarize_selection
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    report = dict(schema='m3_assignment_trace_v2', state='running', final=False,
                  stage='verify inputs', dataset=dataset, note=note, windows=[],
                  settings=SETTINGS, installed_output_changed=False,
                  promotion_accepted=False, live_readiness='not measured',
                  provenance='Fresh OFF reference and traced OFF replay on the same runner')

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    def replay(command, stem):
        report.update(stage=stem, command=command)
        save()
        path = output / (stem + '.tsv')
        started = time.monotonic()
        with path.open('x') as stdout, (output / (stem + '.stderr')).open('x') as stderr:
            subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
        parsed = read_replay(path)
        report.setdefault('runs', {})[stem] = dict(
            elapsed_seconds=time.monotonic() - started, tsv_sha256=digest(path),
            output=parsed['output'], exact_matches_by_string_count=parsed['exact_matches_by_string_count'])
        return path, parsed

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        verify_inputs(corpus, manifest, dataset)
        report.update(source=manifest.get('source', {}), binary_sha256=digest(binary),
                      input_manifest_sha256=digest(manifest_path))
        base_command = command_for(binary, corpus, dataset, 'off', 512, None)
        reference_path, before = replay(base_command, 'reference-off')
        labels = [label for label in before['labels'] if label['midi_note'] == note]
        if not labels:
            raise ValueError('Requested note has no labels')
        with reference_path.open() as stream:
            aggregate = next(csv.DictReader(stream, delimiter='\t'))
        sample_count, sample_rate = int(aggregate['samples']), int(aggregate['sample_rate'])
        start, end = trace_bounds(labels, sample_count, sample_rate)
        traces = {kind: output / (kind + '.tsv') for kind in ('candidate', 'outcome', 'assignment')}
        command = base_command.copy()
        for kind, path in traces.items():
            command.extend(('--' + kind + '-trace', str(path)))
        command.extend(('--candidate-trace-note', str(note), '--candidate-trace-start', str(start),
                        '--candidate-trace-end', str(end)))
        replay_path, after = replay(command, 'traced-off')
        comparison = compare_replays(before, after)
        report.update(comparison=comparison, output=after['output'], sample_count=sample_count,
                      sample_rate=sample_rate, trace_start_seconds=start, trace_end_seconds=end)
        if not comparison['output_bit_identical'] or comparison['changed_labels']:
            raise ValueError('Tracing changed reference output')
        report['stage'] = 'summarize selection and assignment'
        save()
        candidates, outcomes, assignments = (read_rows(traces[kind]) for kind in
                                             ('candidate', 'outcome', 'assignment'))
        for label in labels:
            start, end = label['start_sample'], label['end_sample']
            window = [row for row in candidates if start <= int(row['sample']) < end]
            report['windows'].append(dict(
                label=label,
                selection=summarize_selection(window, outcomes, assignments, note=note,
                                              start=start, end=end, sample_count=sample_count),
                assignment=assignment_summary(assignments, note=note, start=start, end=end,
                                              expected_mask=label['string_mask'])))
        report['stage'] = 'compress diagnostic traces'
        save()
        report['traces'] = {}
        for kind, path in traces.items():
            compressed = path.with_suffix('.tsv.gz')
            record = dict(raw_bytes=path.stat().st_size, raw_sha256=digest(path))
            with path.open('rb') as src, gzip.open(compressed, 'wb', compresslevel=1) as dest:
                shutil.copyfileobj(src, dest)
            record.update(file=compressed.name, bytes=compressed.stat().st_size,
                          sha256=digest(compressed))
            report['traces'][kind] = record
            path.unlink()
        report.update(state='completed', final=True, stage='diagnosis collected')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()


def main():
    from tools.replay_corpus import DATASETS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dataset', choices=sorted(DATASETS), default='physical-middle')
    parser.add_argument('--note', type=int, choices=range(128), default=52)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    if args.replay_timeout_seconds <= 0:
        parser.error('--replay-timeout-seconds must be positive')
    run(args.binary, args.corpus, args.manifest, args.output, dataset=args.dataset,
        note=args.note, timeout=args.replay_timeout_seconds)


if __name__ == '__main__':
    main()
