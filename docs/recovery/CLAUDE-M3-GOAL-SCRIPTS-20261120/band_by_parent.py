import gzip, sys, json, collections
sys.path.insert(0, sys.argv[1])
from tools.candidate_outcome_analysis import _frame, _candidates
P = sys.argv[1] + '/build/github-results/preselection-energy-44752010601/ordinary-current-on-512-outcome.tsv.gz'
HARM = (12, 19, 24, 28, 31)
def band(n): return '<48' if n < 48 else '48-59' if n < 60 else '60-71' if n < 72 else '72+'
T = collections.defaultdict(collections.Counter)
D = collections.defaultdict(collections.Counter)
with gzip.open(P, 'rt') as f:
    next(f); next(f)
    for line in f:
        fr = _frame(line)
        out = {v[1] for v in fr['voices'] if v[3] in (0, 2)}
        labs = {n for (_, n, _) in fr['labels']}
        cands = None
        for (lid, note, mask) in fr['labels']:
            par = any((note - k) in labs for k in HARM)
            key = (band(note), 'parent' if par else 'noparent')
            t = T[key]; t['n'] += 1; t['present'] += note in out; t['matched'] += lid in fr['matched']
            if note not in out:
                if cands is None: cands = _candidates(fr)
                c = cands.get(note)
                D[key]['none' if c is None else 'sel%d' % c['selection']] += 1
print('band     group      labelframes  present%  matched%   | missing split: none/below_thr(1)/spec_rej(2)/dp_evict(3)/selected_not_rendered(4)/coast(5)/quiet(0)')
for b in ('<48', '48-59', '60-71', '72+'):
    for g in ('noparent', 'parent'):
        t = T[(b, g)]
        if not t['n']: continue
        d = D[(b, g)]; m = sum(d.values())
        print(f"{b:6s} {g:9s} {t['n']:9d}  {100*t['present']/t['n']:6.1f}   {100*t['matched']/t['n']:6.1f}   | " +
              ' '.join(f"{k}={100*d[k]/m:.0f}%" for k in ('none', 'sel1', 'sel2', 'sel3', 'sel4', 'sel5', 'sel0')))
tot = sum(t['n'] for t in T.values()); print('total label-frames', tot)
for b in ('<48', '48-59', '60-71', '72+'):
    n = sum(T[(b, g)]['n'] for g in ('noparent', 'parent')); p = sum(T[(b, g)]['present'] for g in ('noparent', 'parent'))
    m = sum(T[(b, g)]['matched'] for g in ('noparent', 'parent'))
    print(f'band {b:6s} labelframes {n:7d} ({100*n/tot:.1f}%)  present {100*p/n:.1f}%  matched {100*m/n:.1f}%  missing-label-frames {n-p}')
