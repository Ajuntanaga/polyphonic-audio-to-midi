"""Fixed causal harmonic prediction comparison; run recorded audio on GitHub only.

Reuse the saved detector prefix instead of running a new detector replay. Fit
owned pitches on 40ms, predict the following 10ms, and compare an added pitch.
Annotations never select the baseline, frequencies, windows, or coefficients.
This is a signal-model falsifier, not a note admission or live quality gate.
"""
import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np

from tools.candidate_outcome_analysis import HEADER, SCHEMAS, _candidates, _frame
from tools.portable_assignment_trace import digest
from tools.portable_ordinary_partial_comparison import (
    CASES, END, RATE, SAMPLES, quantiles, validate_reference)


CONFIG = dict(train_samples=3840, predict_samples=960, stride_samples=1024,
              maximum_hz=3000, candidate_harmonics=4, maximum_base_notes=8,
              svd_relative_cutoff=1e-6, a4_hz=440,
              baseline_frequency='saved phase cents when valid at training cutoff; otherwise equal temperament',
              candidate_frequency='equal temperament',
              amplitude='constant sine/cosine coefficients plus DC',
              candidates=[70, 75])
LIMITS = (
    'The 10ms prediction uses audio later than the training cutoff but never later '
    'than available_sample. Its 50ms history can cross an annotation boundary. '
    'Owned pitches may already be wrong or incomplete. Constant-frequency, '
    'constant-amplitude harmonics do not model all guitar transients, detuning or '
    'inharmonicity. Positive prediction gain can therefore be a modeling error, '
    'not a new note. Rank loss and weak independent columns limit identifiability. '
    'No threshold is selected from these cases. No note is admitted, replayed or '
    'delivered; installed scores, runtime timing and live readiness are unchanged.')


def read_outcomes(raw):
    stream = io.StringIO(raw.decode('utf-8'))
    if stream.readline() not in SCHEMAS or stream.readline() != HEADER:
        raise ValueError('Unsupported saved outcome header')
    frames = [_frame(line) for line in stream]
    if len(frames) != END // 64:
        raise ValueError('Incomplete saved outcome prefix')
    for index, frame in enumerate(frames):
        if (frame['sample'], frame['tick']) != (63 + 64 * index, index + 1):
            raise ValueError('Saved outcome clock differs')
    return frames


def read_retained_outcomes(archive, reference):
    spec = reference['artifact']
    if archive.stat().st_size != spec['bytes'] or digest(archive) != spec['sha256']:
        raise ValueError('Retained artifact identity differs')
    suffix = spec['member_suffix']
    with zipfile.ZipFile(archive) as bundle:
        members = [name for name in bundle.namelist()
                   if name == suffix or name.endswith('/' + suffix)]
        if len(members) != 1:
            raise ValueError('Retained outcome member must be unique')
        packed = bundle.read(members[0])
    data = packed
    for kind in ('compressed', 'raw'):
        if kind == 'raw':
            data = gzip.decompress(packed)
        if (len(data) != spec[kind + '_bytes']
                or hashlib.sha256(data).hexdigest() != spec[kind + '_sha256']):
            raise ValueError('Retained outcome ' + kind + ' identity differs')
    return read_outcomes(data), dict(member=members[0], **spec)


def base_pitches(frame):
    candidates = _candidates(frame)
    notes = {note for note, row in candidates.items()
             if row['selection'] in (4, 5) or row['active']}
    notes.update(voice[0] for voice in frame['voices'])
    result = []
    for note in sorted(notes):
        row = candidates.get(note, {})
        cents = row.get('phase_cents', 0.) if row.get('phase_valid') else 0.
        frequency = CONFIG['a4_hz'] * 2 ** ((note - 69 + cents / 100) / 12)
        if not np.isfinite(frequency) or not 0 < frequency < CONFIG['maximum_hz']:
            raise ValueError('Unusable causal baseline frequency')
        result.append(dict(note=note, frequency_hz=frequency, phase_cents=cents,
                           phase_valid=bool(row.get('phase_valid'))))
    return result


def harmonic_frequencies(pitches):
    frequencies = []
    for pitch in pitches:
        fundamental = pitch['frequency_hz']
        for harmonic in range(1, int(CONFIG['maximum_hz'] // fundamental) + 1):
            value = fundamental * harmonic
            # Merge mathematically shared frequencies, not nearby partials.
            if not any(abs(value - old) < 1e-6 for old in frequencies):
                frequencies.append(value)
    return sorted(frequencies)


def design(frequencies, count):
    time = np.arange(count, dtype=float) / RATE
    phase = 2 * np.pi * time[:, None] * np.asarray(frequencies)[None, :]
    return np.column_stack((np.ones(count), np.cos(phase), np.sin(phase)))


def prediction(audio, available_sample, state_frame, note):
    """Only audio[:available_sample+1] and one pre-prediction state are inputs."""
    train, hold = CONFIG['train_samples'], CONFIG['predict_samples']
    end = available_sample + 1
    start, cutoff = end - train - hold, available_sample - hold
    result = dict(available_sample=available_sample, candidate_note=note,
                  window_start_sample=start, training_end_exclusive=end - hold,
                  prediction_end_exclusive=end, baseline_state_sample=None,
                  status='insufficient_history')
    if start < 0 or state_frame is None:
        return result
    if state_frame['sample'] > cutoff:
        raise ValueError('Baseline state uses prediction-period information')
    if end > len(audio):
        raise ValueError('Audio prefix shorter than requested available sample')
    pitches = base_pitches(state_frame)
    result.update(baseline_state_sample=state_frame['sample'], base_pitches=pitches)
    if any(pitch['note'] == note for pitch in pitches):
        result['status'] = 'already_owned'
        return result
    if not pitches or len(pitches) > CONFIG['maximum_base_notes']:
        result['status'] = 'unavailable_base'
        return result
    frequencies = harmonic_frequencies(pitches)
    fundamental = CONFIG['a4_hz'] * 2 ** ((note - 69) / 12)
    added = [fundamental * harmonic
             for harmonic in range(1, CONFIG['candidate_harmonics'] + 1)
             if fundamental * harmonic <= CONFIG['maximum_hz']]
    base = design(frequencies, train + hold)
    candidate = design(added, train + hold)[:, 1:]
    full = np.column_stack((base, candidate))
    signal = np.asarray(audio[start:end], dtype=float)
    if not np.isfinite(signal).all():
        raise ValueError('Nonfinite audio')
    energy_train, energy_hold = [float(values @ values)
                                for values in (signal[:train], signal[train:])]
    if min(energy_train, energy_hold) <= np.finfo(float).tiny:
        result['status'] = 'zero_energy'
        return result
    rcond = CONFIG['svd_relative_cutoff']
    coefficients, _, rank, singular = np.linalg.lstsq(base[:train], signal[:train], rcond=rcond)
    expanded, _, full_rank, full_singular = np.linalg.lstsq(full[:train], signal[:train], rcond=rcond)
    errors = []
    for matrix, weights in ((base, coefficients), (full, expanded)):
        residual = signal - matrix @ weights
        errors.append([float(values @ values) for values in (residual[:train], residual[train:])])
    # A candidate nearly contained in the baseline subspace is unidentifiable
    # even if the enlarged least-squares fit reports less residual error.
    projection, _, _, _ = np.linalg.lstsq(base[:train], candidate[:train], rcond=rcond)
    independent = candidate[:train] - base[:train] @ projection
    independent_fraction = np.sum(independent ** 2, axis=0) / np.sum(candidate[:train] ** 2, axis=0)
    result.update(status='measured', base_partials=len(frequencies),
        candidate_partials=len(added), base_columns=base.shape[1], full_columns=full.shape[1],
        base_rank=int(rank), full_rank=int(full_rank),
        base_smallest_singular_ratio=float(singular[-1] / singular[0]),
        full_smallest_singular_ratio=float(full_singular[-1] / full_singular[0]),
        candidate_independent_fraction_min=float(independent_fraction.min()),
        candidate_independent_fraction_median=float(np.median(independent_fraction)),
        base_train_error_fraction=errors[0][0] / energy_train,
        added_train_error_fraction=errors[1][0] / energy_train,
        train_gain_fraction=(errors[0][0] - errors[1][0]) / energy_train,
        base_prediction_error_fraction=errors[0][1] / energy_hold,
        added_prediction_error_fraction=errors[1][1] / energy_hold,
        prediction_gain_fraction=(errors[0][1] - errors[1][1]) / energy_hold,
        train_rms=float(np.sqrt(energy_train / train)),
        prediction_rms=float(np.sqrt(energy_hold / hold)))
    return result


def observations(audio, frames):
    samples = [frame['sample'] for frame in frames]
    # One fixed cadence on the complete prefix, plus the already frozen examples.
    # No annotation onset resets or label-conditioned baseline selection.
    schedule = set(range(CONFIG['stride_samples'] - 1, END, CONFIG['stride_samples']))
    schedule.update(case['example_sample'] for case in CASES)
    rows = []
    for sample in sorted(schedule):
        index = bisect_right(samples, sample - CONFIG['predict_samples']) - 1
        state = frames[index] if index >= 0 else None
        for note in CONFIG['candidates']:
            rows.append(prediction(audio, sample, state, note))
    return rows


def summarize(rows, frames):
    by_sample = {frame['sample']: frame for frame in frames}
    summaries = []
    for case in CASES:
        selected = [dict(row) for row in rows if row['candidate_note'] == case['candidate_note']
                    and case['start_sample'] <= row['available_sample'] < case['end_sample']]
        for row in selected:
            frame = by_sample[row['available_sample']]
            if sorted(label[0] for label in frame['labels']) != case['expected_labels']:
                raise ValueError('Frozen case annotation differs')
            candidate = _candidates(frame).get(case['candidate_note'])
            row['saved_selection'] = candidate['selection'] if candidate else None
            row['saved_score_ratio'] = candidate['score_ratio'] if candidate else None
            row['window_starts_before_case'] = row['window_start_sample'] < case['start_sample']
        groups = {}
        for name, subset in (
                ('all', selected),
                ('below_threshold', [r for r in selected if r['saved_selection'] == 1]),
                ('below_threshold_history_inside_case', [r for r in selected
                    if r['saved_selection'] == 1 and not r['window_starts_before_case']])):
            measured = [row for row in subset if row['status'] == 'measured']
            groups[name] = dict(observations=len(subset), statuses=dict(Counter(r['status'] for r in subset)),
                positive_prediction_gains=sum(r['prediction_gain_fraction'] > 0 for r in measured),
                rank_deficient=sum(r['base_rank'] < r['base_columns'] or r['full_rank'] < r['full_columns']
                                   for r in measured),
                history_crosses_case=sum(r['window_starts_before_case'] for r in subset),
                **{metric: quantiles([r[metric] for r in measured]) for metric in (
                    'train_gain_fraction', 'prediction_gain_fraction',
                    'base_prediction_error_fraction', 'added_prediction_error_fraction',
                    'candidate_independent_fraction_min', 'candidate_independent_fraction_median')})
        summaries.append(dict(case=case, groups=groups,
            example=next(row for row in selected if row['available_sample'] == case['example_sample'])))
    return summaries


def run(corpus, manifest_path, reference_path, archive, output):
    output.mkdir(parents=True, exist_ok=True)
    report = dict(schema='m3_ordinary_harmonic_prediction_v1', status='running',
        started_at=datetime.now(timezone.utc).isoformat(), config=CONFIG, limits=LIMITS,
        dataset='ordinary', native_replays=0, installed_output_changed=False,
        runtime_policy_changed=False, admission_acceptance='not established')
    try:
        manifest = json.loads(manifest_path.read_text())
        reference = json.loads(reference_path.read_text())
        if (reference['schema'] != 'm3_ordinary_harmonic_prediction_references_v1'
                or reference['config'] != CONFIG):
            raise ValueError('Frozen diagnostic configuration differs')
        anchor_path = reference_path.parent / reference['anchor_file']
        if digest(anchor_path) != reference['anchor_sha256']:
            raise ValueError('Saved replay reference manifest differs')
        anchor = json.loads(anchor_path.read_text())
        validate_reference(anchor, manifest)
        wav_path = corpus / 'ordinary.wav'
        if (wav_path.stat().st_size != anchor['inputs']['ordinary.wav']['bytes']
                or digest(wav_path) != anchor['inputs']['ordinary.wav']['sha256']):
            raise ValueError('Ordinary waveform identity differs')
        frames, retained = read_retained_outcomes(archive, reference)
        from scipy.io import wavfile
        rate, audio = wavfile.read(wav_path, mmap=True)
        if rate != RATE or audio.ndim != 1 or len(audio) != SAMPLES or audio.dtype != np.int16:
            raise ValueError('Saved mono PCM16 waveform clock/format differs')
        signal = audio[:END].astype(float) / 32768
        rows = observations(signal, frames)
        evidence = output / 'observations.jsonl.gz'
        with gzip.open(evidence, 'wt') as stream:
            for row in rows:
                stream.write(json.dumps(row, allow_nan=False) + '\n')
        report.update(status='completed', source=manifest['source'],
            sample_rate=RATE, full_input_samples=SAMPLES, analyzed_prefix_samples=END,
            reference_sha256=digest(reference_path), runtime_manifest_sha256=digest(manifest_path),
            retained_outcome=retained, observations=len(rows),
            evidence=dict(path=evidence.name, bytes=evidence.stat().st_size, sha256=digest(evidence)),
            cases=summarize(rows, frames))
    except Exception as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('corpus', 'manifest', 'reference', 'archive', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.corpus, args.manifest, args.reference, args.archive, args.output)
    print(json.dumps(dict(status=result['status'], observations=result['observations'],
                          admission_acceptance=result['admission_acceptance'])))


if __name__ == '__main__':
    main()
