"""Adapted same-pitch tails by register and label length, paired with the unmodified run.  Plan and predictions T1-T4 are fixed in
CLAUDE-M3-ADAPTED-TAIL-BREAKDOWN-PREREGISTRATION-20261122.md (commit fe01a1d), written before this script was run.

Saved data only (Codex's unmodified and adapted TensorFlow event files, run 45022134487, availability clock, ordinary corpus), the labels.
No audio, model run, job or native edit; nothing promoted; not a gate.

Unit: every adapted gap piece that is carried in (the span covers the sample before the gap) while a label of the same pitch was active there.
Adapted tail = the piece length; unmodified tail = the unmodified run's coverage of the same pitch running continuously from the gap start,
capped at the same gap end.  Pair difference = adapted - unmodified (ms).

Usage: python3 -P -E CLAUDE-M3-ADAPTED-TAIL-BREAKDOWN-20261122.py [--selftest]
         (no arguments: the saved run files; writes CLAUDE-M3-ADAPTED-TAIL-BREAKDOWN-20261122.json next to this file)
       python3 -P -E CLAUDE-M3-ADAPTED-TAIL-BREAKDOWN-20261122.py --out RESULT.json ORD_BASE ORD_CAND
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('ge', os.path.join(HERE, 'CLAUDE-M3-ADAPTED-GAP-EXTRAS-20261122.py'))
ge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ge)

OUT = os.path.join(HERE, 'CLAUDE-M3-ADAPTED-TAIL-BREAKDOWN-20261122.json')
BANDS = (('low_le47', lambda p: p <= 47), ('mid_48_59', lambda p: 48 <= p <= 59), ('high_ge60', lambda p: p >= 60))


def tails(spans_a, spans_u, labels, horizon, rate):
    """One row per adapted same-pitch carried-in tail: (pitch, label_ms, adapted_ms, unmodified_ms, gap_ms, adapted_reaches_gap_end, unmodified_reaches_gap_end)."""
    active = ge.merge([(x['start_sample'], x['end_sample']) for x in labels])
    gaps = ge.complement(active, horizon)
    cover_u = ge.by_pitch(spans_u)
    rows = []
    for span_l, gstart, lo, hi, p in ge.gap_segments(spans_a, gaps):
        if not (span_l < gstart == lo):
            continue
        label = next((x for x in labels if x['midi_note'] == p and x['start_sample'] <= gstart - 1 < x['end_sample']), None)
        if label is None:
            continue
        gap_end = next(b for a, b in gaps if a == gstart)
        u_end = next((min(b, gap_end) for a, b in cover_u.get(p, []) if a <= gstart < b), gstart)
        rows.append((p, (label['end_sample'] - label['start_sample']) * 1000 / rate, (hi - lo) * 1000 / rate, (u_end - gstart) * 1000 / rate,
                     (gap_end - gstart) * 1000 / rate, hi == gap_end, u_end == gap_end))
    return rows


def med(values):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[len(ordered) // 2], 1)


def pct(values, q):
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 1) if ordered else None


def summarize(rows):
    diffs = [r[2] - r[3] for r in rows]
    return dict(count=len(rows), adapted_median_ms=med([r[2] for r in rows]), unmodified_median_ms=med([r[3] for r in rows]),
                diff_median_ms=med(diffs), diff_p90_ms=pct(diffs, 0.9),
                adapted_longer_pct=round(100 * sum(1 for d in diffs if d > 0) / len(diffs), 1) if diffs else None)


def breakdown(rows):
    out = dict(all=summarize(rows), by_band={name: summarize([r for r in rows if test(r[0])]) for name, test in BANDS})
    lengths = sorted(r[1] for r in rows)
    if lengths:
        cut1, cut2 = lengths[len(lengths) // 3], lengths[2 * len(lengths) // 3]
        out['label_length_terciles_ms'] = dict(cut1=round(cut1, 1), cut2=round(cut2, 1))
        out['by_label_length_tercile'] = dict(
            short=summarize([r for r in rows if r[1] < cut1]),
            middle=summarize([r for r in rows if cut1 <= r[1] < cut2]),
            long=summarize([r for r in rows if r[1] >= cut2]))
    return out


def censoring(rows):
    """POST HOC (not registered): the tail is cut off by the next label, so it is censored at the gap length.  Per gap-length stratum, the share of
    label ends where each run is still sounding at the end of the gap, and the medians."""
    strata = dict(all=rows, gap_lt_110ms=[r for r in rows if r[4] < 110], gap_110_to_300ms=[r for r in rows if 110 <= r[4] < 300],
                  gap_ge_300ms=[r for r in rows if r[4] >= 300])
    out = {}
    for name, part in strata.items():
        n = len(part)
        out[name] = dict(count=n,
                         adapted_reaches_gap_end_pct=round(100 * sum(1 for r in part if r[5]) / n, 1) if n else None,
                         unmodified_reaches_gap_end_pct=round(100 * sum(1 for r in part if r[6]) / n, 1) if n else None,
                         adapted_median_ms=med([r[2] for r in part]), unmodified_median_ms=med([r[3] for r in part]),
                         adapted_median_ms_ending_inside_gap=med([r[2] for r in part if not r[5]]))
    return out


def verdicts(res):
    a, bands, terc = res['all'], res['by_band'], res.get('by_label_length_tercile', {})
    low, high = bands['low_le47'], bands['high_ge60']
    short, long_ = terc.get('short'), terc.get('long')
    return dict(
        T1=dict(adapted_longer_pct=a['adapted_longer_pct'], passes=(a['adapted_longer_pct'] or 0) >= 80),
        T2=dict(diff_median_ms=a['diff_median_ms'], passes=a['diff_median_ms'] is not None and 30 <= a['diff_median_ms'] <= 100),
        T3=dict(low_minus_high_adapted_median_ms=None if low['count'] == 0 or high['count'] == 0 else round(low['adapted_median_ms'] - high['adapted_median_ms'], 1),
                counts=dict(low=low['count'], high=high['count']),
                passes=low['count'] > 0 and high['count'] > 0 and low['adapted_median_ms'] - high['adapted_median_ms'] >= 20),
        T4=dict(short_minus_long_diff_median_ms=None if not short or not long_ or not short['count'] or not long_['count'] else round(short['diff_median_ms'] - long_['diff_median_ms'], 1),
                passes=bool(short and long_ and short['count'] and long_['count'] and abs(short['diff_median_ms'] - long_['diff_median_ms']) < 30)))


def selftest():
    labels = [dict(start_sample=10, end_sample=20, midi_note=40), dict(start_sample=40, end_sample=50, midi_note=60)]
    unmod = [(10, 22, 40), (40, 50, 60)]
    adapt = [(10, 28, 40), (40, 55, 60)]
    rows = tails(adapt, unmod, labels, 60, 1000)
    assert sorted(rows) == [(40, 10.0, 8.0, 2.0, 20.0, False, False), (60, 10.0, 5.0, 0.0, 10.0, False, False)], rows
    res = breakdown(rows)
    assert res['all']['count'] == 2 and res['all']['adapted_longer_pct'] == 100.0 and res['by_band']['low_le47']['count'] == 1, res
    assert res['by_band']['mid_48_59']['count'] == 0 and res['by_band']['high_ge60']['count'] == 1, res
    # an adapted tail that ends exactly with the unmodified one is not "longer"
    same = tails([(10, 22, 40)], [(10, 22, 40)], labels, 60, 1000)
    assert same == [(40, 10.0, 2.0, 2.0, 20.0, False, False)] and summarize(same)['adapted_longer_pct'] == 0.0, same
    # a tail that runs to the gap end is censored: adapted reaches it, the unmodified run stops at 22
    capped = tails([(10, 45, 40)], [(10, 22, 40)], labels, 60, 1000)
    assert capped == [(40, 10.0, 20.0, 2.0, 20.0, True, False)], capped
    cs = censoring(capped)
    assert cs['all']['adapted_reaches_gap_end_pct'] == 100.0 and cs['all']['unmodified_reaches_gap_end_pct'] == 0.0 and cs['gap_lt_110ms']['count'] == 1, cs
    print('selftest ok')


def main(paths=None, out_path=OUT):
    paths = paths or tuple(os.path.join(ge.EVENTS, run + '_tensorflow', 'ordinary-events.json') for run in ('unmodified', 'adapted'))
    ctx = ge.ad.dataset_context('ordinary')
    horizon, rate, labels = ctx['horizon'], ctx['rate'], ctx['labels']
    spans = {run: ge.ad.spans_from_events(ge.ad.read_events(path), horizon, 'available_ns')[0] for run, path in zip(('unmodified', 'adapted'), paths)}
    rows = tails(spans['adapted'], spans['unmodified'], labels, horizon, rate)
    res = breakdown(rows)
    res['verdicts'] = verdicts(res)
    res['clock'] = 'available_ns'
    res['post_hoc_gap_cap'] = censoring(rows)
    # POST HOC: labels where the unmodified run has a same-pitch tail and the adapted run has none (the adapted run lost a tail)
    lost = tails(spans['unmodified'], spans['adapted'], labels, horizon, rate)
    res['post_hoc_unmodified_tails_where_adapted_has_none'] = sum(1 for r in lost if r[3] == 0)
    print(json.dumps(res, indent=1))
    with open(out_path, 'w') as stream:
        json.dump(res, stream, indent=1)


if __name__ == '__main__':
    args = sys.argv[1:]
    if args == ['--selftest']:
        selftest()
    elif not args:
        main()
    elif len(args) == 4 and args[0] == '--out':
        main((args[2], args[3]), out_path=args[1])
    else:
        raise SystemExit(__doc__)
