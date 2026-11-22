"""POST HOC candidate: an onset grace for the cropped-ONNX support filter.  Saved data only.

Plan, predictions G0-G7 and the reading rule are fixed in CLAUDE-M3-ONNX-ONSET-GRACE-PREREGISTRATION-20261122.md, committed before this ran.
filter = (CURRENT intersect support held forward D ms) union (the first G ms of every CURRENT span).  Everything else (events, scorer, frozen label
budget, retained rule) is reused unchanged from CLAUDE-M3-ONNX-SUPPORT-20261122.py.  G = 0 must reproduce the committed D = 220 JSON
(CLAUDE-M3-ONNX-SUPPORT-20261122.json) and D = 260 hold-grid JSON (CLAUDE-M3-ONNX-HOLD-GRID-20261122.json) exactly or nothing is reported.

Usage: python3 -P -E CLAUDE-M3-ONNX-ONSET-GRACE-20261122.py ORD_UNMOD ORD_ADAPTED EXT_UNMOD EXT_ADAPTED
No audio, model run, job or native edit; nothing promoted.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('on', os.path.join(HERE, 'CLAUDE-M3-ONNX-SUPPORT-20261122.py'))
on = importlib.util.module_from_spec(spec)
spec.loader.exec_module(on)
ad, lo = on.ad, on.lo
from tools.native_neural_consensus import intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402

D_GRID, G_GRID = (220, 260), (0, 10, 20, 30, 40, 50, 75, 100)
SUPPORTS = ('cropped unmodified', 'cropped adapted')
OUT = os.path.join(HERE, 'CLAUDE-M3-ONNX-ONSET-GRACE-20261122.json')
KEYS = ('coverage_pct', 'wrong_removed_share', 'gap_delta', 'labels_losing_present_or_longest')


def cell(ctx, model_spans, d, g):
    horizon, rate, current = ctx['horizon'], ctx['rate'], ctx['current']
    ct, cg = current['pitch_sets']['totals'], current['pitch_sets']['unlabeled_gap_voice_samples']
    cur_false = ct['extra_pitch_voice_samples'] + cg
    support = union_spans([*model_spans, *ctx['native']], sample_count=horizon)
    held = ad.dil.dilate(support, int(d * rate / 1000), horizon)
    kept = intersect_spans(ctx['cur_spans'], held, sample_count=horizon)
    gs = int(g * rate / 1000)
    grace = [(l, min(r, l + gs), p) for l, r, p in ctx['cur_spans']] if gs > 0 else []
    spans = union_spans([*kept, *grace], sample_count=horizon)
    hybrid = score(spans, ctx['labels'], **ctx['clock'])
    cmp = compare(current, hybrid)
    t = hybrid['pitch_sets']['totals']
    gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
    false = t['extra_pitch_voice_samples'] + gap
    losing = [r for r in cmp['label_deltas'] if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0]
    filt = dict(
        coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
        precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
        wrong_delta=t['extra_pitch_voice_samples'] - ct['extra_pitch_voice_samples'],
        wrong_removed_share=round(max(0, ct['extra_pitch_voice_samples'] - t['extra_pitch_voice_samples']) / max(1, ct['extra_pitch_voice_samples']), 4),
        gap_delta=gap - cg, labels_losing_present_or_longest=len(losing), no_pitch_safety_regression=cmp['no_pitch_safety_regression'])
    cur = {lab['label_index']: lab for lab in current['labels']}
    ms = 1000.0 / rate
    rows = []
    for r in losing:
        lab = cur[r['label_index']]
        present = lab['present_samples']
        lost = -min(r['present_samples_delta'], 0)
        longest_lost = -min(r['longest_present_samples_delta'], 0)
        rows.append(dict(label=r['label_index'], pitch=lab['midi_note'], current_present_ms=round(present * ms, 1), lost_ms=round(lost * ms, 2),
                         lost_share=round(lost / present, 4) if present else None, longest_lost_ms=round(longest_lost * ms, 2),
                         longest_lost_share=round(longest_lost / lab['longest_present_samples'], 4) if lab['longest_present_samples'] else None))
    return dict(filter=filt, budget=on.budget(rows, filt), max_loss_ms=lo.summary(rows)['max_loss_ms'], losers=rows)


def main(paths):
    res, ctxs = {}, {}
    for dataset, (p_unmod, p_adapt) in (('ordinary', paths[:2]), ('extended-middle', paths[2:])):
        ctx = ctxs[dataset] = ad.dataset_context(dataset)
        spans = {tag: ad.spans_from_events(ad.read_events(path), ctx['horizon'], 'emitted_ns')[0]
                 for tag, path in (('cropped unmodified', p_unmod), ('cropped adapted', p_adapt))}
        res[dataset] = {tag: {d: {g: cell(ctx, spans[tag], d, g) for g in G_GRID} for d in D_GRID} for tag in SUPPORTS}
        res[dataset]['current_coverage_pct'] = round(100 * ctx['current']['pitch_sets']['totals']['present_pitch_samples']
                                                     / ctx['current']['pitch_sets']['totals']['expected_pitch_samples'], 4)
    # identity of G = 0 with the committed D = 220 and D = 260 rows
    c220 = json.load(open(os.path.join(HERE, 'CLAUDE-M3-ONNX-SUPPORT-20261122.json')))
    c260 = json.load(open(os.path.join(HERE, 'CLAUDE-M3-ONNX-HOLD-GRID-20261122.json')))
    identity = {}
    for ds in ('ordinary', 'extended-middle'):
        for tag in SUPPORTS:
            for d, src in ((220, c220), (260, c260)):
                was = src[ds]['sources'][tag]['by_d'][str(d)]['filter']
                now = res[ds][tag][d][0]['filter']
                identity[f'{ds}/{tag}/D{d}'] = all(now[k] == was[k] for k in KEYS)
    res['identity_g0'] = identity
    if not all(identity.values()):
        print('IDENTITY FAILED', json.dumps(identity))
        raise SystemExit(1)

    cur = res['ordinary']['current_coverage_pct']

    def retained(tag, d, g):
        f, e = res['ordinary'][tag][d][g]['filter'], res['extended-middle'][tag][d][g]['filter']
        safe = e['labels_losing_present_or_longest'] == 0 and bool(e['no_pitch_safety_regression'])
        return bool(cur - f['coverage_pct'] <= 0.10 and f['wrong_removed_share'] >= 0.20 and f['gap_delta'] <= -250000 and safe)

    summary = {}
    for tag in SUPPORTS:
        for d in D_GRID:
            cells = res['ordinary'][tag][d]
            first = next((g for g in G_GRID if cells[g]['budget']['passes']), None)
            summary[f'{tag}/D{d}'] = dict(
                smallest_budget_pass_g=first, retained_at_smallest=retained(tag, d, first) if first is not None else None,
                smallest_strict_g=next((g for g in G_GRID if cells[g]['filter']['no_pitch_safety_regression']), None),
                rows={g: dict(cov=cells[g]['filter']['coverage_pct'], prec=cells[g]['filter']['precision_pct'], wrong_removed=cells[g]['filter']['wrong_removed_share'],
                              gap=cells[g]['filter']['gap_delta'], labels=cells[g]['filter']['labels_losing_present_or_longest'],
                              max_loss_ms=cells[g]['max_loss_ms'], over=cells[g]['budget']['over_budget_labels'], budget=cells[g]['budget']['passes'],
                              strict=bool(cells[g]['filter']['no_pitch_safety_regression']), retained=retained(tag, d, g),
                              ext=res['extended-middle'][tag][d][g]['filter']['labels_losing_present_or_longest']) for g in G_GRID})
    res['summary'] = summary
    mono = {}
    for tag in SUPPORTS:
        for d in D_GRID:
            r = [res['ordinary'][tag][d][g]['filter'] for g in G_GRID]
            mono[f'{tag}/D{d}'] = all(a['coverage_pct'] <= b['coverage_pct'] + 1e-9 and a['wrong_removed_share'] >= b['wrong_removed_share'] - 1e-9
                                      and a['labels_losing_present_or_longest'] >= b['labels_losing_present_or_longest'] for a, b in zip(r, r[1:]))
    a220, u220, a260 = summary['cropped adapted/D220'], summary['cropped unmodified/D220'], summary['cropped adapted/D260']
    g = a220['smallest_budget_pass_g']
    row = a220['rows'][g] if g is not None else None
    res['predictions'] = {
        'G0 G=0 identity with committed D220 and D260 rows': all(identity.values()),
        'G1 monotone in G (all cells)': all(mono.values()),
        'G2 adapted D220 passes the budget at some G': g is not None,
        'G3 smallest such G <= 30': g is not None and g <= 30,
        'G4 at that G wrong removed >= 20%': bool(row and row['wrong_removed'] >= 0.20),
        'G5 at that G gap delta <= -250000': bool(row and row['gap'] <= -250000),
        'G6 unmodified D220 never passes the budget': u220['smallest_budget_pass_g'] is None,
        'G7 adapted D260 strict gate True at some G': a260['smallest_strict_g'] is not None}
    res['reading'] = ('C no grid G passes' if g is None else
                      ('A reconciled' if a220['retained_at_smallest'] else 'B trade-off (budget passes only where the benefit is not retained)'))
    with open(OUT, 'w') as stream:
        json.dump(res, stream, indent=1, default=str)

    for key, s in summary.items():
        print(key, 'smallest budget pass G', s['smallest_budget_pass_g'], 'retained there', s['retained_at_smallest'], 'smallest strict G', s['smallest_strict_g'])
        for gg in G_GRID:
            r = s['rows'][gg]
            print(f"  G{gg:<3d} cov {r['cov']:.3f} prec {r['prec']:.2f} wrongRemoved {r['wrong_removed']:.4f} gap {r['gap']:>9d} labels {r['labels']:2d} "
                  f"maxLossMs {r['max_loss_ms']:7.2f} over {r['over']} budget {r['budget']} strict {r['strict']} retained {r['retained']} ext {r['ext']}")
    print('monotone', json.dumps(mono))
    for k, v in res['predictions'].items():
        print(('PASS ' if v else 'FAIL ') + k)
    print('reading', res['reading'])


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
