# step 2: needs ./takes.json written by step 1
import json, math, collections, statistics as st
S='./'
T=json.load(open(S+'takes.json'))
for t in T:
    E=t['E']
    if E:
        t['r12']=10*math.log10(E[1]/E[0]); t['e1max']=10*math.log10(E[0]/max(E)); t['am']=max(range(len(E)),key=lambda k:E[k])+1
cells=collections.defaultdict(list)
for t in T: cells[(t['note'],t['lane'])].append(t)
print('cells for the two extreme notes on lane 4, and the other cells with an argmax!=1 take')
for key in sorted(cells):
    c=cells[key]
    if key in [(60,4),(48,4)]:
        for t in sorted(c,key=lambda t:(t['pas'],t['i'])):
            print(f"  cell {key} {t['id']:17s} p{t['pas']} r12={t['r12']:+6.1f} E1/Emax={t['e1max']:6.1f} am={t['am']} prev n{t['pn']} win{t['win']/96000:.2f}s")
print()
# reproduce held-pass error_db
def agg(c,mode):
    # c = training takes (list); returns predicted ratio vector (dB) for bins 2..H relative to bin1
    out=[]
    H=c[0]['H']
    for k in range(1,H):
        if mode=='meanlog':
            out.append(st.mean(10*math.log10(t['E'][k]/t['E'][0]) for t in c))
        elif mode=='logmean_ratio':
            out.append(10*math.log10(st.mean(t['E'][k]/t['E'][0] for t in c)))
        elif mode=='ratio_of_means':
            out.append(10*math.log10(st.mean(t['E'][k] for t in c)/st.mean(t['E'][0] for t in c)))
        elif mode=='median_log':
            out.append(st.median(10*math.log10(t['E'][k]/t['E'][0]) for t in c))
    return out
def predict(t,mode,excl=lambda x:False):
    tr=[u for u in cells[(t['note'],t['lane'])] if u['pas']!=t['pas'] and u['E'] and not excl(u)]
    if not tr: return None,0
    return agg(tr,mode),len(tr)
for mode in ['meanlog','logmean_ratio','ratio_of_means','median_log']:
    bad=0;n=0;mx=0
    for t in T:
        if not t['E'] or not t['held']['available']: continue
        p,k=predict(t,mode)
        if p is None: continue
        obs=[10*math.log10(t['E'][j]/t['E'][0]) for j in range(1,t['H'])]
        err=[o-q for o,q in zip(obs,p)]
        rep=t['held']['error_db']
        if k!=t['held']['training_count']: bad+=1;continue
        dmax=max(abs(a-b) for a,b in zip(err,rep))
        mx=max(mx,dmax);n+=1
    print(mode,'compared',n,'training-count mismatches',bad,'max |difference| vs report',round(mx,6))

print('\n=== validated aggregator: median of per-take 10log10(Ek/E1) over other-pass takes of the same (note,lane) ===')
def held_err(t,excl_train=lambda u:False):
    tr=[u for u in cells[(t['note'],t['lane'])] if u['pas']!=t['pas'] and u['E'] and not excl_train(u)]
    if not tr: return None
    H=t['H']
    pred=[st.median(10*math.log10(u['E'][k]/u['E'][0]) for u in tr) for k in range(1,H)]
    obs=[10*math.log10(t['E'][k]/t['E'][0]) for k in range(1,H)]
    return [o-p for o,p in zip(obs,pred)],len(tr)
def q(v,p):
    v=sorted(v);
    if not v: return float('nan')
    k=(len(v)-1)*p; lo=int(k); hi=min(lo+1,len(v)-1); return v[lo]+(v[hi]-v[lo])*(k-lo)
OUT={(('string-04-label54')),('string-04-label55')}
def table(score_excl,train_excl,label):
    print(label)
    print('  note  n   h2 |err| P50   P75   P90   max    n>=10dB')
    allh=[]
    for note in (44,48,60,62,69):
        v=[]
        for t in T:
            if t['note']!=note or not t['E'] or t['id'] in score_excl: continue
            r=held_err(t,lambda u:u['id'] in train_excl)
            if r is None: continue
            v.append(abs(r[0][0]))
        allh+=v
        print(f"  {note}  {len(v):2d}   {q(v,.5):5.2f}  {q(v,.75):5.2f}  {q(v,.9):5.2f}  {max(v):5.2f}  {sum(1 for x in v if x>=10)}")
    print(f"  all {len(allh):2d}   {q(allh,.5):5.2f}  {q(allh,.75):5.2f}  {q(allh,.9):5.2f}  {max(allh):5.2f}  {sum(1 for x in allh if x>=10)}")
table(set(),set(),'(A) as the saved report (all takes scored, all in training) -- must match Codex')
table(OUT,set(),'(B) sensitivity: the two takes not scored, still in training')
table(OUT,OUT,'(C) sensitivity: the two takes neither scored nor in training')
print('\n=== all takes with |h2 error| >= 10 dB in (A): own r12 vs cell median of other passes, whether an outlier is in the training set ===')
for t in T:
    if not t['E']: continue
    r=held_err(t)
    if r is None or abs(r[0][0])<10: continue
    tr=[u for u in cells[(t['note'],t['lane'])] if u['pas']!=t['pas'] and u['E']]
    print(f"  {t['id']:17s} n{t['note']} l{t['lane']} p{t['pas']} err_h2={r[0][0]:+6.1f} own r12={t['r12']:+6.1f} train r12={[round(u['r12'],1) for u in tr]} outlier_in_train={any(u['id'] in OUT for u in tr)}")
print('\n=== runtime template (median of own r12 across the cell) per parent note and lane ===')
for note in (44,48,60,62,69):
    for lane in range(8):
        c=cells.get((note,lane))
        if not c: continue
        v=[u['r12'] for u in c if u['E']]
        print(f"  parent {note} lane {lane}: n={len(v)} median {st.median(v):+6.1f} dB, min {min(v):+6.1f}, max {max(v):+6.1f}  passes {sorted(u['pas'] for u in c)}")

print('\n=== coverage of the held-pass |h2 error| (table A, all 95) ===')
errs={}
for t in T:
    if not t['E']: continue
    r=held_err(t)
    if r: errs[t['id']]=(t['note'],abs(r[0][0]))
for B in (1.8,2.3,3.0,5.0,7.5,10.0):
    allv=[e for _,e in errs.values()]
    f=lambda notes:[e for n,e in errs.values() if n in notes]
    print(f"  band +-{B:>4} dB: all {sum(x<=B for x in allv)}/{len(allv)} = {100*sum(x<=B for x in allv)/len(allv):.0f}%   parent48 {sum(x<=B for x in f({48}))}/{len(f({48}))}   parent44 {sum(x<=B for x in f({44}))}/{len(f({44}))}   parent62 {sum(x<=B for x in f({62}))}/{len(f({62}))}")
print('\n=== controls vs runtime templates (observed from octave-admission-context.json, dB of median upper/parent fundamental) ===')
obs={'genuine 56 over 44 (label 29)':(10*math.log10(0.9818001842877859),44,0),
     'genuine 60 over 48 (label 42)':(10*math.log10(0.01166374813459781),48,2),
     'false 74 over 62':(10*math.log10(1.715786524928203),62,6)}
for name,(o,note,lane) in obs.items():
    print(f"{name}: observed {o:+.2f} dB; annotated parent lane {lane}")
    ex=[]
    for l in range(8):
        c=cells.get((note,l))
        if not c: continue
        v=[u['r12'] for u in c if u['E']]; med=st.median(v)
        ex.append((l,med,min(v),max(v),o-med,len(v)))
        mark=' <- annotated' if l==lane else ''
        inside = 'inside cell range' if min(v)-0.0<=o<=max(v) else 'outside cell range'
        print(f"    lane {l}: template {med:+6.1f} [{min(v):+6.1f},{max(v):+6.1f}] n={len(v)} excess {o-med:+6.1f} dB ({inside}){mark}")
    print('    min |excess| over playable lanes = %.1f dB (lane %d)'%min((abs(e[4]),e[0]) for e in ex))

print('\n=== protocol membership: raw-ledger row i == pass-balanced row i ? and primary vs checkpoints ===')
import csv
P=__import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", ".."))+'/build/physical-capture/'
mem={}
bad=0
for s in range(1,9):
    raw=list(csv.DictReader(open(P+f'calibration-bank-experiment/labels/raw/string-0{s}.tsv'),delimiter='\t'))
    pb=list(csv.DictReader(open(P+f'string-0{s}/string-0{s}-pass-balanced.tsv'),delimiter='\t'))
    pr={(r['start_sample'],r['end_sample']) for r in csv.DictReader(open(P+f'string-0{s}/string-0{s}-primary.tsv'),delimiter='\t')}
    ck={(r['start_sample'],r['end_sample']) for r in csv.DictReader(open(P+f'string-0{s}/string-0{s}-checkpoints.tsv'),delimiter='\t')}
    for i,(a,b) in enumerate(zip(raw,pb)):
        if (a['midi_note'],a['calibration_pass'],int(a['end_sample'])-int(a['start_sample']))!=(b['midi_note'],b['calibration_pass'],int(b['end_sample'])-int(b['start_sample'])): bad+=1
        k=(b['start_sample'],b['end_sample'])
        mem[(s,i)]='primary' if k in pr else ('checkpoint' if k in ck else 'neither')
    if len(raw)!=len(pb): print('length differs',s,len(raw),len(pb))
print('raw vs pass-balanced mismatches (note,pass,length):',bad)
cm=collections.Counter()
for t in T:
    t['proto']=mem.get((t['s'],t['i']))
    cm[(t['pas'],t['proto'])]+=1
print('take counts by (pass, protocol):',sorted(cm.items()))
def held_err_proto(t,pool):
    tr=[u for u in cells[(t['note'],t['lane'])] if u['pas']!=t['pas'] and u['E'] and pool(u)]
    if not tr: return None
    pred=st.median(10*math.log10(u['E'][1]/u['E'][0]) for u in tr)
    return t['r12']-pred,len(tr)
def summarize(name,vals):
    v=sorted(abs(x) for x in vals)
    if not v: print('  ',name,'-> no rows'); return
    print(f"  {name:55s} n={len(v):3d} P50 {q(v,.5):5.2f} P75 {q(v,.75):5.2f} P90 {q(v,.9):5.2f} max {max(v):5.2f}  >=10dB: {sum(x>=10 for x in v)}")
print('\nProtocol-stratified |h2 error| (whole-pass hold-out kept; template = median over other-pass takes of the allowed protocol):')
prim=lambda u:u['proto']=='primary'
chk=lambda u:u['proto']=='checkpoint'
S1=[held_err_proto(t,prim) for t in T if t['E'] and t['proto']=='primary']
S2=[held_err_proto(t,prim) for t in T if t['E'] and t['proto']=='checkpoint']
S3=[held_err_proto(t,chk) for t in T if t['E'] and t['proto']=='checkpoint']
S4=[held_err_proto(t,chk) for t in T if t['E'] and t['proto']=='primary']
summarize('primary rows scored vs primary-only templates',[x[0] for x in S1 if x])
summarize('checkpoint rows scored vs primary-only templates',[x[0] for x in S2 if x])
summarize('checkpoint rows scored vs checkpoint-only templates (other pass)',[x[0] for x in S3 if x])
summarize('primary rows scored vs checkpoint-only templates',[x[0] for x in S4 if x])
print('  (a pass-3 row has no other-pass checkpoint template if all checkpoint rows are pass 3: expected empty)')
print('\nWhich rows are scored in the primary-vs-primary stratum with |err|>=10 ?')
for t in T:
    if t['E'] and t['proto']=='primary':
        r=held_err_proto(t,prim)
        if r and abs(r[0])>=10: print('  ',t['id'],t['note'],t['lane'],'p',t['pas'],round(r[0],1))
print('\nCheckpoint rows with |err vs primary template|>=10:')
for t in T:
    if t['E'] and t['proto']=='checkpoint':
        r=held_err_proto(t,prim)
        if r and abs(r[0])>=10: print('  ',t['id'],t['note'],t['lane'],'p',t['pas'],round(r[0],1))
