"""Attribute a completed admission screen using retained text, never a replay.

Run archive analysis on GitHub. Cue/output association is temporal evidence,
not a claim about which candidate was selected by the native rescue branch.
"""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

from tools.midi_lifecycle_analysis import read_events, raw_conflicts, UNASSIGNED_VOICE


CURRENT, TRIAL = 'current-on', 'harmonic-admission-on'
MODES = (CURRENT, TRIAL)
LABEL_KEYS = ('label_index', 'midi_note', 'string_mask', 'start_sample', 'end_sample')
KINDS = ('matched', 'false_wrong_note', 'false_wrong_string', 'false_gap')
CUE_HEADER = 'm3_harmonic_admission_cues_v1\t96000\t1024\n'


def verify(data, spec, prefix=''):
    if (len(data) != spec[prefix + 'bytes'] or
            hashlib.sha256(data).hexdigest() != spec[prefix + 'sha256']):
        raise ValueError('Retained content identity differs')
    return data


def member(bundle, suffix, spec):
    names = [name for name in bundle.namelist()
             if name == suffix or name.endswith('/' + suffix)]
    if len(names) != 1:
        raise ValueError('Retained member must be unique: ' + suffix)
    return verify(bundle.read(names[0]), spec)


def read_cues(data, evidence_data, sample_count, expected_count):
    lines = data.decode().splitlines(keepends=True)
    if not lines or lines[0] != CUE_HEADER:
        raise ValueError('Unexpected retained cue schema')
    cues = []
    for line in lines[1:]:
        start, end, note = map(int, line.split())
        if not (0 <= start < end <= sample_count and start % 1024 == 0
                and end == min(start + 1024, sample_count) and 0 <= note <= 127):
            raise ValueError('Invalid retained cue')
        cues.append((start, end, note))
    observations = [json.loads(line) for line in gzip.decompress(evidence_data).splitlines()]
    admitted = {}
    for row in observations:
        if row['admitted']:
            start = row['available_sample'] + 1
            key = (start, min(start + 1024, sample_count), row['candidate_note'])
            if key in admitted or row['baseline_state_sample'] > row['available_sample'] - 960:
                raise ValueError('Duplicate or noncausal retained evidence')
            admitted[key] = row
    if (len(cues) != expected_count or len(set(cues)) != len(cues)
            or set(cues) != set(admitted)):
        raise ValueError('Cue/evidence correspondence differs')
    return [dict(start_sample=start, end_sample=end, note=note, evidence=admitted[start, end, note])
            for start, end, note in cues], observations


class CueContext:
    def __init__(self, cues):
        self.cues = sorted(cues, key=lambda row: (row['start_sample'], row['note']))
        self.by_note = defaultdict(list)
        for cue in self.cues:
            self.by_note[cue['note']].append(cue)
        self.starts = {note: [row['start_sample'] for row in rows]
                       for note, rows in self.by_note.items()}

    def preceding(self, sample, note):
        index = bisect_right(self.starts.get(note, []), sample) - 1
        if index < 0:
            return None
        row = self.by_note[note][index]
        return dict(row, age_samples=sample - row['start_sample'],
                    in_force=sample < row['end_sample'])

    def active(self, sample):
        return [row for note in sorted(self.by_note)
                if (row := self.preceding(sample, note)) and row['in_force']]


def classification(note, lane, expected):
    if not expected:
        return 'false_gap'
    masks = [row['string_mask'] for row in expected.values() if row['midi_note'] == note]
    if not masks:
        return 'false_wrong_note'
    if 0 in masks or (lane != UNASSIGNED_VOICE and any(mask & (1 << lane) for mask in masks)):
        return 'matched'
    return 'false_wrong_string'


def pitch_state(active, note, expected):
    lanes = sorted(event['voice_id'] for event in active.values() if event['note'] == note)
    mask = sum(1 << lane for lane in lanes if lane != UNASSIGNED_VOICE)
    unassigned = UNASSIGNED_VOICE in lanes
    present = bool(lanes)
    exact = present and (expected == 0 or (mask == expected and not unassigned))
    return dict(mask=mask, unassigned=unassigned, present=present, exact=exact)


def compare(events, labels, sample_count, context, focus_indices):
    """Sweep union boundaries; count voice-samples once and label-samples separately."""
    edges = defaultdict(list)
    for mode in MODES:
        for event in events[mode]:
            edges[event['sample']].append(('event', mode, event))
    for label in labels:
        edges[label['start_sample']].append(('label_on', None, label))
        edges[label['end_sample']].append(('label_off', None, label))
    edges[0]
    edges[sample_count]
    active = {mode: {} for mode in MODES}
    expected = {}
    totals = {mode: Counter() for mode in MODES}
    per_note = {mode: defaultdict(Counter) for mode in MODES}
    label_counts = {mode: defaultdict(Counter) for mode in MODES}
    cases = {index: dict(label=labels[index], lost_exact_samples=0, gained_exact_samples=0,
                        loss_causes=Counter(), loss_spans=[], gain_spans=[]) for index in focus_indices}
    added, removed = defaultdict(list), defaultdict(list)
    boundaries = sorted(edges)
    for left, right in zip(boundaries, boundaries[1:]):
        for kind, mode, row in edges[left]:
            if kind.startswith('label_'):
                if kind == 'label_on':
                    expected[row['label_index']] = row
                else:
                    del expected[row['label_index']]
                continue
            lane, note = row['voice_id'], row['note']
            key = (lane, note if lane == UNASSIGNED_VOICE else -1)
            if row['kind'] == 'on':
                if key in active[mode] or row['velocity'] == 0:
                    raise ValueError('Invalid retained raw MIDI pairing')
                active[mode][key] = row
            else:
                if key not in active[mode] or active[mode][key]['note'] != note:
                    raise ValueError('Invalid retained raw MIDI release')
                del active[mode][key]
        duration = right - left
        voices = {}
        for mode in MODES:
            voices[mode] = {(row['voice_id'], row['note']): row for row in active[mode].values()}
            for (lane, note), row in voices[mode].items():
                kind = classification(note, lane, expected)
                totals[mode][kind] += duration
                per_note[mode][note][kind] += duration
        for mode, other, target in ((TRIAL, CURRENT, added), (CURRENT, TRIAL, removed)):
            for lane, note in voices[mode].keys() - voices[other].keys():
                event = voices[mode][lane, note]
                key = (classification(note, lane, expected), note, lane, event['sample'])
                spans = target[key]
                if spans and spans[-1][1] == left:
                    spans[-1][1] = right
                else:
                    spans.append([left, right])
        for index, label in expected.items():
            states = {mode: pitch_state(active[mode], label['midi_note'], label['string_mask'])
                      for mode in MODES}
            for mode, state in states.items():
                label_counts[mode][index]['exact'] += duration * state['exact']
                label_counts[mode][index]['pitch_present'] += duration * state['present']
            if index not in cases or states[CURRENT]['exact'] == states[TRIAL]['exact']:
                continue
            case = cases[index]
            losing = states[CURRENT]['exact']
            case['lost_exact_samples' if losing else 'gained_exact_samples'] += duration
            trial = states[TRIAL]
            cause = ('pitch_absent' if not trial['present'] else
                     'extra_or_unassigned_voice' if trial['mask'] & label['string_mask'] == label['string_mask']
                     else 'wrong_or_incomplete_assignment')
            if losing:
                case['loss_causes'][cause] += duration
            rows = case['loss_spans' if losing else 'gain_spans']
            state_key = dict(current=states[CURRENT], trial=states[TRIAL])
            if rows and rows[-1]['end_sample'] == left and rows[-1]['states'] == state_key:
                rows[-1]['end_sample'] = right
            else:
                rows.append(dict(start_sample=left, end_sample=right, states=state_key,
                    current_outputs=sorted([lane, note] for lane, note in voices[CURRENT]),
                    trial_outputs=sorted([lane, note] for lane, note in voices[TRIAL]),
                    active_cues_at_start=context.active(left)))
    for index, case in cases.items():
        case['coverage'] = {mode: dict(label_counts[mode][index]) for mode in MODES}
        case['net_exact_change'] = case['gained_exact_samples'] - case['lost_exact_samples']
    changes = []
    for sign, mapping in ((1, added), (-1, removed)):
        for (kind, note, lane, onset), spans in sorted(mapping.items()):
            for left, right in spans:
                changes.append(dict(sign=sign, classification=kind, note=note, voice_id=lane,
                    start_sample=left, end_sample=right, voice_samples=right-left,
                    original_onset_sample=onset,
                    cue_at_original_onset=context.preceding(onset, note),
                    cue_at_span_start=context.preceding(left, note)))
    deltas = [dict(note=note, **{kind: per_note[TRIAL][note][kind] - per_note[CURRENT][note][kind]
                               for kind in KINDS})
              for note in sorted(set(per_note[CURRENT]) | set(per_note[TRIAL]))]
    return dict(totals={mode: dict(totals[mode]) for mode in MODES},
                per_note_deltas=deltas, cases=list(cases.values())), changes, label_counts


def analyze(reference_path, small_path, bulk_path, output):
    reference = json.loads(reference_path.read_text())
    if reference['schema'] != 'm3_ordinary_harmonic_attribution_references_v1':
        raise ValueError('Unexpected attribution reference')
    for path, name in ((small_path, 'small_artifact'), (bulk_path, 'bulk_artifact')):
        verify(path.read_bytes(), reference[name])
    with zipfile.ZipFile(small_path) as small, zipfile.ZipFile(bulk_path) as bulk:
        saved = json.loads(member(small, reference['report']['file'], reference['report']))
        if (saved['source']['commit'] != reference['source_commit'] or
                str(saved['source']['run_id']) != str(reference['run_id']) or not saved['final']):
            raise ValueError('Unexpected source screen')
        current = saved['runs'][CURRENT]
        count, rate = current['sample_count'], current['sample_rate']
        labels = [{key: row[key] for key in LABEL_KEYS} for row in current['midi_lifecycle']['labels']]
        if labels != [{key: row[key] for key in LABEL_KEYS}
                      for row in saved['runs'][TRIAL]['midi_lifecycle']['labels']]:
            raise ValueError('Reference label identities differ')
        events = {}
        with tempfile.TemporaryDirectory() as temporary:
            for mode in MODES:
                run = saved['runs'][mode]
                spec = run['midi_trace']
                packed = member(bulk, spec['file'], spec)
                raw = verify(gzip.decompress(packed), spec, 'raw_')
                path = Path(temporary) / (mode + '.tsv')
                path.write_bytes(raw)
                events[mode] = read_events(path, sample_count=count,
                    transition_count=run['midi_lifecycle']['transitions'])
                if any(raw_conflicts(events[mode])['counts'].values()):
                    raise ValueError('Raw MIDI conflicts prevent attribution')
        cue = saved['cue_generation']
        cue_data = member(bulk, 'ordinary-harmonic-admission-cues.tsv',
                          dict(bytes=cue['cue_bytes'], sha256=cue['cue_sha256']))
        evidence_data = member(bulk, 'ordinary-harmonic-admission-evidence.jsonl.gz',
                              dict(bytes=cue['evidence_bytes'], sha256=cue['evidence_sha256']))
    cues, observations = read_cues(cue_data, evidence_data, count, cue['cue_spans'])
    context = CueContext(cues)
    result, changes, label_counts = compare(events, labels, count, context, reference['focus_labels'])
    for mode in MODES:
        lifecycle = saved['runs'][mode]['midi_lifecycle']
        for row in lifecycle['labels']:
            if label_counts[mode][row['label_index']]['exact'] != row['exact_held_samples']:
                raise ValueError('Retained label coverage does not reproduce screen')
        for kind in KINDS:
            if result['totals'][mode].get(kind, 0) != lifecycle['output_safety']['counts'][kind + '_voice_samples']:
                raise ValueError('Retained output safety does not reproduce screen')
    result['largest_added_false_spans'] = {kind: sorted(
        [row for row in changes if row['sign'] == 1 and row['classification'] == kind],
        key=lambda row: (-row['voice_samples'], row['start_sample'], row['note']))[:12]
        for kind in KINDS if kind != 'matched'}
    result['change_totals'] = {kind: dict(
        added=sum(row['voice_samples'] for row in changes if row['classification'] == kind and row['sign'] == 1),
        removed=sum(row['voice_samples'] for row in changes if row['classification'] == kind and row['sign'] == -1))
        for kind in KINDS}
    for kind, row in result['change_totals'].items():
        if row['added'] - row['removed'] != result['totals'][TRIAL].get(kind, 0) - result['totals'][CURRENT].get(kind, 0):
            raise ValueError('Added/removed output accounting differs')
    output.mkdir(parents=True, exist_ok=True)
    detail = output / 'output-differences.jsonl.gz'
    with gzip.open(detail, 'wt') as stream:
        for row in changes:
            stream.write(json.dumps(row, allow_nan=False) + '\n')
    result.update(schema='m3_ordinary_harmonic_attribution_v1', state='completed', final=True,
        finished_at=datetime.now(timezone.utc).isoformat(),
        source_commit=os.environ.get('SOURCE_SHA'), run_id=os.environ.get('GITHUB_RUN_ID'),
        retained_source=reference, input_identity_pass=True, saved_metric_reproduction_pass=True,
        sample_count=count, sample_rate=rate, observations=len(observations), cues=len(cues),
        output_difference_rows=len(changes), detail=dict(file=detail.name, bytes=detail.stat().st_size,
            sha256=hashlib.sha256(detail.read_bytes()).hexdigest()),
        native_replays=0, audio_processed=False, installed_output_changed=False, promotion_accepted=False,
        interpretation='Exact holds require pitch and exact lane mask; pitch-present holds ignore lanes. '
            'Durations use half-open label bounds with no onset/release grace. Added/removed voice-samples '
            'are disjoint output differences; overlapping label-samples are separate. Gap outputs are extra '
            'notes in unlabeled audio, not missing notes. Cues at an onset or loss are temporal associations, '
            'not proof of which rescue branch ran. No trial selection/assignment trace was retained. '
            'No new detector, audio, timing, allocation, buffer or host measurement was performed.')
    (output / 'report.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(state=result['state'], cases=len(result['cases']),
                          saved_metric_reproduction_pass=True, native_replays=0)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--small-archive', type=Path, required=True)
    parser.add_argument('--bulk-archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.reference, args.small_archive, args.bulk_archive, args.output)


if __name__ == '__main__':
    main()
