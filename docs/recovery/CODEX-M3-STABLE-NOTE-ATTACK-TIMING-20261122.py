"""Describe seven saved labels losing all callbacks; no policy or acoustic claim.

Run once on the six hash-pinned gzip members from component run 44245557161.
These are the seven rows selected by Claude's existing count check, not a new
selection or gate. The four constructed labels share the same event window.
"""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.portable_vst3_corpus_replay import read_callbacks
from tools.portable_stable_note_identity_ledger import sink_spans, label_metrics

BASE = ROOT / 'build/github-results/vst3-stable-note-corpus-44245557161'
REPORT = BASE / 'vst3-stable-note-corpus/report.json'
SUBSET = BASE / 'attack-timing-evidence'
TARGETS = {
    'constructed': ('build/physical-capture/note-combination-corpus-tuning/combinations.tsv',
                    '294a31b0dfe69f423ed56ab88c288f116d7e945d4f35ddce7aff2de3dbbe1384', [112, 113, 114, 115]),
    'physical-highmid': ('build/physical-capture/unison-04-03-02/unison-labels.tsv',
                         '619d517c894ef6f6aeca04608ad27048872e175d091dead5fd0d83ff4b2a175b', [2]),
    'physical-high': ('build/physical-capture/unison-03-02-01/unison-labels.tsv',
                     '9ed3dd8c8d29a35d9d62525e5f57c0df7c863072a94f9b7ace150f2bd29df248', [3, 4]),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def detailed_spans(events, end):
    active, spans = {}, []
    for event in events:
        if event['kind'] == 'on':
            assert event['channel'] not in active
            active[event['channel']] = event
        else:
            onset = active.pop(event['channel'])
            assert onset['note'] == event['note']
            spans.append(dict(start=onset['sample'], end=event['sample'],
                              note=onset['note'], channel=onset['channel']))
    spans.extend(dict(start=e['sample'], end=end, note=e['note'], channel=e['channel'])
                 for e in active.values())
    return spans


def run():
    report = json.loads(REPORT.read_text())
    result = dict(schema='m3_saved_stable_note_attack_timing_v1', run_id=44245557161,
                  report_sha256=sha(REPORT.read_bytes()),
                  selection='Seven labels from the already published Claude count check.',
                  scope='Saved accepted component callbacks; no audio opened or replayed.',
                  datasets={}, labels=[], unique_removed_pairs=[],
                  acoustic_repluck_preservation='not measured')
    unique = {}
    with tempfile.TemporaryDirectory(dir=SUBSET, prefix='parse-') as temp:
        for dataset, (label_file, label_hash, indices) in TARGETS.items():
            raw_labels = (ROOT / label_file).read_bytes()
            assert sha(raw_labels) == label_hash
            labels = []
            for i, row in enumerate(csv.DictReader(raw_labels.decode().splitlines(), delimiter='\t')):
                labels.append(dict(label_index=i, **{k: int(row[k]) for k in
                    ('start_sample', 'end_sample', 'midi_note', 'string_mask')}))
            saved = report['datasets'][dataset]
            events, spans, detailed = {}, {}, {}
            pins = {}
            for arm in ('per_voice', 'stable_note'):
                prior = saved['runs'][arm + '-32-512-plain']
                path = SUBSET / dataset / (arm + '-32-512-plain-callbacks.tsv.gz')
                compressed = path.read_bytes()
                raw = gzip.decompress(compressed)
                assert len(compressed) == prior['trace']['bytes']
                assert sha(compressed) == prior['trace']['sha256']
                assert sha(raw) == prior['trace']['raw_sha256']
                plain = Path(temp) / 'callbacks.tsv'
                plain.write_bytes(raw)
                native = prior['native']
                parsed = read_callbacks(plain, sample_count=native['sample_count'],
                                        expected_count=native['accepted_events'], include_events=True)
                assert not any(parsed['counts'].values())
                events[arm] = parsed['events']
                spans[arm], _ = sink_spans(events[arm], native['sample_count'])
                detailed[arm] = detailed_spans(events[arm], native['sample_count'])
                pins[arm] = dict(file=str(path.relative_to(ROOT)), sha256=sha(compressed),
                                 raw_sha256=sha(raw), accepted_events=len(events[arm]))
            rate = saved['runs']['per_voice-32-512-plain']['native']['sample_rate']
            result['datasets'][dataset] = dict(sample_rate=rate, label_file=label_file,
                                                label_sha256=label_hash, traces=pins)
            for index in indices:
                label = labels[index]
                start, end, note = (label[k] for k in ('start_sample', 'end_sample', 'midi_note'))
                metrics = {}
                for arm, field in [('per_voice', 'before'), ('stable_note', 'after')]:
                    observed = label_metrics(spans[arm], events[arm], [label])[0]
                    expected = next(x for x in saved['comparisons'][field]['labels']
                                    if x['label_index'] == index)
                    assert observed == expected
                    metrics[field] = observed
                before_ons = [e for e in events['per_voice'] if e['kind'] == 'on' and
                              e['note'] == note and start <= e['sample'] < end]
                after_inside = [e for e in events['stable_note'] if e['note'] == note and
                                start <= e['sample'] < end]
                rows = []
                for onset in before_ons:
                    sample = onset['sample']
                    partners = [e for e in events['per_voice'] if e['sample'] == sample and
                                e['note'] == note and e['kind'] == 'off' and
                                e['channel'] != onset['channel']]
                    at_sample = [e for e in events['stable_note'] if e['sample'] == sample and e['note'] == note]
                    continuing = [s for s in detailed['stable_note'] if s['note'] == note and
                                  s['start'] < sample < s['end']]
                    row = dict(dataset=dataset, note=note, sample=sample,
                               from_channels=[e['channel'] for e in partners], to_channel=onset['channel'],
                               unique_other_channel_off=len(partners) == 1,
                               stable_pitch_callbacks_at_sample=at_sample,
                               stable_continuing_spans=continuing)
                    unique[(dataset, sample, onset['sequence'])] = row
                    rows.append(dict(sample=sample, ms_after_label_start=(sample-start)*1000/rate,
                                     from_channels=row['from_channels'], to_channel=onset['channel']))
                covering = [s for s in detailed['stable_note'] if s['note'] == note and
                            s['start'] <= start and s['end'] >= end]
                result['labels'].append(dict(dataset=dataset, **label, **metrics,
                    removed_ons=rows, stable_callbacks_inside=after_inside,
                    stable_covering_spans=[dict(**s, ms_before_label_start=(start-s['start'])*1000/rate,
                        ms_after_label_end=(s['end']-end)*1000/rate) for s in covering]))
    result['unique_removed_pairs'] = list(unique.values())
    result['summary'] = dict(labels=len(result['labels']), unique_windows=4,
        unique_removed_note_ons=len(unique),
        all_have_unique_same_sample_other_channel_off=all(r['unique_other_channel_off'] for r in unique.values()),
        all_removed_samples_have_no_stable_pitch_callback=all(not r['stable_pitch_callbacks_at_sample'] for r in unique.values()),
        all_removed_samples_have_a_continuing_stable_pitch=all(r['stable_continuing_spans'] for r in unique.values()),
        all_target_metrics_equal_saved_report=True,
        all_labels_continuously_covered_by_stable_sink_note=all(r['stable_covering_spans'] for r in result['labels']))
    out = Path(__file__).with_suffix('.json')
    with out.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result['summary'], indent=2))
    for row in result['labels']:
        print(row['dataset'], row['label_index'],
              [round(x['ms_after_label_start'], 3) for x in row['removed_ons']],
              row['stable_covering_spans'])


if __name__ == '__main__':
    run()
