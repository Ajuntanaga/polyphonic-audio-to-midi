#!/usr/bin/env python3
"""Where do the fine-frequency and committed-string fields exist, and do they agree with the annotated lane? (saved v5 table only: no audio, no dispatch, no replay)

  python3 -I CLAUDE-M3-FINE-COMMITTED-EVIDENCE-20261120.py PROJECT_ROOT V5_TABLE.tsv.gz OUT.json

PREDECLARED: over (tick, genuine label note) frames with a label mask of exactly one bit a, not a quiet tick, a candidate row with energy_observed != 0, per note band
(<48, 48-59, 60-71, 72-84): frames; fine_valid != 0; fine_mask != 0; fine_mask has bit a; fine_mask == only bit a; committed_mask != 0; committed_mask has bit a;
committed_mask == only bit a. Descriptive; it states where string-specific evidence exists at all and, where it does, whether it picks the annotated lane. Nothing tuned.
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
    lab = {}
    for (lid, note, mask) in fr['labels']:
        lab.setdefault(note, mask)
    for note, mask in lab.items():
        if mask == 0 or mask & (mask - 1):
            continue
        c = fr['rows'].get(note)
        if c is None or c.get('energy_observed') == 0:
            continue
        a = mask.bit_length() - 1
        k = cnt[band(note)]
        k['frames'] += 1
        k['fine_valid'] += 1 if c['fine_valid'] else 0
        for f in ('fine_mask', 'committed_mask'):
            v = c[f]
            k[f + '!=0'] += 1 if v else 0
            k[f + '_has_annotated'] += 1 if v >> a & 1 else 0
            k[f + '_only_annotated'] += 1 if v == 1 << a else 0
rep = {b: dict(c) for b, c in sorted(cnt.items())}
json.dump(rep, open(OUT, 'w'), indent=1)
print(json.dumps(rep, indent=1))
