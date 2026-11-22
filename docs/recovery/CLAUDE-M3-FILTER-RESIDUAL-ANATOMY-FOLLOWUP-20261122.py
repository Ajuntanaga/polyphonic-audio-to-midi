"""POST HOC, NOT PRE-REGISTERED.  How much of the tail-cut oracle survives a release cue that fires late?  Saved data only.

Written after CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py showed the tail class is 62.7% of the cropped-adapted filter's remaining false output
and 10.5% of CURRENT's tail volume is all the filter removes, and that the registered tail-cut oracle lifts precision from 59.12% to 79.50%.  The
oracle cuts every tail at the last label end, which only the labels know.  A release cue has a delay x, so this cuts every tail at (last label end + x):
remaining false = false - tail volume + the output kept in the first x ms of each tail.  x = 0 must reproduce the registered oracle and x beyond the
longest tail must reproduce the filter itself, or nothing is reported.  Also lists the tail volume by register band (the earlier false-output band
edges) and where the remaining tail sits (under another label or in no label).

Usage: python3 -P -E CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-FOLLOWUP-20261122.py ORD_UNMOD ORD_ADAPTED
No audio, model run, job or native edit; nothing promoted.
"""
import bisect
import importlib.util
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('fr', os.path.join(HERE, 'CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py'))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
OUT = os.path.join(HERE, 'CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-FOLLOWUP-20261122.json')
X_GRID_MS = (0, 25, 50, 75, 100, 150, 200, 300, 500, 10 ** 6)
EDGES = (0, 40, 45, 53, 57, 60, 61, 64, 72, 200)   # the register bands of CLAUDE-M3-FALSE-OUTPUT-BANDS-20261122.py


def kept_in_first(spans_p, geo, x):
    """Output kept in the first x samples of every tail, per pitch."""
    out = {}
    for p, g in geo.items():
        s = spans_p.get(p, [])
        rights = [r for _, r in s]
        total = 0
        for last, right in g['tails']:
            hi = min(right, last + x)
            i = bisect.bisect_right(rights, last)
            while i < len(s) and s[i][0] < hi:
                total += min(s[i][1], hi) - max(s[i][0], last)
                i += 1
        out[p] = total
    return out


def band_name(p):
    for lo, hi in zip(EDGES, EDGES[1:]):
        if lo <= p < hi:
            return f'{lo}-{hi - 1}'


def main(paths):
    ctx = fr.ad.dataset_context('ordinary')
    horizon, rate = ctx['horizon'], ctx['rate']
    exp, annotated, geo, cur_p, cur_agg, _, _, _ = fr.current_part(ctx)
    outputs = {'CURRENT': (cur_p, cur_agg)}
    for tag, path in zip(fr.SUPPORTS, paths):
        model = fr.ad.spans_from_events(fr.ad.read_events(path), horizon, 'emitted_ns')[0]
        spans_p = fr.by_pitch(fr.filter_spans(ctx, model, fr.D_MS), horizon)
        outputs[tag] = (spans_p, fr.aggregate(fr.tally(spans_p, exp, annotated, geo)))
    registered = json.load(open(os.path.join(HERE, 'CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.json')))
    res, ok = dict(x_grid_ms=[x for x in X_GRID_MS[:-1]], delay_sensitivity={}, tail_by_register={}, tail_remaining_split={}), True
    for name, (spans_p, agg) in outputs.items():
        rows = {}
        for x_ms in X_GRID_MS:
            x = int(x_ms * rate / 1000)
            kept = sum(kept_in_first(spans_p, geo, x).values())
            for band, ps in (('all', None), ('lt60', 'lt60')):
                v = agg[band]
                kept_b = kept if ps is None else sum(k for p, k in kept_in_first(spans_p, geo, x).items() if fr.band_of(p) == ps)
                false_after = v['false'] - v['tail'] + kept_b
                rows.setdefault(band, {})[x_ms] = dict(false_after=false_after, precision=round(100 * v['present'] / (v['present'] + false_after), 2),
                                                       tail_kept=kept_b)
        res['delay_sensitivity'][name] = rows
        # identity: x = 0 equals the registered tail-cut oracle, x = huge equals the output itself
        oracle = registered['current']['oracle'] if name == 'CURRENT' else registered['filters'][name]['oracle']
        for band in ('all', 'lt60'):
            ok = ok and rows[band][0]['precision'] == oracle[band]['tail_cut'] and rows[band][10 ** 6]['precision'] == oracle[band]['now']
        reg = {}
        for p, row in fr.tally(spans_p, exp, annotated, geo).items():
            b = reg.setdefault(band_name(p), dict(tail=0, tail_annotated=0, orphan=0, total=0, present=0))
            for k in b:
                b[k] += row[k]
        res['tail_by_register'][name] = {k: dict(v, tail_share_of_band_false=round(v['tail'] / max(1, v['total'] - v['present']), 4)) for k, v in reg.items()}
        a = agg['all']
        res['tail_remaining_split'][name] = dict(tail=a['tail'], under_another_label=a['tail_annotated'], in_no_label=a['tail'] - a['tail_annotated'])
    if not ok:
        print('IDENTITY FAILED (x = 0 or x = inf does not reproduce the registered numbers)')
        raise SystemExit(1)
    # tail length by pitch for the adapted filter: spans, current tail volume, kept volume, median current tail
    per = {}
    for row in registered['filters']['cropped adapted']['tail_records']:
        d = per.setdefault(row['pitch'], dict(spans=0, current=0, kept=0, tails=[]))
        d['spans'] += 1
        d['current'] += row['tail']
        d['kept'] += row['kept']
        d['tails'].append(row['tail'])
    res['tail_by_pitch_adapted'] = {str(p): dict(spans=d['spans'], current_tail_ms_total=round(d['current'] * 1000 / rate), kept_tail_ms_total=round(d['kept'] * 1000 / rate),
                                                 median_current_tail_ms=round(statistics.median(d['tails']) * 1000 / rate, 1)) for p, d in sorted(per.items())}
    res['identity_x0_and_xinf_equal_registered'] = ok
    with open(OUT, 'w') as stream:
        json.dump(res, stream, indent=1)
    for name in outputs:
        print(name)
        for band in ('all', 'lt60'):
            print('  ', band, ' '.join(f"x{x if x < 10 ** 6 else 'inf'}:{res['delay_sensitivity'][name][band][x]['precision']}" for x in X_GRID_MS))
        print('   tail split', res['tail_remaining_split'][name])
        print('   tail by register', {k: (v['tail'], v['tail_share_of_band_false']) for k, v in res['tail_by_register'][name].items()})
    print('tail by pitch (adapted)', json.dumps(res['tail_by_pitch_adapted']))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
