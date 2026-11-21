import gzip, sys, json
sys.path.insert(0, sys.argv[1])
from tools.candidate_outcome_analysis import _frame, _candidates
P = sys.argv[1] + '/build/github-results/preselection-energy-44752010601/ordinary-current-on-512-outcome.tsv.gz'
start = None; rows = []
with gzip.open(P, 'rt') as f:
    next(f); next(f)
    for line in f:
        fr = _frame(line)
        if 42 not in {l[0] for l in fr['labels']}: continue
        if start is None: start = fr['sample']
        c = _candidates(fr).get(60)
        sel = None if c is None else c['selection']
        rows.append((fr['sample'] - start, sel, None if c is None else round(c['score_ratio'], 3), 42 in fr['matched']))
# run-length encode selection state
segs = []
for o, s, r, m in rows:
    if segs and segs[-1][2] == (s, m): segs[-1][1] = o
    else: segs.append([o, o, (s, m)])
print('label42 start', start, 'ticks', len(rows))
print('segments [start_off, end_off, (selection, matched)] first 60:')
for a, b, k in segs[:60]: print(f'{a:6d}-{b:6d}  ({a/96:.0f}-{b/96:.0f} ms)  sel={k[0]} matched={k[1]}')
print('n segments', len(segs))
sel4 = [o for o, s, r, m in rows if s == 4]
print('selected(4) tick offsets (ms):', [round(o/96) for o in sel4])
