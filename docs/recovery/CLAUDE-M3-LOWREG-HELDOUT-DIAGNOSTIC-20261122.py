"""POST HOC diagnostic of the held-out check (not registered).  Same trace, same frozen script, same plumbing: it wraps
`losers.collect` to keep the decisions the held-out script already computed and reports where the B(1.5) pool sits on the
`o_band_score` and `o_release` axes, split by what a fire would have done (harm / null) after the fact.  It changes no gate,
threshold or verdict of CLAUDE-M3-LOWREG-HELDOUT-PREREGISTRATION-20261122.md.

Usage: python3 -P -E CLAUDE-M3-LOWREG-HELDOUT-DIAGNOSTIC-20261122.py TRACE.tsv.gz OUT.json
"""
import importlib.util
import json
import os
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('heldout', os.path.join(HERE, 'CLAUDE-M3-LOWREG-HELDOUT-20261122.py'))
heldout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(heldout)

kept = {}
real_collect = heldout.losers.collect


def collect(path, occupied, find_label):
    kept['decisions'] = real_collect(path, occupied, find_label)
    return kept['decisions']


heldout.losers.collect = collect


def quantiles(values, qs=(0, 0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 1)):
    values = sorted(values)
    if not values:
        return {}
    return {str(q): round(values[min(len(values) - 1, int(q * (len(values) - 1)))], 6) for q in qs}


def klass(d):
    a, b = d['n_label'] is not None, d['q_label'] is not None
    return 'harm' if a and not b else 'swap' if a and b else 'good' if b else 'null'


with tempfile.TemporaryDirectory() as tmp:
    heldout.run('extended-middle', sys.argv[1], os.path.join(tmp, 'scratch.json'))
pool = [d for d in kept['decisions'] if d['ratio'] >= 1.5]
THRESH = (0.0615331, 0.108358, 0.174142)
out = dict(pool=len(pool), note='post hoc; not registered; verdict unchanged')
for name in ('harm', 'null', 'good', 'swap', 'all'):
    sub = [d for d in pool if name == 'all' or klass(d) == name]
    if not sub:
        continue
    out[name] = dict(
        n=len(sub),
        o_band_score_quantiles=quantiles([d['o_band_score'] for d in sub]),
        o_release_quantiles=quantiles([d['o_release'] for d in sub]),
        ratio_quantiles=quantiles([d['ratio'] for d in sub]),
        share_at_or_below=dict((str(t), round(sum(d['o_band_score'] <= t for d in sub) / len(sub), 5)) for t in THRESH),
        relation=dict(Counter(d['rel'] for d in sub)), kind=dict(Counter(d['kind'] for d in sub)))
with open(sys.argv[2], 'w') as stream:
    json.dump(out, stream, indent=1)
print(json.dumps(out, indent=1))
