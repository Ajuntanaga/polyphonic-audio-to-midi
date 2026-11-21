import json, math, gzip, csv, statistics as st, collections
import os
S=os.path.dirname(os.path.abspath(__file__))+'/'  # takes.json from step1 must sit beside this file
P=__import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", ".."))+'/'
T=json.load(open(S+'takes.json'))
cells=collections.defaultdict(list)
for t in T:
    if t['E']:
        t['r12']=10*math.log10(t['E'][1]/t['E'][0]); cells[(t['note'],t['lane'])].append(t)
rep=json.load(open(P+'build/github-results/octave-parent-measurement-44811182398/octave-parent-measurement/report.json'))
ec={m['take_id']:m['expected_cents'] for m in rep['measurements']}
d=math.exp(-1/(0.040*96000))
def corr_db(note,h,c):
    f=440*2**((note-69)/12)*h; w=2*math.pi*f/96000
    delta=w*(2**(c/1200)-1)
    return 10*math.log10(min(8.0,max(1.0,1+2*d*(1-math.cos(delta))/(1-d)**2)))
def diff_db(note,c): return corr_db(note,2,c)-corr_db(note,1,c)
print('== corrected-minus-raw template shift (h2/h1), dB, if phase cents = ledger expected_cents, per cell')
for key in [(44,0),(48,2),(62,6),(48,1),(60,2)]:
    v=cells[key]; e=[ec[t['id']] for t in v]
    sh=[diff_db(key[0],c) for c in e]
    print(f"  cell {key}: expected_cents {[round(x,1) for x in e]} -> shift {[round(x,2) for x in sh]} dB (max {max(sh):.2f})")
print('  worst case at +-20 cents: 44 %.2f  48 %.2f  62 %.2f ; +-40: 44 %.2f 48 %.2f 62 %.2f'%tuple([diff_db(n,20) for n in (44,48,62)]+[diff_db(n,40) for n in (44,48,62)]))
print('\n== one-sided: share of held parent-only takes with SIGNED h2 error > +B  (observed above template), estimator = report as-is')
def held(t):
    tr=[u for u in cells[(t['note'],t['lane'])] if u['pas']!=t['pas']]
    if not tr: return None
    return t['r12']-st.median(u['r12'] for u in tr)
sig=[held(t) for t in T if t['E']]; sig=[x for x in sig if x is not None]
for B in (1.8,2.3,3,5,7.5,10):
    print(f"  signed error > +{B}: {sum(x>B for x in sig)}/{len(sig)} = {100*sum(x>B for x in sig)/len(sig):.0f}%   (<-{B}: {sum(x<-B for x in sig)})")
# new genuine pairs against lane-1 parent-48 cell and parent-48 lanes
print('\n== all measured genuine 48/60 pairs and others against runtime cells (literal raw-control minus corrected-template, lower bound of raw/raw excess)')
obs={'32/29 44/56 lane0':(10*math.log10(0.9818001842877859),44,0),'41/42 48/60 lane2':(-19.332,48,2),'245/244 48/60 lane1':(-8.166,48,1),'354/351 48/60 lane1':(-4.234,48,1),'false74 62/74 lane6':(2.345,62,6)}
for name,(o,n,l) in obs.items():
    v=[t['r12'] for t in cells[(n,l)]]; med=st.median(v)
    lanes=[(ln,st.median([t['r12'] for t in cells[(n,ln)]])) for ln in range(8) if (n,ln) in cells]
    mn=min((abs(o-m),ln) for ln,m in lanes)
    print(f"  {name:22s} obs {o:+6.2f}  template {med:+6.1f} [{min(v):+.1f},{max(v):+.1f}] n={len(v)}  excess {o-med:+6.1f}  vs cell max {o-max(v):+6.1f}  | min|excess| over playable lanes {mn[0]:.1f} (lane {mn[1]})")
# per-tick rows: availability and phase validity (flags are '1'/'0'; invalid rows carry cents 0.0 as a placeholder)
rows=list(csv.DictReader(gzip.open(P+'build/recovery/cross-pitch-independent-20261120/octave-pair-controls-rows.tsv.gz','rt'),delimiter='\t'))
by=collections.defaultdict(list)
for r in rows: by[r['case']].append(r)
print('\n== per-tick availability and phase validity (saved rows, read only)')
for case,rs in by.items():
    av=[r for r in rs if r['availability']=='available']
    pv=sum(r['parent_phase_valid']=='1' for r in rs); uv=sum(r['upper_phase_valid']=='1' for r in rs)
    bo=[r for r in rs if r['parent_phase_valid']=='1' and r['upper_phase_valid']=='1']
    s=f"  {case:14s} ticks {len(rs):4d} available {len(av):4d} parent_valid {pv:4d} upper_valid {uv:4d} both {len(bo):4d}"
    if bo:
        cp=[float(r['parent_phase_cents']) for r in bo]; cu=[float(r['upper_phase_cents']) for r in bo]
        s+=f" | parent cents med {st.median(cp):+.1f} upper cents med {st.median(cu):+.1f}"
    print(s)
