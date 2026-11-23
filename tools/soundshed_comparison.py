"""Causal Soundshed event adapter and fixed pitch-range comparison. No audio I/O."""
import csv
import math

from tools.fretnet_comparison import label_budget
from tools.pitch_detector_comparison import compare, native_spans, score


ARMS = ('range_preserving', 'soundshed', 'union', 'pitch_split_60')


def read_events(path, *, sample_count, sample_rate):
    """Keep detector callback offsets exactly; fail on invalid order or pairing."""
    events = []
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if reader.fieldnames != ['sample', 'kind', 'note', 'velocity', 'sequence']:
            raise ValueError('Unexpected causal event columns')
        for row in reader:
            sample, note, sequence = (int(row[k]) for k in ('sample', 'note', 'sequence'))
            velocity = float(row['velocity'])
            if (not 0 <= sample < sample_count or not 35 <= note <= 88
                    or sequence != len(events) or row['kind'] not in ('on', 'off')
                    or not math.isfinite(velocity) or not 0 <= velocity <= 1
                    or events and sample < events[-1]['sample']):
                raise ValueError('Invalid causal event')
            events.append(dict(sample=sample, kind=row['kind'], note=note,
                velocity=max(1, min(127, round(127 * velocity))) if row['kind'] == 'on' else 0,
                voice_id=255, sequence=sequence))
    spans, audit = native_spans(events, sample_count=sample_count, sample_rate=sample_rate)
    audit.update(clock='Input block start + detector sampleOffset; no shift or lookahead correction.',
                 source_event_count=len(events), string_assignment='not measured')
    return spans, audit


def evaluate(spans, labels, baseline, *, sample_count, sample_rate):
    clock = dict(sample_count=sample_count, sample_rate=sample_rate)
    reference = score(baseline['pitch_spans'], labels, **clock)
    if reference != baseline['measurement']:
        raise ValueError('Saved CURRENT measurement does not reproduce')
    current = baseline['pitch_spans']
    arms = {
        # Frozen model support, not a pitch boundary chosen from performance.
        'range_preserving': [s for s in current if not 35 <= s[2] <= 88] + spans,
        'soundshed': spans,
        'union': current + spans,
        'pitch_split_60': [s for s in current if s[2] < 60] + [s for s in spans if s[2] >= 60],
    }
    results = {}
    for name, arm in arms.items():
        measured = score(arm, labels, **clock)
        comparison = compare(reference, measured)
        results[name] = dict(measurement=measured, comparison=comparison,
            label_budget=label_budget(comparison, sample_rate), report_only=name != 'range_preserving')
    outside = [r for r in labels if not 35 <= r['midi_note'] <= 88]
    return dict(arms=results, baseline_reproduced=True,
        unsupported_range=dict(model_low=35, model_high=88, labels=len(outside),
            annotated_label_samples=sum(r['end_sample'] - r['start_sample'] for r in outside),
            label_indices=[r['label_index'] for r in outside], kept_in_all_denominators=True))


def research_screen(datasets):
    if set(datasets) != {'ordinary', 'extended-middle'}:
        raise ValueError('Both protected recordings are required')
    results = {}
    for arm in ARMS:
        gain = datasets['ordinary']['arms'][arm]['comparison']['pitch_coverage_gain_pp']
        useful = gain is not None and math.isfinite(gain) and gain >= 5.0
        rows = [d['arms'][arm] for d in datasets.values()]
        results[arm] = dict(useful_gain=useful, ordinary_gain_pp=gain,
            strict_pass=useful and all(r['label_budget']['strict_screen_pass'] for r in rows),
            budget_pass=useful and all(r['label_budget']['budget_screen_pass'] for r in rows),
            report_only=arm != 'range_preserving', promotion_accepted=False)
    return dict(arms=results, promotion_accepted=False,
        interpretation='Causal detector sample-clock pitch occupancy. Range-preserving arm '
            'is a saved-span combination; no combined implementation. No string, unison '
            'multiplicity, acoustic re-pluck, allocation, VST3 host or live-guitar acceptance. '
            'Detector-only callback cost is reported separately; no fitted timing offset.')
