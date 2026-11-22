"""What false output does the cropped-ONNX support filter leave behind?  Saved data only.

Plan, definitions, predictions R0-R8 and the reading rule are fixed in CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-PREREGISTRATION-20261122.md, committed
before this ran.  The filter is exactly the committed one of CLAUDE-M3-ONNX-SUPPORT-20261122.py (support = model spans union the native
confirmation, held forward D = 220 ms, filter = CURRENT intersect support, emitted clock); this script only classifies its output into the
orphan / tail / head / between classes of CLAUDE-M3-SPLIT-FALSE-OUTPUT-ANATOMY-20261121.py, attributing each filtered sample to the CURRENT span
it came from.  Nothing is refit.  Identity checks 1-3 of the pre-registration must pass or nothing is reported.

Usage: python3 -P -E CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py --selftest
       python3 -P -E CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py ORD_UNMOD ORD_ADAPTED
No audio, model run, job or native edit; nothing promoted.
"""
import bisect
import importlib.util
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


on = load('on', 'CLAUDE-M3-ONNX-SUPPORT-20261122.py')
split = load('split', 'CLAUDE-M3-PITCH-SPLIT-20261121.py')
ad = on.ad
from tools.native_neural_consensus import intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import score, union_spans  # noqa: E402

D_MS, SPLIT = 220, 60
SUPPORTS = ('cropped unmodified', 'cropped adapted')
CLASSES = ('orphan', 'tail', 'head', 'between')
BANDS = ('lt60', 'ge60', 'all')
ANATOMY = os.path.join(HERE, 'CLAUDE-M3-SPLIT-FALSE-OUTPUT-ANATOMY-20261121.json')
COMMITTED = os.path.join(HERE, 'CLAUDE-M3-ONNX-SUPPORT-20261122.json')
OUT = os.path.join(HERE, 'CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.json')
FILTER_KEYS = ('coverage_pct', 'precision_pct', 'wrong_removed_share', 'gap_delta')


def isect(a, b):
    """Intersection of two sorted disjoint interval lists, as an interval list."""
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if lo < hi:
            out.append([lo, hi])
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def size(items):
    return sum(r - l for l, r in items)


def band_of(pitch):
    return 'lt60' if pitch < SPLIT else 'ge60'


def stats_ms(values, rate):
    """Median / p10 / p90 in ms with the earlier anatomy's quantile convention."""
    v = sorted(values)
    if not v:
        return None
    ms = lambda x: round(x * 1000 / rate, 2)
    return dict(median=ms(statistics.median(v)), p10=ms(v[int(.1 * len(v))]), p90=ms(v[min(len(v) - 1, int(.9 * len(v)))]))


def geometry(cur_spans, labels, horizon):
    """Merged label intervals per pitch, all labels merged, and the class regions of every CURRENT span (unioned per pitch)."""
    exp, every = {}, []
    for lab in labels:
        exp.setdefault(lab['midi_note'], []).append((lab['start_sample'], lab['end_sample']))
        every.append((lab['start_sample'], lab['end_sample']))
    exp = {p: split.merged(v) for p, v in exp.items()}
    annotated = split.merged(every)
    geo = {}
    for left, right, p in union_spans([tuple(s) for s in cur_spans], sample_count=horizon):
        g = geo.setdefault(p, dict(span=[], orphan=[], head=[], tail=[], hull=[], tails=[]))
        g['span'].append([left, right])
        over = [(a, b) for a, b in exp.get(p, []) if a < right and b > left]
        if not over:
            g['orphan'].append([left, right])
            continue
        first, last = min(a for a, _ in over), max(b for _, b in over)
        if left < first:
            g['head'].append([left, first])
        if right > last:
            g['tail'].append([last, right])
            g['tails'].append((last, right))
        g['hull'].append([max(left, first), min(right, last)])
    return exp, annotated, geo


def by_pitch(spans, horizon):
    out = {}
    for left, right, p in union_spans([tuple(s) for s in spans], sample_count=horizon):
        out.setdefault(p, []).append([left, right])
    return out


def tally(spans_p, exp, annotated, geo):
    """Per-pitch class volumes of an output (CURRENT or a filter), each sample taking the class of the CURRENT span it lies in."""
    rows = {}
    for p, s in spans_p.items():
        g, e = geo.get(p), exp.get(p, [])
        if g is None or size(isect(s, g['span'])) != size(s):
            raise SystemExit(f'pitch {p}: output is not inside CURRENT')
        present = size(isect(s, e))
        hull = isect(s, g['hull'])
        row = dict(total=size(s), present=present, between=size(hull) - present, between_annotated=size(isect(hull, annotated)) - present)
        for c in ('orphan', 'head', 'tail'):
            part = isect(s, g[c])
            row[c], row[c + '_annotated'] = size(part), size(isect(part, annotated))
        rows[p] = row
    return rows


def aggregate(rows):
    keys = ('total', 'present', 'orphan', 'head', 'tail', 'between', 'orphan_annotated', 'head_annotated', 'tail_annotated', 'between_annotated')
    out = {b: {k: 0 for k in keys} for b in ('lt60', 'ge60')}
    for p, r in rows.items():
        for k in keys:
            out[band_of(p)][k] += r[k]
    out['all'] = {k: out['lt60'][k] + out['ge60'][k] for k in keys}
    for v in out.values():
        v['false'] = v['total'] - v['present']
        if v['false'] != v['orphan'] + v['head'] + v['tail'] + v['between']:
            raise SystemExit('classes do not sum to the false volume')
        v['extra'] = sum(v[c + '_annotated'] for c in CLASSES)
        v['gap'] = v['false'] - v['extra']
        v['share'] = {c: round(v[c] / (v['false'] or 1), 4) for c in CLASSES}
    return out


def tail_rows(spans_p, geo):
    rows = []
    for p, g in geo.items():
        s = spans_p.get(p, [])
        rights = [r for _, r in s]
        for last, right in g['tails']:
            i, vol, ext = bisect.bisect_right(rights, last), 0, 0
            while i < len(s) and s[i][0] < right:
                a, b = max(s[i][0], last), min(s[i][1], right)
                vol, ext = vol + b - a, max(ext, b - last)
                i += 1
            rows.append(dict(pitch=p, tail=right - last, kept=vol, extent=ext))
    return rows


def orphan_rows(spans_p, geo):
    rows = []
    for p, g in geo.items():
        s = spans_p.get(p, [])
        for left, right in g['orphan']:
            rows.append(dict(pitch=p, length=right - left, kept=size(isect(s, [[left, right]]))))
    return rows


def tail_summary(rows, rate):
    out = {}
    for band in BANDS:
        r = [x for x in rows if band == 'all' or band_of(x['pitch']) == band]
        live = [x for x in r if x['kept'] > 0]
        out[band] = dict(tail_spans=len(r), surviving=len(live), removed_entirely_share=round(1 - len(live) / len(r), 4) if r else None,
                         current_tail_ms=stats_ms([x['tail'] for x in r], rate), kept_extent_ms=stats_ms([x['extent'] for x in live], rate),
                         kept_volume_ms=stats_ms([x['kept'] for x in live], rate))
    return out


def orphan_summary(rows):
    out = {}
    for band in BANDS:
        r = [x for x in rows if band == 'all' or band_of(x['pitch']) == band]
        live = [x for x in r if x['kept'] > 0]
        out[band] = dict(orphan_spans=len(r), surviving=len(live), removed_entirely_share=round(1 - len(live) / len(r), 4) if r else None,
                         median_kept_share_of_surviving=round(statistics.median([x['kept'] / x['length'] for x in live]), 4) if live else None)
    return out


def oracle(band):
    present, false = band['present'], band['false']
    prec = lambda f: round(100 * present / (present + f), 2)
    return dict(now=prec(false), tail_cut=prec(false - band['tail']), orphan_cut=prec(false - band['orphan']),
                both_cut=prec(false - band['tail'] - band['orphan']), false=false, false_after_tail_cut=false - band['tail'],
                false_after_orphan_cut=false - band['orphan'], false_after_both=false - band['tail'] - band['orphan'])


def scorer_totals(measured):
    t = measured['pitch_sets']['totals']
    return dict(present=t['present_pitch_samples'], extra=t['extra_pitch_voice_samples'], gap=measured['pitch_sets']['unlabeled_gap_voice_samples'])


def check_sums(agg, measured, name):
    want = scorer_totals(measured)
    got = dict(present=agg['all']['present'], extra=agg['all']['extra'], gap=agg['all']['gap'])
    if got != want:
        raise SystemExit(f'{name}: class volumes do not reproduce the scorer: {got} vs {want}')
    return True


def check_current(agg, tails, rows_orphan, rate, spans_by_band):
    """Identity check 1: CURRENT's classification equals the committed anatomy JSON (ordinary)."""
    ref = json.load(open(ANATOMY))['datasets']['ordinary']['CURRENT']
    result = {}
    for band in ('lt60', 'ge60'):
        want, v = ref[band], agg[band]
        got = dict(spans=spans_by_band[band], orphan_spans=sum(1 for x in rows_orphan if band_of(x['pitch']) == band),
                   head=v['head'], tail=v['tail'], orphan=v['orphan'], between=v['between'], false_total=v['false'], present=v['present'],
                   tail_spans=tails[band]['tail_spans'], tail_ms=tails[band]['current_tail_ms'], share=v['share'])
        result[band] = all(got[k] == want[k] for k in got)
        if not result[band]:
            print('MISMATCH', band, {k: (got[k], want[k]) for k in got if got[k] != want[k]})
    return result


def filter_spans(ctx, model_spans, d):
    """Identical to ad.score_filters: CURRENT intersect (model union native, held forward d ms)."""
    horizon, rate = ctx['horizon'], ctx['rate']
    support = union_spans([*model_spans, *ctx['native']], sample_count=horizon)
    held = ad.dil.dilate(support, int(d * rate / 1000), horizon)
    return union_spans(intersect_spans(ctx['cur_spans'], held, sample_count=horizon), sample_count=horizon)


def filter_row(ctx, hybrid):
    current = ctx['current']
    ct, cg = current['pitch_sets']['totals'], current['pitch_sets']['unlabeled_gap_voice_samples']
    t, gap = hybrid['pitch_sets']['totals'], hybrid['pitch_sets']['unlabeled_gap_voice_samples']
    false = t['extra_pitch_voice_samples'] + gap
    return dict(coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
                precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
                wrong_removed_share=round(max(0, ct['extra_pitch_voice_samples'] - t['extra_pitch_voice_samples']) / max(1, ct['extra_pitch_voice_samples']), 4),
                gap_delta=gap - cg)


def current_part(ctx):
    horizon, rate = ctx['horizon'], ctx['rate']
    exp, annotated, geo = geometry(ctx['cur_spans'], ctx['labels'], horizon)
    cur_p = by_pitch(ctx['cur_spans'], horizon)
    agg = aggregate(tally(cur_p, exp, annotated, geo))
    tails = tail_summary(tail_rows(cur_p, geo), rate)
    orph = orphan_rows(cur_p, geo)
    spans_by_band = {b: sum(1 for p, s in cur_p.items() if band_of(p) == b for _ in s) for b in ('lt60', 'ge60')}
    return exp, annotated, geo, cur_p, agg, tails, orph, spans_by_band


def selftest():
    ctx = ad.dataset_context('ordinary')
    _, _, _, _, agg, tails, orph, spans_by_band = current_part(ctx)
    ident = check_current(agg, tails, orph, ctx['rate'], spans_by_band)
    sums = check_sums(agg, ctx['current'], 'CURRENT')
    print('identity 1 (CURRENT split equals committed anatomy):', ident, '| identity 2 (class sums equal scorer):', sums)
    for band in BANDS:
        v = agg[band]
        print(f"  {band}: present {v['present']:,} false {v['false']:,} (extra {v['extra']:,} gap {v['gap']:,}) shares {v['share']}")
    ok = all(ident.values()) and sums
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return ok


def main(paths):
    ctx = ad.dataset_context('ordinary')
    horizon, rate = ctx['horizon'], ctx['rate']
    exp, annotated, geo, cur_p, cur_agg, cur_tails, cur_orph, spans_by_band = current_part(ctx)
    identity = dict(current_split_equals_committed_anatomy=check_current(cur_agg, cur_tails, cur_orph, rate, spans_by_band),
                    current_sums_equal_scorer=check_sums(cur_agg, ctx['current'], 'CURRENT'))
    committed = json.load(open(COMMITTED))['ordinary']
    res = dict(schema='claude_m3_filter_residual_anatomy_v1', hold_ms=D_MS, clock='emitted_ns', horizon=horizon, rate=rate,
               current=dict(bands=cur_agg, tails=cur_tails, orphans=orphan_summary(cur_orph), oracle={b: oracle(cur_agg[b]) for b in BANDS}),
               filters={}, inputs={})
    for tag, path in zip(SUPPORTS, paths):
        model = ad.spans_from_events(ad.read_events(path), horizon, 'emitted_ns')[0]
        spans = filter_spans(ctx, model, D_MS)
        hybrid = score(spans, ctx['labels'], **ctx['clock'])
        spans_p = by_pitch(spans, horizon)
        agg = aggregate(tally(spans_p, exp, annotated, geo))
        identity[f'{tag} sums equal scorer'] = check_sums(agg, hybrid, tag)
        now, was = filter_row(ctx, hybrid), committed['sources'][tag]['by_d'][str(D_MS)]['filter']
        digest = ad.sha256(path)
        identity[f'{tag} filter row and event hash equal committed'] = (all(now[k] == was[k] for k in FILTER_KEYS)
                                                                        and digest == committed['inputs'][tag]['sha256'])
        res['inputs'][tag] = dict(path=os.path.basename(path), sha256=digest)
        tr, orr = tail_rows(spans_p, geo), orphan_rows(spans_p, geo)
        removal = {b: {c: (round(1 - agg[b][c] / cur_agg[b][c], 4) if cur_agg[b][c] else None) for c in CLASSES} for b in BANDS}
        res['filters'][tag] = dict(runs=len(spans), filter_row=now, committed_row={k: was[k] for k in FILTER_KEYS}, bands=agg, removal_share=removal,
                                   tails=tail_summary(tr, rate), orphans=orphan_summary(orr), oracle={b: oracle(agg[b]) for b in BANDS},
                                   tail_records=tr, orphan_records=orr)
    res['identity'] = identity

    def flat(d):
        return [v for x in d.values() for v in (flat(x) if isinstance(x, dict) else [x])]
    ok = all(flat(identity))
    res['identity_all_pass'] = ok
    if not ok:
        with open(OUT, 'w') as stream:
            json.dump(res, stream, indent=1, default=str)
        print('IDENTITY FAILED', json.dumps(identity))
        raise SystemExit(1)

    a, u = res['filters']['cropped adapted'], res['filters']['cropped unmodified']
    ar, ao = a['removal_share']['all'], a['oracle']['all']
    res['predictions'] = {
        'R0 all identity checks pass': ok,
        'R1 all: orphan removal share > tail removal share': ar['orphan'] > ar['tail'],
        'R2 all: tail removal share < 15%': ar['tail'] < 0.15,
        'R3 all: orphan removal share within 25-50%': 0.25 <= ar['orphan'] <= 0.50,
        'R4 lower band: tails > 50% of remaining false output': a['bands']['lt60']['share']['tail'] > 0.50,
        'R5 lower band: median kept extent of surviving tails >= 200 ms': bool(a['tails']['lt60']['kept_extent_ms']
                                                                              and a['tails']['lt60']['kept_extent_ms']['median'] >= 200),
        'R6 all: tail-cut oracle lifts precision by >= 10 points': ao['tail_cut'] - ao['now'] >= 10,
        'R7 lower band: unmodified vs adapted tail share differ by < 3 points': abs(a['bands']['lt60']['share']['tail'] - u['bands']['lt60']['share']['tail']) < 0.03,
        'R8 all: orphan-cut lift < tail-cut lift': ao['orphan_cut'] - ao['now'] < ao['tail_cut'] - ao['now']}
    shares = a['bands']['all']['share']
    largest = max(CLASSES, key=lambda c: shares[c])
    res['reading'] = dict(largest_class_of_adapted_remaining_false_output=largest, shares=shares,
                          lever={'tail': 'release cue (held-note overhang)', 'orphan': 'detection side (false notes the support confirms)'}.get(largest, 'neither (head or between)'))
    with open(OUT, 'w') as stream:
        json.dump(res, stream, indent=1, default=str)

    def line(name, agg, extra=''):
        for band in BANDS:
            v = agg[band]
            print(f"  {name:20s} {band:5s} present {v['present']:>10,} false {v['false']:>10,} (extra {v['extra']:>10,} gap {v['gap']:>10,}) "
                  f"orphan {v['orphan']:>10,} tail {v['tail']:>10,} head {v['head']:>8,} between {v['between']:>8,} | shares {v['share']}{extra}")
    print('identity', json.dumps(identity))
    line('CURRENT', cur_agg)
    for tag in SUPPORTS:
        f = res['filters'][tag]
        print(tag, 'runs', f['runs'], 'filter row', f['filter_row'])
        line(tag, f['bands'])
        for band in BANDS:
            print(f'    removal {band}:', f['removal_share'][band], '| tails', json.dumps(f['tails'][band]), '| orphans', json.dumps(f['orphans'][band]))
            print(f'    oracle {band}:', json.dumps(f['oracle'][band]))
    print('CURRENT tails', json.dumps(cur_tails))
    print('CURRENT orphans', json.dumps(res['current']['orphans']))
    print('CURRENT oracle', json.dumps(res['current']['oracle']))
    for k, v in res['predictions'].items():
        print(('PASS ' if v else 'FAIL ') + k)
    print('reading', json.dumps(res['reading']))


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        sys.exit(0 if selftest() else 1)
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
