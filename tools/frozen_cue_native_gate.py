"""Compare a standalone native measurement with the frozen mixture reference."""
from __future__ import annotations

import csv
import math
from pathlib import Path


# These tolerances cover numeric features only. Cue intervals, reasons, peak
# presence, bins, and causal sample clocks must agree exactly.
TOLERANCES = {
    'hz': {'absolute': 1e-5, 'relative': 0.0},
    'cents': {'absolute': 1e-5, 'relative': 0.0},
    'power': {'absolute': 1e-24, 'relative': 1e-6},
    'reference': {'absolute': 1e-24, 'relative': 1e-6},
    'prominence': {'absolute': 1e-4, 'relative': 0.0},
}


def compare_native_observations(audio, observations, native_cues):
    from tools.independent_partial_evidence import measure, frozen_pair_screen, frozen_cue_intervals

    counts = dict(clock=0, reason=0, peak_presence=0, peak_bin=0,
                  reference_presence=0, numeric=0)
    examples, intervals = [], []
    maximum_error = {key: 0.0 for key in TOLERANCES}
    frames = rows = 0

    def mismatch(kind, end, note, field, expected, actual):
        counts[kind] += 1
        if len(examples) < 16:
            examples.append(dict(kind=kind, end_sample=end, note=note, field=field,
                                 expected=expected, actual=actual))

    with Path(observations).open() as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        for row in measure(audio, 96000, notes=tuple(range(32, 85))):
            frames += 1
            end, history = row['sample'] + 1, row['history_available']
            intervals.extend(frozen_cue_intervals([row], sample_count=len(audio)))
            for note in range(32, 85):
                got = next(reader, None)
                if got is None:
                    raise ValueError('native observations ended before the reference')
                rows += 1
                expected_clock = [end, note, int(history), int(history)]
                actual_clock = [int(got[key]) for key in ('end_sample', 'note', 'history', 'valid')]
                if actual_clock != expected_clock:
                    mismatch('clock', end, note, 'sample/history', expected_clock, actual_clock)
                value = row['notes'].get(str(note))
                reason = frozen_pair_screen(value) if history else 'missing_peak'
                if got['reason'] != reason:
                    mismatch('reason', end, note, 'reason', reason, got['reason'])
                for label, harmonic in (('third', 2), ('fifth', 4)):
                    peak = value['partials'][harmonic] if history else None
                    found = got[label + '_bin'] != ''
                    if found != (peak is not None):
                        mismatch('peak_presence', end, note, label, peak is not None, found)
                        continue
                    if peak is None:
                        continue
                    if int(got[label + '_bin']) != peak['fft_bin']:
                        mismatch('peak_bin', end, note, label, peak['fft_bin'], int(got[label + '_bin']))
                    for name, source in (('hz', 'frequency_hz'), ('cents', 'cents'),
                                         ('power', 'power'), ('reference', 'local_reference_power'),
                                         ('prominence', 'local_prominence_db')):
                        expected, text = peak[source], got[label + '_' + name]
                        actual = float(text) if text else None
                        if (expected is None) != (actual is None):
                            mismatch('reference_presence', end, note, label + '_' + name, expected, actual)
                            continue
                        if expected is None:
                            continue
                        if not math.isfinite(actual):
                            mismatch('numeric', end, note, label + '_' + name, expected, text)
                            continue
                        error = abs(actual - expected)
                        maximum_error[name] = max(maximum_error[name], error)
                        tolerance = TOLERANCES[name]
                        if error > tolerance['absolute'] + tolerance['relative'] * abs(expected):
                            mismatch('numeric', end, note, label + '_' + name, expected, actual)
        if next(reader, None) is not None:
            raise ValueError('native observations continue beyond the reference')
    expected_cues = 'm3_frozen_note_cues_v1\t96000\t1024\n' + ''.join(
        f"{item['begin_sample']}\t{item['end_sample']}\t{item['midi_note']}\n" for item in intervals)
    cues_identical = Path(native_cues).read_bytes() == expected_cues.encode('ascii')
    return dict(parity_pass=cues_identical and not any(counts.values()),
                cue_intervals_identical=cues_identical, reference_cue_intervals=len(intervals),
                analysis_frames=frames, note_observations=rows, mismatches=counts,
                mismatch_examples=examples, maximum_absolute_error=maximum_error,
                numeric_tolerances=TOLERANCES)
