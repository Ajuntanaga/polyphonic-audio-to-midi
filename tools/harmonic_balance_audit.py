"""Offline harmonic-power measurements with separate recorded-pass holdouts.

Profiles retain the detector's DC-filter response. Only the correlation filter
is undone when comparing fitted complex coefficients to these measurements.
Nothing in this module can change note selection or MIDI output.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import lfilter


def normalized_power(power, bands=7):
    values = np.asarray(power, dtype=float).copy()
    if values.shape != (3,) or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("expected three finite nonnegative powers")
    values[[not (bands & (1 << h)) for h in range(3)]] = 0
    total = float(values.sum())
    return values / total if total > 0 else values


def power_similarity(first, second, bands=7):
    return float(np.sqrt(normalized_power(first, bands) *
                         normalized_power(second, bands)).sum())


def correlation_power(amplitudes, residual_hz, rate, growth=0.0):
    """Undo a 40-ms correlator, including a constant exponential envelope.

    Native calibration already corrects the correlation response but retains
    the input DC block. Removing that DC response here would mix two domains.
    """
    decay = math.exp(-1 / (0.040 * rate))
    transfer = (1 - decay) / (1 - decay * np.exp(
        -(growth + 2j * np.pi * np.asarray(residual_hz)) / rate))
    return np.abs(np.asarray(amplitudes) / transfer) ** 2


def measure_clip(samples, rate, center, begin, end):
    """Measure labeled isolated audio; no calibration frequencies are supplied.

    The preceding context initializes the DC filter. Each 750-ms frame searches
    its own fundamental, then the first three partials. Frames overlap and are
    deliberately reported as measurements, not independent test examples.
    """
    values = np.asarray(samples, dtype=float)
    if (values.ndim != 1 or not np.isfinite(values).all() or rate <= 0 or
            not 0 <= begin < end <= len(values) or end - begin < 0.75 * rate):
        raise ValueError("invalid isolated measurement clip")
    values = lfilter([1, -1], [1, -math.exp(-2 * math.pi * 15 / rate)], values)
    count = round(0.75 * rate)
    window = np.hanning(count)
    times = np.arange(count) / rate
    nfft = 4 * (1 << (count - 1).bit_length())
    bins = np.fft.rfftfreq(nfft, 1 / rate)
    frames = []
    for start in range(begin, end - count + 1, round(0.25 * rate)):
        signal = values[start:start + count] * window
        spectrum = np.abs(np.fft.rfft(signal, nfft)) ** 2

        def peak(nominal, width_cents):
            low, high = nominal * np.exp2(np.asarray([-width_cents, width_cents]) / 1200)
            eligible = np.flatnonzero((bins >= low) & (bins <= high))
            if not len(eligible):
                raise ValueError("partial outside measurable frequency range")
            best = eligible[int(np.argmax(spectrum[eligible]))]
            spacing = rate / nfft
            bounds = (max(low, bins[best] - 2 * spacing), min(high, bins[best] + 2 * spacing))

            def power(frequency):
                return float(abs(np.exp(-2j * np.pi * frequency * times) @ signal) ** 2 /
                             float(window.sum()) ** 2)

            fitted = minimize_scalar(lambda hz: -power(hz), bounds=bounds,
                                     method="bounded", options={"xatol": 1e-8})
            return float(fitted.x), power(fitted.x)

        fundamental, first_power = peak(center, 60)
        partials = [(fundamental, first_power), peak(2 * fundamental, 40), peak(3 * fundamental, 40)]
        powers = [power for _, power in partials]
        frames.append({"start_seconds": start / rate, "power": powers,
                       "profile": normalized_power(powers).tolist(),
                       "fundamental_cents": float(1200 * math.log2(fundamental / center)),
                       "partial_cents": [1200 * math.log2(hz / ((h + 1) * fundamental))
                                         for h, (hz, _) in enumerate(partials)]})
    return frames


def summarize_isolated(clips):
    """Learn from ascending pass only, score descending/checkpoint attacks."""
    prototypes = {}
    for string in sorted({c["string"] for c in clips}):
        training = [f["profile"] for c in clips if c["string"] == string and c["pass"] == 1
                    for f in c["frames"]]
        if not training:
            raise ValueError("missing ascending-pass training data")
        prototypes[str(string)] = normalized_power(np.median(training, axis=0)).tolist()
    result = {"training_pass": 1, "prototypes": prototypes, "bands": {}}
    for bands in (3, 7):
        attacks = []
        for clip in clips:
            if clip["pass"] == 1:
                continue
            scores = {string: [power_similarity(frame["power"], profile, bands)
                               for frame in clip["frames"]]
                      for string, profile in prototypes.items()}
            ranks = sorted(prototypes, key=lambda string: -float(np.median(scores[string])))
            attacks.append({"clip": clip["clip"], "pass": clip["pass"],
                            "expected_string": clip["string"], "chosen_string": int(ranks[0]),
                            "median_similarity": {s: float(np.median(v)) for s, v in scores.items()},
                            "margin": float(np.median(scores[ranks[0]]) - np.median(scores[ranks[1]]))
                            if len(ranks) > 1 else None})
        result["bands"][str(bands)] = {"heldout_attacks": len(attacks),
            "matched_attacks": sum(a["expected_string"] == a["chosen_string"] for a in attacks),
            "attacks": attacks}
    return result


def score_existing_fit(times, signal, center, sources, training, rate, models, prototypes, bands):
    """Inspect fixed fits, without rerunning their frequency optimization."""
    try:
        from .harmonic_drift_fit import _linear
    except ImportError:
        from harmonic_drift_fit import _linear
    times = np.asarray(times) - times[0]
    source_by_string = {s['string']: s for s in sources}
    results = []
    for model in models:
        if model['fit_family'] not in ('static', 'gain_drift'):
            continue
        members = model['members']
        selected = [source_by_string[m['string']] for m in members]
        cents = np.asarray([m.get('cents', m.get('cents_at_start')) for m in members])
        growth = np.asarray([m.get('growth_per_second', 0) for m in members])
        residual_hz = np.arange(1, 4)[:, None] * center * (np.exp2(
            (cents[None, :] + np.asarray([s['partial_cents'] for s in selected]).T) / 1200) - 1)
        row = {'mask': model['mask'], 'fit_family': model['fit_family'], 'members': [],
               'independent_cross_band_support': model['independent_cross_band_support'],
               'test_prediction_loss': model['test_prediction_loss']}
        for name, start, stop in (('training', 0, training), ('test', training, len(times))):
            fit = _linear(times[start:stop], signal[:, start:stop], center, selected,
                          cents, cents, growth, times[-1], np.ones(3), bands)
            similarities = []
            for i, member in enumerate(members):
                power = correlation_power(fit['amplitude'][:, i], residual_hz[:, i], rate, growth[i])
                profile = normalized_power(power, bands)
                similarity = power_similarity(profile, prototypes[str(member['string'])], bands)
                similarities.append(similarity)
                if name == 'training':
                    row['members'].append({'string': member['string']})
                row['members'][i][name + '_profile'] = profile.tolist()
                row['members'][i][name + '_similarity'] = similarity
            row['minimum_' + name + '_similarity'] = min(similarities)
        results.append(row)
    return results


def prepare_clips(recordings, labels, destination, note):
    """Copy only annotated note spans plus short filter context, using mmap."""
    import csv
    import hashlib
    import json
    import re
    from pathlib import Path
    from scipy.io import wavfile

    recordings, labels, destination = map(Path, (recordings, labels, destination))
    destination.mkdir(parents=True, exist_ok=True)
    paths = {}
    for path in recordings.glob('*.wav'):
        matched = re.fullmatch(r'string[_ ]?([1-8])', path.stem, re.IGNORECASE)
        if matched:
            physical = int(matched[1])
            if physical in paths:
                raise ValueError('ambiguous isolated source recording')
            paths[physical] = path
    clips = []
    for string in range(8):
        if not 0 <= note - (32 + 4 * string) <= 24:
            continue
        physical = 8 - string
        ledger = labels / f'string-{physical:02d}' / f'string-{physical:02d}-pass-balanced.tsv'
        with ledger.open() as stream:
            rows = [r for r in csv.DictReader(stream, delimiter='\t') if int(r['midi_note']) == note]
        rate, values = wavfile.read(paths[physical], mmap=True)
        if values.dtype != np.float32 or values.ndim != 1:
            raise ValueError('expected mono float32 source recording')
        for index, row in enumerate(rows):
            start, end = int(row['start_sample']), int(row['end_sample'])
            begin = max(0, start - round(0.25 * rate))
            if not 0 <= begin < start < end <= len(values):
                raise ValueError('annotation outside source audio')
            name = f's{string}-n{note}-attack{index}.wav'
            path = destination / name
            wavfile.write(path, rate, values[begin:end])
            clips.append({'clip': name, 'string': string, 'pass': int(row['calibration_pass']),
                          'midi_note': note, 'source_start_sample': begin,
                          'labeled_begin': start - begin, 'labeled_end': end - begin,
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        del values
    manifest = {'note': note, 'clips': clips, 'source_kind': 'original physical isolated recordings',
                'training_pass': 1, 'holdout_passes': [2, 3]}
    target = destination / 'manifest.json'
    target.write_text(json.dumps(manifest, indent=2) + '\n')
    return target


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recordings', required=True)
    parser.add_argument('--labels', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--note', type=int, default=40)
    args = parser.parse_args()
    print(prepare_clips(args.recordings, args.labels, args.output, args.note))
