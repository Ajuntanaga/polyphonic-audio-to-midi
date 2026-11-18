"""Pitch-level comparison for paired component callbacks; not string accuracy.

Exact pitch multiplicity preserves simultaneous unisons as well as silence.
Fewer attacks alone cannot prove that acoustic re-plucks were preserved.
"""
from tools.portable_stable_note_identity_ledger import (
    sink_spans, pitch_timeline, label_metrics, pitch_safety)


def compare_component_pitch(before, after, labels, samples):
    if type(samples) is not int or samples <= 0 or not labels:
        raise ValueError('A positive recording clock and nonempty labels are required')
    identities = set()
    for label in labels:
        identity = label['label_index']
        if identity in identities or not 0 <= label['start_sample'] < label['end_sample'] <= samples:
            raise ValueError('Duplicate label identity or invalid label bounds')
        identities.add(identity)
    results = []
    timelines = []
    for events in (before, after):
        previous = -1
        for event in events:
            if type(event['sample']) is not int or not 0 <= event['sample'] <= samples or event['sample'] < previous:
                raise ValueError('Unordered callback or callback outside recording')
            previous = event['sample']
        spans, open_notes = sink_spans(events, samples)
        timeline = pitch_timeline(spans, samples)
        timelines.append(timeline)
        results.append(dict(labels=label_metrics(spans, events, labels),
            safety=pitch_safety(timeline, events, labels), open_notes_at_eof=open_notes))
    left, right = results
    changes = []
    for a, b in zip(left['labels'], right['labels']):
        changes.append(dict(label_index=a['label_index'],
            pitch_present_delta=b['pitch_present_samples'] - a['pitch_present_samples'],
            longest_hold_delta=b['longest_sink_hold_samples'] - a['longest_sink_hold_samples'],
            note_on_delta=b['note_ons_inside_label'] - a['note_ons_inside_label']))
    gates = dict(pitch_multiplicity_identical=timelines[0] == timelines[1],
        eof_open_notes_identical=left['open_notes_at_eof'] == right['open_notes_at_eof'],
        no_label_pitch_loss=all(row['pitch_present_delta'] >= 0 for row in changes),
        no_shorter_label_holds=all(row['longest_hold_delta'] >= 0 for row in changes),
        no_label_attack_growth=all(row['note_on_delta'] <= 0 for row in changes),
        no_false_output_growth=all(right['safety'][key] <= value
            for key, value in left['safety'].items()))
    return dict(before=left, after=right, label_changes=changes, gates=gates,
        gate_pass=all(gates.values()), acoustic_repluck_preservation='not measured',
        physical_string_assignment='not measured', promotion_accepted=False)
