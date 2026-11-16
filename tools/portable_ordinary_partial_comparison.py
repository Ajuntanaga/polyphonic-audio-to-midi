"""Compare a missing ordinary note with fixed false-note controls on GitHub.

Two unchanged current-ON replays observe existing demodulated mixture tracks.
This diagnostic neither admits notes nor selects a new admission threshold.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np

from tools.candidate_outcome_analysis import HEADER, _candidates, _frame
from tools.frozen_cue_corpus_gate import read_replay
from tools.partial_motion_evidence import (condition_mixture_tracks,
    phase_window_trajectories, trajectories)
from tools.portable_assignment_trace import compress_trace_window, digest, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for
from tools.portable_routing_trace import outcome_window


DATASET, RATE, SAMPLES, END = 'ordinary', 96000, 10689600, 235200
FLAGS = ['--diagnostic-spectral-lane-collision']
CASES = [
    dict(name='missing-note75', parent_note=47, candidate_note=75,
         start_sample=163306, end_sample=235200, example_sample=167359,
         expected_labels=[10, 11, 12]),
    dict(name='false-note70-chord', parent_note=42, candidate_note=70,
         start_sample=217, end_sample=72000, example_sample=4991,
         expected_labels=[0, 1, 2, 3, 4]),
    dict(name='false-note70-gap', parent_note=42, candidate_note=70,
         start_sample=72000, end_sample=81839, example_sample=72063,
         expected_labels=[]),
]
INTERPRETATION = (
    'Fifth-minus-fundamental cents describes the measured fifth partial relative to '
    'five times the measured fundamental, not a source-pure pitch or string identity. '
    'Tracks and causal filters retain the full prefix without annotation resets. '
    'The 160ms estimates summarize preceding windows and may include preceding passages; '
    'availability time, not the window center, selects a case. Missing estimates are '
    'unknown, not zero. The amplitude check is relative to past mixture amplitude, '
    'not a noise or SNR measurement. Candidate selection is recorded, not changed. '
    'Full scored output, raw MIDI and outcome must match saved references. '
    'This observation establishes no admission gain, timing acceptance or live delivery.')


def validate_reference(reference, manifest):
    if (reference['schema'] != 'm3_ordinary_partial_references_v1'
            or reference['dataset'] != DATASET or reference['cases'] != CASES
            or reference['window'] != [0, END] or reference['settings'] != SETTINGS
            or reference['flags'] != FLAGS or reference['block_samples'] != 512):
        raise ValueError('Wrong fixed ordinary partial comparison')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if reference['source'][key] != manifest['source'][key]:
            raise ValueError('Saved input provenance differs: ' + key)
    for name in (DATASET + '.wav', DATASET + '.tsv', 'calibration.m3cb', 'templates.tsv'):
        if reference['inputs'][name] != manifest['files'][name]:
            raise ValueError('Saved input identity differs: ' + name)
    saved = reference['replay_reference']
    if saved['sample_rate'] != RATE or saved['sample_count'] != SAMPLES:
        raise ValueError('Saved sample clock differs')
    for key in ('tsv_sha256', 'midi_sha256', 'outcome_sha256'):
        value = saved.get(key, '')
        if len(value) != 64 or any(char not in '0123456789abcdef' for char in value):
            raise ValueError('Saved complete digest required: ' + key)


def read_motion(path, note):
    with path.open() as stream:
        header = json.loads(next(stream))
        frames = [json.loads(line) for line in stream if line.strip()]
    if any(header.get(key) != value for key, value in dict(
            kind='header', schema='m3_partial_motion_v1', sample_rate=RATE,
            sample_origin=0, sample_clock='zero_based_input_sample', note=note,
            harmonics=6, tracks='measured_demodulated_mixture').items()):
        raise ValueError('Partial-motion header differs')
    if len(frames) != END // 64:
        raise ValueError('Incomplete partial-motion prefix')
    for index, frame in enumerate(frames):
        if (frame['kind'] != 'frame' or frame['note'] != note
                or frame['sample'] != 63 + index * 64 or frame['tick'] != index + 1):
            raise ValueError('Partial-motion note or clock differs')
    frequencies = np.asarray([row['frequency_hz'] for row in frames], dtype=float)
    signal = (np.asarray([row['real'] for row in frames], dtype=float)
              + 1j * np.asarray([row['imaginary'] for row in frames], dtype=float)).T
    if frequencies.shape != (len(frames), 6) or signal.shape != (6, len(frames)):
        raise ValueError('Partial-motion bands differ')
    centers = frequencies[0]
    if not np.isfinite(centers).all() or centers[0] <= 0 or not np.all(frequencies == centers):
        raise ValueError('Partial-motion centers changed or are unavailable')
    enabled = centers > 0
    if not np.allclose(centers[enabled], centers[0] * np.arange(1, 7)[enabled], atol=1e-6):
        raise ValueError('Partial-motion harmonic centers differ')
    signal[~enabled] = np.nan
    signal[:, [not row['tracks_available'] for row in frames]] = np.nan
    return frames, signal, centers


def quantiles(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return {name: float(np.percentile(values, pct)) if len(values) else None
            for name, pct in (('min', 0), ('p10', 10), ('p50', 50), ('p90', 90), ('max', 100))}


def pair_observations(track):
    """Keep all six harmonic indexes: band five is divided by five upstream."""
    valid = track['valid'][0] & track['valid'][4]
    difference = track['cents'][4] - track['cents'][0]
    return dict(samples=np.rint(track['increment_times'] * RATE).astype(int),
                valid=valid, difference=np.where(valid, difference, np.nan))


def summarize_pair(pair, case, selected_samples=None, *, window_samples=0):
    keep = (pair['samples'] >= case['start_sample']) & (pair['samples'] < case['end_sample'])
    if selected_samples is not None:
        keep &= np.isin(pair['samples'], list(selected_samples))
    valid = keep & pair['valid']
    return dict(observations=int(keep.sum()), valid_pairs=int(valid.sum()),
        valid_pair_fraction=float(valid.sum() / keep.sum()) if keep.any() else None,
        windows_starting_before_case=int((keep & (pair['samples'] - window_samples < case['start_sample'])).sum())
            if window_samples else 0,
        fifth_minus_fundamental_cents=quantiles(pair['difference'][valid]))


def analyze(frames, signal, centers, outcomes, note, destination):
    times = np.asarray([row['sample'] for row in frames]) / RATE
    conditioned = condition_mixture_tracks(times, signal, observation_period=64 / RATE)
    tracks = {
        'raw': trajectories(times, signal, centers[0]),
        'conditioned': trajectories(times, conditioned, centers[0]),
        'conditioned_160ms': phase_window_trajectories(times, conditioned, centers[0]),
    }
    pairs = {key: pair_observations(track) for key, track in tracks.items()}
    columns = HEADER.rstrip('\n').split('\t')
    snapshots = [_frame('\t'.join(row[key] for key in columns)) for row in outcomes]
    if [row['sample'] for row in snapshots] != [row['sample'] for row in frames]:
        raise ValueError('Outcome and partial-motion prefix clocks differ')
    cases = []
    for case in CASES:
        if case['parent_note'] != note:
            continue
        selected, counts, example = set(), Counter(), None
        for frame in snapshots:
            if not case['start_sample'] <= frame['sample'] < case['end_sample']:
                continue
            if sorted(label[0] for label in frame['labels']) != case['expected_labels']:
                raise ValueError('Fixed case annotation differs')
            candidate = _candidates(frame).get(case['candidate_note'])
            counts['frames'] += 1
            counts['candidate_unobserved' if candidate is None else
                   'candidate_selection_' + str(candidate['selection'])] += 1
            if candidate is not None and candidate['selection'] == 1:
                selected.add(frame['sample'])
            if frame['sample'] == case['example_sample']:
                example = dict(sample=frame['sample'], candidate=candidate, estimates={})
        if example is None:
            raise ValueError('Fixed example missing')
        summaries = {}
        for name, pair in pairs.items():
            summaries[name] = dict(
                all=summarize_pair(pair, case, window_samples=15360 if name.endswith('160ms') else 0),
                candidate_below_threshold=summarize_pair(pair, case, selected,
                    window_samples=15360 if name.endswith('160ms') else 0))
            # No nearest future window, backfill, or invalid-to-zero replacement.
            positions = np.flatnonzero(pair['samples'] <= case['example_sample'])
            index = int(positions[-1]) if len(positions) else None
            example['estimates'][name] = None if index is None else dict(
                available_sample=int(pair['samples'][index]),
                age_samples=case['example_sample'] - int(pair['samples'][index]),
                valid=bool(pair['valid'][index]),
                fifth_minus_fundamental_cents=float(pair['difference'][index])
                    if pair['valid'][index] else None)
        cases.append(dict(case=case, counts=dict(counts), summaries=summaries, example=example))
    bulk = destination / 'partial-comparison.tsv.gz'
    with gzip.open(bulk, 'wt', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(('method', 'available_sample', 'valid_pair', 'fundamental_cents',
                         'fifth_cents', 'fifth_minus_fundamental_cents'))
        for name, pair in pairs.items():
            for i, sample in enumerate(pair['samples']):
                writer.writerow((name, int(sample), int(pair['valid'][i]),
                    *[float(tracks[name]['cents'][band, i]) if tracks[name]['valid'][band, i] else ''
                      for band in (0, 4)],
                    float(pair['difference'][i]) if pair['valid'][i] else ''))
    return dict(cases=cases, enabled_bands=(centers > 0).tolist(),
        nominal_28_semitone_offset_from_fifth_cents=float(2800 - 1200 * np.log2(5)),
        observations=dict(file=bulk.name, bytes=bulk.stat().st_size, sha256=digest(bulk)))


def verify_capture(replay, midi, outcome, saved):
    parsed = read_replay(replay)
    result = dict(tsv_sha256=digest(replay), midi_sha256=digest(midi),
                  outcome_sha256=digest(outcome), output=parsed['output'])
    if any(result[key] != saved[key] for key in result):
        raise ValueError('Complete scored output, raw MIDI or outcome differs from saved reference')
    with replay.open() as stream:
        aggregate = next(csv.DictReader(stream, delimiter='\t'))
    if int(aggregate['samples']) != SAMPLES or int(aggregate['sample_rate']) != RATE:
        raise ValueError('Replay sample clock differs')
    return dict(result, saved_reference_bit_identical=True, sample_count=SAMPLES, sample_rate=RATE)


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_ordinary_partial_comparison_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), runs={}, interpretation=INTERPRETATION)
    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    try:
        manifest, reference = json.loads(manifest_path.read_text()), json.loads(reference_path.read_text())
        validate_reference(reference, manifest)
        verify_inputs(corpus, manifest, DATASET)
        report.update(source=manifest['source'], binary_sha256=digest(binary),
            input_manifest_sha256=digest(manifest_path), reference_checkpoint_sha256=digest(reference_path))
        for note in (47, 42):
            directory = output / f'parent-{note}'
            directory.mkdir()
            paths = {name: directory / (name + ('.jsonl' if name == 'partial-motion' else '.tsv'))
                     for name in ('replay', 'midi-event', 'outcome', 'partial-motion')}
            command = command_for(binary, corpus, DATASET, 'off', 512, None, midi_trace=paths['midi-event'])
            command.extend(FLAGS)
            command.extend(('--outcome-trace', str(paths['outcome']), '--partial-motion-trace',
                str(paths['partial-motion']), '--partial-motion-note', str(note),
                '--partial-motion-start', '0', '--partial-motion-end', str(END / RATE)))
            report.update(stage=f'observe parent {note}', command=command)
            save()
            with paths['replay'].open('x') as stdout, (directory / 'replay.stderr').open('x') as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
            result = verify_capture(paths['replay'], paths['midi-event'], paths['outcome'],
                                    reference['replay_reference'])
            report['runs'][str(note)] = result
            frames, signal, centers = read_motion(paths['partial-motion'], note)
            outcomes = outcome_window(paths['outcome'], SAMPLES, 0, END)
            result.update(analyze(frames, signal, centers, outcomes, note, directory))
            result['traces'] = {}
            for name in ('midi-event', 'outcome'):
                result['traces'][name] = compress_trace_window(paths[name], start=0, end=END)
                paths[name].unlink()
            path = paths['partial-motion']
            compressed = path.with_suffix(path.suffix + '.gz')
            with path.open('rb') as source, gzip.open(compressed, 'wb', compresslevel=1) as target:
                shutil.copyfileobj(source, target)
            result['traces']['partial-motion'] = dict(file=compressed.name,
                raw_sha256=digest(path), sha256=digest(compressed), bytes=compressed.stat().st_size)
            path.unlink()
            save()
        report.update(state='completed', final=True, stage='fixed cases observed',
                      saved_references_bit_identical=True)
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        if report['final']:
            report['finished_at'] = datetime.now(timezone.utc).isoformat()
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
