#!/usr/bin/env python3
"""Quiet-floor included/excluded census of the v5 table (Codex request, CODEX-M3-V5-VERDICT-REPLY-20261120.md).

  python3 -I CLAUDE-M3-QUIET-FLOOR-CENSUS-20261120.py PROJECT_ROOT TABLE.tsv.gz OUT.json BASELINE_ANALYSIS.json

Saved data only: no audio, no dispatch, no refit, no new scalar. It re-reads the same table with the frozen loaders and
classifier of CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py (imported, not copied) and reconciles every (band, stage) count to the
original census in BASELINE_ANALYSIS.json, so a drifting denominator fails loudly. Pure Python, one streaming pass.

PREDECLARED BEFORE ANY NUMBER WAS COMPUTED (parameter-free, nothing tuned):
  ratio    = score_energy / floor_stats.med_score of the same tick, using the frozen `score_over_floor_median` definition;
             available only when the row's energy_observed == 1 and the tick's median score is positive.
  at_floor = ratio <= 1.0   (the note is no stronger than the median observed pitch that tick: no pitch-specific energy)
  above    = ratio >  1.0
  unknown  = ratio unavailable. Unknown frames stay in every denominator and are reported as their own column, never
             imputed and never dropped.
  "included" view = all G_miss frames (the original census). "excluded" view = G_miss minus at_floor frames (unknown kept).
  Fixed histogram bins of the ratio: <=0.25, 0.25-0.5, 0.5-1, 1-2, 2-5, 5-20, >20 (descriptive; no cut is selected from it).
  Passage = the original merged label-interval group; each passage counts once in passage-weighted shares.
  The original verdict is changed ONLY if, in the excluded view for notes >= 60, evidence formation becomes the majority of
  G_miss frames (branch B) or admission is no longer the largest stage. Branches A and C come from the separate scalar
  analysis, and quiet-floor exclusion is a secondary sensitivity only (Codex freeze, item 4), so they are not reopened here.
  Label 42 tail and the preceding false hold use the original Step D definitions (note 60 on the table's tick grid).
"""
import collections, importlib.util, json, sys

PROJ, TABLE, OUT, BASE = sys.argv[1:5]
sys.argv = [sys.argv[0], PROJ]                       # the frozen module reads PROJ from argv[1] at import
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

BIN_EDGES = (0.25, 0.5, 1.0, 2.0, 5.0, 20.0)
BIN_NAMES = ('<=0.25', '0.25-0.5', '0.5-1', '1-2', '2-5', '5-20', '>20')


def ratio_of(c, med):
    if c is None or c.get('energy_observed') != 1 or c.get('score_energy') is None or med is None or med <= 0:
        return None
    return c['score_energy'] / med


def flag_of(r):
    return 'floor_unknown' if r is None else ('at_floor' if r <= 1.0 else 'above_floor')


def bin_of(r):
    for i, e in enumerate(BIN_EDGES):
        if r <= e: return BIN_NAMES[i]
    return BIN_NAMES[-1]


def quantiles(vals):
    if not vals: return None
    v = sorted(vals); n = len(v)
    q = lambda p: v[min(n - 1, int(p * n))]
    return dict(n=n, min=v[0], p25=q(0.25), median=q(0.5), p75=q(0.75), max=v[-1])


def main():
    first, last = {}, {}
    cross = collections.defaultdict(collections.Counter)         # (band, lid) -> (state, flag) counter, rendered kept as a state
    hist = collections.defaultdict(collections.Counter)          # band -> ratio bin (G_miss with a ratio)
    tickinfo, ticks = [], 0
    for fr in m.load_new(TABLE):
        s = fr['sample']; ticks += 1
        lab_notes = {}
        for (lid, note, mask) in fr['labels']:
            first.setdefault(lid, s); last[lid] = s
            lab_notes.setdefault(note, lid)
        voice_notes = {v[1] for v in fr['voices']}
        fl = fr.get('floor'); med = fl['med_score'] if fl else None
        for note, lid in lab_notes.items():
            rendered = note in voice_notes
            c = fr['rows'].get(note)
            state, formed = m.classify(c, rendered, fr['quiet'], note)
            r = ratio_of(c, med)
            band = m.band_of(note)
            cross[(band, lid)][('rendered' if rendered else state, flag_of(r))] += 1
            if not rendered and r is not None: hist[band][bin_of(r)] += 1
        c60 = fr['rows'].get(60); r60 = 60 in voice_notes
        st60 = 'rendered' if r60 else m.classify(c60, r60, fr['quiet'])[0]
        tickinfo.append((s, st60, flag_of(ratio_of(c60, med)), ratio_of(c60, med), r60, 42 in lab_notes.values()))
    gid, ngroups = m.groups_from_labels(first, last)
    rep = {'ticks': ticks, 'groups': ngroups, 'predeclared': __doc__.split('PREDECLARED')[1].split('"""')[0].strip()}

    # ---- per band: stage x flag, included/excluded views, reconcile to the original census
    base = json.load(open(BASE))['census']
    bands = ('<48', '48-59', '60-71', '72+')
    byband = collections.defaultdict(collections.Counter)
    for (band, lid), cnt in cross.items(): byband[band].update(cnt)
    rep['bands'], mism = {}, []
    for band in bands:
        cnt = byband[band]
        by_state = collections.defaultdict(lambda: collections.Counter())
        for (st, fl_), n in cnt.items(): by_state[st][fl_] += n
        for st, flags in by_state.items():
            if sum(flags.values()) != base['%s|G' % band]['frames'].get(st, 0): mism.append((band, st, sum(flags.values())))
        for st, n in base['%s|G' % band]['frames'].items():
            if st not in by_state: mism.append((band, st, 0))
        miss = {st: dict(f) for st, f in by_state.items() if st != 'rendered'}
        tot = lambda fl_: sum(f.get(fl_, 0) for f in miss.values())
        gm = sum(tot(x) for x in ('at_floor', 'above_floor', 'floor_unknown'))
        incl = {st: sum(f.values()) for st, f in miss.items()}
        excl = {st: sum(v for k, v in f.items() if k != 'at_floor') for st, f in miss.items()}
        share = lambda d: {st: round(n / sum(d.values()), 4) for st, n in sorted(d.items())} if sum(d.values()) else {}
        rend = dict(by_state['rendered']) if 'rendered' in by_state else {}
        rep['bands'][band] = dict(
            g_miss_frames=gm, at_floor=tot('at_floor'), above_floor=tot('above_floor'), floor_unknown=tot('floor_unknown'),
            at_floor_share_of_g_miss=round(tot('at_floor') / gm, 4) if gm else None,
            stage_by_flag=miss, included_stage_share=share(incl), excluded_stage_share=share(excl),
            excluded_frames=sum(excl.values()), rendered_genuine_by_flag=rend,
            ratio_histogram_g_miss={k: hist[band].get(k, 0) for k in BIN_NAMES})
    rep['reconciliation_to_original_census'] = dict(mismatches=mism, ok=not mism)

    # ---- verdict sensitivity: notes >= 60, included vs excluded
    def pooled(view):
        d = collections.Counter()
        for band in ('60-71', '72+'):
            for st, f in rep['bands'][band]['stage_by_flag'].items():
                d[st] += sum(f.values()) if view == 'included' else sum(v for k, v in f.items() if k != 'at_floor')
        return d
    for view in ('included', 'excluded'):
        d = pooled(view); t = sum(d.values())
        rep['verdict_%s' % view] = dict(g_miss_frames=t, stage_frames=dict(d), formation_share=round(d['formation'] / t, 4) if t else None,
                                        largest_stage=max(d, key=d.get) if d else None)
    inc, exc = rep['verdict_included'], rep['verdict_excluded']
    rep['original_verdict_changed'] = bool(exc['formation_share'] is not None and (exc['formation_share'] > 0.5 or exc['largest_stage'] != 'admission'))

    # ---- per passage: counts by band, and the passage-weighted shares
    per = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.Counter()))
    for (band, lid), cnt in cross.items():
        g = gid[lid]
        for (st, fl_), n in cnt.items():
            if st == 'rendered': per[g][band]['rendered'] += n
            else:
                per[g][band]['g_miss'] += n; per[g][band][fl_] += n
                if fl_ == 'above_floor': per[g][band]['above_floor:' + st] += n
    rep['per_passage'] = {str(g): {b: dict(per[g][b]) for b in bands if per[g][b]} for g in sorted(per)}
    rep['passage_summary'] = {}
    for band in bands:
        sh_floor, sh_above, sh_unk, n_pass = [], [], [], 0
        for g in per:
            c = per[g][band]
            if c['g_miss']:
                n_pass += 1
                sh_floor.append(c['at_floor'] / c['g_miss']); sh_above.append(c['above_floor'] / c['g_miss']); sh_unk.append(c['floor_unknown'] / c['g_miss'])
        rep['passage_summary'][band] = dict(
            passages_with_g_miss=n_pass,
            passage_weighted_at_floor_share=round(sum(sh_floor) / n_pass, 4) if n_pass else None,
            passage_weighted_above_floor_share=round(sum(sh_above) / n_pass, 4) if n_pass else None,
            passage_weighted_unknown_share=round(sum(sh_unk) / n_pass, 4) if n_pass else None,
            at_floor_share_distribution=quantiles(sh_floor),
            passages_majority_at_floor=sum(1 for x in sh_floor if x > 0.5),
            passages_majority_above_floor=sum(1 for x in sh_above if x > 0.5))

    # ---- label 42 tail and false hold (original Step D definitions)
    l42 = [i for i, t in enumerate(tickinfo) if t[5]]
    seg = {}
    if l42:
        i0, i1 = l42[0], l42[-1]
        r42 = [i for i in l42 if tickinfo[i][4]]
        coast_end = r42[-1] if r42 else None
        tail = list(range(coast_end + 1, i1 + 1)) if coast_end is not None else []
        j = i0 - 1
        while j >= 0 and tickinfo[j][4]: j -= 1
        hold = list(range(j + 1, i0))
        for name, idx in (('label42_tail', tail), ('false_hold', hold)):
            cc = collections.Counter((tickinfo[i][1], tickinfo[i][2]) for i in idx)
            hh = collections.Counter(bin_of(tickinfo[i][3]) for i in idx if tickinfo[i][3] is not None)
            seg[name] = dict(ticks=len(idx), first_sample=tickinfo[idx[0]][0] if idx else None, last_sample=tickinfo[idx[-1]][0] if idx else None,
                             stage_by_flag={'%s|%s' % k: v for k, v in sorted(cc.items())},
                             flag_totals={f: sum(v for (st, fl_), v in cc.items() if fl_ == f) for f in ('at_floor', 'above_floor', 'floor_unknown')},
                             ratio_histogram={k: hh.get(k, 0) for k in BIN_NAMES})
    rep['label42'] = seg
    json.dump(rep, open(OUT, 'w'), indent=1, default=str)
    keys = ('ticks', 'groups', 'reconciliation_to_original_census', 'verdict_included', 'verdict_excluded', 'original_verdict_changed')
    print(json.dumps({k: rep[k] for k in keys}, indent=1, default=str))


main()
