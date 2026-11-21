import gzip, sys
sys.path.insert(0, sys.argv[1])
from tools.candidate_outcome_analysis import _frame
P = sys.argv[1] + '/build/github-results/preselection-energy-44752010601/ordinary-current-on-512-outcome.tsv.gz'
L0 = 653055
rows = []   # (offset, rendered60 outcomes, labelnotes)
with gzip.open(P, 'rt') as f:
    next(f); next(f)
    for line in f:
        fr = _frame(line)
        s = fr['sample']
        if s < L0 - 96000*6 or s >= L0 + 64: continue
        o60 = [v[3] for v in fr['voices'] if v[1] == 60]
        rows.append((s - L0, o60, tuple(sorted(n for (_, n, _) in fr['labels'])), fr['quiet']))
# contiguous run of rendered-60 ending at the last tick before label 42
i = len(rows) - 1
while i >= 0 and rows[i][0] >= 0: i -= 1
j = i
while j >= 0 and rows[j][1]: j -= 1
print('contiguous note-60 rendering ending at the label-42 start: from %.1f ms to %.1f ms (%d ticks, %.0f ms)' % (rows[j+1][0]/96, rows[i][0]/96, i-j, (rows[i][0]-rows[j+1][0]+64)/96))
import collections
c = collections.Counter()
for o, o60, labs, q in rows[j+1:i+1]:
    c[(labs, tuple(sorted(set(o60))))] += 1
for k, v in sorted(c.items(), key=lambda kv: -kv[1]): print(v, 'ticks (%.0f ms)' % (v*64/96), 'label notes', k[0], 'note-60 outcome codes', k[1])
# passage start for the labels seen
