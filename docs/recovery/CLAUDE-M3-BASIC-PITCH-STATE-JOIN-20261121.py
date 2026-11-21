#!/usr/bin/env python3
"""Where was CURRENT blind while Basic Pitch heard the note? (saved v5 table + saved Basic Pitch report only: no audio, no dispatch, no download, no replay)

  python3 -I CLAUDE-M3-BASIC-PITCH-STATE-JOIN-20261121.py PROJECT_ROOT V5_TABLE.tsv.gz REPORT.json OUT.json

Follows CLAUDE-M3-BASIC-PITCH-READ-20261121.md section 5.4. Basic Pitch covers 65.6% of the 60-71 and 72+ annotated time where saved CURRENT covers
5.8% and 0%. The question is whether CURRENT's own table shows evidence for those notes that it then fails to render (selection / penalty), or
shows no usable evidence (candidate stage). The join is per LABEL: the report carries Basic Pitch's present duration per label but no frame timing,
so no per-tick alignment with Basic Pitch is claimed.

PREDECLARED BEFORE ANY NUMBER WAS COMPUTED (descriptive; one dataset, one block (512), one CURRENT configuration; presence is pitch only, not string):
  Table: ordinary-current-on-512-outcome-v5.tsv.gz (sha256 of the decompressed trace b664c7ff...), read with the frozen loader load_new.
  Labels: report datasets.ordinary.comparison.label_deltas, matched to table label ids by (label_index == table label id) AND note equality; any
    mismatch aborts the run (nothing is guessed). Per label f_bp = model_present_samples / annotated_samples, f_cur = current_present_samples / annotated_samples.
  Per-tick state of (tick, label, note n): 'rendered' if a voice with rendered note n has outcome in {0, 2} (pitch-correct, any string);
    otherwise the frozen contract's classify(c, rendered=False, quiet_tick, n) state: unavailable, out_of_range, quiet, unobserved, spectral, dp,
    selected_not_rendered, formation, admission, other. Same-note labels in one tick (unisons) each count the same rendered note: noted limitation.
  Groups of the non-rendered states (fixed now): NO_EVIDENCE = {unavailable, out_of_range, quiet, unobserved} (the detector produced no usable
    energy for that pitch this tick, or the tick was quiet); OBSERVED = {spectral, dp, selected_not_rendered, formation, admission, other}
    (energy was observed and the note was not rendered). The OBSERVED states are not subdivided into causes here.
  Population P: labels with 60 <= n <= 84 and f_cur < 0.10 (CURRENT blind). Strata by f_bp: HIGH f_bp >= 0.50, MID 0 < f_bp < 0.50, ZERO f_bp == 0.
  Control C: labels with 60 <= n <= 84 and f_cur >= 0.50 (CURRENT hears them), any f_bp.
  For each stratum report: labels, ticks, tick-weighted share of rendered / NO_EVIDENCE / OBSERVED, each state's share, the per-label median
    energy_observed fraction, and f_bp / f_cur sums. Plus a sanity check: Pearson r across all labels between the table's per-label rendered share
    and the report's f_cur (should be high; a low value means the label join or the unit is wrong and nothing below is to be trusted).
  Reading rule, fixed now and descriptive: among the NON-rendered ticks of the HIGH stratum, NO_EVIDENCE >= 2/3 means the gap is mainly candidate
    evaluation (front end); OBSERVED >= 2/3 means mainly what happens after observation (selection, penalty, admission); otherwise mixed. The ZERO
    stratum is the comparison: a stratum difference is reported, not interpreted as cause.
"""
import collections, json, statistics, sys

PROJ, TABLE, REPORT, OUT = sys.argv[1:5]
sys.argv = [sys.argv[0], PROJ]
import importlib.util
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

NO_EVIDENCE = ('unavailable', 'out_of_range', 'quiet', 'unobserved')
OBSERVED = ('spectral', 'dp', 'selected_not_rendered', 'formation', 'admission', 'other')


def main():
    rep = json.load(open(REPORT))
    L = {r['label_index']: r for r in rep['datasets']['ordinary']['comparison']['label_deltas']}
    per = collections.defaultdict(lambda: dict(note=None, ticks=0, observed=0, state=collections.Counter()))
    n_ticks = 0
    for fr in m.load_new(TABLE):
        n_ticks += 1
        if not fr['labels']:
            continue
        rendered = {v[1] for v in fr['voices'] if v[3] in (0, 2)}
        for (lid, note, mask) in fr['labels']:
            p = per[lid]
            if p['note'] is None:
                p['note'] = note
            elif p['note'] != note:
                raise SystemExit('label %d has two notes in the table' % lid)
            p['ticks'] += 1
            c = fr['rows'].get(note)
            if c is not None and c.get('energy_observed') == 1:
                p['observed'] += 1
            if note in rendered:
                p['state']['rendered'] += 1
            else:
                st, _ = m.classify(c, False, fr['quiet'], note)
                p['state'][st] += 1
    bad = [lid for lid, p in per.items() if lid not in L or L[lid]['midi_note'] != p['note']]
    if bad:
        raise SystemExit('label join mismatch on %d labels, e.g. %r' % (len(bad), bad[:5]))
    missing = [lid for lid in L if lid not in per]

    rows = []
    for lid, p in per.items():
        r = L[lid]
        a = r['annotated_samples']
        rows.append(dict(label=lid, note=p['note'], ticks=p['ticks'], observed_frac=p['observed'] / p['ticks'] if p['ticks'] else 0,
                         rendered_frac=p['state']['rendered'] / p['ticks'] if p['ticks'] else 0,
                         f_bp=r['model_present_samples'] / a, f_cur=r['current_present_samples'] / a, state=dict(p['state'])))
    xs = [r['rendered_frac'] for r in rows]
    ys = [r['f_cur'] for r in rows]
    corr = statistics.correlation(xs, ys)

    def stratum(sel):
        ticks = sum(r['ticks'] for r in sel)
        st = collections.Counter()
        for r in sel:
            st.update(r['state'])
        nonr = ticks - st['rendered']
        noev = sum(st[k] for k in NO_EVIDENCE)
        obs = sum(st[k] for k in OBSERVED)
        med = statistics.median(r['observed_frac'] for r in sel) if sel else None
        return dict(labels=len(sel), ticks=ticks, rendered_share=st['rendered'] / ticks if ticks else None,
                    non_rendered_ticks=nonr,
                    no_evidence_share_of_non_rendered=noev / nonr if nonr else None,
                    observed_share_of_non_rendered=obs / nonr if nonr else None,
                    reading=(None if not nonr else 'front-end' if noev / nonr >= 2 / 3 else 'after-observation' if obs / nonr >= 2 / 3 else 'mixed'),
                    state_share_of_non_rendered={k: st[k] / nonr for k in NO_EVIDENCE + OBSERVED if nonr and st[k]},
                    median_label_energy_observed_fraction=med,
                    sum_f_bp=sum(r['f_bp'] for r in sel), sum_f_cur=sum(r['f_cur'] for r in sel))

    hi = [r for r in rows if 60 <= r['note'] <= 84]
    blind = [r for r in hi if r['f_cur'] < 0.10]
    out = dict(table_ticks=n_ticks, labels_in_table=len(per), labels_missing_from_table=len(missing), sanity_pearson_rendered_share_vs_report_f_cur=corr,
               population_60_84=len(hi), blind_population=len(blind),
               strata=dict(
                   HIGH=stratum([r for r in blind if r['f_bp'] >= 0.50]),
                   MID=stratum([r for r in blind if 0 < r['f_bp'] < 0.50]),
                   ZERO=stratum([r for r in blind if r['f_bp'] == 0]),
                   CONTROL_cur_hears=stratum([r for r in hi if r['f_cur'] >= 0.50])),
               by_band_of_blind_HIGH={b: stratum([r for r in blind if r['f_bp'] >= 0.50 and lo <= r['note'] <= hi_])
                                      for b, lo, hi_ in (('60-71', 60, 71), ('72-84', 72, 84))})
    json.dump(out, open(OUT, 'w'), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))


main()
