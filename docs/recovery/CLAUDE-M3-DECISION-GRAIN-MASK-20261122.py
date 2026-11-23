#!/usr/bin/env python3
"""POST HOC granularity question about Codex's frozen rapid-mute mask (CODEX-M3-RAPID-MUTE-PLAN-20261122.md).

The shipped VST3 stamps every VoiceTransition at its own decision frame (native/vst3/vst3_component.cpp:1127, vst3_event_sink.cpp:29-30), so a causal release
acts at a 64-sample decision, while Codex's frozen diagnostic mask works per 512-sample callback.  Does the same existing cue (quiet disposition 5,
rapid_mute_ratio) scored at the detector's own decision grain change the frozen per-label budget verdict?

Exactly two masks, no search, nothing tuned:
  M0  callback grain, Codex's mask (identity gate: must reproduce CODEX-M3-RAPID-MUTE-20261122.json exactly);
  M1  decision grain: for every decision at zero-based sample s whose quiet disposition is 5, mark [s + 1, s + 65), clipped to the horizon, merged.
Both are CURRENT minus the marked intervals (the old span resumes when the flag clears: an optimistic occupancy diagnostic, not a NoteOff/NoteOn
implementation).  Same scorer, pins, strict/aggregate checks and frozen 25 ms AND 5% budget as CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py, which this loads.
Disclosure: motivated by the two labels (31, 70) that fail M0, so it is post hoc; one variant; both recordings are design data; nothing here is a candidate.

Usage (saved data only; no audio, model run, job, native edit or promotion):
  python3 -P -E CLAUDE-M3-DECISION-GRAIN-MASK-20261122.py --selftest   plumbing only: unit checks, trace pins, per-tick reader vs the callback reader, M0 vs Codex's marked intervals,
                                                                      and the scoring path on an EMPTY mask (booleans only: nothing is removed, so no M0 or M1 outcome is seen)
  python3 -P -E CLAUDE-M3-DECISION-GRAIN-MASK-20261122.py --dry        selftest plus mask geometry counts (no M0 or M1 outcome is computed or printed)
  python3 -P -E CLAUDE-M3-DECISION-GRAIN-MASK-20261122.py --run        the one scored run (refuses to overwrite its JSON)
"""
import bisect
import csv
import gzip
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


rm = load('rm', 'CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py')       # callback reader, marked_runs, subtract, variant, scorer wiring, pins
chk, fr, ad = rm.chk, rm.fr, rm.ad
DECISION, ORDINARY, RAPID_MUTE = 64, rm.ORDINARY, rm.RAPID_MUTE
OUT = os.path.join(HERE, 'CLAUDE-M3-DECISION-GRAIN-MASK-20261122.json')


# ---------------------------------------------------------------- the two masks
def read_ticks(name):
    """One streaming pass: every decision's (sample, quiet), with the pin, grid and range checks of rm.read_quiet (whose callback dict it must reproduce)."""
    pin, sha = chk.PINS[name], hashlib.sha256()
    samples, quiets, counts, previous = [], [], [0] * 8, None
    with gzip.open(os.path.join(ROOT, pin['trace']), 'rb') as stream:
        def lines():
            for raw in stream:
                sha.update(raw)
                yield raw.decode('utf-8')
        text = lines()
        if next(text).strip() != '# m3_candidate_outcome_v5':
            raise SystemExit('not the complete v5 trace')
        for row in csv.DictReader(text, delimiter='\t'):
            s, tick, quiet = int(row['sample']), int(row['tick']), int(row['quiet'])
            if s != DECISION * tick - 1 or (previous is not None and tick != previous + 1):
                raise SystemExit('tick grid is not the contiguous 64-sample decision grid')
            if not 0 <= quiet <= 7:
                raise SystemExit(f'quiet disposition {quiet} outside 0..7')
            previous = tick
            samples.append(s)
            quiets.append(quiet)
            counts[quiet] += 1
    audit = dict(rows=len(samples), quiet_counts=counts, raw_sha256=sha.hexdigest(), last_sample=samples[-1])
    if audit['raw_sha256'] != pin['sha']:
        raise SystemExit(f'{name}: raw trace hash differs from the pin')
    return samples, quiets, audit


def callback_last(samples, quiets):
    """Per completed 512-sample callback the quiet disposition of its last decision, keyed by the callback's end boundary (as rm.read_quiet)."""
    return {s + 1: q for s, q in zip(samples, quiets) if (s + 1) % rm.CALLBACK == 0}


def decision_mask(samples, quiets, horizon):
    """M1: [s + 1, s + 65) after every decision with disposition 5, clipped to the horizon, merged."""
    return rm.merge_runs((s + 1, min(s + 1 + DECISION, horizon)) for s, q in zip(samples, quiets) if q == RAPID_MUTE and s + 1 < horizon)


def make_inside(runs):
    starts = [r[0] for r in runs]

    def inside(x):
        i = bisect.bisect_right(starts, x) - 1
        return i >= 0 and runs[i][0] <= x < runs[i][1]
    return inside


def counts_only(samples, quiets, m0, m1):
    """Mask geometry that involves neither CURRENT nor labels."""
    in0 = make_inside(m0)
    c5 = [(s, in0(s)) for s, q in zip(samples, quiets) if q == RAPID_MUTE]
    return dict(ticks=len(samples), code5_ticks=len(c5), code5_inside_m0=sum(1 for _, i in c5 if i), code5_outside_m0=sum(1 for _, i in c5 if not i),
                nonzero_non5_inside_m0=sum(1 for s, q in zip(samples, quiets) if q != RAPID_MUTE and in0(s)),
                m0_runs=len(m0), m1_runs=len(m1), m0_samples=fr.size(m0), m1_samples=fr.size(m1),
                only_m0_samples=fr.size(rm.subtract(m0, m1)), only_m1_samples=fr.size(rm.subtract(m1, m0)),
                m1_single_decision_runs=sum(1 for lo, hi in m1 if hi - lo <= DECISION), m1_longest_run=max((hi - lo for lo, hi in m1), default=0))


def unit_checks():
    ok = []
    s = [63, 127, 191, 255, 319]
    ok.append(decision_mask(s, [0, 5, 5, 0, 5], 330) == [[128, 256], [320, 330]])      # two adjacent flags merge, the last is clipped to the horizon
    ok.append(decision_mask(s, [5, 0, 0, 0, 0], 64) == [] and decision_mask(s, [5, 0, 0, 0, 0], 65) == [[64, 65]])   # s + 1 must lie before the horizon
    ok.append(decision_mask(s, [0, 0, 0, 0, 0], 1000) == [] and decision_mask([], [], 100) == [])
    ticks = list(range(63, 63 + 64 * 16, 64))
    q = [0] * 16
    q[7] = 5                                         # decision at sample 511: the last of callback 0
    q[2] = 5                                         # a mid-callback flag that callback grain ignores
    last = callback_last(ticks, q)
    ok.append(sorted(last) == [512, 1024] and last[512] == 5 and last[1024] == 0)
    ok.append(rm.marked_runs(last, 2000) == [[512, 1024]] and decision_mask(ticks, q, 2000) == [[192, 256], [512, 576]])
    inside = make_inside([[10, 20], [30, 40]])
    ok.append([inside(x) for x in (9, 10, 19, 20, 29, 30, 39, 40)] == [False, True, True, False, False, True, True, False])
    c = counts_only(ticks, q, [[512, 1024]], decision_mask(ticks, q, 2000))
    ok.append(c['code5_ticks'] == 2 and c['code5_inside_m0'] == 0 and c['code5_outside_m0'] == 2 and c['m1_samples'] == 128 and c['m0_samples'] == 512
              and c['only_m1_samples'] == 64 and c['only_m0_samples'] == 448 and c['m1_single_decision_runs'] == 2 and c['m1_longest_run'] == 64)   # [512, 576) lies inside M0
    return all(ok), ok


_CTX = {}


def context(name):
    if name not in _CTX:
        _CTX[name] = ad.dataset_context(name)
    return _CTX[name]


def plumbing(codex):
    """Everything that needs no CURRENT outcome and no label outcome: unit checks, trace pins and grid, per-tick reader vs the callback reader, M0 vs Codex's
    marked intervals, and the scoring path run on an EMPTY mask (masked output = CURRENT, so every removal must be zero; booleans only, M1 is not touched)."""
    good, parts = unit_checks()
    print('unit checks', 'PASS' if good else 'FAIL', parts)
    ok, loaded = good, {}
    for name in chk.PINS:
        horizon = codex['datasets'][name]['horizon']
        samples, quiets, audit = read_ticks(name)
        last, audit_rm = rm.read_quiet(name)
        same_last, same_audit = callback_last(samples, quiets) == last, audit == audit_rm == codex['datasets'][name]['trace_audit']
        m0 = rm.marked_runs(last, horizon)
        same_m0 = m0 == [list(x) for x in codex['datasets'][name]['marked_intervals']]
        null_ok = null_mask_check(name, horizon)
        print(f"{name}: ticks {audit['rows']:,} sha ok; per-tick reader reproduces the callback dict {same_last}; audit equals rm's and Codex's {same_audit}; "
              f"M0 equals Codex's marked intervals {same_m0}; scoring path on an empty mask removes nothing {null_ok}")
        ok = ok and same_last and same_audit and same_m0 and null_ok
        loaded[name] = (samples, quiets, audit, last, m0, horizon)
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return ok, loaded


# ---------------------------------------------------------------- scoring
def volumes(ctx, per_pitch):
    measured = fr.score(rm.triples(per_pitch), ctx['labels'], **ctx['clock'])
    t = measured['pitch_sets']['totals']
    return dict(present=t['present_pitch_samples'], wrong=t['extra_pitch_voice_samples'], gap=measured['pitch_sets']['unlabeled_gap_voice_samples'])


def null_mask_check(name, horizon):
    """The scored half of main() with an empty mask: the masked output is CURRENT itself, so nothing may be removed, no label may lose anything, the label
    table must be empty and the budget must pass.  Returns one boolean; no volume or label value is printed."""
    ctx = context(name)
    cur_p = fr.by_pitch(ctx['cur_spans'], horizon)
    cur_row, _, _ = rm.variant(ctx, cur_p)
    same_p = {p: rm.subtract(v, []) for p, v in cur_p.items()}
    row, _, cmp = rm.variant(ctx, same_p)
    s = summarize(row, cmp, cur_row)
    nothing = volumes(ctx, {p: fr.isect(c, []) for p, c in cur_p.items()})
    return (s['removed'] == dict(present=0, wrong=0, gap=0) and s['labels_losing_presence'] == 0 and s['labels_losing_longest_hold'] == 0
            and s['over_budget_labels'] == [] and s['budget_passes'] is True and label_rows(ctx, cmp, cmp, ctx['rate']) == []
            and nothing == dict(present=0, wrong=0, gap=0))


def summarize(row, cmp, cur_row):
    removed = {k: cur_row[k] - row[k] for k in ('present', 'wrong', 'gap')}
    over = [o['label_index'] for o in row['budget']['over_budget_labels']]
    return dict(present=row['present'], wrong=row['wrong'], gap=row['gap'], precision_pct=row['precision_pct'], coverage_pct=row['coverage_pct'], runs=row['runs'],
                removed=removed, removed_wrong_pct=round(100 * removed['wrong'] / cur_row['wrong'], 3), removed_gap_pct=round(100 * removed['gap'] / cur_row['gap'], 3),
                affected_false_pct=round(100 * (removed['wrong'] + removed['gap']) / max(1, sum(removed.values())), 3),
                labels_losing_presence=sum(1 for r in cmp['label_deltas'] if r['present_samples_delta'] < 0),
                labels_losing_longest_hold=sum(1 for r in cmp['label_deltas'] if r['longest_present_samples_delta'] < 0),
                over_budget_labels=over, newly_missed_labels=row['budget']['newly_missed_labels'], aggregate_pitch_safety=row['budget']['aggregate_pitch_safety'],
                budget_passes=row['budget']['passes'])


def label_rows(ctx, cmp0, cmp1, rate):
    rows = []
    for i, lab in enumerate(ctx['labels']):
        d0, d1 = cmp0['label_deltas'][i], cmp1['label_deltas'][i]
        loss = [-d0['present_samples_delta'], -d1['present_samples_delta'], -d0['longest_present_samples_delta'], -d1['longest_present_samples_delta']]
        if max(loss) > 0:
            cur = d0['current_present_samples']
            rows.append(dict(label=i, midi=lab['midi_note'], current_present=cur, allowance_samples=int(min(0.05 * cur, 0.025 * rate)),
                             presence_loss_M0=loss[0], presence_loss_M1=loss[1], hold_loss_M0=loss[2], hold_loss_M1=loss[3]))
    return rows


# P6, P7 and P8 were revised before the commit (from 0.06, 0.04, 0.30) after working out, from already-seen M0 numbers and the budget definition, that a mark in the
# interior of a label's single present run splits its longest hold; see the pre-registration, "Budget arithmetic".  No M0 or M1 outcome was computed.
ODDS = {'P1': 0.97, 'P2': 0.50, 'P3': 0.55, 'P4': 0.60, 'P5': 0.35, 'P6': 0.01, 'P7': 0.01, 'P8': 0.60, 'P9': 0.85, 'P10': 0.70}
PRED_TEXT = {
    'P1': 'identity gate: M0 reproduces every Codex number on both recordings',
    'P2': 'ordinary: M1 removes at least as large a share of CURRENT gap extra as M0 (41.945%)',
    'P3': 'ordinary: M1 loses fewer present samples than M0 (4,350)',
    'P4': 'ordinary: at least 17 labels lose presence under M1 (M0: 17)',
    'P5': 'ordinary: label 31 is within the frozen budget under M1',
    'P6': 'ordinary: label 70 is within the frozen budget under M1',
    'P7': 'ordinary: M1 passes the frozen budget (no label over, none newly missed, aggregate pitch safety)',
    'P8': 'ordinary: at least one label within budget under M0 is over budget under M1',
    'P9': 'extended-middle: M1 passes the frozen budget',
    'P10': 'ordinary: at least 99% of the CURRENT output M1 affects is false',
}


def main():
    codex = json.load(open(rm.CODEX_JSON))
    ok, loaded = plumbing(codex)
    if not ok:
        raise SystemExit('plumbing failed; no scored run')
    out = dict(schema='m3_decision_grain_mask_v1', post_hoc=True, decision_samples=DECISION, datasets={}, identity={})
    for name in chk.PINS:
        samples, quiets, audit, last, m0, horizon = loaded[name]
        ctx = context(name)
        rate, theirs = ctx['rate'], codex['datasets'][name]
        m1 = decision_mask(samples, quiets, horizon)
        cur_p = fr.by_pitch(ctx['cur_spans'], horizon)
        cur_row, _, _ = rm.variant(ctx, cur_p)
        rows, cmps = {}, {}
        for tag, marked in (('M0', m0), ('M1', m1)):
            mask_p = {p: rm.subtract(v, marked) for p, v in cur_p.items()}
            if not all(fr.size(fr.isect(mask_p[p], cur_p[p])) == fr.size(mask_p[p]) for p in cur_p):
                raise SystemExit(f'{name} {tag}: mask is not inside CURRENT')
            rows[tag], _, cmps[tag] = rm.variant(ctx, mask_p)
        ident = dict(
            current_totals_equal=dict(present=cur_row['present'], wrong_pitch=cur_row['wrong'], gap=cur_row['gap']) == dict(
                present=theirs['current']['present_pitch_samples'], wrong_pitch=theirs['current']['wrong_pitch_samples'], gap=theirs['current']['gap_extra_pitch_samples']),
            masked_totals_equal=dict(present=rows['M0']['present'], wrong_pitch=rows['M0']['wrong'], gap=rows['M0']['gap']) == dict(
                present=theirs['masked']['present_pitch_samples'], wrong_pitch=theirs['masked']['wrong_pitch_samples'], gap=theirs['masked']['gap_extra_pitch_samples']),
            comparison_equal=cmps['M0'] == theirs['comparison'], budget_equal=rows['M0']['budget'] == {k: theirs['budget'][k] for k in rows['M0']['budget']},
            runs_equal=dict(current=cur_row['runs'], masked=rows['M0']['runs']) == theirs['occupancy_runs'])
        out['identity'][name] = ident
        print(name, 'identity', json.dumps(ident))
        regions = dict(both=fr.isect(m0, m1), only_M0=rm.subtract(m0, m1), only_M1=rm.subtract(m1, m0))
        entry = dict(horizon=horizon, rate=rate, geometry=counts_only(samples, quiets, m0, m1), current=dict(present=cur_row['present'], wrong=cur_row['wrong'], gap=cur_row['gap']),
                     M0=summarize(rows['M0'], cmps['M0'], cur_row), M1=summarize(rows['M1'], cmps['M1'], cur_row),
                     removed_by_region={k: dict(samples=fr.size(v), **volumes(ctx, {p: fr.isect(c, v) for p, c in cur_p.items()})) for k, v in regions.items()})
        if name == ORDINARY:
            entry['labels'] = label_rows(ctx, cmps['M0'], cmps['M1'], rate)
        out['datasets'][name] = entry
    o, e = out['datasets'][ORDINARY], out['datasets'][[n for n in out['datasets'] if n != ORDINARY][0]]
    over0, over1 = set(o['M0']['over_budget_labels']), set(o['M1']['over_budget_labels'])
    preds = {
        'P1': all(all(v.values()) for v in out['identity'].values()),
        'P2': o['M1']['removed_gap_pct'] >= o['M0']['removed_gap_pct'],
        'P3': o['M1']['removed']['present'] < o['M0']['removed']['present'],
        'P4': o['M1']['labels_losing_presence'] >= 17,
        'P5': 31 not in over1,
        'P6': 70 not in over1,
        'P7': bool(o['M1']['budget_passes']),
        'P8': bool(over1 - over0),
        'P9': bool(e['M1']['budget_passes']),
        'P10': o['M1']['affected_false_pct'] >= 99.0,
    }
    brier = {k: round((ODDS[k] - (1.0 if v else 0.0)) ** 2, 4) for k, v in preds.items()}
    passes_both = all(d['M1']['budget_passes'] for d in out['datasets'].values())
    reading = ('VOID: the identity gate (P1) failed, so M0 does not reproduce Codex\'s numbers and no M1 number is interpreted; the plumbing fault is diagnosed and disclosed first' if not preds['P1'] else
               'LEAD ONLY: M1 passes the frozen budget on both recordings (design data; nothing is accepted; a causal trial design is Codex\'s call)' if passes_both else
               'CLOSED: M1 fails the frozen budget on at least one recording; the callback-grain rejection stands at the detector\'s own decision grain; no further variant is run')
    out.update(predictions={k: dict(text=PRED_TEXT[k], odds=ODDS[k], outcome=v, brier=brier[k]) for k, v in preds.items()}, brier_sum=round(sum(brier.values()), 4),
               hits=sum(preds.values()), reading=reading, codex_json_sha256=hashlib.sha256(open(rm.CODEX_JSON, 'rb').read()).hexdigest())
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    for name, d in out['datasets'].items():
        print(name, 'geometry', json.dumps(d['geometry']))
        for tag in ('M0', 'M1'):
            print(f"  {tag}", json.dumps({k: v for k, v in d[tag].items()}))
        print('  removed_by_region', json.dumps(d['removed_by_region']))
    print('labels (ordinary)')
    for r in out['datasets'][ORDINARY]['labels']:
        print('  ', json.dumps(r))
    print('predictions', json.dumps({k: v['outcome'] for k, v in out['predictions'].items()}), 'hits', out['hits'], 'brier', out['brier_sum'])
    print('reading:', reading)


def dry():
    codex = json.load(open(rm.CODEX_JSON))
    ok, loaded = plumbing(codex)
    for name, (samples, quiets, audit, last, m0, horizon) in loaded.items():
        print(name, 'geometry (counts only)', json.dumps(counts_only(samples, quiets, m0, decision_mask(samples, quiets, horizon))))
    return ok


if __name__ == '__main__':
    arg = sys.argv[1:]
    if arg == ['--selftest']:
        raise SystemExit(0 if plumbing(json.load(open(rm.CODEX_JSON)))[0] else 1)
    if arg == ['--dry']:
        raise SystemExit(0 if dry() else 1)
    if arg == ['--run']:
        if os.path.exists(OUT):
            raise SystemExit('refusing to overwrite ' + OUT)
        main()
    else:
        raise SystemExit(__doc__)
