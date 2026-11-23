"""Observation-only attribution of the frozen repeated-attack controls.

No audio decoding or detector implementation lives here. Candidate state is
post-decision state; an unavailable observation is never evidence of zero onset.
"""
import gzip
import hashlib
import json
from pathlib import Path

from tools.candidate_outcome_analysis import HEADER, CANDIDATE_FIELDS_V4, _frame, _candidates
from tools.midi_lifecycle_analysis import EVENT_FIELDS, read_events
from tools.portable_stable_note_identity_ledger import read_tags


def read_tagged(path, normalized, *, samples, transitions):
    """Use the existing strict event/tag readers after a lossless v1 projection."""
    with Path(path).open() as source, Path(normalized).open('x') as target:
        if source.readline() != '# m3_midi_events_v2\n':
            raise ValueError('Expected tagged v2 events')
        if source.readline() != '\t'.join((*EVENT_FIELDS, 'continuation_voice_id')) + '\n':
            raise ValueError('Expected complete tagged header')
        target.write('# m3_midi_events_v1\n' + '\t'.join(EVENT_FIELDS) + '\n')
        for line in source:
            fields = line.rstrip('\n').split('\t')
            if len(fields) != 7:
                raise ValueError('Incomplete tagged event')
            target.write('\t'.join(fields[:6]) + '\n')
    events = read_events(normalized, sample_count=samples, transition_count=transitions)
    tags, normalized_sha = read_tags(Path(path), events)
    if hashlib.sha256(Path(normalized).read_bytes()).hexdigest() != normalized_sha:
        raise ValueError('Tag projection changed event bytes')
    return events, tags, normalized_sha


def require_callback_identity(source, vst3, *, stable):
    """Compare physical core lanes or stable host channels, never ledger slots."""
    if len(source) != len(vst3):
        raise ValueError('Callback count changed')
    for expected, actual in zip(source, vst3):
        channel = expected['channel'] - 1 if stable else expected['voice_id']
        if (any(expected[key] != actual[key] for key in ('sample', 'kind', 'note'))
                or channel != actual['channel']
                or abs(expected['velocity'] / 127.0 - actual['velocity']) > 1e-7):
            raise ValueError('Callback payload or channel changed')


def require_ledger_integrity(native, callbacks, pairs):
    faults = ('queue_rejected_events', 'unqueued_after_failure', 'cleanup_callbacks',
              'blocked_blocks', 'detection_disabled_blocks', 'callback_pairing_errors')
    if (any(native[key] != 0 for key in faults) or native['output_blocked_at_eof']
            or native['cleanup_pending_at_eof']):
        raise ValueError('Ledger fault')
    if (native['source_callbacks'] != len(callbacks) or native['transferred_pairs'] != pairs
            or native['suppressed_source_events'] != 2 * pairs):
        raise ValueError('Ledger provenance accounting changed')


def read_target(path, *, samples, note):
    points = []
    with Path(path).open() as stream:
        if stream.readline() != '# m3_candidate_outcome_v4\n' or stream.readline() != HEADER:
            raise ValueError('Expected full v4 outcome trace')
        for index, line in enumerate(stream):
            frame = _frame(line)
            if (frame['sample'] != 63 + 64 * index
                    or (points and frame['tick'] != points[-1]['tick'] + 1)):
                raise ValueError('Decision grid incomplete or reordered')
            for value in frame['candidate_text'].split(',') if frame['candidate_text'] else ():
                if len(value.split(':')) != len(CANDIDATE_FIELDS_V4):
                    raise ValueError('Candidate tuple is not v4')
            candidate = _candidates(frame).get(note)
            points.append(dict(sample=frame['sample'], tick=frame['tick'],
                quiet=frame['quiet'], signal_samples=frame['signal_samples'],
                candidate=candidate, target_voices=[list(v) for v in frame['voices'] if v[1] == note]))
    if len(points) != samples // 64:
        raise ValueError('Decision trace did not cover the complete fixture')
    return points


def window(points, left, right):
    """Inclusive bounds, on the verified regular decision grid."""
    begin = max(0, (left - 63 + 63) // 64)
    end = min(len(points), (right - 63) // 64 + 1)
    return points[begin:max(begin, end)]


def onset_summary(points):
    observed = [p for p in points if p['candidate'] is not None
                and p['candidate']['onset_observed'] == 1]
    positive = [p for p in observed if p['candidate']['onset'] > 0]
    return dict(decisions=len(points), candidate_missing=sum(p['candidate'] is None for p in points),
        onset_observed=len(observed), onset_unavailable=len(points) - len(observed),
        positive_onset_decisions=len(positive),
        maximum_onset=max((p['candidate']['onset'] for p in observed), default=None),
        first_positive_sample=positive[0]['sample'] if positive else None,
        last_positive_sample=positive[-1]['sample'] if positive else None,
        active_selected_decisions=sum(p['candidate'] is not None and p['candidate']['active'] == 1
                                     and p['candidate']['selection'] == 4 for p in points))


def event_attribution(points, control, event, tags, delivered, *, marker, sample_rate):
    sample = event['sample']
    index = (sample - 63) // 64
    if index < 0 or index >= len(points) or points[index]['sample'] != sample:
        raise ValueError('MIDI event is not on a captured decision')
    point = points[index]
    prior = window(points, marker, sample - 1)
    positive = [p for p in prior if p['candidate'] is not None
                and p['candidate']['onset_observed'] == 1 and p['candidate']['onset'] > 0]
    last_positive = positive[-1]['sample'] if positive else None
    continuous = (all(p['candidate'] is not None and p['candidate']['active'] == 1
                      and p['candidate']['selection'] == 4
                      for p in window(points, last_positive, sample))
                  if last_positive is not None else None)
    suppressed = event['sequence'] not in delivered
    c = point['candidate']
    instantaneous_pattern = bool(suppressed and last_positive is not None and continuous
        and c is not None and c['onset_observed'] == 1 and c['onset'] == 0)
    before, after = round(.100 * sample_rate), round(.025 * sample_rate)
    return dict(event=event, continuation_voice_id=tags[event['sequence']],
        suppressed=suppressed, delay_from_marker_ms=(sample-marker)*1000/sample_rate,
        post_decision=point, single_control_at_same_sample=control[index],
        prior_100ms=onset_summary(window(points, sample-before, sample-1)),
        since_insertion=onset_summary(prior),
        following_25ms=onset_summary(window(points, sample+1, sample+after)),
        single_control_since_insertion=onset_summary(window(control, marker, sample-1)),
        continuously_active_selected_since_last_positive=continuous,
        instantaneous_onset_memory_pattern=instantaneous_pattern,
        neighborhood=points[max(0, index-16):index+17])


def attribute_fixture(points, control, events, tags, callbacks, added_on_samples,
                      *, marker, note, sample_rate):
    delivered = {event['source_sequence'] for event in callbacks}
    rows = []
    for sample in added_on_samples:
        targets = [event for event in events if event['kind'] == 'on'
                   and event['note'] == note and event['sample'] == sample]
        if not targets:
            raise ValueError('Saved added response is absent from the core trace')
        rows.extend(event_attribution(points, control, event, tags, delivered,
            marker=marker, sample_rate=sample_rate) for event in targets)
    return dict(note=note, marker=marker, added_response_samples=added_on_samples,
        events=rows, suppressed_responses=sum(row['suppressed'] for row in rows),
        instantaneous_onset_memory_pattern_samples=[row['event']['sample'] for row in rows
                                                   if row['instantaneous_onset_memory_pattern']],
        interpretation='Constructed control only; instantaneous pattern is a diagnosis, '
            'not a safe policy or evidence of acoustic re-pluck preservation.')


def write_target(path, points):
    with gzip.open(path, 'wt') as stream:
        for point in points:
            stream.write(json.dumps(point, sort_keys=True, allow_nan=False) + '\n')
