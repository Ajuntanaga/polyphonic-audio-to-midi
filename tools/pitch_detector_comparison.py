"""Pitch-only comparison of saved note intervals on the recording sample clock.

Both detectors are reduced to one occupancy interval per pitch. This deliberately
does not compare lanes, unison multiplicity, raw retriggers or host delivery.
The existing MIDI lifecycle scorer supplies the annotation and gap arithmetic.
"""
from collections import defaultdict
import csv
import hashlib
import math
from pathlib import Path

from tools.midi_lifecycle_analysis import summarize


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read_labels(path):
    with Path(path).open(newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    return [dict(label_index=i, **{key: int(row[key]) for key in
            ('start_sample', 'end_sample', 'midi_note', 'string_mask')})
            for i, row in enumerate(rows)]


def native_spans(events, *, sample_count, sample_rate):
    """Validate original pairing before forming a pitch union; retain EOF opens."""
    checked = summarize(events, [], sample_count=sample_count, sample_rate=sample_rate)
    if not checked['coverage_valid']:
        raise ValueError('Saved MIDI pairing is invalid')
    active, spans = {}, []
    for event in events:
        lane, note = event['voice_id'], event['note']
        key = (lane, note if lane == 255 else -1)
        if event['kind'] == 'on':
            active[key] = event
        else:
            start = active.pop(key)
            if start['sample'] < event['sample']:
                spans.append((start['sample'], event['sample'], note))
    for event in active.values():
        if event['sample'] < sample_count:
            spans.append((event['sample'], sample_count, event['note']))
    return spans, dict(raw_transitions=len(events), raw_note_ons=checked['note_ons'],
        open_at_recording_end=checked['open_at_recording_end'], pairing_valid=True,
        eof_policy='Occupancy observed through EOF; no physical release is inferred.')


def model_spans(notes, *, sample_count, sample_rate):
    """Round upstream seconds to nearest native sample, then clip to recording.

    No fitted timing shift, output pitch restriction, grace period or note removal.
    Notes wholly outside the recording and sub-sample spans remain counted below.
    """
    spans = []
    audit = dict(raw_note_events=len(notes), clipped_notes=0,
                 empty_after_rounding_or_clipping=0)
    for row in notes:
        start, end, pitch, amplitude = row[:4]
        if (not all(math.isfinite(float(v)) for v in (start, end, pitch, amplitude))
                or not start < end or int(pitch) != pitch or not 0 <= pitch <= 127):
            raise ValueError('Invalid external note event')
        left, right = (math.floor(float(t) * sample_rate + .5) for t in (start, end))
        clipped = max(0, min(sample_count, left)), max(0, min(sample_count, right))
        audit['clipped_notes'] += clipped != (left, right)
        if clipped[0] == clipped[1]:
            audit['empty_after_rounding_or_clipping'] += 1
        else:
            spans.append((*clipped, int(pitch)))
    return spans, audit


def union_spans(spans, *, sample_count):
    """Merge touching/overlapping same-pitch spans for BOTH compared detectors."""
    by_note = defaultdict(list)
    for left, right, note in spans:
        if (any(type(v) is not int for v in (left, right, note))
                or not 0 <= left < right <= sample_count or not 0 <= note <= 127):
            raise ValueError('Invalid sample-clock note span')
        by_note[note].append((left, right))
    result = []
    for note, intervals in sorted(by_note.items()):
        merged = []
        for left, right in sorted(intervals):
            if merged and left <= merged[-1][1]:
                merged[-1][1] = max(right, merged[-1][1])
            else:
                merged.append([left, right])
        for left, right in merged:
            result.append((left, right, note))
    return result


def union_events(spans, *, sample_count):
    edges = []
    for left, right, note in union_spans(spans, sample_count=sample_count):
        edges.extend(((left, 'on', note), (right, 'off', note)))
    # These events are an occupancy adapter, not a native MIDI trace. An end at
    # sample_count closes the scoring window, not a synthetic host NoteOff.
    return [dict(sample=s, kind=k, note=n, velocity=100 if k == 'on' else 0,
                 voice_id=255, sequence=i)
            for i, (s, k, n) in enumerate(sorted(edges, key=lambda e: (e[0], e[1] != 'off', e[2])))]


def score(spans, labels, *, sample_count, sample_rate):
    events = union_events(spans, sample_count=sample_count)
    pitch_labels = [dict(row, string_mask=0) for row in labels]
    measured = summarize(events, pitch_labels, sample_count=sample_count,
                         sample_rate=sample_rate, include_pitch_set_coverage=True)
    if not measured['coverage_valid']:
        raise ValueError('Pitch union adapter produced invalid pairing')
    pitch = measured['pitch_set_coverage']
    metrics = []
    for row in measured['labels']:
        metrics.append(dict(label_index=row['label_index'], midi_note=row['midi_note'],
            start_sample=row['start_sample'], end_sample=row['end_sample'],
            annotated_samples=row['annotated_hold_samples'],
            present_samples=row['exact_held_samples'],
            longest_present_samples=row['longest_exact_hold_samples'],
            present_segments=row['exact_hold_segments'],
            first_present_delay_samples=row['first_exact_hold_delay_samples']))
    return dict(schema='m3_external_pitch_comparison_v1', sample_count=sample_count,
        sample_rate=sample_rate, pitch_sets=pitch, labels=metrics,
        interpretation='Distinct pitch occupancy, independent of lanes; same-pitch '
            'overlaps and touching spans merged for both detectors. Per-label durations '
            'may overlap; pitch_sets deduplicates simultaneous same-pitch annotations. '
            'No onset/release grace or fitted timing offset. Gap outputs are extra '
            'notes, not missing notes. No raw retrigger, unison-multiplicity, string, '
            'snapshot-frame, real-time latency or host-delivery result.')


def compare(reference, candidate):
    if any(reference[k] != candidate[k] for k in ('schema', 'sample_count', 'sample_rate')):
        raise ValueError('Comparison sample clock or schema mismatch')
    identity = ('label_index', 'midi_note', 'start_sample', 'end_sample', 'annotated_samples')
    if (len(reference['labels']) != len(candidate['labels']) or any(
            any(a[k] != b[k] for k in identity)
            for a, b in zip(reference['labels'], candidate['labels']))):
        raise ValueError('Comparison annotations differ')
    before, after = reference['pitch_sets'], candidate['pitch_sets']
    totals = before['totals'], after['totals']
    if any(totals[0][k] != totals[1][k] for k in ('annotated_samples', 'expected_pitch_samples')):
        raise ValueError('Comparison denominators differ')
    expected = totals[0]['expected_pitch_samples']
    unique = totals[0]['annotated_samples']
    percent = lambda value, denominator: 100 * value / denominator if denominator else None
    deltas = {k: totals[1][k] - totals[0][k] for k in totals[0]}
    label_deltas = [dict(label_index=a['label_index'], midi_note=a['midi_note'],
                    start_sample=a['start_sample'], end_sample=a['end_sample'],
                    annotated_samples=a['annotated_samples'],
                    current_present_samples=a['present_samples'], model_present_samples=b['present_samples'],
                    current_longest_present_samples=a['longest_present_samples'],
                    model_longest_present_samples=b['longest_present_samples'],
                    present_samples_delta=b['present_samples']-a['present_samples'],
                    longest_present_samples_delta=b['longest_present_samples']-a['longest_present_samples'])
               for a, b in zip(reference['labels'], candidate['labels'])]
    changed = [row for row in label_deltas
               if row['present_samples_delta'] or row['longest_present_samples_delta']]
    gap_delta = after['unlabeled_gap_voice_samples'] - before['unlabeled_gap_voice_samples']
    bands = {}
    for name, low, high in (('below48',0,47), ('48to59',48,59), ('60to71',60,71), ('72plus',72,127)):
        pairs = [(a,b) for a,b in zip(reference['labels'],candidate['labels']) if low <= a['midi_note'] <= high]
        bands[name] = dict(annotated_label_samples=sum(a['annotated_samples'] for a,b in pairs),
            current_present_label_samples=sum(a['present_samples'] for a,b in pairs),
            model_present_label_samples=sum(b['present_samples'] for a,b in pairs),
            lost_labels=sum(b['present_samples'] < a['present_samples'] for a,b in pairs))
    return dict(current_pitch_coverage_percent=percent(totals[0]['present_pitch_samples'],expected),
        model_pitch_coverage_percent=percent(totals[1]['present_pitch_samples'],expected),
        pitch_coverage_gain_pp=percent(deltas['present_pitch_samples'],expected),
        current_exact_pitch_set_percent=percent(totals[0]['exact_pitch_set_samples'],unique),
        model_exact_pitch_set_percent=percent(totals[1]['exact_pitch_set_samples'],unique),
        sample_deltas=deltas, extra_gap_pitch_samples_delta=gap_delta,
        label_deltas=label_deltas, label_changes=changed, label_bands=bands,
        no_pitch_safety_regression=(deltas['extra_pitch_voice_samples'] <= 0 and gap_delta <= 0
            and deltas['exact_pitch_set_samples'] >= 0 and deltas['all_expected_pitches_samples'] >= 0
            and all(min(r['present_samples_delta'], r['longest_present_samples_delta']) >= 0 for r in changed)),
        promotion_accepted=False)
