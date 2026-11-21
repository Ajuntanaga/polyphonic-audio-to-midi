"""Fixed causal-feature feasibility screen; no audio/model I/O in this module."""
import numpy as np

from tools.pitch_detector_comparison import union_spans


LAGS = (0, 1, 2, 4, 8, 16)
HARMONICS = (-36, -24, -19, -12, 12, 19, 24, 28, 31, 36)
NEIGHBORS = (-2, -1, 1, 2)
MODEL_PARAMS = dict(max_iter=100, max_depth=3, max_leaf_nodes=8,
    learning_rate=0.05, min_samples_leaf=128, l2_regularization=0.1,
    max_bins=64, early_stopping=False, random_state=0)


def lag(values, count):
    result = np.zeros_like(values)
    if count == 0:
        return values.copy()
    if count < len(values):
        result[count:] = values[:-count]
    return result


def rolling(values, width, operation):
    """Trailing window including now; missing history is zero, never future."""
    stack = np.stack([lag(values, k) for k in range(width)])
    return getattr(np, operation)(stack, axis=0)


def offset_pitch(values, offset):
    result = np.zeros_like(values)
    if offset < 0:
        result[:, -offset:] = values[:, :offset]
    elif offset > 0:
        result[:, :-offset] = values[:, offset:]
    else:
        result[:] = values
    return result


def causal_features(note, onset):
    """N x 88 x 76; no pitch ID, time, annotation, native row or future frame."""
    if (note.ndim != 2 or note.shape[1] != 88 or onset.shape != note.shape
            or not np.isfinite(note).all() or not np.isfinite(onset).all()):
        raise ValueError('Expected finite, dense 88-pitch activations')
    columns, names = [], []
    def add(name, values):
        names.append(name)
        columns.append(values)
    for name, values in (('note', note), ('onset', onset)):
        for k in LAGS:
            add(f'{name}_lag{k}', lag(values, k))
        for width in (4, 16):
            for operation in ('min', 'mean', 'max'):
                add(f'{name}_{operation}{width}', rolling(values, width, operation))
        recent = rolling(values, 8, 'max')
        for offset in HARMONICS:
            add(f'{name}_offset{offset}_now', offset_pitch(values, offset))
            add(f'{name}_offset{offset}_max8', offset_pitch(recent, offset))
        for offset in NEIGHBORS:
            add(f'{name}_neighbor{offset}', offset_pitch(values, offset))
        for operation in ('sum', 'max'):
            aggregate = getattr(np, operation)(values, axis=1)[:, None]
            add(f'{name}_global_{operation}', np.broadcast_to(aggregate, values.shape))
    result = np.stack(columns, axis=2).astype(np.float32)
    if len(names) != 76:
        raise ValueError('Frozen feature family changed')
    return result, names


def decision_intervals(frames, timing, sample_count, sample_rate=96000):
    """Use the last row available at each measured FIFO completion sample."""
    clocks = {int(row[0]): int(row[3]) for row in timing}
    if len(clocks) != len(timing):
        raise ValueError('Duplicate timing source clock')
    samples = np.array([(clocks[int(row[3])] * sample_rate + 999999999)//1000000000
                        for row in frames], dtype=np.int64)
    if np.any(samples < 0) or np.any(np.diff(samples) < 0):
        raise ValueError('Nonmonotonic FIFO completion')
    # Both readout rows become available together. An earlier row cannot own a
    # positive-duration interval before the second row from that same call.
    keep = np.r_[samples[:-1] != samples[1:], True] & (samples < sample_count)
    indices = np.flatnonzero(keep)
    starts = samples[indices]
    ends = np.r_[starts[1:], sample_count].astype(np.int64)
    if not len(indices) or np.any(ends <= starts):
        raise ValueError('No valid causal decision intervals')
    return indices, starts, ends


def full_interval_targets(starts, ends, labels, sample_count):
    """Positive only when the entire held interval has an expected same pitch."""
    expected = union_spans([(int(r['start_sample']), int(r['end_sample']),
                             int(r['midi_note'])) for r in labels], sample_count=sample_count)
    target = np.zeros((len(starts), 88), dtype=bool)
    for left, right, note in expected:
        if 21 <= note <= 108:
            target[:, note-21] |= (starts >= left) & (ends <= right)
    return target


def passage_split(labels, sample_count, sample_rate=96000,
                  train_passages=79, calibration_end=105, purge_seconds=3):
    passages = sorted(set((r['start_sample'], r['end_sample']) for r in labels))
    if not 0 < train_passages < calibration_end < len(passages):
        raise ValueError('Insufficient complete passages for the frozen split')
    if any(a[1] > b[0] for a, b in zip(passages, passages[1:])):
        raise ValueError('This protocol requires separated synchronized passages')
    boundary = lambda index: (passages[index-1][1] + passages[index][0])//2
    train_end, calibration_stop = boundary(train_passages), boundary(calibration_end)
    def purged_start(index, stop):
        cut = boundary(index) + int(purge_seconds * sample_rate)
        eligible = [k for k in range(index, stop) if passages[k][0] >= cut]
        if not eligible:
            raise ValueError('Purge removes the whole held-out partition')
        first = eligible[0]
        return max(cut, boundary(first)), first
    calibration_start, calibration_first = purged_start(train_passages, calibration_end)
    test_start, test_first = purged_start(calibration_end, len(passages))
    regions = dict(train=(0, train_end), calibration=(calibration_start, calibration_stop),
                   test=(test_start, sample_count))
    ids = {name: [int(r['label_index']) for r in labels
                  if left <= r['start_sample'] and r['end_sample'] <= right]
           for name, (left, right) in regions.items()}
    return dict(regions=regions, label_indices=ids, passage_count=len(passages),
        assigned_passage_ranges=dict(train=[0, train_passages],
            calibration=[calibration_first, calibration_end], test=[test_first, len(passages)]),
        purge_seconds=purge_seconds,
        caveat='Whole passages, not independent source takes: source notes recur in mixtures. '
               'Exploratory feasibility only, even if held-out gates pass.')


def calibration_cutoff(probability, target, mask):
    negatives = probability[mask][~target[mask]]
    if not negatives.size or not np.isfinite(negatives).all():
        raise ValueError('Calibration needs finite negative examples')
    maximum = float(negatives.max())
    # One deterministic cutoff, never optimized on test results. At probability
    # 1 this becomes >1 and deliberately admits nothing.
    return float(np.nextafter(maximum, np.inf))


def occupancy_spans(probability, cutoff, starts, ends, sample_count):
    row, pitch = np.nonzero(probability >= cutoff)
    return union_spans([(int(starts[i]), int(ends[i]), int(p)+21)
                        for i, p in zip(row, pitch)], sample_count=sample_count)


def region_inputs(spans, labels, left, right):
    retained = [r for r in labels if r['start_sample'] < right and r['end_sample'] > left]
    if any(r['start_sample'] < left or r['end_sample'] > right for r in retained):
        raise ValueError('Split would cut a label')
    mapping = [int(r['label_index']) for r in retained]
    local_labels = [dict(r, label_index=i, start_sample=r['start_sample']-left,
                         end_sample=r['end_sample']-left) for i, r in enumerate(retained)]
    local_spans = [(max(a, left)-left, min(b, right)-left, p)
                   for a, b, p in spans if a < right and b > left]
    return local_spans, local_labels, mapping
