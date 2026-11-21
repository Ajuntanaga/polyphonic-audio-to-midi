#!/usr/bin/env python3
"""Sanity check that 'string 5 never right on rendered upper notes' is not a label/detector string-index mismatch (saved v5 table only).

  python3 -I CLAUDE-M3-STRING-INDEX-SANITY-20261120.py PROJECT_ROOT V5_TABLE.tsv.gz OUT.json

PREDECLARED: over every rendered voice with outcome in {0 correct_voice, 2 wrong_string}, quiet ticks excluded, count by (note band: <48, 48-59, 60-71, 72-84) x
(assigned string 0..7): voices, and how many are outcome 0. If assigned string 5 has correct voices at lower bands, the 61-84 zero is note-range specific, not an index
mismatch. Descriptive only; nothing tuned.
"""
import collections, json, sys
PROJ, TABLE, OUT = sys.argv[1:4]
sys.argv = [sys.argv[0], PROJ]
import importlib.util
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
band = lambda n: '<48' if n < 48 else '48-59' if n < 60 else '60-71' if n < 72 else '72-84'
cnt = collections.defaultdict(collections.Counter)
for fr in m.load_new(TABLE):
    if fr['quiet']:
        continue
    for v in fr['voices']:
        if v[3] in (0, 2):
            k = '%s|string=%d' % (band(v[1]), v[2])
            cnt[k]['voices'] += 1
            cnt[k]['correct'] += 1 if v[3] == 0 else 0
rep = {k: dict(v) for k, v in sorted(cnt.items())}
json.dump(rep, open(OUT, 'w'), indent=1)
print(json.dumps(rep, indent=1))
