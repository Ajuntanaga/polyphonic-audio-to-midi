"""Score the cropped-ONNX detector events of run 45034216124 as the support of the CURRENT filter, on the measured emitted clock.  Saved data only.

The plan, the predictions S0-S8, the frozen label budget and the reading rule are fixed in CLAUDE-M3-ONNX-SUPPORT-PREREGISTRATION-20261122.md,
committed before any of the four event files was opened.  This script only implements that plan, reusing the committed adapted-support scorer
(CLAUDE-M3-ADAPTED-SUPPORT-20261122.py: support = model spans union the native confirmation, held forward D ms, filter = CURRENT intersect support)
and the committed per-label loss table (CLAUDE-M3-ADAPTED-SUPPORT-LOSERS-20261122.py).  Nothing is refit.

Four supports per corpus: arm A (the saved ONNX offline causal run), the cropped unmodified events, the cropped adapted events, and arm A union
the cropped adapted events.  D in {50, 220}.  Primary clock: emitted_ns (FIFO completion, measured).  `--clock available_ns` is a POST HOC diagnostic.

Usage: python3 -P -E CLAUDE-M3-ONNX-SUPPORT-20261122.py [--clock available_ns] ORD_UNMOD ORD_ADAPTED EXT_UNMOD EXT_ADAPTED
No audio, model run, job or native edit; nothing promoted.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ad = load('ad', 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py')
lo = load('lo', 'CLAUDE-M3-ADAPTED-SUPPORT-LOSERS-20261122.py')
union_spans = ad.union_spans

EXPECTED_EVENTS = dict(ordinary=(1192, 1223), **{'extended-middle': (28, 42)})   # Codex's detector-event counts for this run
BUDGET_MS, BUDGET_SHARE = 25.0, 0.05                                            # frozen in CLAUDE-M3-LABEL-RULE-DECISION-20261122.md
NAMES = ('arm A', 'cropped unmodified', 'cropped adapted', 'arm A union cropped adapted')


def budget(rows, filt):
    """The frozen option-2 label budget for one support, one D, one corpus."""
    over = [r['label'] for r in rows
            if r['lost_ms'] > BUDGET_MS or (r['lost_share'] or 0) > BUDGET_SHARE
            or r['longest_lost_ms'] > BUDGET_MS or (r['longest_lost_share'] or 0) > BUDGET_SHARE]
    missed = [r['label'] for r in rows if (r['lost_share'] or 0) >= 0.9999]
    return dict(over_budget_labels=over, newly_missed_labels=missed, wrong_delta=filt['wrong_delta'], gap_delta=filt['gap_delta'],
                passes=not over and not missed and filt['wrong_delta'] <= 0 and filt['gap_delta'] <= 0)


def analyse(paths, clock):
    out = {}
    for dataset, (p_unmod, p_adapt) in (('ordinary', paths[:2]), ('extended-middle', paths[2:])):
        ctx = ad.dataset_context(dataset)
        horizon = ctx['horizon']
        spans, audits, events = {'arm A': ctx['arm_a']}, {}, {}
        for tag, path in (('cropped unmodified', p_unmod), ('cropped adapted', p_adapt)):
            events[tag] = len(ad.read_events(path))
            spans[tag], audits[tag] = ad.spans_from_events(ad.read_events(path), horizon, clock)
        spans['arm A union cropped adapted'] = union_spans([*spans['arm A'], *spans['cropped adapted']], sample_count=horizon)
        sources = {}
        for name in NAMES:
            filters = ad.score_filters(ctx, spans[name])
            by_d = {}
            for d in ad.HOLDS_MS:
                rows = lo.loss_rows(ctx, spans[name], d)
                by_d[d] = dict(filter=filters[d], loss_summary=lo.summary(rows), losers=rows, budget=budget(rows, filters[d]))
            sources[name] = dict(runs=len(spans[name]), by_d=by_d)
        out[dataset] = dict(sources=sources, event_audit=audits, event_counts=events,
                            inputs={tag: dict(path=os.path.basename(p), sha256=ad.sha256(p))
                                    for tag, p in (('cropped unmodified', p_unmod), ('cropped adapted', p_adapt))})
        out[dataset]['current'] = dict(coverage_pct=round(100 * ctx['current']['pitch_sets']['totals']['present_pitch_samples']
                                                          / ctx['current']['pitch_sets']['totals']['expected_pitch_samples'], 4))
    return out


def predictions(res):
    o, e = res['ordinary']['sources'], res['extended-middle']['sources']
    u, a = o['cropped unmodified']['by_d'][220], o['cropped adapted']['by_d'][220]
    base = o['arm A']['by_d'][220]
    ok_counts = all(res[ds]['event_counts'][t] == n for ds, pair in EXPECTED_EVENTS.items()
                    for t, n in zip(('cropped unmodified', 'cropped adapted'), pair))
    pairing = all(res[ds]['event_audit'][t]['pairing_valid'] for ds in ('ordinary', 'extended-middle') for t in ('cropped unmodified', 'cropped adapted'))
    return {
        'S0 all four files pair-valid and event counts equal Codex 1192/1223/28/42': bool(ok_counts and pairing),
        'S1 unmodified: 5-7 labels losing, wrong removed 21-24% (D220 ordinary)':
            5 <= u['filter']['labels_losing_present_or_longest'] <= 7 and 0.21 <= u['filter']['wrong_removed_share'] <= 0.24,
        'S2 adapted loses no more labels than unmodified (D220 ordinary)':
            a['filter']['labels_losing_present_or_longest'] <= u['filter']['labels_losing_present_or_longest'],
        'S3 adapted removes at least as much wrong output as unmodified (D220 ordinary)':
            a['filter']['wrong_removed_share'] >= u['filter']['wrong_removed_share'],
        'S4 the model has a say: both lose at most 34 labels at D50 ordinary':
            all(o[t]['by_d'][50]['filter']['labels_losing_present_or_longest'] <= 34 for t in ('cropped unmodified', 'cropped adapted')),
        'S5 emitted lag costs: adapted loses at least 5 labels at D220 ordinary':
            a['filter']['labels_losing_present_or_longest'] >= 5,
        'S6 extended-middle D220: both cropped supports 0 labels losing and the safety flag True':
            all(e[t]['by_d'][220]['filter']['labels_losing_present_or_longest'] == 0 and e[t]['by_d'][220]['filter']['no_pitch_safety_regression']
                for t in ('cropped unmodified', 'cropped adapted')),
        'S7 both cropped supports fail the frozen label budget at D220 ordinary': not u['budget']['passes'] and not a['budget']['passes'],
        'S8 adapted D220 ordinary coverage within 39.946-39.986 and precision >= 59.0':
            39.946 <= a['filter']['coverage_pct'] <= 39.986 and a['filter']['precision_pct'] >= 59.0,
    }


def reading(res):
    """Pre-fixed reading rule: does the cropped path retain the cleanup benefit?  Judged on the cropped ADAPTED support and the cropped UNMODIFIED support separately."""
    cur = res['ordinary']['current']['coverage_pct']
    ext = res['extended-middle']['sources']
    verdict = {}
    for tag in ('cropped unmodified', 'cropped adapted'):
        f = res['ordinary']['sources'][tag]['by_d'][220]['filter']
        ef = ext[tag]['by_d'][220]['filter']
        safe = ef['labels_losing_present_or_longest'] == 0 and bool(ef['no_pitch_safety_regression'])
        verdict[tag] = dict(retained=bool(cur - f['coverage_pct'] <= 0.10 and f['wrong_removed_share'] >= 0.20 and f['gap_delta'] <= -250000 and safe),
                            coverage_loss_pts=round(cur - f['coverage_pct'], 4), wrong_removed_share=f['wrong_removed_share'], gap_delta=f['gap_delta'], extended_middle_safe=safe)
    return verdict


def main(paths, clock):
    res = analyse(paths, clock)
    res['clock'] = clock
    res['predictions' if clock == 'emitted_ns' else 'post_hoc_same_checks_on_' + clock] = predictions(res)
    res['reading'] = reading(res)
    out = os.path.join(HERE, 'CLAUDE-M3-ONNX-SUPPORT-20261122' + ('' if clock == 'emitted_ns' else '-' + clock) + '.json')
    with open(out, 'w') as stream:
        json.dump(res, stream, indent=1, default=str)
    for dataset in ('ordinary', 'extended-middle'):
        print(dataset, res[dataset]['event_counts'], json.dumps(res[dataset]['inputs']))
        for name in NAMES:
            for d in ad.HOLDS_MS:
                x = res[dataset]['sources'][name]['by_d'][d]
                f = x['filter']
                print(f"  {name:28s} D{d:<3d} cov {f['coverage_pct']:.3f} prec {f['precision_pct']:.2f} wrongRemoved {f['wrong_removed_share']:.4f} gap {f['gap_delta']:>9d} "
                      f"labels {f['labels_losing_present_or_longest']:3d} maxLossMs {x['loss_summary']['max_loss_ms']:7.2f} overBudget {len(x['budget']['over_budget_labels']):3d} "
                      f"budgetPass {x['budget']['passes']} safety {f['no_pitch_safety_regression']}")
    for k, v in res['predictions' if clock == 'emitted_ns' else 'post_hoc_same_checks_on_' + clock].items():
        print(('PASS ' if v else 'FAIL ') + k)
    print('reading', json.dumps(res['reading']))


if __name__ == '__main__':
    args, clock = sys.argv[1:], 'emitted_ns'
    if args[:1] == ['--clock']:
        clock, args = args[1], args[2:]
    if len(args) != 4 or clock not in ('emitted_ns', 'available_ns'):
        raise SystemExit(__doc__)
    main(args, clock)
