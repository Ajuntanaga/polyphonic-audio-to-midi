"""Measure detector note lifetimes separately from tuner-preview matches.

Intervals use the recording's sample clock and half-open annotation bounds.
No onset/release tolerance or live acceptance threshold is inferred here.
The detector trace precedes the plugin's MIDI delivery and channel mapping.
"""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import csv
from itertools import groupby
from pathlib import Path
from statistics import median

from tools.frozen_cue_corpus_gate import read_replay


EVENT_FIELDS = ('sample', 'kind', 'note', 'velocity', 'voice_id', 'sequence')
MAX_VOICES = 8
UNASSIGNED_VOICE = 255


CONFLICT_FIELDS = ('cross_pitch_on_before_release', 'repeated_pitch_on_before_release',
                   'off_without_raw_on', 'zero_velocity_on', 'unassigned_on')


def raw_conflicts(events):
    """Keep all raw outstanding pitches, including a displaced previous owner.

    Same-pitch repeats are counted, with an off paired to the oldest onset.
    EOF opens are reported separately and are not proof of stuck host MIDI.
    """
    active = defaultdict(list)
    counts = dict.fromkeys(CONFLICT_FIELDS, 0)
    examples = []
    for event in events:
        lane, note = event['voice_id'], event['note']
        key = (lane, note if lane == UNASSIGNED_VOICE else -1)
        held = active[key]
        matches = [i for i, previous in enumerate(held) if previous['note'] == note]
        if event['kind'] == 'on':
            conflict = any(previous['note'] != note for previous in held)
            counts['cross_pitch_on_before_release'] += conflict
            counts['repeated_pitch_on_before_release'] += bool(matches)
            counts['zero_velocity_on'] += event['velocity'] == 0
            counts['unassigned_on'] += lane == UNASSIGNED_VOICE
            if conflict and len(examples) < 12:
                examples.append(dict(event=event, unreleased_raw_note_ons=list(held)))
            held.append(event)
        elif matches:
            held.pop(matches[0])
        else:
            counts['off_without_raw_on'] += 1
    return dict(counts=counts, examples=examples,
        raw_note_ons_open_at_eof=[event for held in active.values() for event in held],
        interpretation='Complete raw detector event order, before the host ledger. '
            'Old pitches are never overwritten by conflicting onsets. EOF opens '
            'are not proof of stuck MIDI; host delivery and durations are not measured.')


def read_events(path, *, sample_count, transition_count):
    """Require the complete native event capture, including events outside labels."""
    events = []
    with Path(path).open(newline='') as stream:
        if stream.readline().rstrip('\r\n') != '# m3_midi_events_v1':
            raise ValueError('Unknown MIDI event trace schema')
        rows = csv.DictReader(stream, delimiter='\t')
        if rows.fieldnames != list(EVENT_FIELDS):
            raise ValueError('Malformed MIDI event trace header')
        for row in rows:
            if set(row) != set(EVENT_FIELDS) or any(value is None for value in row.values()):
                raise ValueError('Malformed MIDI event trace row')
            event = {'kind': row['kind']}
            for field in EVENT_FIELDS:
                if field != 'kind':
                    if not row[field].isascii() or not row[field].isdigit():
                        raise ValueError('Invalid MIDI event integer: ' + field)
                    event[field] = int(row[field])
            if (event['kind'] not in ('on', 'off')
                    or not 0 <= event['sample'] < sample_count
                    or event['note'] > 127 or event['velocity'] > 127
                    or event['voice_id'] not in (*range(MAX_VOICES), UNASSIGNED_VOICE)
                    or event['sequence'] > 0xffffffff
                    or (events and (event['sample'] < events[-1]['sample']
                                    or event['sequence'] <= events[-1]['sequence']))):
                raise ValueError('Invalid or reordered M3 MIDI event')
            events.append(event)
    if len(events) != transition_count:
        raise ValueError('MIDI event capture differs from replay transition count')
    return events


def summarize(events, labels, *, sample_count, sample_rate):
    """Reduce complete detector transitions, retaining EOF uncertainty explicitly."""
    if (type(sample_count) is not int or sample_count <= 0
            or type(sample_rate) is not int or sample_rate <= 0):
        raise ValueError('Invalid recording sample clock')
    for index, label in enumerate(labels):
        if (label['label_index'] != index
                or not 0 <= label['start_sample'] < label['end_sample'] <= sample_count
                or not 0 <= label['midi_note'] <= 127
                or not 0 <= label['string_mask'] <= 255):
            raise ValueError('Invalid M3 annotation interval')

    active, mask_starts, masks = {}, {}, {}
    spans, on_samples = defaultdict(list), defaultdict(list)
    durations, examples, errors = [], [], Counter()
    counts = Counter(event['kind'] for event in events)

    def anomaly(kind, event):
        errors[kind] += 1
        if len(examples) < 16:
            examples.append(dict(error=kind, **event))

    for sample, group in groupby(events, key=lambda event: event['sample']):
        affected = set()
        for event in group:
            lane, note = event['voice_id'], event['note']
            affected.add(note)
            # The ledger keys assigned identities by lane and unassigned ones by pitch.
            identity = (lane, note if lane == UNASSIGNED_VOICE else -1)
            prior = active.get(identity)
            if event['kind'] == 'on':
                on_samples[note].append(sample)
                if event['velocity'] == 0:
                    anomaly('zero_velocity_note_on', event)
                if prior is not None:
                    anomaly('note_on_before_lane_release', event)
                    affected.add(prior['note'])
                active[identity] = dict(note=note, start_sample=sample)
            elif prior is None or prior['note'] != note:
                anomaly('note_off_without_matching_note_on', event)
            else:
                durations.append(sample - prior['start_sample'])
                del active[identity]
        for note in affected:
            mask = sum(1 << identity[0] for identity, held in active.items()
                       if held['note'] == note and identity[0] != UNASSIGNED_VOICE)
            unassigned = (UNASSIGNED_VOICE, note) in active
            state = (mask, unassigned)
            previous = masks.get(note, (0, False))
            if state != previous:
                start = mask_starts.get(note, 0)
                if any(previous) and start < sample:
                    spans[note].append((start, sample, *previous))
                masks[note], mask_starts[note] = state, sample
    for note, state in masks.items():
        if any(state) and mask_starts[note] < sample_count:
            spans[note].append((mask_starts[note], sample_count, *state))

    rows = None
    if not errors:
        rows = []
        ends = {note: [span[1] for span in intervals] for note, intervals in spans.items()}
        for label in labels:
            start, end, note, expected = (label[key] for key in
                ('start_sample', 'end_sample', 'midi_note', 'string_mask'))
            matched = longest = segments = 0
            first = previous_end = None
            current_length = 0
            intervals = spans[note]
            for left, right, actual, unassigned in intervals[bisect_right(ends.get(note, []), start):]:
                if left >= end:
                    break
                if expected == 0 or (actual == expected and not unassigned):
                    overlap_start, overlap_end = max(left, start), min(right, end)
                    overlap = overlap_end - overlap_start
                    matched += overlap
                    if previous_end == overlap_start:
                        current_length += overlap
                    else:
                        current_length = overlap
                        segments += 1
                    longest = max(longest, current_length)
                    previous_end = overlap_end
                    if first is None:
                        first = overlap_start
            ons = on_samples[note]
            rows.append(dict(label_index=label['label_index'], midi_note=note,
                string_mask=expected, start_sample=start, end_sample=end,
                annotated_hold_samples=end - start, exact_held_samples=matched,
                unmatched_hold_samples=end - start - matched,
                longest_exact_hold_samples=longest, exact_hold_segments=segments,
                first_exact_hold_delay_samples=None if first is None else first - start,
                note_ons_inside_label=bisect_left(ons, end) - bisect_left(ons, start)))

    return dict(schema='m3_detector_midi_lifecycle_v1', sample_rate=sample_rate,
        sample_count=sample_count, transitions=len(events), note_ons=counts['on'],
        note_offs=counts['off'], event_error_counts=dict(errors), event_error_examples=examples,
        coverage_valid=not errors, balanced_at_recording_end=not errors and not active,
        open_at_recording_end=[dict(voice_id=identity[0], **held,
            observed_hold_samples=sample_count - held['start_sample'])
            for identity, held in sorted(active.items())],
        closed_note_duration_samples=None if errors or not durations else
            dict(minimum=min(durations), median=median(durations), maximum=max(durations)),
        labels=rows,
        annotated_hold_samples=sum(label['end_sample'] - label['start_sample'] for label in labels),
        exact_held_samples=None if rows is None else sum(row['exact_held_samples'] for row in rows),
        samples_after_last_label=sample_count - max((label['end_sample'] for label in labels), default=0),
        onset_release_tolerance='not measured', acceptance_target='not measured',
        host_delivery='not measured', physical_string_identity='not measured',
        interpretation='Raw annotated sample durations, not tuner labeled-frame matches. '
            'Overlapping labels count separately in duration totals. '
            'Exact holds require all expected routing lanes for the pitch simultaneously '
            'and no extra lane for that pitch; a zero label mask accepts any lane. '
            'Unassigned voices cannot establish an exact nonzero routing mask. '
            'Lane identity is not independent physical-string or delivered-channel proof. '
            'Pairing anomalies describe detector trace order, before host ledger sorting or repair. '
            'Open notes at EOF need recording-tail or host-release checks before calling them stuck. '
            'No silence, forced EOF release, onset grace or release tolerance is invented.')


def analyze_trace(event_path, replay_path, *, include_raw_conflicts=False):
    replay = read_replay(replay_path)
    with Path(replay_path).open(newline='') as stream:
        aggregate = next(csv.DictReader(stream, delimiter='\t'))
    values = {}
    for key in ('samples', 'sample_rate', 'transitions'):
        if not aggregate[key].isascii() or not aggregate[key].isdigit():
            raise ValueError('Invalid replay sample clock or transition count')
        values[key] = int(aggregate[key])
    events = read_events(event_path, sample_count=values['samples'],
                         transition_count=values['transitions'])
    result = summarize(events, replay['labels'], sample_count=values['samples'],
                       sample_rate=values['sample_rate'])
    if include_raw_conflicts:
        result['raw_midi'] = raw_conflicts(events)
    return result
