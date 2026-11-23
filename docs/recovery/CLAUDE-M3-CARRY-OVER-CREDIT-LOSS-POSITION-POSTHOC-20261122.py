#!/usr/bin/env python3
"""POST HOC addendum 2 to CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.py: where inside a label does the rapid-mute mask's present-sample loss fall?
Written after the census' primary results were seen; descriptive only, no predictions, no verdict, nothing here is a candidate, a budget change or an exemption.
Saved data only: it reads two committed JSON files and nothing else.

For each of the 17 ordinary-recording labels that lose present samples under the callback-grain mask M0 (the label_anatomy rows of CLAUDE-M3-RAPID-MUTE-CHECK-20261122.json),
the census gives the label's class and the in-label length of its carried span (tail_in_label: a carried span covers [start, start + tail) of the label, because it must
cover the label's first sample).  The loss lies inside the carried tail when its last lost offset (measured from the label start) is at most that tail.  A label with no
carried span (fresh_only) has a tail of 0.  The decision-grain mask M1 needs no offsets: its three losing labels (31, 70, 123) are carried_only in the census.

Usage: python3 -P -E CLAUDE-M3-CARRY-OVER-CREDIT-LOSS-POSITION-POSTHOC-20261122.py [--selftest | --run]   (--run refuses to overwrite its JSON)
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CENSUS = os.path.join(HERE, 'CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.json')
ANATOMY = os.path.join(HERE, 'CLAUDE-M3-RAPID-MUTE-CHECK-20261122.json')
OUT = os.path.join(HERE, 'CLAUDE-M3-CARRY-OVER-CREDIT-LOSS-POSITION-POSTHOC-20261122.json')


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def tails(census):
    """label -> (class, in-label length of the carried span, number of carried spans)."""
    return {r['label']: (r['cls'], sum(s['tail_in_label'] for s in r['spans']), len(r['spans']))
            for r in census['datasets']['ordinary']['labels_not_fresh_only']}


def position(rows, tail_of):
    out = []
    for r in rows:
        cls, tail, _ = tail_of.get(r['label'], ('fresh_only', 0, 0))
        out.append(dict(label=r['label'], cls=cls, lost=r['lost'], first_offset=r['first_offset'], last_offset=r['last_offset'], carried_tail=tail,
                        inside_carried=r['last_offset'] <= tail))
    return out


def unit_checks():
    tail_of = {1: ('carried_only', 1000, 1), 2: ('mixed', 100, 1)}
    rows = [dict(label=1, lost=10, first_offset=0, last_offset=10),        # inside a carried-only label
            dict(label=2, lost=10, first_offset=90, last_offset=110),      # reaches past the carried tail of a mixed label
            dict(label=3, lost=5, first_offset=0, last_offset=5)]          # a label with no carried span
    p = position(rows, tail_of)
    return [[r['inside_carried'] for r in p] == [True, False, False],
            [r['cls'] for r in p] == ['carried_only', 'mixed', 'fresh_only'],
            p[2]['carried_tail'] == 0,
            tails({'datasets': {'ordinary': {'labels_not_fresh_only': [dict(label=7, cls='mixed', spans=[dict(tail_in_label=40)])]}}}) == {7: ('mixed', 40, 1)}]


def main(run):
    ok = unit_checks()
    print('unit checks', ok)
    if not all(ok):
        raise SystemExit('unit checks failed')
    if not run:
        return
    if os.path.exists(OUT):
        raise SystemExit('output exists; refusing to overwrite')
    with open(CENSUS) as f:
        census = json.load(f)
    with open(ANATOMY) as f:
        anatomy = json.load(f)
    tail_of = tails(census)
    rows = anatomy['datasets']['ordinary']['label_anatomy']
    pos = position(rows, tail_of)
    join = {r['label']: r['loss_M0'] for r in census['joins']['labels_with_m0_loss']}
    by_class = {}
    for r in pos:
        c = by_class.setdefault(r['cls'], dict(labels=0, lost=0, lost_inside_carried=0))
        c['labels'] += 1
        c['lost'] += r['lost']
        c['lost_inside_carried'] += r['lost'] if r['inside_carried'] else 0
    out = dict(schema='m3_carry_over_loss_position_posthoc_v1', post_hoc=True, labels=len(pos), lost_total=sum(r['lost'] for r in pos),
               lost_inside_carried=sum(r['lost'] for r in pos if r['inside_carried']), labels_not_inside_carried=[r['label'] for r in pos if not r['inside_carried']],
               max_carried_spans_per_label=max(n for _, _, n in tail_of.values()), matches_census_join=join == {r['label']: r['lost'] for r in pos},
               census_m0_loss_total=census['joins']['m0_loss_total'], by_class=by_class, rows=pos,
               census_json_sha256=sha(CENSUS), anatomy_json_sha256=sha(ANATOMY))
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=1)
    print('wrote', os.path.basename(OUT))


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else '--selftest'
    if arg not in ('--selftest', '--run'):
        raise SystemExit(__doc__)
    main(arg == '--run')
