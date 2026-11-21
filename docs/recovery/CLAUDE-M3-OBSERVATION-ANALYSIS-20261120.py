#!/usr/bin/env python3
"""Frozen-contract analysis of the observation-only replay table.

Contract: docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-PLAN-20261120.md as amended by CODEX-M3-ANALYSIS-FREEZE-20261120.md.
No audio, no dispatch. Pure Python, no numpy. One streaming pass over the saved table.

  python3 -I CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py PROJECT_ROOT TABLE.tsv.gz OUT.json [--format legacy] [--max-ticks N]

--format legacy parses the eight-column m3_candidate_outcome_v4 layout (the saved ordinary-current-on-512 trace). In that
layout a requested note that was not serialized is 'unavailable' (the inclusion filter), so a legacy run only exercises the
plumbing; the stage verdict is meaningful only on the new unfiltered table (adapter `load_new`, to be completed once the
column layout is announced). Nothing here is tuned to the saved trace: every number below is the frozen contract.
"""
import bisect, collections, gzip, json, random, re, statistics, sys

PROJ = sys.argv[1]
sys.path.insert(0, PROJ)
from tools.candidate_outcome_analysis import _frame, _candidates   # Codex's parsers, unchanged

def _detector_range():
    # The detector evaluates candidates only inside [lowest_note, highest_note] (native/include/m3/types.hpp);
    # candidate_admission_diagnostics() returns an all-zero default outside it, which must never be read as a score of zero.
    t = open(PROJ + '/native/include/m3/types.hpp').read()
    lo, hi = re.search(r'lowest_note\{(\d+)\}', t), re.search(r'highest_note\{(\d+)\}', t)
    if not (lo and hi): raise ValueError('cannot read the detector note range from types.hpp')
    return int(lo.group(1)), int(hi.group(1))


DET_LOW, DET_HIGH = _detector_range()
SEED = 20261120
BOOT = 2000
HARM_OCT = 12
HI_BANDS = ('60-71', '72+')
BANDS = (('<48', 0, 47), ('48-59', 48, 59), ('60-71', 60, 71), ('72+', 72, 127))
# Step B family frozen by the plan, in the plan's listed order (ties resolve by this order).
SCALARS = ('score_ratio', 'fund_ratio', 'band_score', 'band_fund', 'score_over_power', 'cal_direct', 'cal_margin', 'onset')
# Step C, descriptive only: never eligible to nominate branch A. score_over_loudest is annotation-conditioned.
DESCRIPTIVE = ('score_energy_raw', 'score_over_loudest')
# Floor hypothesis (predeclared 2026-11-20, tested separately from the frozen family): score over a per-tick cross-pitch floor
# built from the v5 `floor_stats` column. These are evaluated with the identical train/test AUC machinery but are NOT in SCALARS,
# so they can never change the frozen selection. They survive only if `floor_hypothesis` in the report says beats_frozen=True:
# the floor scalar's train minimum AUC AND test minimum AUC (over the C and CR control sets) must both strictly exceed the
# selected frozen scalar's. Otherwise the hypothesis is dead. Band sums are divided by the detector-range pitch count of the band
# (the sums cover only observed pitches, so the band mean is an approximation: named *_approx).
FLOOR_SC = ('score_over_floor_median', 'score_over_floor_p25', 'score_over_band_mean_approx')
FLOOR_FIELDS = ('n_observed', 'med_score', 'p25_score', 'med_fund', 'p25_fund', 'sum_score_lt48', 'sum_fund_lt48',
                'sum_score_48_59', 'sum_fund_48_59', 'sum_score_60_71', 'sum_fund_60_71', 'sum_score_72_84', 'sum_fund_72_84')
FLOOR_BANDS = (('lt48', DET_LOW, 47), ('48_59', 48, 59), ('60_71', 60, 71), ('72_84', 72, DET_HIGH))
ALL_SC = SCALARS + DESCRIPTIVE + FLOOR_SC
STATES = ('unavailable', 'out_of_range', 'quiet', 'unobserved', 'spectral', 'dp', 'selected_not_rendered', 'formation', 'admission', 'other')


def band_of(n):
    for name, lo, hi in BANDS:
        if lo <= n <= hi: return name


def parse_floor(text):
    """The v5 floor_stats cell: 13 colon-separated doubles. NaN (empty tick) becomes None; a malformed cell raises."""
    parts = text.split(':')
    if len(parts) != len(FLOOR_FIELDS): raise ValueError('floor_stats has %d fields, expected %d' % (len(parts), len(FLOOR_FIELDS)))
    vals = [float(p) for p in parts]
    return {k: (None if v != v else v) for k, v in zip(FLOOR_FIELDS, vals)}


def floor_scalars(se, floor, note):
    out = dict.fromkeys(FLOOR_SC)
    if se is None or floor is None: return out
    pos = lambda d: d if (d is not None and d > 0) else None
    if pos(floor['med_score']): out['score_over_floor_median'] = se / floor['med_score']
    if pos(floor['p25_score']): out['score_over_floor_p25'] = se / floor['p25_score']
    if note is not None:
        for name, lo, hi in FLOOR_BANDS:
            if lo <= note <= hi:
                npitch = hi - lo + 1
                mean = floor['sum_score_' + name] / npitch
                if mean > 0: out['score_over_band_mean_approx'] = se / mean
    return out


def scalar_vector(c, power, loudest, floor=None, note=None):
    """{scalar: value or None}. None = unavailable for that scalar; the frame stays in every denominator."""
    se = c.get('score_energy') if c.get('energy_observed') == 1 else None
    pos = lambda d: d if (d is not None and d > 0) else None
    out = {'score_ratio': c['score_ratio'], 'fund_ratio': c['fund_ratio'], 'band_score': c['band_score'],
           'band_fund': c['band_fund'], 'cal_direct': float(c['cal_direct']),
           'cal_margin': c['best_cal'] - c['second_cal'],
           'onset': c['onset'] if c.get('onset_observed') == 1 else None,
           'score_over_power': (se / power) if (se is not None and pos(power)) else None,
           'score_energy_raw': se,
           'score_over_loudest': (se / loudest) if (se is not None and pos(loudest)) else None}
    out.update(floor_scalars(se, floor, note))
    return out


def classify(c, rendered, quiet_tick, note=None):
    """Partition a requested (tick, note) frame exactly once; unavailable and quiet first (freeze amendment 2).
    'rendered' is handled by the caller (G_all minus G_miss); this is the G_miss partition."""
    if note is not None and not DET_LOW <= note <= DET_HIGH: return 'out_of_range', False
    if c is None: return 'unavailable', False
    formed = bool(c['direct'] or c['local'] or c['evidence'])
    if quiet_tick or c['selection'] == 0: return 'quiet', formed
    if c.get('energy_observed') == 0: return 'unobserved', formed      # the trace's own validity flag: not evaluated this tick
    if c['selection'] == 2: return 'spectral', formed
    if c['selection'] == 3: return 'dp', formed
    if c['selection'] in (4, 5) and not rendered: return 'selected_not_rendered', formed
    if not formed and c['rescue_mask'] == 0: return 'formation', formed
    if formed and c['selection'] == 1 and c['rescue_mask'] == 0: return 'admission', formed
    return 'other', formed


# ---------------------------------------------------------------- loading
def load_legacy(path, max_ticks=None):
    """Yield per-tick dicts for the saved eight-column trace; this layout has no per-tick input power."""
    with gzip.open(path, 'rt') as f:
        next(f); next(f)
        for n, line in enumerate(f):
            if max_ticks and n >= max_ticks: break
            fr = _frame(line)
            yield dict(sample=fr['sample'], tick=fr['tick'], quiet=fr['quiet'], labels=fr['labels'],
                       voices=fr['voices'], rows=_candidates(fr), power=None, floor=None)


STD_COLS = ('sample', 'tick', 'quiet', 'signal_samples', 'labels', 'matched_labels', 'voices', 'candidates')
LEGACY_TRACE = '/build/github-results/preselection-energy-44752010601/ordinary-current-on-512-outcome.tsv.gz'


def load_new(path, max_ticks=None):
    """The new unfiltered table: the eight legacy columns, located by header name, plus extra columns. The per-tick input
    power is the one extra column whose name contains 'power'. Yields the same per-tick dicts as load_legacy.
    A layout that differs (missing column, no or several power columns) raises, so it is reported rather than guessed."""
    with gzip.open(path, 'rt') as f:
        schema = next(f).strip(); header = next(f).rstrip('\n').split('\t')
        idx = {n: header.index(n) for n in STD_COLS}
        pw = [i for i, n in enumerate(header) if i not in idx.values() and 'power' in n.lower()]
        if len(pw) != 1: raise ValueError('expected exactly one per-tick power column, found %r' % [header[i] for i in pw])
        fl = [i for i, n in enumerate(header) if n == 'floor_stats']       # optional: v5 with the floor aggregates
        if len(fl) > 1: raise ValueError('several floor_stats columns')
        for n, line in enumerate(f):
            if max_ticks and n >= max_ticks: break
            parts = line.rstrip('\n').split('\t')
            if len(parts) != len(header): raise ValueError('row %d has %d columns, header has %d' % (n, len(parts), len(header)))
            fr = _frame('\t'.join(parts[idx[c]] for c in STD_COLS))
            try: power = float(parts[pw[0]])
            except ValueError: power = None
            floor = parse_floor(parts[fl[0]]) if fl else None
            yield dict(sample=fr['sample'], tick=fr['tick'], quiet=fr['quiet'], labels=fr['labels'],
                       voices=fr['voices'], rows=_candidates(fr), power=power, floor=floor)


def gate_stream(new_ticks, legacy_ticks, g):
    """Integrity gate 2 in lockstep with the new table: every legacy frame field and every legacy (tick, note) tuple field must
    be reproduced exactly (parsed values, so extra columns and extra rows do not matter). A mismatch fails the gate; it does not
    by itself prove the detector changed (provenance or serialization can differ). Also checks the per-tick power."""
    c = g['c']
    for new in new_ticks:
        old = next(legacy_ticks, None)
        if old is None:
            c['legacy_exhausted'] += 1
        else:
            c['ticks_compared'] += 1
            if (new['sample'], new['tick']) != (old['sample'], old['tick']): c['tick_grid_mismatch'] += 1
            for k in ('quiet', 'labels', 'voices'):
                if new[k] != old[k]: c['frame_%s_mismatch' % k] += 1
            for note, orow in old['rows'].items():
                nrow = new['rows'].get(note)
                if nrow is None:
                    c['legacy_row_missing'] += 1
                    if len(g['examples']) < 5: g['examples'].append(('row_missing', new['tick'], note))
                    continue
                for k, v in orow.items():
                    if nrow.get(k) != v:
                        c['field_mismatch:' + k] += 1
                        if len(g['examples']) < 5: g['examples'].append((k, new['tick'], note, v, nrow.get(k)))
        p = new['power']
        if p is None or p != p or p < 0 or p == float('inf'): c['power_invalid'] += 1
        fl = new.get('floor')
        if fl is not None:                                  # the v5 floor aggregates: count in range, quantiles only when n > 0, sums >= 0
            n_ok = fl['n_observed'] is not None and 0 <= fl['n_observed'] <= DET_HIGH - DET_LOW + 1 and fl['n_observed'] == int(fl['n_observed'])
            q = [fl[k] for k in ('med_score', 'p25_score', 'med_fund', 'p25_fund')]
            sums = [fl[k] for k in FLOOR_FIELDS if k.startswith('sum_')]
            bad = (not n_ok or any(v is None or v < 0 or v == float('inf') for v in sums)
                   or (n_ok and fl['n_observed'] == 0) != all(v is None for v in q)
                   or any(v is not None and (v < 0 or v == float('inf')) for v in q))
            if bad:
                c['floor_invalid'] += 1
                if len(g['examples']) < 5: g['examples'].append(('floor_invalid', new['tick'], fl))
        yield new


# ---------------------------------------------------------------- records
def build_records(ticks):
    first, last = {}, {}
    census = collections.defaultdict(collections.Counter)      # (band, kind, anchor label) -> state counter
    elig = []                                                   # Step B rows (kind, anchor label, sample, note, scalars)
    tickinfo = []                                               # note-60 audit rows for Step D
    integ = collections.Counter()
    prev = None
    for fr in ticks:
        s = fr['sample']
        integ['ticks'] += 1
        if prev is not None:
            if fr['tick'] != prev['tick'] + 1: integ['tick_not_consecutive'] += 1
            if s - prev['sample'] != 64: integ['sample_step_not_64'] += 1
        prev = fr
        lab_notes = {}
        for (lid, note, mask) in fr['labels']:
            first.setdefault(lid, s); last[lid] = s
            lab_notes.setdefault(note, lid)
        voice_notes = {v[1] for v in fr['voices']}
        reqs, seen_c = [], set()
        for note, lid in lab_notes.items(): reqs.append(('G', note, lid))
        for note, lid in lab_notes.items():                     # annotated parent + 12, itself not annotated
            up = note + HARM_OCT
            if up > DET_HIGH and up <= 127 and up not in lab_notes and up not in seen_c:
                seen_c.add(up); integ['c_out_of_detector_range'] += 1      # not a candidate the detector can ever form
            elif up <= DET_HIGH and up not in lab_notes and up not in seen_c:
                seen_c.add(up); reqs.append(('C', up, lid))
        energies = [fr['rows'][n]['score_energy'] for _, n, _ in reqs
                    if n in fr['rows'] and fr['rows'][n].get('energy_observed') == 1]
        loudest = max(energies) if energies else None
        for kind, note, lid in reqs:
            integ['requested'] += 1
            rendered = note in voice_notes
            c = fr['rows'].get(note)
            integ['requested_with_row'] += (c is not None) or not (DET_LOW <= note <= DET_HIGH)
            state, formed = classify(c, rendered, fr['quiet'], note)
            census[(band_of(note), kind, lid)]['rendered' if rendered else state] += 1
            if c is None: continue
            if kind == 'G' and (rendered or not formed): continue   # Step B: G_miss with formed evidence only
            elig.append((kind + ('R' if kind == 'C' and rendered else ''), lid, s, note,
                         scalar_vector(c, fr['power'], loudest, fr.get('floor'), note)))
        c60 = fr['rows'].get(60)
        r60 = 60 in voice_notes
        st60 = 'rendered' if r60 else classify(c60, r60, fr['quiet'])[0]
        tickinfo.append((s, st60, scalar_vector(c60, fr['power'], loudest, fr.get('floor'), 60) if c60 else None, r60,
                         42 in lab_notes.values(), tuple(sorted(lab_notes))))
    return first, last, census, elig, tickinfo, integ


def groups_from_labels(first, last):
    """Merge overlapping label intervals into passage groups; return label -> group id (ordered by start)."""
    order = sorted(first, key=lambda l: (first[l], last[l]))
    gid, cur_end, g = {}, None, -1
    for l in order:
        if cur_end is None or first[l] > cur_end:
            g += 1; cur_end = last[l]
        else:
            cur_end = max(cur_end, last[l])
        gid[l] = g
    return gid, g + 1


# ---------------------------------------------------------------- statistics
def weighted_auc(g_items, c_items):
    """P(genuine > control); every passage group counts once per class (weight 1/n in group); ties half."""
    ng, nc = collections.Counter(g for g, _ in g_items), collections.Counter(g for g, _ in c_items)
    if not ng or not nc: return None
    pts = sorted([(v, 0, 1.0 / ng[g]) for g, v in g_items] + [(v, 1, 1.0 / nc[g]) for g, v in c_items], key=lambda t: t[0])
    cum_c = num = 0.0; i = 0
    while i < len(pts):
        j = i; gw = cw = 0.0
        while j < len(pts) and pts[j][0] == pts[i][0]:
            if pts[j][1] == 0: gw += pts[j][2]
            else: cw += pts[j][2]
            j += 1
        num += gw * (cum_c + 0.5 * cw); cum_c += cw; i = j
    return num / (len(ng) * len(nc))


def group_values(items):
    d = collections.defaultdict(list)
    for g, v in items: d[g].append(v)
    return {g: sorted(v) for g, v in d.items()}


def cluster_bootstrap(gvals, cvals):
    """Resample whole passage groups from the union, keeping each group's genuine/control dependence.
    Replicates missing a class are invalid and counted, never assigned an AUC."""
    G, C = sorted(gvals), sorted(cvals)
    M = {}
    for a in G:
        for b in C:
            cb = cvals[b]; tot = 0.0
            for x in gvals[a]:
                lo = bisect.bisect_left(cb, x); hi = bisect.bisect_right(cb, x)
                tot += lo + 0.5 * (hi - lo)
            M[(a, b)] = tot / (len(gvals[a]) * len(cb))
    allg = sorted(set(G) | set(C)); rng = random.Random(SEED); stats, invalid = [], 0
    for _ in range(BOOT):
        m = collections.Counter(rng.choice(allg) for _ in allg)
        hg = sum(m[a] for a in G); hc = sum(m[b] for b in C)
        if hg == 0 or hc == 0: invalid += 1; continue
        stats.append(sum(m[a] * m[b] * M[(a, b)] for a in G if m[a] for b in C if m[b]) / (hg * hc))
    stats.sort()
    if not stats: return None, None, invalid, 0
    return stats[int(0.025 * len(stats))], stats[min(len(stats) - 1, int(0.975 * len(stats)))], invalid, len(stats)


def seg_summary(rows, sign_cut):
    """rows: list of (state, scalars or None). Side-by-side range per scalar plus the train-fixed rule's admissions."""
    out = {'ticks': len(rows), 'available': sum(1 for _, v in rows if v is not None),
           'states': dict(collections.Counter(s for s, _ in rows)), 'scalars': {}}
    for sc in ALL_SC:
        vals = [v[sc] for _, v in rows if v is not None and v[sc] is not None]
        out['scalars'][sc] = ({'n': len(vals), 'min': min(vals), 'median': statistics.median(vals), 'max': max(vals)}
                              if vals else {'n': 0})
    if sign_cut:
        sc, sign, cut = sign_cut
        vals = [sign * v[sc] for _, v in rows if v is not None and v[sc] is not None]
        out['rule_admits'] = {'scalar': sc, 'computable': len(vals), 'above_cut': sum(1 for x in vals if x > cut)}
    return out


# ---------------------------------------------------------------- main analysis
def analyse(first, last, census, elig, tickinfo, integ):
    gid, ngroups = groups_from_labels(first, last)
    train = {g for g in range(ngroups) if g % 2 == 0}                  # alternate chronological groups, first to train
    rep = {'integrity': dict(integ), 'groups': ngroups, 'train_groups': len(train), 'test_groups': ngroups - len(train)}
    # ---- Step A: census per band and kind, frames and passage-weighted shares
    agg = collections.defaultdict(collections.Counter)
    pg = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for (band, kind, lid), c in census.items():
        agg[(band, kind)].update(c); pg[(band, kind)][gid[lid]].update(c)
    rep['census'] = {}
    for (band, kind), c in sorted(agg.items()):
        row = {'frames_total': sum(c.values()), 'frames': {k: c[k] for k in sorted(c)}}
        if kind == 'G':                                                # G_miss shares: exclude rendered from the denominator
            row['g_miss_frames'] = sum(c[k] for k in c if k != 'rendered')
            shares = collections.defaultdict(list)
            for g, gc in pg[(band, kind)].items():
                tot = sum(gc[k] for k in gc if k != 'rendered')
                if tot:
                    for k in STATES: shares[k].append(gc[k] / tot)
            row['passage_weighted_share'] = {k: (sum(v) / len(v) if v else None) for k, v in shares.items()}
            row['passages_with_g_miss'] = len(shares['unavailable'])
        rep['census']['%s|%s' % (band, kind)] = row
    # ---- Branch B: class 1 (evidence formation) must exceed 50% of ALL G_miss frames at >= 60
    tot = form = 0
    for (band, kind), c in agg.items():
        if kind == 'G' and band in HI_BANDS:
            tot += sum(c[k] for k in c if k != 'rendered'); form += c['formation']
    branch_b = dict(g_miss_frames=tot, formation=form, share=(form / tot if tot else None), holds=(form / tot > 0.5) if tot else None)
    # ---- Step B: single scalars, band >= 60, train-only orientation and selection
    hi = [r for r in elig if band_of(r[3]) in HI_BANDS]
    byset = lambda kinds, split: [r for r in hi if r[0] in kinds and ((gid[r[1]] in train) == split)]
    CTRL = {'C': ('C', 'CR'), 'CR': ('CR',)}
    rep['eligible'] = {sp: {k: dict(frames=len(byset(kk, s)), groups=len({gid[r[1]] for r in byset(kk, s)}))
                            for k, kk in (('G_miss_formed', ('G',)), ('C', CTRL['C']), ('C_rend', CTRL['CR']))}
                       for sp, s in (('train', True), ('test', False))}
    per_scalar, best = {}, None
    for sc in ALL_SC:
        items = lambda kinds, split: [(gid[r[1]], r[4][sc]) for r in byset(kinds, split) if r[4][sc] is not None]
        res = {}
        for sp, s in (('train', True), ('test', False)):
            for cs in ('C', 'CR'):
                res['%s_auc_%s' % (sp, cs)] = weighted_auc(items(('G',), s), items(CTRL[cs], s))
        tr = [res['train_auc_C'], res['train_auc_CR']]
        sign = -1 if (all(v is not None for v in tr) and sum(tr) / 2 < 0.5) else 1
        if sign == -1:
            for k in list(res):
                if res[k] is not None: res[k] = 1 - res[k]
        res['orientation'] = sign
        per_scalar[sc] = res
        if sc in SCALARS and all(v is not None for v in (res['train_auc_C'], res['train_auc_CR'])):
            m = min(res['train_auc_C'], res['train_auc_CR'])
            if best is None or m > best[0]: best = (m, sc)             # strict: ties keep the earlier listed scalar
    rep['per_scalar'] = per_scalar
    rep['selected_scalar'] = best[1] if best else None
    # ---- Floor hypothesis (predeclared; see FLOOR_SC). Never feeds the frozen selection above.
    present = any(r[4]['score_over_floor_median'] is not None for r in hi)
    fh = {'available': present, 'predeclared_rule': 'a floor scalar survives only if BOTH its train and test minimum AUC (over the C and CR '
                                                   'control sets, train-fixed orientation) strictly exceed the selected frozen scalar\'s; '
                                                   'otherwise the hypothesis is dead. Three floor scalars were tried; none is tuned.'}
    if present and best:
        minauc = lambda sc, sp: (None if any(per_scalar[sc]['%s_auc_%s' % (sp, cs)] is None for cs in ('C', 'CR'))
                                 else min(per_scalar[sc]['%s_auc_%s' % (sp, cs)] for cs in ('C', 'CR')))
        ref = dict(scalar=best[1], train_min_auc=minauc(best[1], 'train'), test_min_auc=minauc(best[1], 'test'))
        fh['frozen_selected'] = ref; fh['floor'] = {}
        for fsc in FLOOR_SC:
            tr, te = minauc(fsc, 'train'), minauc(fsc, 'test')
            beats = all(v is not None for v in (tr, te, ref['train_min_auc'], ref['test_min_auc'])) and \
                tr > ref['train_min_auc'] and te > ref['test_min_auc']
            fh['floor'][fsc] = dict(train_min_auc=tr, test_min_auc=te, orientation=per_scalar[fsc]['orientation'], beats_frozen=bool(beats))
        fh['any_beats_frozen'] = any(v['beats_frozen'] for v in fh['floor'].values())
    else:
        fh['any_beats_frozen'] = None
        fh['reason'] = 'floor_stats column absent' if not present else 'no frozen scalar computable on both control sets'
    rep['floor_hypothesis'] = fh
    verdict = {'branch_A': None, 'branch_A_reason': None, 'branch_B': branch_b}
    sign_cut = None
    if best:
        sc = best[1]; sign = per_scalar[sc]['orientation']
        v = lambda r: sign * r[4][sc]
        tr_ctrl = [v(r) for r in byset(CTRL['C'], True) if r[4][sc] is not None]
        cut = max(tr_ctrl) if tr_ctrl else None                         # admits zero train controls (strictly greater)
        te_g = [r for r in byset(('G',), False) if r[4][sc] is not None]
        te = {cs: [r for r in byset(CTRL[cs], False) if r[4][sc] is not None] for cs in CTRL}
        adm = {cs: (sum(1 for r in te[cs] if v(r) > cut) if cut is not None else None) for cs in CTRL}
        pgrp = collections.defaultdict(lambda: [0, 0])
        for r in te_g:
            pgrp[gid[r[1]]][0] += 1; pgrp[gid[r[1]]][1] += (cut is not None and v(r) > cut)
        rec = sum(1 for n, k in pgrp.values() if n and k / n >= 0.25)
        rule = dict(scalar=sc, orientation=sign, train_cut=cut, test_control_admissions=adm['C'], test_cr_admissions=adm['CR'],
                    test_genuine_groups=len(pgrp), recovered_groups=rec, recovery_share=(rec / len(pgrp)) if pgrp else None)
        gi = [(gid[r[1]], v(r)) for r in te_g]
        enough = True
        for cs in CTRL:
            ci = [(gid[r[1]], v(r)) for r in te[cs]]
            lo, hi_, inval, valid = cluster_bootstrap(group_values(gi), group_values(ci)) if gi and ci else (None, None, 0, 0)
            ng_, nc_ = len({g for g, _ in gi}), len({g for g, _ in ci})
            rule['test_auc_ci_' + cs] = dict(lo=lo, hi=hi_, valid_replicates=valid, invalid_replicates=inval,
                                              test_groups_G=ng_, test_groups_ctrl=nc_)
            enough = enough and ng_ >= 2 and nc_ >= 2
        rep['rule'] = rule
        ok = (adm['C'] == 0 and adm['CR'] == 0 and rule['recovery_share'] is not None and rule['recovery_share'] >= 0.25)
        for cs in CTRL:
            ci = rule['test_auc_ci_' + cs]; a = per_scalar[sc]['test_auc_' + cs]
            ok = ok and a is not None and a >= 0.90 and ci['lo'] is not None and ci['lo'] >= 0.80
        verdict['branch_A'] = 'insufficient support (a test class has < 2 passage groups)' if not enough else bool(ok)
        verdict['branch_A_reason'] = 'train-selected single scalar %s; screening gate only, no deployment claim' % sc
        sign_cut = (sc, sign, cut) if cut is not None else None
    # ---- Step D: false-hold audit on the table's own tick grid (bounds derived from the labelled/rendered ticks)
    l42 = [i for i, t in enumerate(tickinfo) if t[4]]
    step_d = {'note': 'Overlap on each scalar separately is not proof that no joint, temporal or nonmonotone rule separates; '
                      'report as no demonstrated safe separator inside the frozen single-scalar family.'}
    if l42:
        i0, i1 = l42[0], l42[-1]
        r42 = [i for i in l42 if tickinfo[i][3]]
        coast_end = r42[-1] if r42 else None
        tail = list(range(coast_end + 1, i1 + 1)) if coast_end is not None else []
        j = i0 - 1
        while j >= 0 and tickinfo[j][3]: j -= 1
        hold = list(range(j + 1, i0))
        pick = lambda idx: [(tickinfo[i][1], tickinfo[i][2]) for i in idx]
        bounds = lambda idx: (dict(first_sample=tickinfo[idx[0]][0], last_sample=tickinfo[idx[-1]][0], ticks=len(idx)) if idx else None)
        step_d['label42'] = dict(start_sample=tickinfo[i0][0], end_sample=tickinfo[i1][0],
                                 last_rendered_note60_sample=tickinfo[coast_end][0] if coast_end is not None else None)
        step_d['tail_bounds'] = bounds(tail); step_d['false_hold_bounds'] = bounds(hold)
        segs = {'false_hold_all': hold,
                'false_hold_over_annotations': [i for i in hold if tickinfo[i][5]],
                'false_hold_in_gap': [i for i in hold if not tickinfo[i][5]],
                'label42_tail': tail}
        step_d['segments'] = {k: seg_summary(pick(ix), sign_cut) for k, ix in segs.items()}
        # side-by-side: does the tail range lie inside the hold range on each scalar (descriptive overlap only)?
        ov = {}
        for sc in ALL_SC:
            a, b = step_d['segments']['label42_tail']['scalars'][sc], step_d['segments']['false_hold_all']['scalars'][sc]
            if a.get('n') and b.get('n'):
                ov[sc] = dict(tail_inside_hold_range=(b['min'] <= a['min'] and a['max'] <= b['max']),
                              tail_range_overlaps_hold_range=not (a['max'] < b['min'] or b['max'] < a['min']))
        step_d['scalar_overlap'] = ov
        step_d['tail_state_census'] = step_d['segments']['label42_tail']['states']
    rep['step_d'] = step_d
    rep['verdict'] = verdict
    return rep


if __name__ == '__main__':
    table, out = sys.argv[2], sys.argv[3]
    fmt = sys.argv[sys.argv.index('--format') + 1] if '--format' in sys.argv else 'legacy'
    mt = int(sys.argv[sys.argv.index('--max-ticks') + 1]) if '--max-ticks' in sys.argv else None
    ignore = '--ignore-gates' in sys.argv                  # debugging only; any result is then NOT VALID
    G = {'c': collections.Counter(), 'examples': []}
    legacy_it = None
    if fmt == 'legacy':
        ticks = load_legacy(table, mt)
    else:
        legacy_it = load_legacy(PROJ + LEGACY_TRACE, mt)
        ticks = gate_stream(load_new(table, mt), legacy_it, G)
    first, last, census, elig, tickinfo, integ = build_records(ticks)
    gates = dict(G['c'])
    if legacy_it is not None: gates['new_exhausted_legacy_ticks_remaining'] = sum(1 for _ in legacy_it)
    gates['requested_rows_missing'] = integ['requested'] - integ['requested_with_row'] if fmt != 'legacy' else 0
    gates['tick_not_consecutive'] = integ['tick_not_consecutive']; gates['sample_step_not_64'] = integ['sample_step_not_64']
    failed = {k: v for k, v in gates.items() if k != 'ticks_compared' and v}
    if failed and fmt != 'legacy':
        json.dump(dict(status='INTEGRITY GATE FAILED' + (' (--ignore-gates: result NOT VALID)' if ignore else ' - no analysis'),
                       failed=failed, gates=gates, examples=G['examples']), open(out, 'w'), indent=1, default=str)
        print('INTEGRITY GATE FAILED:', json.dumps(failed), json.dumps(G['examples'][:5], default=str))
        if not ignore: sys.exit(2)
    rep = analyse(first, last, census, elig, tickinfo, integ)
    rep['gates'] = dict(gates=gates, failed=failed, examples=G['examples'], valid=(not failed and fmt != 'legacy'),
                        note='legacy format = plumbing only; verdicts are valid only for the new unfiltered table with all gates clean')
    json.dump(rep, open(out, 'w'), indent=1, default=str)
    print(json.dumps({k: rep[k] for k in ('gates', 'integrity', 'groups', 'train_groups', 'test_groups', 'eligible', 'selected_scalar',
                                           'rule', 'floor_hypothesis', 'verdict') if k in rep}, indent=1, default=str))
