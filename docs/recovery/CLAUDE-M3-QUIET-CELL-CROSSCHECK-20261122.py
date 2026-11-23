#!/usr/bin/env python3
"""POST HOC cross-check of the saved quiet-cell restart analysis (job 45087140206) against the boundary census.

Saved data only: reads three JSON files, writes one.  No audio, model, job, native or tuning step.  Nothing here is
pre-registered; it is descriptive and labelled POST HOC.  Run with `python3 -I` (the Codex report is downloaded data).

  python3 -I CLAUDE-M3-QUIET-CELL-CROSSCHECK-20261122.py --run

Inputs are pinned by SHA-256; a mismatch stops the run before any number is computed.
"""
import collections
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PINS = {
    'codex_report': ('build/github-results/quiet-cell-restart-45087140206/report/quiet-cell-restart/report/report.json',
                     'edfcaad6ea998524b787d7535828d110daee2b37583a0654b03dace25b6174cf'),
    'codex_compact': ('docs/recovery/CODEX-M3-QUIET-CELL-RESTART-RESULT-20261122.json',
                      '7404e5c90800ae45ddce2db94d9b1ce1c463de170a236bd02053891d129658b9'),
    'my_census': ('docs/recovery/CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.json',
                  '8ab2ca37a5e43d85158a46ab552ee02b94603c6400ad761b4e31ee161e15c47f'),
}
OUT = os.path.join(HERE, 'CLAUDE-M3-QUIET-CELL-CROSSCHECK-20261122.json')
FEATURES = ('interval_fundamental_share', 'interval_harmonic_share', 'recent_to_raw_harmonics', 'raw_fundamental_share')
WINDOWS = ('in_run', 'by_25ms')
MINE = (('F1_onset', 'F1'), ('F2_rise_vs_pre', 'F2'), ('F3_rise_in_window', 'F3'))


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def auc(pos, neg):
    """Ties count half; a missing value (None) ranks below every number."""
    lo = -math.inf
    p = [lo if v is None else v for v in pos]
    n = [lo if v is None else v for v in neg]
    wins = 0.0
    for a in p:
        for b in n:
            wins += 1.0 if a > b else (0.5 if a == b else 0.0)
    return wins / (len(p) * len(n))


def ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def spearman(x, y):
    rx, ry = ranks(x), ranks(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None


def plumbing():
    assert auc([3.0, 4.0], [1.0, 2.0]) == 1.0
    assert auc([1.0, 2.0], [3.0, 4.0]) == 0.0
    assert auc([1.0], [1.0]) == 0.5
    assert auc([None], [None]) == 0.5 and auc([0.0], [None]) == 1.0 and auc([None], [0.0]) == 0.0
    assert abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-12
    assert abs(spearman([1, 2, 3, 4], [40, 30, 20, 10]) + 1.0) < 1e-12
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    assert ranks([5, 5, 1, 9]) == [2.5, 2.5, 1.0, 4.0]
    return True


def feature(unit, window, name):
    entry = unit[window]['features'].get(name, {})
    return entry['maximum'] if entry.get('count') else None


def main(write):
    plumbing()
    paths, gates = {}, {}
    for key, (rel, pin) in PINS.items():
        paths[key] = os.path.join(ROOT, rel)
        gates[key] = dict(path=rel, sha256=pin, ok=os.path.exists(paths[key]) and sha256(paths[key]) == pin)
    if not all(g['ok'] for g in gates.values()):
        print('input pin mismatch or file missing:', json.dumps(gates, indent=1))
        return 2
    report = json.load(open(paths['codex_report']))
    compact = json.load(open(paths['codex_compact']))
    census = json.load(open(paths['my_census']))
    units = report['datasets']['ordinary']['units']
    reported = compact['datasets']['ordinary']['summaries']
    pairs = census['datasets']['ordinary']['pairs']
    out = dict(schema='claude_m3_quiet_cell_crosscheck_v1', post_hoc=True, pins=gates, plumbing_ok=True)

    # 1. Codex's reported AUCs, recomputed from its own per-unit maxima.
    classes = collections.Counter(u['classification'] for u in units)
    out['unit_classes'] = dict(classes)
    rec, worst = [], 0.0
    for window in WINDOWS:
        for name in FEATURES:
            pos = [feature(u, window, name) for u in units if u['classification'] == 'positive']
            neg = [feature(u, window, name) for u in units if u['classification'] == 'negative']
            value = auc(pos, neg)
            claimed = reported[window][name]['auc']
            worst = max(worst, abs(value - claimed))
            rec.append(dict(window=window, feature=name, recomputed=value, reported=claimed, n_pos=len(pos), n_neg=len(neg),
                            missing_pos=sum(v is None for v in pos), missing_neg=sum(v is None for v in neg)))
    out['reproduction'] = dict(rows=rec, worst_abs_difference=worst)

    # 2. Map Codex units onto my pairs by (pitch, run start); account for every unit that does not map.
    by_primary, by_any = {}, {}
    for p in pairs:
        key = (p['pitch'], p['run'][0])
        by_any.setdefault(key, []).append(p)
        if p['kind'] == 'primary':
            by_primary.setdefault(key, []).append(p)
    shared, unmapped = [], []
    for u in units:
        if u['classification'] not in ('positive', 'negative'):
            continue
        key = (u['note'], u['run'][0])
        candidates = [p for p in by_primary.get(key, []) if p['cls'] == u['classification']]
        (shared if len(candidates) == 1 else unmapped).append((u, candidates[0] if len(candidates) == 1 else None))
    why = collections.Counter()
    for u, _ in unmapped:
        key = (u['note'], u['run'][0])
        if any(p['kind'] == 'secondary' and p['cls'] == u['classification'] for p in by_any.get(key, [])):
            why['matches_my_secondary_negative_pair'] += 1
        elif u['original_span_class'] == 'positive':
            why['other_run_inside_a_positive_span'] += 1
        else:
            why['unexplained'] += 1
    out['mapping'] = dict(
        shared=dict(collections.Counter(u['classification'] for u, _ in shared)),
        spans_equal=sum(1 for u, p in shared if list(u['span']) == list(p['span'])),
        runs_equal=sum(1 for u, p in shared if list(u['run']) == list(p['run'])),
        unmapped=dict(collections.Counter(u['classification'] for u, _ in unmapped)), unmapped_reason=dict(why),
        codex_continuing_units=classes.get('continuing', 0),
        my_pair_kinds={'%s/%s' % k: v for k, v in sorted(collections.Counter((p['kind'], p['cls']) for p in pairs).items())})

    # 3. AUC of every score on the pairs both analyses contain (23 positive, 224 negative).
    shared_rows = []
    for name, tag in MINE:
        pos = [p['values'][name] for u, p in shared if p['cls'] == 'positive']
        neg = [p['values'][name] for u, p in shared if p['cls'] == 'negative']
        shared_rows.append(dict(source='mine', score=tag, window='pair window', auc=auc(pos, neg), n_pos=len(pos), n_neg=len(neg)))
    for window in WINDOWS:
        for name in FEATURES:
            pos = [feature(u, window, name) for u, p in shared if p['cls'] == 'positive']
            neg = [feature(u, window, name) for u, p in shared if p['cls'] == 'negative']
            shared_rows.append(dict(source='codex', score=name, window=window, auc=auc(pos, neg), n_pos=len(pos), n_neg=len(neg)))
    out['shared_pair_auc'] = shared_rows

    # 4. How much of my F2 is Codex's feature?  Spearman on the shared pairs, by_25ms (the like-for-like deadline) and in_run.
    conc = []
    for window in WINDOWS:
        for name in FEATURES:
            for cls in ('positive', 'negative', 'both'):
                sel = [(p['values']['F2_rise_vs_pre'], feature(u, window, name)) for u, p in shared if cls == 'both' or p['cls'] == cls]
                ok = [(a, b) for a, b in sel if a is not None and b is not None and math.isfinite(a)]
                conc.append(dict(window=window, feature=name, cls=cls, n=len(ok), spearman=spearman([a for a, b in ok], [b for a, b in ok]) if len(ok) > 2 else None))
    out['f2_vs_codex_spearman'] = conc
    if write:
        if os.path.exists(OUT):
            print('refusing to overwrite', OUT)
            return 2
        json.dump(out, open(OUT, 'w'), indent=1, sort_keys=True)
        print('wrote', OUT, 'sha256', sha256(OUT)[:12])
    return out


def report(out):
    print('plumbing ok; pins ok')
    r = out['reproduction']
    print('Codex AUCs recomputed from its units, worst |difference| %.2e' % r['worst_abs_difference'])
    for row in r['rows']:
        print('  %-8s %-28s recomputed %.6f reported %.6f  (n %d+/%d-, missing %d/%d)' % (row['window'], row['feature'], row['recomputed'], row['reported'], row['n_pos'], row['n_neg'], row['missing_pos'], row['missing_neg']))
    m = out['mapping']
    print('mapping', json.dumps(m))
    print('AUC on the shared 23+/224- pairs:')
    for row in out['shared_pair_auc']:
        print('  %-6s %-28s %-12s %.4f' % (row['source'], row['score'], row['window'], row['auc']))
    print('Spearman, my F2 against Codex features (shared pairs):')
    for row in out['f2_vs_codex_spearman']:
        print('  %-8s %-28s %-8s n %3d  %s' % (row['window'], row['feature'], row['cls'], row['n'], 'n/a' if row['spearman'] is None else '%+.3f' % row['spearman']))


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode not in ('--dry', '--run'):
        print(__doc__)
        sys.exit(1)
    result = main(write=(mode == '--run'))
    if isinstance(result, dict):
        report(result)
        sys.exit(0)
    sys.exit(result)
