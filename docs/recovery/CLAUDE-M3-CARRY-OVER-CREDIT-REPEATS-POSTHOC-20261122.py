#!/usr/bin/env python3
"""POST HOC addendum to CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.py: the denominator of the carried labels.  Written after the census' primary results were seen;
descriptive tables only, no predictions, no verdict, nothing here is a candidate, a budget change or an exemption.  Saved data only.

For every ordinary-recording label L (pitch p, start a) that has an earlier same-pitch label A (the one with the greatest end <= a), the pair (A, L) has a gap
g = a - end(A).  Was A's note still sounding in CURRENT at its last annotated sample, and did that same CURRENT span continue into L?
  merged             CURRENT held p at end(A) - 1 and the same span still covers sample a (the two notes are one CURRENT span);
  held_then_released CURRENT held p at end(A) - 1 but that span ended at or before a (a release, then whatever L got);
  pred_not_held      CURRENT did not hold p at end(A) - 1.
Gap buckets: tight (g <= 21,120 samples, 220 ms: within the detector's longest coasting hold), mid (up to 96,000 samples, 1 s), wide (longer).
Each outcome is crossed with L's census class (missed / fresh_only / carried_only / mixed, TOL = 2,400).

Usage: python3 -P -E CLAUDE-M3-CARRY-OVER-CREDIT-REPEATS-POSTHOC-20261122.py [--selftest | --run]   (--run refuses to overwrite its JSON)
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


census = load('census', 'CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.py')
fr = census.fr
OUT = os.path.join(HERE, 'CLAUDE-M3-CARRY-OVER-CREDIT-REPEATS-POSTHOC-20261122.json')
TIGHT, MID = census.HOLD_MAX, 96000
OUTCOMES = ('merged', 'held_then_released', 'pred_not_held')
BUCKETS = ('tight', 'mid', 'wide')


def bucket_of(gap):
    return 'tight' if gap <= TIGHT else 'mid' if gap <= MID else 'wide'


def pairs(labels, spans_p, rows):
    """One record per label that has an earlier same-pitch label."""
    same = {}
    for j, lab in enumerate(labels):
        same.setdefault(lab['midi_note'], []).append((lab['end_sample'], lab['start_sample'], j))
    out = []
    for i, lab in enumerate(labels):
        p, a = lab['midi_note'], lab['start_sample']
        earlier = [(e, j) for e, s, j in same[p] if j != i and e <= a]
        if not earlier:
            continue
        end_a, j = max(earlier)
        span = next(([l, r] for l, r in spans_p.get(p, []) if l <= end_a - 1 < r), None)
        outcome = 'pred_not_held' if span is None else 'merged' if span[1] > a else 'held_then_released'
        out.append(dict(label=i, pred=j, midi=p, gap=a - end_a, bucket=bucket_of(a - end_a), outcome=outcome, cls=rows[i]['cls']))
    return out


def table(recs):
    t = {b: {o: {c: 0 for c in census.CLASSES} for o in OUTCOMES} for b in BUCKETS}
    for r in recs:
        t[r['bucket']][r['outcome']][r['cls']] += 1
    return t


def unit_checks():
    labels = [dict(midi_note=40, start_sample=0, end_sample=100), dict(midi_note=40, start_sample=150, end_sample=250),     # A -> L merged, tight (gap 50)
              dict(midi_note=41, start_sample=0, end_sample=100), dict(midi_note=41, start_sample=150, end_sample=250),     # released, L fresh
              dict(midi_note=42, start_sample=0, end_sample=100), dict(midi_note=42, start_sample=150, end_sample=250),     # A not held, L missed
              dict(midi_note=43, start_sample=0, end_sample=100), dict(midi_note=43, start_sample=50000, end_sample=50100)]  # merged across a mid gap
    spans = {40: [[10, 200]], 41: [[10, 120], [160, 240]], 42: [], 43: [[10, 50050]]}
    rows = census.classify(labels, spans, 25)
    recs = {r['label']: r for r in pairs(labels, spans, rows)}
    return [sorted(recs) == [1, 3, 5, 7],
            recs[1]['outcome'] == 'merged' and recs[1]['bucket'] == 'tight' and recs[1]['gap'] == 50 and recs[1]['cls'] == 'carried_only',
            recs[3]['outcome'] == 'held_then_released' and recs[3]['cls'] == 'fresh_only',
            recs[5]['outcome'] == 'pred_not_held' and recs[5]['cls'] == 'missed',
            recs[7]['outcome'] == 'merged' and recs[7]['bucket'] == 'mid' and recs[7]['cls'] == 'carried_only']


def main(run):
    ok = unit_checks()
    print('unit checks', ok)
    if not all(ok):
        raise SystemExit('unit checks failed')
    if not run:
        return
    if os.path.exists(OUT):
        raise SystemExit('output exists; refusing to overwrite')
    ctx = census.context('ordinary')
    cur_p = fr.by_pitch(ctx['cur_spans'], ctx['horizon'])
    rows = census.classify(ctx['labels'], cur_p, census.TOL_PRIMARY)
    recs = pairs(ctx['labels'], cur_p, rows)
    t = table(recs)
    carried = {r['label'] for r in rows if r['cls'] in ('carried_only', 'mixed')}
    in_pairs = {r['label'] for r in recs if r['outcome'] == 'merged'}
    out = dict(schema='m3_carry_over_repeats_posthoc_v1', post_hoc=True, tight_samples=TIGHT, mid_samples=MID, labels_with_predecessor=len(recs),
               labels_without_predecessor=len(rows) - len(recs), table=t,
               merged_equals_bridged_labels=in_pairs == {r['label'] for r in rows if r['bridged'] > 0},
               carried_labels_not_merged=sorted(carried - in_pairs),
               wide_or_mid_merged=[dict(label=r['label'], gap=r['gap'], cls=r['cls']) for r in recs if r['outcome'] == 'merged' and r['bucket'] != 'tight'],
               census_json_sha256=census.sha(census.OUT), census_script_sha256=census.sha(os.path.join(HERE, 'CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.py')))
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=1)
    print('wrote', os.path.basename(OUT))


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else '--selftest'
    if arg not in ('--selftest', '--run'):
        raise SystemExit(__doc__)
    main(arg == '--run')
