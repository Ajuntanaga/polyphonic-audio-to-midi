# Claude 2026-11-20: reads saved report.json and ledger TSVs only (no audio, no jobs). Run step 1 then step 2 from one folder: python3 -I step1.py; python3 -I step2.py
# Read-only: saved report.json + ledger TSVs only. No audio, no jobs.
import json, math, csv, collections, sys
P=__import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", ".."))+'/'
R=P+'build/github-results/octave-parent-measurement-44811182398/octave-parent-measurement/report.json'
d=json.load(open(R))
M=d['measurements']
held={h['take_id']:h for h in d['held_pass']['runtime_energy']}
led={}
def ledger(s):
    if s not in led:
        rows=list(csv.DictReader(open(P+f'build/physical-capture/calibration-bank-experiment/labels/raw/string-0{s}.tsv'),delimiter='\t'))
        led[s]=rows
    return led[s]
T=[]
for m in M:
    s=int(m['take_id'].split('-')[1]); i=m['label_index']
    rows=ledger(s)
    r=rows[i]
    assert int(r['start_sample'])==m['start_sample'] and int(r['midi_note'])==m['note'], m['take_id']
    prev=rows[i-1] if i>0 else None; nxt=rows[i+1] if i+1<len(rows) else None
    E=m.get('runtime_energy')
    T.append(dict(id=m['take_id'],s=s,i=i,note=m['note'],lane=m['lane'],pas=m['held_pass'],H=m['production_harmonics'],E=E,
      elig=(m.get('runtime') or {}).get('eligible'),win=int(r['end_sample'])-int(r['start_sample']),
      pn=int(prev['midi_note']) if prev else None, pp=int(prev['calibration_pass']) if prev else None,
      pgap=(int(r['start_sample'])-int(prev['end_sample']))/96000 if prev else None,
      nn=int(nxt['midi_note']) if nxt else None, ngap=(int(nxt['start_sample'])-int(r['end_sample']))/96000 if nxt else None,
      held=held[m['take_id']], proj=m.get('projection_energy')))
json.dump(T,open('./takes.json','w'))
print(len(T), sum(1 for t in T if t['E']))
# argmax bin
cnt=collections.Counter()
rows=[]
for t in T:
    E=t['E']
    if not E: continue
    am=max(range(len(E)),key=lambda k:E[k])+1
    t['am']=am
    t['r12']=10*math.log10(E[1]/E[0])
    t['e1max']=10*math.log10(E[0]/max(E))
    cnt[(t['note'],am)]+=1
print('argmax bin by note:',sorted(cnt.items()))
print()
def f(x): return 'NA' if x is None else f'{x:.2f}'
print('takes with argmax bin != 1:')
for t in T:
    if t.get('am',1)!=1:
        impl=t['note']+12*math.log2(t['am'])
        print(f"{t['id']:18s} n{t['note']} lane{t['lane']} p{t['pas']} H{t['H']} am={t['am']} implied≈{impl:.1f} E1/Emax={t['e1max']:.1f}dB r12={t['r12']:+.1f} | prev n{t['pn']}(p{t['pp']}) gap{f(t['pgap'])}s next n{t['nn']} gap{f(t['ngap'])}s win{t['win']/96000:.2f}s")
