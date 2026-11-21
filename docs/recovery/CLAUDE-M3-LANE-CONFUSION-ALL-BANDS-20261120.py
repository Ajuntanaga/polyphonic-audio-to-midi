#!/usr/bin/env python3
"""Annotated-lane x assigned-lane confusion for every rendered voice at every note band (saved v5 table only: no audio, no dispatch, no replay).

  python3 -I CLAUDE-M3-LANE-CONFUSION-ALL-BANDS-20261120.py PROJECT_ROOT V5_TABLE.tsv.gz OUT.json

Follows CLAUDE-M3-STRING-INDEX-SANITY-20261120.py, which found voices assigned to string 5 almost never correct (24 of 12,902 at notes 48-59, 0 of 680 at 60-71) and
string 7 never correct at 60-71 (0 of 1,804). PREDECLARED: over rendered voices with outcome in {0,2}, quiet ticks excluded, whose label mask has exactly one bit, count
(annotated lane, assigned lane) per note band (<48, 48-59, 60-71, 72-84). Descriptive; it shows whether the mismatch is a clean relabelling of strings (an index mismatch)
or a spread (an evidence problem). Nothing tuned.
"""
import collections, json, sys
PROJ, TABLE, OUT = sys.argv[1:4]
sys.argv = [sys.argv[0], PROJ]
import importlib.util
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
band = lambda n: '<48' if n < 48 else '48-59' if n < 60 else '60-71' if n < 72 else '72-84'
cnt = collections.defaultdict(collections.Counter)
multi = collections.Counter()
for fr in m.load_new(TABLE):
    if fr['quiet']:
        continue
    lab = {}
    for (lid, note, mask) in fr['labels']:
        lab.setdefault(note, mask)
    for v in fr['voices']:
        if v[3] not in (0, 2):
            continue
        mask = lab.get(v[1], 0)
        if mask == 0 or mask & (mask - 1):
            multi[band(v[1])] += 1
            continue
        cnt[band(v[1])]['ann=%d|assigned=%d' % (mask.bit_length() - 1, v[2])] += 1
rep = {b: dict(sorted(c.items())) for b, c in sorted(cnt.items())}
rep['skipped_multi_or_zero_mask_voices'] = dict(multi)
json.dump(rep, open(OUT, 'w'), indent=1)
for b in ('<48', '48-59', '60-71', '72-84'):
    print(b, json.dumps(rep.get(b, {})))
print('skipped', dict(multi))
