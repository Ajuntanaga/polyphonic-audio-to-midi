"""Descriptive, saved current-ON ordinary trace only: P(upper rendered | annotated parent n, upper n+k annotated)
versus P(upper rendered | annotated parent n, upper n+k NOT annotated), k=12. Rendered = voice note n+k with any outcome."""
import gzip, sys, collections, json
sys.path.insert(0, sys.argv[1])
from tools.candidate_outcome_analysis import _frame
P = sys.argv[1] + '/build/github-results/preselection-energy-44752010601/ordinary-current-on-512-outcome.tsv.gz'
K = 12
T = collections.defaultdict(collections.Counter)
def band(u): return '<60' if u < 60 else '60-71' if u < 72 else '72+'
prev_gap_pass = collections.Counter()
with gzip.open(P, 'rt') as f:
    next(f); next(f)
    for line in f:
        fr = _frame(line)
        labs = {n for (_, n, _) in fr['labels']}
        if not labs: continue
        out = {v[1] for v in fr['voices']}
        for n in labs:
            u = n + K
            if u > 100: continue
            key = (band(u), 'upper_annotated' if u in labs else 'upper_NOT_annotated')
            T[key]['n'] += 1; T[key]['rendered'] += (u in out)
for key in sorted(T):
    t = T[key]; print(key, 'parent-frames=%d' % t['n'], 'upper rendered=%.1f%%' % (100*t['rendered']/t['n']))
