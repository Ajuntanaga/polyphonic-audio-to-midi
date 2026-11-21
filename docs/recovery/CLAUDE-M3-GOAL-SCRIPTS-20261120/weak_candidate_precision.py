"""Descriptive only: among serialized below_threshold (selection 1) candidates that are not rendered, how many
are annotated pitches (genuine, missing) versus not annotated at that tick, by score/threshold bin and band.
No threshold is chosen or fitted; bins are fixed in advance (0.20-0.30, 0.30-0.50, 0.50-1.00, >=1.00)."""
import gzip, sys, json, collections
sys.path.insert(0, sys.argv[1])
from tools.candidate_outcome_analysis import _frame, _candidates
P = sys.argv[1] + '/build/github-results/preselection-energy-44752010601/ordinary-current-on-512-outcome.tsv.gz'
HARM = (12, 19, 24, 28, 31)
BINS = ((0.20, 0.30), (0.30, 0.50), (0.50, 1.00), (1.00, 1e9))
def b(r):
    for lo, hi in BINS:
        if lo <= r < hi: return f'{lo:.2f}-{hi:.2f}' if hi < 1e8 else f'>={lo:.2f}'
    return '<0.20'
def band(n): return '>=60' if n >= 60 else '<60'
T = collections.defaultdict(collections.Counter)
with gzip.open(P, 'rt') as f:
    next(f); next(f)
    for line in f:
        fr = _frame(line)
        out = {v[1] for v in fr['voices'] if v[3] in (0, 2)}
        outall = {v[1] for v in fr['voices']}
        labs = {n for (_, n, _) in fr['labels']}
        for note, c in _candidates(fr).items():
            if c['selection'] != 1 or note in outall: continue
            key = (band(note), b(c['score_ratio']))
            if note in labs: cls = 'annotated(missing)'
            elif any((note - k) in labs for k in HARM): cls = 'unannotated_harmonic_of_annotated'
            elif not labs: cls = 'unannotated_gap'
            else: cls = 'unannotated_other'
            T[key][cls] += 1
            T[key]['n'] += 1
for key in sorted(T):
    t = T[key]; n = t['n']
    print(key, 'n=%d' % n, ' '.join(f"{k}={100*t[k]/n:.0f}%" for k in ('annotated(missing)', 'unannotated_harmonic_of_annotated', 'unannotated_other', 'unannotated_gap')))
