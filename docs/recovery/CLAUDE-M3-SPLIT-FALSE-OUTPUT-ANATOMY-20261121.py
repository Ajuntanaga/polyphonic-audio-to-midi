"""Where does the split's false output come from?  Saved spans only (no audio, model, job).

PRE-REGISTRATION, written 2026-11-21 ~23:55 PST BEFORE this script was run.  What I had already
seen: the per-band decomposition in the frozen split report (report sha 12da7077...): CURRENT lower
band false (extra+gap) 11,067,777 vs present 12,983,554; A lower false 4,948,558 vs present
10,225,084; A upper (>=60) false 1,628,205 over 204 raw spans; CURRENT upper false 362,017 over 11
raw spans.  I had NOT seen any per-span or per-tail breakdown.

Question: is false output (a) a note that overlaps no label of its own pitch at all ("orphan": a false
note, a harmonic or octave error), (b) a tail after the last same-pitch label it overlaps (release
lag), or (c) a head before the first same-pitch label it overlaps?  Every false sample of a span is
exactly one of these, plus a small remainder between two same-pitch labels merged into one span.

Predictions, each can fail:
 P1  A upper band: tails are the majority of false volume (>50%), orphans under 25%, and the
     median tail is between 60 and 140 ms (the readout's own right context is 72.74/84.35 ms, plus
     the 3-frame release).  If instead orphans dominate, the upper cost is false notes, not lag.
 P2  CURRENT lower band: orphans are the majority of false volume (>50%) and tails the minority,
     because CURRENT's 1.13 false-per-present ratio below MIDI 48 looks like wrong notes, not
     overhang.  I am unsure; this is the prediction I would bet least on.
 P3  A lower band: tails exceed orphans.
 P4  Heads are under 5% of false volume for A in both bands (A is causal and cannot start early).
 Check: per (arm, band) head+tail+orphan+between == decomposition extra+gap of the frozen report.

Nothing here is promoted, installed or a candidate.  It describes saved spans.  It does not establish
lane assignment, unison multiplicity, callback deadlines or live-host delivery.

Usage: python3 -I CLAUDE-M3-SPLIT-FALSE-OUTPUT-ANATOMY-20261121.py EVIDENCE_DIR
"""
import gzip
import importlib.util
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('split', os.path.join(HERE, 'CLAUDE-M3-PITCH-SPLIT-20261121.py'))
split = importlib.util.module_from_spec(spec)
spec.loader.exec_module(split)
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import union_spans  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-SPLIT-FALSE-OUTPUT-ANATOMY-20261121.json')
MS = lambda v: round(v * 1000 / split.SAMPLE_RATE, 2)


def anatomy(spans, labels, horizon):
    expected, every = {}, []
    for row in labels:
        expected.setdefault(row['midi_note'], []).append((row['start_sample'], row['end_sample']))
        every.append((row['start_sample'], row['end_sample']))
    expected = {p: split.merged(v) for p, v in expected.items()}
    annotated = split.merged(every)
    out = {name: dict(spans=0, orphan_spans=0, head=0, tail=0, orphan=0, between=0, false_total=0,
                      tails=[], present=0) for name, _, _ in split.BANDS[:2]}
    for left, right, note in union_spans([tuple(s) for s in spans], sample_count=horizon):
        band = 'lt60' if note < split.SPLIT else 'ge60'
        row = out[band]
        exp = expected.get(note, [])
        overlapping = [(l, r) for l, r in exp if l < right and r > left]
        present = split.inter([[left, right]], exp)
        false = (right - left) - present
        row['spans'] += 1
        row['present'] += present
        row['false_total'] += false
        if not overlapping:
            row['orphan_spans'] += 1
            row['orphan'] += false
            continue
        first, last = min(l for l, _ in overlapping), max(r for _, r in overlapping)
        head, tail = max(0, first - left), max(0, right - last)
        row['head'] += head
        row['tail'] += tail
        row['between'] += false - head - tail
        if tail:
            row['tails'].append(tail)
    for row in out.values():
        tails = sorted(row.pop('tails'))
        row['tail_spans'] = len(tails)
        row['tail_ms'] = None if not tails else dict(
            median=MS(statistics.median(tails)), p10=MS(tails[int(.1 * len(tails))]),
            p90=MS(tails[min(len(tails) - 1, int(.9 * len(tails)))]))
        total = row['false_total'] or 1
        row['share'] = {k: round(row[k] / total, 4) for k in ('orphan', 'tail', 'head', 'between')}
    return out


def run(evidence_dir):
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    frozen = json.load(open(os.path.join(HERE, '..', '..', 'build/github-results/basic-pitch-cached-44891340815/'
                                         'claude-pitch-split/report.json')))
    result = dict(schema='claude_m3_split_false_anatomy_v1', datasets={})
    for name, data in report['datasets'].items():
        base = baseline['datasets'][name]
        horizon = data['common_support']['sample_count']
        labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
        current = clip_spans(base['pitch_spans'], horizon)
        path = os.path.join(evidence_dir, name + '-bridge-events.json.gz')
        if os.path.getsize(path) != data['evidence']['bytes'] or split.sha(path) != data['evidence']['sha256']:
            raise ValueError(name + ': evidence differs from pin')
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            arm_a = [tuple(s) for s in json.load(stream)['arm_spans']['A']]
        row = {}
        for key, spans in (('CURRENT', current), ('A', arm_a)):
            parts = anatomy(spans, labels, horizon)
            for band in ('lt60', 'ge60'):
                want = frozen['datasets'][name]['decomposition'][key]['bands'][band]
                got = parts[band]
                if got['false_total'] != want['extra'] + want['gap'] or got['present'] != want['present']:
                    raise ValueError(f'{name} {key} {band}: anatomy does not reproduce the frozen decomposition')
            row[key] = parts
        result['datasets'][name] = row
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1])
    for name, row in out['datasets'].items():
        print('==', name)
        for key, parts in row.items():
            for band, v in parts.items():
                print(f"  {key:8s} {band}: spans {v['spans']:4d} (orphan spans {v['orphan_spans']:3d}) present {v['present']:>10,} "
                      f"false {v['false_total']:>10,} -> orphan {v['share']['orphan']:.1%} tail {v['share']['tail']:.1%} "
                      f"head {v['share']['head']:.1%} between {v['share']['between']:.1%} | tail ms {v['tail_ms']}")
