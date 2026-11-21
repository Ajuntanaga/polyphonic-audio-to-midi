#!/usr/bin/env python3
"""What are the wrong-note voices? Census of the largest false class (saved v5 table only: no audio, no dispatch, no replay).

  python3 -I CLAUDE-M3-WRONG-NOTE-CENSUS-20261121.py PROJECT_ROOT V5_TABLE.tsv.gz OUT.json

Why: CURRENT has 164,263 wrong-note voice-frames, 92,638 wrong-string and 62,856 gap (ordinary@512). The relief thread only touched the DP-evicted miss class; the largest
false class has not been characterised in the saved table. This does that, descriptively. It proposes nothing.

PREDECLARED BEFORE ANY NUMBER WAS COMPUTED (exploratory, associations only, one CURRENT configuration, annotation is not audibility):
  Population W = voices with outcome 1 (wrong_note) on non-quiet ticks. rendered = voice[1], detected = voice[0].
  L = the set of labeled notes of the same tick (labels carry a note and a string mask; masks are ignored here).
  Relation (first rule that holds, in this order), RELATED = {12, 19, 24, 28, 31, 36}:
    harmonic_above  : some l in L with rendered - l in RELATED   (rendered note is a harmonic-interval above a labeled note)
    subharmonic_below: some l in L with l - rendered in RELATED
    near_semitone   : some l in L with 1 <= |rendered - l| <= 2
    other
  Also reported: rebinned (detected != rendered); whether a labeled note related to it is itself rendered in the tick ("parent_rendered", for harmonic_above and
  subharmonic_below, using the closest such label); the candidate selection code of the detected note (0 quiet,1 below_threshold,2 spectral,3 dp,4 selected,5 coasting);
  note bands (<48, 48-59, 60-71, 72-84, >84); the number of labeled notes in the tick (1, 2, 3+); and run structure: runs = maximal consecutive ticks of one rendered note
  as wrong_note, with counts of runs, frames in runs of <= 4 ticks, 5-99, >= 100, and the longest run.
  Shares are over W frames. Nothing is tuned or thresholded; any rule this suggests needs its own predeclaration and a separately authorized screen.
"""
import collections, json, sys
PROJ, TABLE, OUT = sys.argv[1:4]
sys.argv = [sys.argv[0], PROJ]
import importlib.util
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
RELATED = {12, 19, 24, 28, 31, 36}
band = lambda n: '<48' if n < 48 else '48-59' if n < 60 else '60-71' if n < 72 else '72-84' if n <= 84 else '>84'
tot = collections.Counter(); rel = collections.Counter(); sel = collections.Counter(); bnd = collections.Counter()
nl = collections.Counter(); parent = collections.Counter(); rebin = collections.Counter(); cross = collections.Counter()
runs_open = {}; runs = []
for fr in m.load_new(TABLE):
    seen = set()
    if not fr['quiet']:
        L = sorted({n for (_, n, _) in fr['labels']})
        rendered_notes = {v[1] for v in fr['voices']}
        for v in fr['voices']:
            if v[3] != 1:
                continue
            det, ren = v[0], v[1]
            tot['W'] += 1
            kind = 'other'; par = None
            ha = [l for l in L if ren - l in RELATED]; sb = [l for l in L if l - ren in RELATED]
            ns = [l for l in L if 1 <= abs(ren - l) <= 2]
            if ha: kind = 'harmonic_above'; par = min(ha, key=lambda l: ren - l)
            elif sb: kind = 'subharmonic_below'; par = min(sb, key=lambda l: l - ren)
            elif ns: kind = 'near_semitone'
            rel[kind] += 1
            if par is not None:
                parent[(kind, 'parent_rendered' if par in rendered_notes else 'parent_not_rendered')] += 1
            rebin['rebinned' if det != ren else 'same'] += 1
            c = fr['rows'].get(det)
            sel[c['selection'] if c else 'no_row'] += 1
            bnd[band(ren)] += 1
            nl['1' if len(L) == 1 else '2' if len(L) == 2 else '3+'] += 1
            cross[(kind, band(ren))] += 1
            seen.add(ren)
            r = runs_open.get(ren)
            if r is not None and r[0] == fr['tick'] - 1:
                runs_open[ren] = (fr['tick'], r[1] + 1)
            else:
                if r is not None: runs.append(r[1])
                runs_open[ren] = (fr['tick'], 1)
    for k in [k for k, r in runs_open.items() if r[0] != fr['tick']]:
        runs.append(runs_open.pop(k)[1])
runs += [r[1] for r in runs_open.values()]
W = tot['W']
pct = lambda d: {str(k): [v, round(100 * v / W, 1)] for k, v in sorted(d.items(), key=lambda kv: -kv[1])}
rep = dict(W_frames=W, relation=pct(rel), parent_state={'%s|%s' % k: v for k, v in sorted(parent.items())}, rebinned=pct(rebin),
           selection_code_of_detected=pct(sel), band=pct(bnd), labels_in_tick=pct(nl),
           relation_by_band={'%s|%s' % k: v for k, v in sorted(cross.items())},
           runs=dict(n=len(runs), le4_frames=sum(r for r in runs if r <= 4), mid_frames=sum(r for r in runs if 5 <= r < 100),
                     ge100_frames=sum(r for r in runs if r >= 100), longest=max(runs) if runs else None,
                     runs_le4=sum(1 for r in runs if r <= 4), runs_ge100=sum(1 for r in runs if r >= 100)))
json.dump(rep, open(OUT, 'w'), indent=1)
print(json.dumps(rep, indent=1))
