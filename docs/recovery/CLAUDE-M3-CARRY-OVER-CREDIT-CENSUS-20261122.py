#!/usr/bin/env python3
"""POST HOC census: how much of CURRENT's per-label presence credit is carried over from a span that began before the label?  Saved data only.

Motivation: the two labels that fail Codex's frozen rapid-mute budget under the callback-grain mask (31, 70) and the one that still fails at the decision grain
(70) all have a CURRENT presence that equals the end of a long CURRENT span that began before the label (the census JSON's span fields give 499,327 - 489,817
= 9,510 and 1,227,711 - 1,224,217 = 3,494).  Is that a property of those labels or of CURRENT in general?  Descriptive only: no verdict, no threshold, no
candidate, no budget or gate proposal.

Definitions (the CURRENT spans are the per-pitch unions of the scorer's own spans, fr.by_pitch; a label is (pitch, start a, end b)):
  present   = the CURRENT span samples of the label's pitch inside [a, b) (exactly the scorer's per-label current_present_samples);
  fresh     = present samples whose span begins at or after a - TOL (the span is the detector's response to this label);
  carried   = present samples whose span began before a - TOL (the pitch was already sounding when the label began);
    bridged = the span's pre-label part [l, a) overlaps an earlier same-pitch label (ring-over between two notes of one pitch);
    head    = it does not (the span began in unlabeled time or in other pitches' labels).
  label class: missed (no present), fresh_only, carried_only (every present sample is carried), mixed.
TOL = 2,400 samples (25 ms, the frozen budget's present-time limit) is primary; TOL = 0 is reported as a sensitivity.

Usage (no audio, model run, job, native edit, promotion or download):
  python3 -P -E CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.py --selftest   unit checks on synthetic spans plus identity gates on both recordings (booleans only)
  python3 -P -E CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.py --dry        selftest plus label and span counts (no class count, no carried volume)
  python3 -P -E CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.py --run        the one run (refuses to overwrite its JSON)
"""
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fr = load('fr', 'CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py')
ad = fr.ad
CODEX_JSON = os.path.join(HERE, 'CODEX-M3-RAPID-MUTE-20261122.json')
DECISION_JSON = os.path.join(HERE, 'CLAUDE-M3-DECISION-GRAIN-MASK-20261122.json')
CENSUS_JSON = os.path.join(HERE, 'CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.json')
OUT = os.path.join(HERE, 'CLAUDE-M3-CARRY-OVER-CREDIT-CENSUS-20261122.json')
NAMES = ('ordinary', 'extended-middle')
TOL_PRIMARY, TOLS = 2400, (2400, 0)
WHOLE_LOST = (42, 70, 200, 306, 364)       # labels the rejected native joint reset lost whole (the boundary census, Part B)
HOLD_MAX = 21120                           # 220 ms at 96 kHz: the detector's longest coasting hold (written as a sample count; the recordings are 96 kHz)
CLASSES = ('missed', 'fresh_only', 'carried_only', 'mixed')


# ---------------------------------------------------------------- the classifier (pure)
def classify(labels, spans_p, tol):
    """One row per label.  labels: dicts with midi_note, start_sample, end_sample; spans_p: {pitch: sorted disjoint [[l, r), ...]}."""
    same = {}
    for j, lab in enumerate(labels):
        same.setdefault(lab['midi_note'], []).append((lab['start_sample'], lab['end_sample'], j))
    rows = []
    for i, lab in enumerate(labels):
        p, a, b = lab['midi_note'], lab['start_sample'], lab['end_sample']
        row = dict(label=i, midi=p, start=a, end=b, annotated=b - a, present=0, fresh=0, bridged=0, head=0, carried=[])
        for l, r in spans_p.get(p, []):
            lo, hi = max(l, a), min(r, b)
            if lo >= hi:
                continue
            row['present'] += hi - lo
            if l >= a - tol:
                row['fresh'] += hi - lo
                continue
            earlier = [b2 for a2, b2, j in same[p] if j != i and a2 < a and max(l, a2) < min(a, b2)]
            if earlier:
                prev_end = min(max(earlier), a)
                row['bridged'] += hi - lo
                kind = 'bridged'
            else:
                prev_end = None
                row['head'] += hi - lo
                kind = 'head'
            row['carried'].append(dict(kind=kind, span=[l, r], carry_in=a - l, present=hi - lo, tail_in_label=hi - a,
                                       gap=None if prev_end is None else a - prev_end))
        row['cls'] = ('missed' if row['present'] == 0 else 'fresh_only' if row['bridged'] + row['head'] == 0
                      else 'carried_only' if row['fresh'] == 0 else 'mixed')
        rows.append(row)
    return rows


def partition_ok(rows):
    return all(r['present'] == r['fresh'] + r['bridged'] + r['head'] and sum(c['present'] for c in r['carried']) == r['bridged'] + r['head'] for r in rows)


# ---------------------------------------------------------------- aggregates
def aggregate(rows, rate):
    n = {c: sum(1 for r in rows if r['cls'] == c) for c in CLASSES}
    present, annotated = sum(r['present'] for r in rows), sum(r['annotated'] for r in rows)
    fresh, bridged, head = (sum(r[k] for r in rows) for k in ('fresh', 'bridged', 'head'))
    carried = [dict(c, label=r['label']) for r in rows for c in r['carried']]
    gaps = [c['gap'] for c in carried if c['kind'] == 'bridged']
    return dict(
        labels=len(rows), label_classes=n, present=present, annotated=annotated, fresh=fresh, bridged=bridged, head=head,
        carried_share_of_present=round((bridged + head) / present, 5) if present else None,
        carried_pct_of_annotated=round(100 * (bridged + head) / annotated, 4) if annotated else None,
        coverage_pct=round(100 * present / annotated, 4) if annotated else None, fresh_coverage_pct=round(100 * fresh / annotated, 4) if annotated else None,
        carried_spans=len(carried), bridged_spans=len(gaps), head_spans=len(carried) - len(gaps),
        bridge_gap_ms=fr.stats_ms(gaps, rate), bridge_gap_median_samples=sorted(gaps)[len(gaps) // 2] if gaps else None,
        bridge_gap_over_hold=sum(1 for g in gaps if g > HOLD_MAX),
        carry_in_ms=fr.stats_ms([c['carry_in'] for c in carried], rate),
        carried_only_tail_in_label_ms=fr.stats_ms([c['tail_in_label'] for r in rows if r['cls'] == 'carried_only' for c in r['carried']], rate),
        bridged_gap_total=sum(gaps), bridged_present_total=sum(c['present'] for c in carried if c['kind'] == 'bridged'))


def label_view(r):
    return dict(label=r['label'], midi=r['midi'], cls=r['cls'], present=r['present'], fresh=r['fresh'], bridged=r['bridged'], head=r['head'],
                spans=[dict(kind=c['kind'], carry_in=c['carry_in'], tail_in_label=c['tail_in_label'], gap=c['gap']) for c in r['carried']])


# ---------------------------------------------------------------- data and gates
_CTX = {}


def context(name):
    if name not in _CTX:
        _CTX[name] = ad.dataset_context(name)
    return _CTX[name]


def gates(codex):
    """Identity gates per recording (booleans only): per-label present equals Codex's current_present_samples, run count equals Codex's occupancy runs,
    the partition is exact at both tolerances."""
    out = {}
    for name in NAMES:
        ctx = context(name)
        cur_p = fr.by_pitch(ctx['cur_spans'], ctx['horizon'])
        theirs = codex['datasets'][name]
        deltas = theirs['comparison']['label_deltas']
        rows = classify(ctx['labels'], cur_p, TOL_PRIMARY)
        out[name] = dict(
            labels_equal=len(rows) == len(deltas) and all(r['label'] == d['label_index'] and r['present'] == d['current_present_samples'] and r['annotated'] == d['annotated_samples']
                                                         for r, d in zip(rows, deltas)),
            runs_equal=sum(len(v) for v in cur_p.values()) == theirs['occupancy_runs']['current'],
            partition_exact=all(partition_ok(classify(ctx['labels'], cur_p, t)) for t in TOLS))
    return out


def unit_checks():
    # pitch 40 labels: A [100, 200), L [300, 400); spans chosen to hit every class
    labels = [dict(midi_note=40, start_sample=100, end_sample=200), dict(midi_note=40, start_sample=300, end_sample=400),
              dict(midi_note=41, start_sample=100, end_sample=200), dict(midi_note=42, start_sample=100, end_sample=200),
              dict(midi_note=43, start_sample=100, end_sample=200), dict(midi_note=44, start_sample=100, end_sample=200)]
    spans = {40: [[110, 350]],            # starts inside A, bridges the gap into L: A fresh, L bridged carried_only
             41: [[10, 150]],             # began 90 before the label, no earlier same-pitch label: head
             42: [[100 - 20, 130], [160, 190]],   # starts 20 before: fresh at TOL 25, carried(head) at TOL 0; second span fresh
             43: [],                      # missed
             44: [[150, 260]]}            # starts inside: fresh_only
    r25, r0 = classify(labels, spans, 25), classify(labels, spans, 0)
    ok = [r25[0]['cls'] == 'fresh_only' and r25[0]['fresh'] == 90,
          r25[1]['cls'] == 'carried_only' and r25[1]['bridged'] == 50 and r25[1]['carried'][0]['gap'] == 100 and r25[1]['carried'][0]['carry_in'] == 190,
          r25[2]['cls'] == 'carried_only' and r25[2]['head'] == 50 and r25[2]['carried'][0]['gap'] is None,
          r25[3]['cls'] == 'fresh_only' and r25[3]['fresh'] == 30 + 30 and r0[3]['cls'] == 'mixed' and r0[3]['head'] == 30 and r0[3]['fresh'] == 30,
          r25[4]['cls'] == 'missed' and r25[4]['present'] == 0,
          r25[5]['cls'] == 'fresh_only' and r25[5]['present'] == 50,
          partition_ok(r25) and partition_ok(r0)]
    # two overlapping same-pitch labels: the later one's carried span is bridged from the earlier even though the earlier has not ended
    lab2 = [dict(midi_note=50, start_sample=0, end_sample=100), dict(midi_note=50, start_sample=60, end_sample=160)]
    r2 = classify(lab2, {50: [[10, 140]]}, 0)
    ok.append(r2[1]['cls'] == 'carried_only' and r2[1]['carried'][0]['gap'] == 0 and r2[0]['cls'] == 'fresh_only')
    agg = aggregate(r25, 96000)
    ok.append(agg['label_classes'] == dict(missed=1, fresh_only=3, carried_only=2, mixed=0) and agg['bridged_spans'] == 1 and agg['head_spans'] == 1)
    return ok


def selftest():
    ok = unit_checks()
    print('unit checks', ok)
    if not all(ok):
        raise SystemExit('unit checks failed')
    codex = json.load(open(CODEX_JSON))
    g = gates(codex)
    for name, v in g.items():
        print(name, 'identity', json.dumps(v))
    if not all(all(v.values()) for v in g.values()):
        raise SystemExit('identity gates failed')
    return g


def dry():
    g = selftest()
    for name in NAMES:
        ctx = context(name)
        cur_p = fr.by_pitch(ctx['cur_spans'], ctx['horizon'])
        print(name, 'labels', len(ctx['labels']), 'CURRENT spans', sum(len(v) for v in cur_p.values()), 'pitches with spans', len(cur_p))
    return g


# ---------------------------------------------------------------- the run
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    if os.path.exists(OUT):
        raise SystemExit('output exists; refusing to overwrite')
    codex = json.load(open(CODEX_JSON))
    g = gates(codex)
    if not all(all(v.values()) for v in g.values()):
        raise SystemExit('identity gates failed; no run')
    decision, census = json.load(open(DECISION_JSON)), json.load(open(CENSUS_JSON))
    out = dict(schema='m3_carry_over_credit_census_v1', post_hoc=True, tol_primary=TOL_PRIMARY, hold_max_samples=HOLD_MAX, identity=g, datasets={})
    kept = {}
    for name in NAMES:
        ctx = context(name)
        cur_p = fr.by_pitch(ctx['cur_spans'], ctx['horizon'])
        entry = dict(rate=ctx['rate'], horizon=ctx['horizon'], current_present_scorer=codex['datasets'][name]['current']['present_pitch_samples'])
        for tol in TOLS:
            rows = classify(ctx['labels'], cur_p, tol)
            entry[f'tol_{tol}'] = aggregate(rows, ctx['rate'])
            if tol == TOL_PRIMARY:
                kept[name] = rows
                entry['labels_not_fresh_only'] = [label_view(r) for r in rows if r['cls'] in ('carried_only', 'mixed')]
        out['datasets'][name] = entry
    rows = kept['ordinary']
    by = {r['label']: r for r in rows}
    lab17 = decision['datasets']['ordinary']['labels']
    positives = sorted({p['label'] for p in census['datasets']['ordinary']['pairs'] if p['kind'] == 'primary' and p['cls'] == 'positive'})
    loss = lambda key: {c: sum(x[key] for x in lab17 if by[x['label']]['cls'] == c) for c in CLASSES}
    joins = dict(
        m0_presence_loss_by_class=loss('presence_loss_M0'), m1_presence_loss_by_class=loss('presence_loss_M1'),
        m0_loss_total=sum(x['presence_loss_M0'] for x in lab17), m1_loss_total=sum(x['presence_loss_M1'] for x in lab17),
        labels_with_m0_loss=[dict(label=x['label'], cls=by[x['label']]['cls'], present=by[x['label']]['present'], loss_M0=x['presence_loss_M0'], loss_M1=x['presence_loss_M1'],
                                  carry_in=[c['carry_in'] for c in by[x['label']]['carried']]) for x in lab17],
        whole_lost=[dict(label=i, cls=by[i]['cls'], present=by[i]['present'], carry_in=[c['carry_in'] for c in by[i]['carried']]) for i in WHOLE_LOST],
        positives=dict(count=len(positives), classes={c: sum(1 for i in positives if by[i]['cls'] == c) for c in CLASSES}))
    out['joins'] = joins
    o = out['datasets']['ordinary']['tol_%d' % TOL_PRIMARY]
    odds = dict(P1=.97, P2=.55, P3=.50, P4=.65, P5=.55, P6=.50, P7=.40, P8=.70)
    carried_total = o['bridged'] + o['head']
    truth = dict(
        P1=all(all(v.values()) for v in g.values()),
        P2=o['label_classes']['carried_only'] >= 20,
        P3=carried_total >= 0.05 * o['present'],
        P4=sum(1 for i in WHOLE_LOST if by[i]['cls'] == 'carried_only') >= 4,
        P5=o['bridged'] >= 0.60 * carried_total if carried_total else False,
        P6=o['bridge_gap_median_samples'] is not None and o['bridge_gap_median_samples'] < HOLD_MAX,
        P7=joins['m0_presence_loss_by_class']['carried_only'] >= 0.5 * joins['m0_loss_total'],
        P8=carried_total < 0.03 * o['annotated'])
    out['predictions'] = {k: dict(odds=odds[k], outcome=truth[k], brier=round((odds[k] - truth[k]) ** 2, 4)) for k in odds}
    out['brier_sum'] = round(sum(v['brier'] for v in out['predictions'].values()), 4)
    out['hits'] = sum(1 for k in odds if odds[k] != .5 and (odds[k] > .5) == truth[k])
    out['inputs'] = dict(codex_json_sha256=sha(CODEX_JSON), decision_grain_json_sha256=sha(DECISION_JSON), boundary_census_json_sha256=sha(CENSUS_JSON))
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=1)
    print('wrote', os.path.basename(OUT), 'brier', out['brier_sum'], 'hits', out['hits'])


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    if arg == '--selftest':
        selftest()
    elif arg == '--dry':
        dry()
    elif arg == '--run':
        main()
    else:
        raise SystemExit(__doc__)
