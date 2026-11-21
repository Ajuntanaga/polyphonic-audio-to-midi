"""Fixed clock/decoder bridge for cached Basic Pitch outputs, not a tracker.

Nominal model coordinates are diagnostic axes, not causal delivery timestamps or
measured acoustic onset times. Historical scores keep their original clocks.
"""
from bisect import bisect_left, bisect_right
import math

from tools.basic_pitch_streaming import ForwardDecoder
from tools.pitch_detector_comparison import compare


ARMS = {
    'A': 'Saved rolling events on measured FIFO completion clock',
    'B': 'Same rolling events on input-block availability clock',
    'C': 'Unchanged forward decoder on rolling cache, stream nominal grid',
    'D': 'Unchanged forward decoder on offline cache, offline window nominal grid',
    'E': 'Saved upstream notes on offline window nominal grid',
    'F': 'Saved upstream notes on original recorded timestamp convention',
}
BRIDGES = (
    ('A', 'B', 'worker_completion_and_queue'),
    ('B', 'C', 'availability_context_clock'),
    ('C', 'D', 'activation_pipeline_bundle'),
    ('D', 'E', 'decoder_bundle'),
    ('E', 'F', 'timestamp_convention'),
)


def nominal_model_sample(frame, clock):
    if type(frame) is not int or frame < 0:
        raise ValueError('Frame must be a nonnegative integer')
    if clock == 'stream':
        return frame * 256
    if clock == 'offline_window':
        # 43844 input samples, 30 overlapping frames, 15 trimmed per side.
        # The original input has 3840 leading zeros; these cancel the trim.
        return (frame // 142) * 36164 + (frame % 142) * 256
    raise ValueError('Unknown nominal clock')


def nominal_source_sample(frame, clock, sample_rate=96000):
    value = nominal_model_sample(frame, clock) * sample_rate
    return (2 * value + 22050) // (2 * 22050)


def upstream_frame_times(frame_count):
    """Pinned fa5997a model_frames_to_time; no fitted alignment correction."""
    if type(frame_count) is not int or frame_count <= 0:
        raise ValueError('Positive frame count required')
    offset = (256 / 22050) * (172 - 43844 / 256) + .0018
    return [(frame * 256) / 22050 - offset * (frame // 172)
            for frame in range(frame_count)]


def unique_time_index(seconds, times, tolerance=1e-9):
    if not math.isfinite(float(seconds)):
        raise ValueError('Nonfinite endpoint')
    left = bisect_left(times, seconds - tolerance)
    right = bisect_right(times, seconds + tolerance)
    if right - left != 1:
        raise ValueError('Endpoint must match exactly one upstream frame')
    return left


def offline_note_frames(notes, frame_count):
    times = upstream_frame_times(frame_count)
    indexed, max_error = [], 0.
    for row in notes:
        start, end, pitch, amplitude = row[:4]
        if (not all(math.isfinite(float(v)) for v in (start, end, pitch, amplitude))
                or not start < end or int(pitch) != pitch or not 0 <= pitch <= 127):
            raise ValueError('Invalid saved upstream note')
        left, right = (unique_time_index(t, times) for t in (start, end))
        if not left < right:
            raise ValueError('Inverted note endpoints are not ordered')
        max_error = max(max_error, abs(times[left] - start), abs(times[right] - end))
        indexed.append((left, right, int(pitch)))
    return indexed, dict(notes=len(notes), endpoints=2*len(notes),
                         tolerance_seconds=1e-9, maximum_error_seconds=max_error,
                         unique_exact_frame_matches=True)


def decode_cached(notes, onsets):
    if len(notes) != len(onsets) or not len(notes):
        raise ValueError('Incomplete activation cache')
    decoder, events = ForwardDecoder(), []
    for frame, (note, onset) in enumerate(zip(notes, onsets)):
        events.extend(decoder.consume(note, onset, frame))
    return events, [i + 21 for i, active in enumerate(decoder.active) if active]


def frame_event_spans(events, clock, sample_count, sample_rate=96000):
    """Diagnostic frame coordinates only; never passed to emission_spans."""
    active, spans, previous = {}, [], -1
    for event in events:
        frame, note, kind = event['frame'], event['note'], event['kind']
        if (type(frame) is not int or frame < previous or type(note) is not int
                or not 0 <= note <= 127):
            raise ValueError('Invalid or unordered frame event')
        previous = frame
        sample = min(sample_count, nominal_source_sample(frame, clock, sample_rate))
        if kind == 'on' and note not in active:
            active[note] = sample
        elif kind == 'off' and note in active:
            start = active.pop(note)
            if start < sample:
                spans.append((start, sample, note))
        else:
            raise ValueError('Invalid frame-event pairing')
    for note, start in active.items():
        if start < sample_count:
            spans.append((start, sample_count, note))
    return spans, dict(pairing_valid=True, event_count=len(events),
                      decoder_open_pitches=sorted(active),
                      eof_policy='Open occupancy clipped at common horizon')


def indexed_note_spans(notes, clock, sample_count, sample_rate=96000):
    result = []
    for left, right, note in notes:
        left, right = (min(sample_count, nominal_source_sample(f, clock, sample_rate))
                       for f in (left, right))
        if left < right:
            result.append((left, right, note))
    return result


def labels_from_measurement(measurement):
    return [dict(label_index=r['label_index'], midi_note=r['midi_note'], string_mask=0,
                 start_sample=r['start_sample'], end_sample=r['end_sample'])
            for r in measurement['labels']]


def common_horizon(sample_count, stream_frames, offline_frames, sample_rate=96000):
    if min(sample_count, stream_frames, offline_frames, sample_rate) <= 0:
        raise ValueError('Positive clocks and cache lengths required')
    return min(sample_count,
               nominal_source_sample(stream_frames, 'stream', sample_rate),
               nominal_source_sample(offline_frames, 'offline_window', sample_rate))


def clip_labels(labels, horizon):
    result, mapping, removed = [], [], 0
    for row in labels:
        left, right = row['start_sample'], min(row['end_sample'], horizon)
        kept = max(0, right - left)
        removed += row['end_sample'] - row['start_sample'] - kept
        if kept:
            mapping.append(row['label_index'])
            result.append(dict(row, label_index=len(result), end_sample=right))
    return result, dict(original_label_indices=mapping,
                       removed_label_samples=removed,
                       wholly_outside_labels=len(labels)-len(result))


def clip_spans(spans, horizon):
    return [(int(left), min(int(right), horizon), int(note)) for left, right, note in spans
            if left < horizon and left < right]


def bridge_comparisons(measurements):
    result = {}
    for before, after, name in BRIDGES:
        result[name] = dict(before=before, after=after,
                           comparison=compare(measurements[before], measurements[after]))
    # The signed path must telescope; no percentage of a causal loss is implied.
    direct = compare(measurements['A'], measurements['F'])
    for key, delta in direct['sample_deltas'].items():
        if sum(r['comparison']['sample_deltas'][key] for r in result.values()) != delta:
            raise ValueError('Bridge path did not reconcile')
    if sum(r['comparison']['extra_gap_pitch_samples_delta'] for r in result.values()) != direct['extra_gap_pitch_samples_delta']:
        raise ValueError('Gap bridge path did not reconcile')
    return result


def compact_measurement(measurement):
    pitch = measurement['pitch_sets']
    totals = pitch['totals']
    return dict(**totals, extra_gap_pitch_samples=pitch['unlabeled_gap_voice_samples'],
        pitch_coverage_percent=100*totals['present_pitch_samples']/totals['expected_pitch_samples'],
        exact_pitch_set_percent=100*totals['exact_pitch_set_samples']/totals['annotated_samples'])
