"""Registered analysis of the synthetic mixed-level probe.  Pure python and numpy; reads the worker report and the frozen spec, nothing else.

Every verdict below is fixed in docs/recovery/CLAUDE-M3-MIXED-LEVEL-PROPOSAL-20261122.md before any window is run.  Frontend values (the two
normalization scalars) and note decisions (frame posteriors at the readout frames) are scored separately.  Usage:
    python3 -m tools.mixed_level_analysis analyse REPORT.json SPEC.json [OUT.json]
"""
import json
import sys

import numpy as np

from tools.mixed_level_probe import window_id

FLOOR_DB = -100.0
PIN_TOLERANCE_DB = 0.5
PIN_SHARE = 0.9
SLOPE_RANGE = (0.85, 1.15)
RAISE_FRACTION = 0.7
RAISE_SHARE = 0.9
FRONTEND_MODEL_TOLERANCE_DB = 1e-3
DETECTED = 0.3
ELIGIBLE = 0.5
DROP = 0.2
MIN_CELLS = 4
LEVEL_EFFECT = 0.2
MASK_FRACTION = 0.5
MASK_FLOOR = 0.1
DITHER_TOLERANCE = 0.1
DITHER_SHARE = 0.8
ADAPTED_ABOVE_UNMODIFIED = 12


def verdict(passed, **detail):
    return dict(verdict='pass' if passed else 'miss', **detail)


def not_evaluable(reason, **detail):
    return dict(verdict='not_evaluable', reason=reason, **detail)


def by_id(records):
    return {r['id']: r for r in records}


def companions(p, level, timing=None):
    return [(t, d) for t in p['timings'] if timing in (None, t) for d in p['deltas'] if level + d <= p['companion_cap']]


def probe_ids(p, floor, form, companion_kind):
    """companion_kind: 'none', 'ended', 'through' or 'any'."""
    ids = []
    for midi in p['pitches']:
        for level in p['levels']:
            if companion_kind in ('none', 'any'):
                ids.append(window_id(floor, form, midi, level))
            if companion_kind in ('ended', 'through', 'any'):
                for timing in p['timings']:
                    if companion_kind in ('any', timing):
                        for _, delta in companions(p, level, timing):
                            ids.append(window_id(floor, form, midi, level, (timing, delta)))
    return ids


def frontend_same_across_models(tables):
    a, u = tables['adapted'], tables['unmodified']
    worst_min = max(abs(a[i]['min_db'] - u[i]['min_db']) for i in a)
    worst_range = max(abs(a[i]['range_db'] - u[i]['range_db']) for i in a)
    return verdict(worst_min <= FRONTEND_MODEL_TOLERANCE_DB and worst_range <= FRONTEND_MODEL_TOLERANCE_DB,
                   max_abs_min_db=worst_min, max_abs_range_db=worst_range)


def f1_minimum_pinned(table, p):
    """Adapted-model windows only (the frontend is shared).  Each of 8 cells: share of windows whose min is within 0.5 dB of the -100 dB power floor."""
    cells = {}
    for floor in p['floors']:
        for form in p['forms']:
            for kind in ('none', 'ended'):
                ids = probe_ids(p, floor, form, kind)
                share = float(np.mean([abs(table[i]['min_db'] - FLOOR_DB) <= PIN_TOLERANCE_DB for i in ids]))
                cells['%s/%s/%s' % (floor, form, kind)] = dict(n=len(ids), share_pinned=round(share, 4))
    return verdict(all(c['share_pinned'] >= PIN_SHARE for c in cells.values()), cells=cells)


def f2_range_tracks_level(table, p):
    slopes = {}
    for floor in p['floors']:
        for form in p['forms']:
            for midi in p['pitches']:
                levels = p['levels']
                ranges = [table[window_id(floor, form, midi, level)]['range_db'] for level in levels]
                slopes['%s/%s/m%d' % (floor, form, midi)] = round(float(np.polyfit(levels, ranges, 1)[0]), 4)
    lo, hi = SLOPE_RANGE
    return verdict(all(lo <= s <= hi for s in slopes.values()), slopes=slopes)


def f3_ended_companion_raises_range(table, p):
    pairs = []
    for floor in p['floors']:
        for form in p['forms']:
            for midi in p['pitches']:
                for level in p['levels']:
                    base = table[window_id(floor, form, midi, level)]['range_db']
                    for _, delta in companions(p, level, 'ended'):
                        raised = table[window_id(floor, form, midi, level, ('ended', delta))]['range_db'] - base
                        pairs.append((delta, raised))
    ok = [raised >= RAISE_FRACTION * delta for delta, raised in pairs]
    by_delta = {str(d): round(float(np.median([r for dd, r in pairs if dd == d])), 3) for d in p['deltas']}
    return verdict(float(np.mean(ok)) >= RAISE_SHARE, pairs=len(pairs), share_raised=round(float(np.mean(ok)), 4),
                   median_range_raise_db_by_delta=by_delta)


def response(table, floor, form, midi, level, companion=None):
    return table[window_id(floor, form, midi, level, companion)]['response']


def d1_pure_gain(table, p):
    detected, dependent, rows = 0, 0, {}
    for midi in p['pitches']:
        top = response(table, 'zero', 'sustained', midi, -30)
        bottom = response(table, 'zero', 'sustained', midi, -80)
        detected += top >= DETECTED
        dependent += top - bottom >= LEVEL_EFFECT
        rows['m%d' % midi] = dict(at_minus_30=round(top, 4), at_minus_80=round(bottom, 4))
    return verdict(detected >= 2 and dependent >= 2, pitches_detected=int(detected), pitches_level_dependent=int(dependent), rows=rows)


def d2_ended_companion_masks(table, p):
    delta = max(p['deltas'])
    cells = [(m, level) for m in p['pitches'] for level in p['levels']
             if response(table, 'zero', 'sustained', m, level) >= ELIGIBLE and level + delta <= p['companion_cap']]
    if len(cells) < MIN_CELLS:
        return not_evaluable('fewer than %d eligible cells' % MIN_CELLS, eligible=len(cells))
    drops = [response(table, 'zero', 'sustained', m, level) - response(table, 'zero', 'sustained', m, level, ('ended', delta))
             for m, level in cells]
    share = float(np.mean([d >= DROP for d in drops]))
    return verdict(share >= 0.5, eligible=len(cells), share_dropped=round(share, 4), median_drop=round(float(np.median(drops)), 4))


def d3_normalization_share(table, p):
    delta = 20
    cells = [(m, level) for m in p['pitches'] for level in p['levels']
             if response(table, 'zero', 'sustained', m, level) >= ELIGIBLE and level + delta <= p['companion_cap']]
    if len(cells) < MIN_CELLS:
        return not_evaluable('fewer than %d eligible cells' % MIN_CELLS, eligible=len(cells))

    def mean_drop(timing):
        return float(np.mean([response(table, 'zero', 'sustained', m, level)
                              - response(table, 'zero', 'sustained', m, level, (timing, delta)) for m, level in cells]))
    through, ended = mean_drop('through'), mean_drop('ended')
    if through < MASK_FLOOR:
        return not_evaluable('a sounding companion does not mask (mean drop %.3f)' % through, eligible=len(cells),
                             mean_drop_through=round(through, 4), mean_drop_ended=round(ended, 4))
    return verdict(ended >= MASK_FRACTION * through, eligible=len(cells), mean_drop_through=round(through, 4),
                   mean_drop_ended=round(ended, 4))


def d4_cut_level_dependence(adapted, unmodified, p):
    dependent, rows = 0, {}
    for midi in p['pitches']:
        top = response(adapted, 'zero', 'cut', midi, -30)
        bottom = response(adapted, 'zero', 'cut', midi, -70)
        dependent += top - bottom >= LEVEL_EFFECT
        rows['m%d' % midi] = dict(at_minus_30=round(top, 4), at_minus_70=round(bottom, 4))
    above, cells = 0, 0
    for midi in p['pitches']:
        for level in p['levels']:
            cells += 1
            above += response(adapted, 'zero', 'cut', midi, level) > response(unmodified, 'zero', 'cut', midi, level)
    return dict(
        d4=verdict(dependent >= 2, pitches_level_dependent=int(dependent), rows=rows),
        d4b=verdict(above >= ADAPTED_ABOVE_UNMODIFIED, cells=cells, adapted_above_unmodified=int(above)))


def d5_dither_irrelevant(table, p):
    close, total = 0, 0
    for form in p['forms']:
        for midi in p['pitches']:
            for level in p['levels']:
                for companion in [None] + companions(p, level):
                    total += 1
                    zero = response(table, 'zero', form, midi, level, companion)
                    dither = response(table, 'dither', form, midi, level, companion)
                    close += abs(dither - zero) <= DITHER_TOLERANCE
    return verdict(close / total >= DITHER_SHARE, pairs=total, share_within_tolerance=round(close / total, 4))


def descriptive(table, p):
    """Compact per-window values for both models' notes: frontend and decision fields separate."""
    return {i: dict(min_db=round(r['min_db'], 3), range_db=round(r['range_db'], 3), response=r.get('response'),
                    onset=max(r['onset_probe']) if 'onset_probe' in r else None, other_max=round(r['other_max'], 4))
            for i, r in table.items()}


def analyse(report, spec):
    p = spec['probe']
    gates = {}
    tables = {}
    for arm in spec['models']:
        model = report['models'][arm]
        tables[arm] = by_id(model['windows'])
        if len(tables[arm]) != p['expected_windows']:
            raise ValueError('Unexpected window count for ' + arm)
        gates[arm] = model['identity']
    if report.get('state') != 'complete':
        raise ValueError('Report is not complete')
    adapted, unmodified = tables['adapted'], tables['unmodified']
    out = dict(gates=gates, verdicts={}, descriptive={arm: descriptive(tables[arm], p) for arm in tables})
    out['verdicts']['F0_frontend_same_across_models'] = frontend_same_across_models(tables)
    out['verdicts']['F1_minimum_pinned_at_power_floor'] = f1_minimum_pinned(adapted, p)
    out['verdicts']['F2_range_slope_one_in_level'] = f2_range_tracks_level(adapted, p)
    out['verdicts']['F3_ended_companion_raises_range'] = f3_ended_companion_raises_range(adapted, p)
    if gates['adapted']['passed']:
        out['verdicts']['D1_pure_gain_response'] = d1_pure_gain(adapted, p)
        out['verdicts']['D2_ended_companion_masks'] = d2_ended_companion_masks(adapted, p)
        out['verdicts']['D3_normalization_share_of_masking'] = d3_normalization_share(adapted, p)
        out['verdicts']['D5_dither_irrelevant'] = d5_dither_irrelevant(adapted, p)
        if gates['unmodified']['passed']:
            cut = d4_cut_level_dependence(adapted, unmodified, p)
            out['verdicts']['D4_cut_presence_follows_level'] = cut['d4']
            out['verdicts']['D4b_adapted_above_unmodified_after_cut'] = cut['d4b']
    else:
        out['verdicts']['decisions'] = not_evaluable('identity gate failed for the adapted model')
    return out


if __name__ == '__main__':
    if len(sys.argv) < 4 or sys.argv[1] != 'analyse':
        raise SystemExit(__doc__)
    result = analyse(json.load(open(sys.argv[2])), json.load(open(sys.argv[3])))
    text = json.dumps(result, indent=1)
    if len(sys.argv) > 4:
        open(sys.argv[4], 'w').write(text + '\n')
    print(json.dumps(result['verdicts'], indent=1))
