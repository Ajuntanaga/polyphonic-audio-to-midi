"""Registered scores of docs/recovery/CLAUDE-M3-LEVEL-CONDITIONED-PREREGISTRATION-20261122.md (saved tapes only; no audio, no job).

Part A: label-end presence in the silent-after subset, control164 against candidate166 (adapted model).
Part B: does the level pattern of presence at the label end survive conditioning on early detection (frames g-17..g-13)?
Usage: python3 CLAUDE-M3-LEVEL-CONDITIONED-20261122.py ENDS.json CURVES.json.gz UNMODIFIED_DIR ADAPTED_DIR [CANDIDATE166_DIR] OUT.json
Each directory holds ordinary-stream.npz.  Nothing here is a policy or a gate.
"""
import gzip
import hashlib
import importlib.util
import json
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FLOOR_DB, END_J0, PRE_INDEX = -179.0, 20, 12
EARLY = (-17, -13)                 # frames g-17..g-13, about 151 to 197 ms before the end (registered)
MIN_SPAN_SAMPLES = int(0.230 * 96000)
THRESHOLD = 0.3
A_TOLERANCE_PP = 3.0               # "a few points", fixed in the pre-registration
B1_AUC, B1_MIN_CLASS = 0.65, 20
B2_SHARE, B3_DROP, B4_SHARE, B4_MIN = 0.70, 0.05, 0.5, 10
LOW_DB = -60.0
C1_AUC, C2_AUC, C2_DROP_DB, C3_RHO, C_MIN_CLASS = 0.60, 0.70, 6.0, 0.60, 20
C_STRATUM = (-60.0, -40.0)
EARLY_INDEX = 0                    # grid index 0 = window [E-200 ms, E-120 ms)
BOOT_N, BOOT_SEED = 2000, 20261122
GROUPS = ('both', 'adapted_only', 'original_only', 'neither')


def load_rc():
    spec = importlib.util.spec_from_file_location('rc', os.path.join(HERE, 'CLAUDE-M3-REAL-RELEASE-CURVES-20261122.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def auc(positive, negative):
    if not positive or not negative:
        return None
    return sum((p > n) + 0.5 * (p == n) for p in positive for n in negative) / (len(positive) * len(negative))


def bootstrap_auc(rows, key, seed=BOOT_SEED):
    """95% interval of the AUC of level for `key` (a boolean field), resampling ends."""
    rng = random.Random(seed)
    values = []
    for _ in range(BOOT_N):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        a = auc([r['pre'] for r in sample if r[key]], [r['pre'] for r in sample if not r[key]])
        if a is not None:
            values.append(a)
    values.sort()
    return [round(values[int(0.025 * len(values))], 3), round(values[int(0.975 * len(values)) - 1], 3)] if values else None


def load_tape(directory):
    tape = np.load(os.path.join(directory, 'ordinary-stream.npz'), allow_pickle=False)
    note, frames = tape['note'], tape['frames']
    clock = bool((frames[:, 0] == np.arange(len(frames))).all() and (frames[:, 1] == 256 * frames[:, 0]).all())
    return note, clock, sha256(os.path.join(directory, 'ordinary-stream.npz'))


def early_detected(note, row, rc):
    column = note[:, row['midi_note'] - 21]
    g = rc.frame_at_or_before(row['end'])
    lo = g + EARLY[0]
    if lo < 0 or g >= len(column):
        return None
    return float(np.mean(column[lo:g + EARLY[1] + 1])) >= THRESHOLD


def build_rows(ends, curves, tapes, rc):
    by_index = {r['idx']: r for r in curves['corpora']['ordinary']['ends']}
    rows = []
    for e in ends['corpora']['ordinary']['ends']:
        levels = by_index[e['idx']]['end_levels']
        after, pre = levels[END_J0], levels[PRE_INDEX]
        if after is None or pre is None or e['end'] + int(0.080 * 96000) > e['window']:
            continue
        row = dict(early_level=levels[EARLY_INDEX], idx=e['idx'], midi=e['midi_note'], start=e['start'], end=e['end'], window=e['window'], group=e['group'],
                   contested=e['contested_end'], pre=pre, silent_after=after <= FLOOR_DB,
                   span_ok=e['end'] - e['start'] >= MIN_SPAN_SAMPLES)
        spec = dict(midi_note=e['midi_note'], end=e['end'], window=e['window'])
        for arm, note in tapes.items():
            m = rc.measure_end(note, spec)
            row[arm + '_present'] = None if m is None else bool(m['detected'])
            row[arm + '_early'] = early_detected(note, spec, rc)
        rows.append(row)
    return rows


def group_check(rows):
    """control tapes must reproduce the saved groups of the ends file."""
    bad = 0
    for r in rows:
        u, a = r.get('unmodified_present'), r.get('adapted_present')
        expect = 'both' if u and a else 'adapted_only' if a else 'original_only' if u else 'neither'
        bad += expect != r['group']
    return dict(ends=len(rows), mismatched=bad)


def part_a(rows, adapted_key, candidate_key):
    usable = [r for r in rows if r[adapted_key] is not None and r[candidate_key] is not None]

    def block(sel):
        n = len(sel)
        c = sum(r[adapted_key] for r in sel)
        k = sum(r[candidate_key] for r in sel)
        return dict(n=n, control_present=c, candidate_present=k, control_pct=round(100 * c / n, 2), candidate_pct=round(100 * k / n, 2),
                    change_pp=round(100 * (k - c) / n, 2), lost=sum(r[adapted_key] and not r[candidate_key] for r in sel),
                    gained=sum(r[candidate_key] and not r[adapted_key] for r in sel))
    silent = [r for r in usable if r['silent_after']]
    other = [r for r in usable if not r['silent_after']]
    s, o = block(silent), block(other)
    bands = {}
    for lo, hi in ((0, 48), (48, 60), (60, 72), (72, 100)):
        sel_s = [r for r in silent if lo <= r['midi'] < hi]
        sel_o = [r for r in other if lo <= r['midi'] < hi]
        bands['%d-%d' % (lo, hi)] = dict(silent=block(sel_s) if sel_s else None, other=block(sel_o) if sel_o else None)
    return dict(
        all=block(usable), silent_after=s, other=o, by_band=bands,
        A1=dict(bar_pp=A_TOLERANCE_PP, change_pp=s['change_pp'], verdict='pass' if abs(s['change_pp']) <= A_TOLERANCE_PP else 'miss'),
        A2=dict(abs_change_silent_pp=abs(s['change_pp']), abs_change_other_pp=abs(o['change_pp']),
                verdict='pass' if abs(o['change_pp']) > abs(s['change_pp']) else 'miss'))


def part_b(rows, arm):
    present, early = arm + '_present', arm + '_early'
    base = [r for r in rows if r['span_ok'] and r[present] is not None and r[early] is not None]
    cond = [r for r in base if r[early]]
    low = [r for r in base if r['pre'] < LOW_DB]
    low_cond = [r for r in cond if r['pre'] < LOW_DB]
    for r in base:
        r['_present'] = r[present]

    def a(sel):
        return auc([r['pre'] for r in sel if r['_present']], [r['pre'] for r in sel if not r['_present']])
    n_pos, n_neg = sum(r['_present'] for r in cond), sum(not r['_present'] for r in cond)
    a_all, a_cond = a(base), a(cond)
    out = dict(n_excluded_short_or_unmapped=len(rows) - len(base), n=len(base), early_detected=len(cond),
               present_given_early=dict(present=n_pos, absent=n_neg),
               auc_unconditioned=None if a_all is None else round(a_all, 3), auc_conditioned=None if a_cond is None else round(a_cond, 3),
               auc_conditioned_bootstrap_95=bootstrap_auc(cond, '_present') if n_pos and n_neg else None,
               auc_unconditioned_bootstrap_95=bootstrap_auc(base, '_present'),
               present_given_not_early=sum(r['_present'] for r in base if not r[early]),
               not_early=len(base) - len(cond))
    out['B1'] = (dict(verdict='not_evaluable', reason='fewer than %d ends in a class' % B1_MIN_CLASS, present=n_pos, absent=n_neg)
                 if min(n_pos, n_neg) < B1_MIN_CLASS else dict(bar=B1_AUC, auc=out['auc_conditioned'],
                                                                verdict='pass' if a_cond >= B1_AUC else 'miss'))
    share_not_early = (sum(not r[early] for r in low) / len(low)) if low else None
    out['B2'] = dict(n_below=len(low), share_not_early=None if share_not_early is None else round(share_not_early, 3), bar=B2_SHARE,
                     verdict='not_evaluable' if share_not_early is None else ('pass' if share_not_early >= B2_SHARE else 'miss'))
    drop = None if a_all is None or a_cond is None else a_all - a_cond
    out['B3'] = dict(drop=None if drop is None else round(drop, 3), bar=B3_DROP,
                     verdict='not_evaluable' if drop is None else ('pass' if drop >= B3_DROP else 'miss'))
    share_present = (sum(r['_present'] for r in low_cond) / len(low_cond)) if low_cond else None
    out['B4'] = (dict(verdict='not_evaluable', n=len(low_cond)) if len(low_cond) < B4_MIN
                 else dict(n=len(low_cond), share_present=round(share_present, 3), bar=B4_SHARE,
                           verdict='pass' if share_present <= B4_SHARE else 'miss'))
    bins = []
    for lo, hi in ((-200, -70), (-70, -60), (-60, -50), (-50, -40), (-40, 0)):
        sel = [r for r in base if lo <= r['pre'] < hi]
        sel_c = [r for r in sel if r[early]]
        bins.append(dict(pre_db=[lo, hi], n=len(sel), early_detected=len(sel_c),
                         present_all=round(sum(r['_present'] for r in sel) / len(sel), 3) if sel else None,
                         present_given_early=round(sum(r['_present'] for r in sel_c) / len(sel_c), 3) if sel_c else None,
                         n_early=len(sel_c),
                         present_given_not_early=round(sum(r['_present'] for r in sel if not r[early]) / (len(sel) - len(sel_c)), 3)
                         if len(sel) > len(sel_c) else None))
    out['by_level'] = bins
    out['uncontested'] = dict(n=sum(not r['contested'] for r in base), early_detected=sum(not r['contested'] for r in cond),
                              auc_unconditioned=None, auc_conditioned=None)
    un_all, un_cond = [r for r in base if not r['contested']], [r for r in cond if not r['contested']]
    for name, sel in (('auc_unconditioned', un_all), ('auc_conditioned', un_cond)):
        value = a(sel)
        out['uncontested'][name] = None if value is None else round(value, 3)
    return out


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(x, y):
    a, b = np.array(ranks(x)), np.array(ranks(y))
    return float(np.corrcoef(a, b)[0, 1])


def part_c(rows, arm):
    present, early = arm + '_present', arm + '_early'
    pop = [r for r in rows if r['span_ok'] and r[present] is not None and r[early] and r['early_level'] is not None]
    for r in pop:
        r['_present'], r['drop'] = r[present], r['early_level'] - r['pre']

    def evaluate(sel, predictor):
        pos, neg = [predictor(r) for r in sel if r['_present']], [predictor(r) for r in sel if not r['_present']]
        if min(len(pos), len(neg)) < C_MIN_CLASS:
            return dict(n=len(sel), present=len(pos), absent=len(neg), auc=None)
        return dict(n=len(sel), present=len(pos), absent=len(neg), auc=round(auc(pos, neg), 3))
    out = dict(population=len(pop))
    rho = spearman([r['pre'] for r in pop], [r['drop'] for r in pop]) if len(pop) > 2 else None
    out['spearman_pre_drop'] = None if rho is None else round(rho, 3)
    out['C3'] = dict(rho=out['spearman_pre_drop'], bar=C3_RHO, verdict='pass' if rho is not None and abs(rho) <= C3_RHO else 'miss')
    stratum = [r for r in pop if C_STRATUM[0] <= r['pre'] < C_STRATUM[1]]
    small_drop = [r for r in pop if r['drop'] < C2_DROP_DB]
    c1, c2 = evaluate(stratum, lambda r: -r['drop']), evaluate(small_drop, lambda r: r['pre'])
    c1['bootstrap_95'] = bootstrap_auc_of(stratum, lambda r: -r['drop']) if c1['auc'] is not None else None
    c2['bootstrap_95'] = bootstrap_auc_of(small_drop, lambda r: r['pre']) if c2['auc'] is not None else None
    out['C1'] = dict(stratum_pre_db=list(C_STRATUM), bar=C1_AUC, **c1,
                     verdict='not_evaluable' if c1['auc'] is None else ('pass' if c1['auc'] >= C1_AUC else 'miss'))
    out['C2'] = dict(stratum_drop_below_db=C2_DROP_DB, bar=C2_AUC, **c2,
                     verdict='not_evaluable' if c2['auc'] is None else ('pass' if c2['auc'] >= C2_AUC else 'miss'))
    if out['C3']['verdict'] == 'miss':
        out['C1']['verdict'] = out['C2']['verdict'] = 'not_evaluable'
        out['note'] = 'C3 missed: the two quantities are too correlated to separate; C1 and C2 not evaluable'
    out['descriptive_by_drop'] = []
    for lo, hi in ((-100, 0), (0, 6), (6, 12), (12, 20), (20, 100)):
        sel = [r for r in pop if lo <= r['drop'] < hi]
        out['descriptive_by_drop'].append(dict(drop_db=[lo, hi], n=len(sel), median_pre=None if not sel else round(sorted(r['pre'] for r in sel)[len(sel) // 2], 1),
                                               present=None if not sel else round(sum(r['_present'] for r in sel) / len(sel), 3)))
    un = [r for r in pop if not r['contested']]
    un_stratum = [r for r in un if C_STRATUM[0] <= r['pre'] < C_STRATUM[1]]
    un_small = [r for r in un if r['drop'] < C2_DROP_DB]
    out['uncontested'] = dict(population=len(un), C1_stratum=evaluate(un_stratum, lambda r: -r['drop']), C2_stratum=evaluate(un_small, lambda r: r['pre']))
    return out


def bootstrap_auc_of(rows, predictor, seed=BOOT_SEED):
    rng = random.Random(seed)
    values = []
    for _ in range(BOOT_N):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        a = auc([predictor(r) for r in sample if r['_present']], [predictor(r) for r in sample if not r['_present']])
        if a is not None:
            values.append(a)
    values.sort()
    return [round(values[int(0.025 * len(values))], 3), round(values[int(0.975 * len(values)) - 1], 3)] if values else None


def main(argv):
    ends_path, curves_path, unmodified_dir, adapted_dir = argv[:4]
    candidate_dir = argv[4] if len(argv) >= 6 else None
    out_path = argv[-1]
    rc = load_rc()
    ends = json.load(open(ends_path))
    curves = json.load(gzip.open(curves_path, 'rt'))
    tapes, pins, clocks = {}, {}, {}
    for arm, directory in (('unmodified', unmodified_dir), ('adapted', adapted_dir)) + ((('candidate166', candidate_dir),) if candidate_dir else ()):
        tapes[arm], clocks[arm], pins[arm] = load_tape(directory)
    rows = build_rows(ends, curves, tapes, rc)
    result = dict(schema='m3_level_conditioned_v1', ends_sha256=sha256(ends_path), tape_sha256=pins, c0a_frame_clock=clocks,
                  group_check=group_check(rows), rows=len(rows))
    result['part_b'] = {arm: part_b(rows, arm) for arm in ('adapted', 'unmodified')}
    result['part_c'] = {arm: part_c(rows, arm) for arm in ('adapted', 'unmodified')}
    if candidate_dir:
        result['part_a'] = (part_a(rows, 'adapted_present', 'candidate166_present') if all(clocks.values()) and result['group_check']['mismatched'] == 0
                            else dict(verdict='withheld', reason='integrity check failed', clocks=clocks, group_check=result['group_check']))
    with open(out_path, 'w') as handle:
        json.dump(result, handle, indent=1)
        handle.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'part_b'}, indent=1))
    print(json.dumps({a: {k: v for k, v in b.items() if k.startswith('B')} for a, b in result['part_b'].items()}, indent=1))
    print(json.dumps(result['part_c'], indent=1))


if __name__ == '__main__':
    if len(sys.argv) < 6:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
