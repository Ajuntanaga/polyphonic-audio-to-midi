"""POST HOC hold-length grid for the cropped-ONNX support on the emitted clock.  Saved data only.

Plan, predictions L0-L7 and the reading rule are fixed in CLAUDE-M3-ONNX-HOLD-GRID-PREREGISTRATION-20261122.md, committed before this ran.
Reuses CLAUDE-M3-ONNX-SUPPORT-20261122.py (and through it the committed adapted-support scorer and loser table) unchanged, replacing only the
hold grid and restricting the supports to the two cropped event sets.  The D = 220 row must reproduce the committed
CLAUDE-M3-ONNX-SUPPORT-20261122.json exactly or nothing is reported.

Usage: python3 -P -E CLAUDE-M3-ONNX-HOLD-GRID-20261122.py ORD_UNMOD ORD_ADAPTED EXT_UNMOD EXT_ADAPTED
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

GRID = [220, 260, 300, 350, 400, 500, 600]
SUPPORTS = ('cropped unmodified', 'cropped adapted')
COMMITTED = os.path.join(HERE, 'CLAUDE-M3-ONNX-SUPPORT-20261122.json')
OUT = os.path.join(HERE, 'CLAUDE-M3-ONNX-HOLD-GRID-20261122.json')
KEYS = ('coverage_pct', 'wrong_removed_share', 'gap_delta', 'labels_losing_present_or_longest')


def retained(res, tag, d):
    cur = res['ordinary']['current']['coverage_pct']
    f = res['ordinary']['sources'][tag]['by_d'][d]['filter']
    ef = res['extended-middle']['sources'][tag]['by_d'][d]['filter']
    safe = ef['labels_losing_present_or_longest'] == 0 and bool(ef['no_pitch_safety_regression'])
    return bool(cur - f['coverage_pct'] <= 0.10 and f['wrong_removed_share'] >= 0.20 and f['gap_delta'] <= -250000 and safe)


def main(paths):
    on.ad.HOLDS_MS = GRID
    on.NAMES = SUPPORTS
    res = on.analyse(paths, 'emitted_ns')
    committed = json.load(open(COMMITTED))
    identity = {}
    for ds in ('ordinary', 'extended-middle'):
        for tag in SUPPORTS:
            now = res[ds]['sources'][tag]['by_d'][220]['filter']
            was = committed[ds]['sources'][tag]['by_d']['220']['filter']
            identity[f'{ds}/{tag}'] = all(now[k] == was[k] for k in KEYS)
    res['identity_with_committed_d220'] = identity
    if not all(identity.values()):
        print('IDENTITY FAILED', json.dumps(identity))
        raise SystemExit(1)

    summary = {}
    for tag in SUPPORTS:
        rows = {}
        for d in GRID:
            x = res['ordinary']['sources'][tag]['by_d'][d]
            f, b = x['filter'], x['budget']
            e = res['extended-middle']['sources'][tag]['by_d'][d]
            rows[d] = dict(coverage=f['coverage_pct'], precision=f['precision_pct'], wrong_removed=f['wrong_removed_share'], gap_delta=f['gap_delta'],
                           labels_losing=f['labels_losing_present_or_longest'], over_budget=b['over_budget_labels'], max_loss_ms=x['loss_summary']['max_loss_ms'],
                           budget_pass=b['passes'], strict=bool(f['no_pitch_safety_regression']), retained=retained(res, tag, d),
                           ext_labels_losing=e['filter']['labels_losing_present_or_longest'], ext_strict=bool(e['filter']['no_pitch_safety_regression']))
        first = next((d for d in GRID if rows[d]['budget_pass']), None)
        summary[tag] = dict(rows=rows, smallest_budget_pass=first, retained_at_smallest=rows[first]['retained'] if first else None,
                            smallest_strict=next((d for d in GRID if rows[d]['strict']), None))
    res['summary'] = summary

    chk = {}
    for tag in SUPPORTS:
        r = [summary[tag]['rows'][d] for d in GRID]
        chk[tag] = dict(cov_nondecreasing=all(a['coverage'] <= b['coverage'] + 1e-9 for a, b in zip(r, r[1:])),
                        wrong_nonincreasing=all(a['wrong_removed'] >= b['wrong_removed'] - 1e-9 for a, b in zip(r, r[1:])),
                        labels_nonincreasing=all(a['labels_losing'] >= b['labels_losing'] for a, b in zip(r, r[1:])))
    res['monotone_checks'] = chk
    a, u = summary['cropped adapted'], summary['cropped unmodified']
    ar = a['rows'][a['smallest_budget_pass']] if a['smallest_budget_pass'] else None
    res['predictions'] = {
        'L0 D220 identity with committed JSON': all(identity.values()),
        'L1 monotone in D (coverage, wrong removed, labels losing)': all(all(v.values()) for v in chk.values()),
        'L2 adapted passes the budget at some grid D': a['smallest_budget_pass'] is not None,
        'L3 smallest adapted passing D <= 350': a['smallest_budget_pass'] is not None and a['smallest_budget_pass'] <= 350,
        'L4 at that D wrong removed >= 20%': bool(ar and ar['wrong_removed'] >= 0.20),
        'L5 at that D gap delta <= -250000': bool(ar and ar['gap_delta'] <= -250000),
        'L6 unmodified needs larger D than adapted, or never passes':
            u['smallest_budget_pass'] is None or (a['smallest_budget_pass'] is not None and u['smallest_budget_pass'] > a['smallest_budget_pass']),
        'L7 strict gate True at some grid D for adapted': a['smallest_strict'] is not None}

    def verdict(s):
        if s['smallest_budget_pass'] is None:
            return 'C support gap (budget fails at every grid D)'
        return 'A reconciled' if s['retained_at_smallest'] else 'B trade-off (budget passes only where the benefit is not retained)'
    res['reading'] = {tag: verdict(summary[tag]) for tag in SUPPORTS}
    with open(OUT, 'w') as stream:
        json.dump(res, stream, indent=1, default=str)

    for tag in SUPPORTS:
        print(tag)
        for d in GRID:
            r = summary[tag]['rows'][d]
            print(f"  D{d:<4d} cov {r['coverage']:.3f} prec {r['precision']:.2f} wrongRemoved {r['wrong_removed']:.4f} gap {r['gap_delta']:>9d} labels {r['labels_losing']:2d} "
                  f"maxLossMs {r['max_loss_ms']:7.2f} over {r['over_budget']} budget {r['budget_pass']} strict {r['strict']} retained {r['retained']} "
                  f"ext {r['ext_labels_losing']}/{r['ext_strict']}")
        print('  smallest budget pass', summary[tag]['smallest_budget_pass'], 'smallest strict', summary[tag]['smallest_strict'])
    print('monotone', json.dumps(chk))
    for k, v in res['predictions'].items():
        print(('PASS ' if v else 'FAIL ') + k)
    print('reading', json.dumps(res['reading']))


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
