"""Causal input-level observations and pitch-occupancy bounds; no policy replay.

Pure mechanics accept synthetic arrays locally. Recorded waveform I/O is confined
to portable_neural_input_level on GitHub Actions. A level becomes available only
at saved callback entry, once the whole consumed block is available; never at an
earlier source sample position. Computation time is optimistically zero for the bound.
"""
from collections import Counter, defaultdict
import math

from tools.pitch_detector_comparison import union_spans

FEATURES = ('power20', 'power80', 'power_max')
CLASSES = ('genuine', 'wrong', 'gap')
DB_EDGES = tuple(range(-120, 1, 6))
NS = 1_000_000_000


def db(power):
    if power is None:
        return None
    if not math.isfinite(power) or power < 0:
        raise ValueError('Invalid input power')
    return 10 * math.log10(power) if power > 0 else -180.0


def causal_levels(mono, callbacks, rate):
    """Trailing 20/80ms RMS power, updated at actual callback entry.

    Startup uses observed samples only, without zero padding. Unknown before the
    first callback entry is retained rather than treated as silence.
    """
    import numpy as np
    samples = np.asarray(mono)
    if samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all() or rate <= 0:
        raise ValueError('Invalid waveform or rate')
    prefix = np.empty(len(samples) + 1, dtype=np.float64)
    prefix[0] = 0
    np.cumsum(np.square(samples, dtype=np.float64), out=prefix[1:])
    windows = (round(rate * .020), round(rate * .080))
    if min(windows) < 1:
        raise ValueError('Sample rate too low')
    updates = []
    end = previous_finished = 0
    for row in callbacks:
        if (row['samples'] < 0 or row['source_end'] != end + row['samples']
                or row['source_end'] > len(samples) or row['duration_ns'] < 0
                or row['started_ns'] < previous_finished):
            raise ValueError('Invalid callback ordering or source coverage')
        end = row['source_end']
        finished = row['started_ns'] + row['duration_ns']
        # The harness waits for the entire input block before calling process().
        if row['started_ns'] * rate < end * NS:
            raise ValueError('Callback starts before input block is available')
        previous_finished = finished
        if row['samples'] == 0:
            continue
        when = (row['started_ns'] * rate + NS - 1) // NS
        powers = [float(max(0., prefix[end] - prefix[max(0, end - w)])) / min(end, w)
                  for w in windows]
        updates.append(dict(start=min(when, len(samples)), source_end=end,
                            power20=powers[0], power80=powers[1], power_max=max(powers)))
    if end != len(samples):
        raise ValueError('Callbacks do not cover the full recording')
    levels = [dict(start=0, source_end=0, **dict.fromkeys(FEATURES))]
    for row in updates:
        if row['start'] >= len(samples):
            break
        if row['start'] == levels[-1]['start']:
            levels[-1] = row
        else:
            levels.append(row)
    for index, row in enumerate(levels):
        row['end'] = levels[index + 1]['start'] if index + 1 < len(levels) else len(samples)
    return levels


def occupancy_by_level(spans, labels, levels, sample_count):
    """Partition unioned output exactly into genuine, wrong and gap occupancy."""
    edges = defaultdict(list)
    for a, b, note in union_spans(spans, sample_count=sample_count):
        edges[a].append(('voice', note, 1)); edges[b].append(('voice', note, -1))
    for row in labels:
        a, b, note = row['start_sample'], row['end_sample'], row['midi_note']
        if not 0 <= a < b <= sample_count:
            raise ValueError('Annotation outside recording')
        edges[a].append(('label', note, 1)); edges[b].append(('label', note, -1))
    if not levels or levels[0]['start'] != 0 or levels[-1]['end'] != sample_count:
        raise ValueError('Incomplete level clock')
    rows = [dict(row, **dict.fromkeys(CLASSES, 0)) for row in levels]
    for i, row in enumerate(rows):
        if row['start'] >= row['end'] or (i and rows[i-1]['end'] != row['start']):
            raise ValueError('Discontinuous level clock')
        edges[row['start']]; edges[row['end']]
    active, expected = Counter(), Counter()
    points = sorted(edges)
    index = 0
    for left, right in zip(points, points[1:]):
        for kind, note, delta in edges[left]:
            counts = active if kind == 'voice' else expected
            counts[note] += delta
            if counts[note] < 0:
                raise ValueError('Unbalanced interval edges')
            if not counts[note]: del counts[note]
        while left >= rows[index]['end']:
            index += 1
        duration = right - left
        common = len(active.keys() & expected.keys())
        rows[index]['genuine'] += common * duration
        rows[index]['wrong'] += (len(active) - common) * duration if expected else 0
        rows[index]['gap'] += len(active) * duration if not expected else 0
    return rows


def histogram(rows, feature):
    """Fixed descriptive bins, not a list of trial thresholds."""
    result = [dict(lower_db=None if i == 0 else DB_EDGES[i-1],
                   upper_db=DB_EDGES[i] if i < len(DB_EDGES) else None,
                   **dict.fromkeys(CLASSES, 0)) for i in range(len(DB_EDGES) + 1)]
    unknown = dict.fromkeys(CLASSES, 0)
    for row in rows:
        value = db(row[feature])
        target = unknown if value is None else result[sum(value >= edge for edge in DB_EDGES)]
        for kind in CLASSES: target[kind] += row[kind]
    return dict(bins=result, unknown=unknown)


def lossless_ceiling(all_rows, feature):
    """Largest common strict-less-than cut preserving all observed genuine time.

    This is an optimistic occupancy bound: immediate suppression and restoration
    are allowed. Real ownership/retrigger mechanics can only make it harder.
    The minimum is fitted to these recordings, so passing is not generalization.
    """
    present = [row[feature] for rows in all_rows.values() for row in rows
               if row['genuine'] and row[feature] is not None]
    if not present:
        raise ValueError('No genuine output with known level')
    ceiling = min(present)
    datasets = {}
    for name, rows in all_rows.items():
        removable = {kind:sum(row[kind] for row in rows
                     if row[feature] is not None and row[feature] < ceiling) for kind in CLASSES}
        if removable['genuine']:
            raise ValueError('Lossless ceiling removed genuine output')
        datasets[name] = removable
    return dict(feature=feature, threshold_power=ceiling, threshold_db=db(ceiling),
                comparison='strictly below; equality and unknown retained', datasets=datasets)
