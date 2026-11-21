#!/usr/bin/env python3
"""Are missed labeled notes being replaced by a rendered sub-harmonic wrong note? (saved v5 table only: no audio, no dispatch, no replay)

  python3 -I CLAUDE-M3-SUBHARMONIC-GHOST-LINK-20261121.py PROJECT_ROOT V5_TABLE.tsv.gz OUT.json

Follows CLAUDE-M3-WRONG-NOTE-CENSUS-20261121.py: of 161,526 non-quiet wrong-note voice-frames, 50.3% are a harmonic interval BELOW a labeled note (81,310) and in 56,442 of
those the labeled note is itself not rendered. This asks how many missed labeled notes have such a ghost.

PREDECLARED BEFORE ANY NUMBER WAS COMPUTED (exploratory, associations only, one CURRENT configuration, annotation is not audibility):
  Population M = (tick, labeled note n) on non-quiet ticks with n not among the rendered notes of the tick (the frozen G_miss, minus quiet ticks), stage from the frozen
    classify() (formation, admission, dp, spectral, selected_not_rendered, unobserved, other, ...), note band of n.
  ghost_sub = some rendered voice of the tick has outcome 1 (wrong_note) and rendered note r with n - r in RELATED = {12, 19, 24, 28, 31, 36}.
  ghost_any = some rendered wrong_note voice in the tick.
  For ghost_sub frames only: the ghost's candidate row (detected note r) and the parent's row (note n) -> compare score_ratio (candidate score / admission threshold):
    parent_row_missing, parent_stronger (>), parent_equal_or_weaker (<=); both reported as counts. No cut is chosen.
  Reported: M by band and stage with the share ghost_sub and ghost_any; the same for ghost_sub restricted to notes >= 60; and a run-structure line: how many (label, ghost note)
  pairs and the median number of ticks a ghost accompanies a missed parent.
  Nothing is tuned; any rule this suggests would need its own predeclaration and a separately authorized screen.
  AMENDMENT (added after the first run, because ghost_any was 64-97% of missed frames, so a ghost near a missed note could be common by chance): a CONTROL on rendered labeled
  notes (n among the rendered notes), same ghost_sub definition, by band. The first-run numbers are kept; the control is what says whether ghost presence is specific to misses.
"""
import collections, json, sys
PROJ, TABLE, OUT = sys.argv[1:4]
sys.argv = [sys.argv[0], PROJ]
import importlib.util
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
RELATED = {12, 19, 24, 28, 31, 36}
band = lambda n: '<48' if n < 48 else '48-59' if n < 60 else '60-71' if n < 72 else '72-84' if n <= 84 else '>84'
ctrl = collections.defaultdict(collections.Counter)
cnt = collections.defaultdict(collections.Counter); cmp_ = collections.defaultdict(collections.Counter); pairs = collections.Counter()
for fr in m.load_new(TABLE):
    if fr['quiet']:
        continue
    rendered = {v[1] for v in fr['voices']}
    wrong = [(v[0], v[1]) for v in fr['voices'] if v[3] == 1]
    lab = {}
    for (lid, note, mask) in fr['labels']:
        lab.setdefault(note, lid)
    for n, lid in lab.items():
        if n in rendered:
            ctrl[band(n)]['N'] += 1
            ctrl[band(n)]['ghost_sub'] += 1 if any((n - r) in RELATED for (d, r) in wrong) else 0
            continue
        c = fr['rows'].get(n)
        state, _ = m.classify(c, False, False, n)
        b = band(n)
        ghosts = [(d, r) for (d, r) in wrong if (n - r) in RELATED]
        k = cnt[(b, state)]
        k['M'] += 1
        k['ghost_any'] += 1 if wrong else 0
        if ghosts:
            k['ghost_sub'] += 1
            d, r = min(ghosts, key=lambda x: n - x[1])
            pairs[(lid, r)] += 1
            gr = fr['rows'].get(d)
            if c is None or gr is None or c.get('score_ratio') is None or gr.get('score_ratio') is None:
                cmp_[b]['row_missing'] += 1
            elif c['score_ratio'] > gr['score_ratio']:
                cmp_[b]['parent_stronger'] += 1
            else:
                cmp_[b]['parent_equal_or_weaker'] += 1
rows = {}
for (b, st), k in sorted(cnt.items()):
    rows['%s|%s' % (b, st)] = dict(k, ghost_sub_pct=round(100 * k['ghost_sub'] / k['M'], 1), ghost_any_pct=round(100 * k['ghost_any'] / k['M'], 1))
byband = collections.defaultdict(collections.Counter)
for (b, st), k in cnt.items():
    byband[b].update(k)
bb = {b: dict(k, ghost_sub_pct=round(100 * k['ghost_sub'] / k['M'], 1), ghost_any_pct=round(100 * k['ghost_any'] / k['M'], 1)) for b, k in sorted(byband.items())}
lens = sorted(pairs.values())
rep = dict(by_band=bb, by_band_and_stage=rows, score_ratio_parent_vs_ghost={b: dict(v) for b, v in sorted(cmp_.items())},
           control_rendered_labeled_notes={b: dict(v, ghost_sub_pct=round(100 * v['ghost_sub'] / v['N'], 1)) for b, v in sorted(ctrl.items())},
           pairs=dict(n=len(pairs), median_ticks=lens[len(lens) // 2] if lens else None, max_ticks=lens[-1] if lens else None))
json.dump(rep, open(OUT, 'w'), indent=1)
print(json.dumps(rep, indent=1))
