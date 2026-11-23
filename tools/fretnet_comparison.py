"""Fixed FretNet pitch-occupancy adapter; no trained model or audio I/O.

The six standard-guitar positions are a pitch decoder, not this instrument's
string assignments. All annotations, including pitches outside 40..83, remain
in the scoring denominator. The clock is offline and nominal.
"""
import math

from tools.pitch_detector_comparison import compare, score, union_spans


OPEN_NOTES = (40, 45, 50, 55, 59, 64)
SAMPLE_RATE = 22050
HOP = 512


def frame_windows(hcqt):
    import numpy as np
    value = np.asarray(hcqt)
    if (value.ndim != 3 or value.shape[:2] != (6, 144)
            or value.shape[2] < 1 or not np.isfinite(value).all()):
        raise ValueError('Expected finite HCQT [6,144,T]')
    padded = np.pad(value, ((0, 0), (0, 0), (4, 4)), mode='constant')
    windows = np.lib.stride_tricks.sliding_window_view(padded, 9, axis=2)
    return np.ascontiguousarray(windows.transpose(2, 0, 1, 3)[None], dtype=np.float32)


def decode_tablature(logits, sigmoid):
    """Author order: float32 sigmoid, then argmax; saturation ties are retained."""
    import numpy as np
    value = np.asarray(logits)
    if (value.ndim != 3 or value.shape[0] != 1 or value.shape[2] != 126
            or value.shape[1] < 1 or value.dtype != np.float32
            or not np.isfinite(value).all()):
        raise ValueError('Expected finite float32 tablature logits [1,T,126]')
    probabilities = np.asarray(sigmoid(value))
    if (probabilities.shape != value.shape or not np.isfinite(probabilities).all()
            or probabilities.min() < 0 or probabilities.max() > 1):
        raise ValueError('Invalid sigmoid output')
    # Export profile: six groups, each with silence first and frets 0..19.
    return (probabilities.reshape(value.shape[1], 6, 21).argmax(axis=2) - 1).T


def tablature_spans(frets, *, sample_count, sample_rate):
    """Occupancy of frame i is [i*hop/sr,(i+1)*hop/sr), clipped at EOF."""
    import numpy as np
    frets = np.asarray(frets)
    if (frets.ndim != 2 or frets.shape[0] != 6 or frets.shape[1] < 1
            or not np.issubdtype(frets.dtype, np.integer)
            or frets.min() < -1 or frets.max() > 19
            or type(sample_count) is not int or sample_count <= 0
            or type(sample_rate) is not int or sample_rate <= 0):
        raise ValueError('Invalid semantic tablature or recording clock')
    frames = frets.shape[1]
    edges = [min(sample_count, (2 * i * HOP * sample_rate + SAMPLE_RATE)
                  // (2 * SAMPLE_RATE)) for i in range(frames + 1)]
    if edges[-1] < sample_count:
        raise ValueError('Model frame horizon does not cover the recording')
    active, spans = {}, []
    for i in range(frames):
        pitches = {OPEN_NOTES[s] + int(frets[s, i]) for s in range(6) if frets[s, i] >= 0}
        for note in sorted(set(active) - pitches):
            start = active.pop(note)
            if start < edges[i]:
                spans.append((start, edges[i], note))
        for note in sorted(pitches - set(active)):
            active[note] = edges[i]
    spans.extend((left, sample_count, note) for note, left in active.items() if left < sample_count)
    return union_spans(spans, sample_count=sample_count)


def label_budget(comparison, sample_rate):
    failures = []
    for row in comparison['label_deltas']:
        reasons = []
        for key in ('present', 'longest_present'):
            old = row['current_' + key + '_samples']
            new = row['model_' + key + '_samples']
            loss = max(0, old - new)
            # Integer arithmetic: BOTH 25 ms and 5% limits must hold.
            if loss * 1000 > 25 * sample_rate or loss * 100 > 5 * old:
                reasons.append(key)
        if row['current_present_samples'] > 0 and row['model_present_samples'] == 0:
            reasons.append('newly_entirely_missed')
        if reasons:
            failures.append(dict(label_index=row['label_index'], midi_note=row['midi_note'],
                                 reasons=reasons))
    delta = comparison['sample_deltas']
    aggregate_safe = (delta['extra_pitch_voice_samples'] <= 0
        and comparison['extra_gap_pitch_samples_delta'] <= 0
        and delta['all_expected_pitches_samples'] >= 0
        and delta['exact_pitch_set_samples'] >= 0)
    return dict(per_label_ms=25, per_label_percent=5, failures=failures,
        failed_labels=len(failures), aggregate_safe=aggregate_safe,
        budget_screen_pass=aggregate_safe and not failures,
        strict_screen_pass=comparison['no_pitch_safety_regression'], promotion_accepted=False)


def evaluate(spans, labels, baseline, *, sample_count, sample_rate):
    clock = dict(sample_count=sample_count, sample_rate=sample_rate)
    # Reproduce the saved reference before using it as a comparator.
    reference = score(baseline['pitch_spans'], labels, **clock)
    if reference != baseline['measurement']:
        raise ValueError('Saved CURRENT measurement does not reproduce')
    arms = {
        'fretnet': spans,
        'union': baseline['pitch_spans'] + spans,
        'pitch_split_60': ([s for s in baseline['pitch_spans'] if s[2] < 60]
                           + [s for s in spans if s[2] >= 60]),
    }
    results = {}
    for name, arm in arms.items():
        measured = score(arm, labels, **clock)
        comparison = compare(reference, measured)
        results[name] = dict(measurement=measured, comparison=comparison,
            label_budget=label_budget(comparison, sample_rate), report_only=name != 'fretnet')
    outside = [r for r in labels if not 40 <= r['midi_note'] <= 83]
    return dict(arms=results, baseline_reproduced=True,
        unsupported_range=dict(model_low=40, model_high=83, labels=len(outside),
            annotated_label_samples=sum(r['end_sample'] - r['start_sample'] for r in outside),
            label_indices=[r['label_index'] for r in outside], kept_in_all_denominators=True))


def research_screen(datasets):
    if set(datasets) != {'ordinary', 'extended-middle'}:
        raise ValueError('Both protected recordings are required')
    results = {}
    for arm in ('fretnet', 'union', 'pitch_split_60'):
        gain = datasets['ordinary']['arms'][arm]['comparison']['pitch_coverage_gain_pp']
        useful = gain is not None and math.isfinite(gain) and gain >= 5.0
        rows = [d['arms'][arm] for d in datasets.values()]
        results[arm] = dict(useful_gain=useful, ordinary_gain_pp=gain,
            strict_pass=useful and all(r['label_budget']['strict_screen_pass'] for r in rows),
            budget_pass=useful and all(r['label_budget']['budget_screen_pass'] for r in rows),
            report_only=arm != 'fretnet', promotion_accepted=False)
    return dict(arms=results, promotion_accepted=False,
        interpretation='Offline pitch occupancy; no measured string, unison, re-pluck, '
            'causal latency, native deadline, host or live-guitar acceptance. '
            'Diagnostic unions/split are not deployable fusion policies.')
