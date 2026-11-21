import gzip, sys, json
sys.path.insert(0, sys.argv[1])
from tools.candidate_outcome_analysis import _frame
P = sys.argv[1] + '/build/github-results/preselection-energy-44752010601/ordinary-current-on-512-outcome.tsv.gz'
start = {}; seq = {41: [], 42: []}
with gzip.open(P, 'rt') as f:
    next(f); next(f)
    for line in f:
        fr = _frame(line)
        for (lid, note, mask) in fr['labels']:
            if lid in seq:
                start.setdefault(lid, fr['sample'])
                seq[lid].append((fr['sample'] - start[lid], lid in fr['matched']))
res = {}
for lid, s in seq.items():
    w = [(o, m) for (o, m) in s if 30720 <= o < 46080]
    runs = []; cur = 0; segs = []; b = None
    for o, m in w:
        if m:
            if cur == 0: b = o
            cur += 1
        else:
            if cur: runs.append((b, cur)); cur = 0
    if cur: runs.append((b, cur))
    res[lid] = dict(win_ticks=len(w), win_matched=sum(m for _, m in w), win_runs=runs,
                    win_longest_ticks=max([r[1] for r in runs] or [0]),
                    win_longest_samples=64 * max([r[1] for r in runs] or [0]),
                    unmatched_offsets=[o for o, m in w if not m][:20],
                    ticks_total=len(s), tick_step_set=sorted({s[i+1][0] - s[i][0] for i in range(len(s)-1)})[:5])
print(json.dumps(res, indent=1))
