#!/usr/bin/env python3
"""Saved-data checks for the M3 runtime leakage floor and the exact = recall x lane decomposition.

usage: floor_and_decomposition.py BANK.m3cb takes.json github-full-corpus-20261109.json

Part 1: per (note, lane) cell, runtime median 10log10(E2/E1) from held takes vs the bank's h2/h1, and the one-pole
        leakage prediction (h1 -> h2 cell only, unit-energy partial, phases free: min/max of |a_true -+ a_leak|^2).
Part 2: exact = P(pitch present) x P(right lane | pitch present) from the saved full-corpus report.
No audio is read; nothing is launched.
"""
import json, math, struct, sys, statistics as st, collections

BANK, TAKES, CORPUS = sys.argv[1:4]
FS = 96000.0
D = math.exp(-1.0 / (0.040 * FS))
OPEN = [32, 36, 40, 44, 48, 52, 56, 60]

raw = open(BANK, 'rb').read()
off = 25
pts = {}
for lane in range(8):
    for fret in range(25):
        off += 2
        prof = struct.unpack_from('<6H', raw, off); off += 12
        off += 12 + 1 + 4 + 1
        pts[(lane, fret)] = [p / 32768.0 for p in prof]


def leak_amp(f0):
    w = 2 * math.pi * f0 / FS
    a = (1 - D) ** 2
    return math.sqrt(a / (a + 2 * D * (1 - math.cos(w))))


def db(x):
    return 10 * math.log10(x) if x > 0 else float('-inf')


T = json.load(open(TAKES))
cells = collections.defaultdict(list)
for t in T:
    E = t.get('E')
    if E and len(E) >= 2 and E[0] > 0 and E[1] > 0:
        cells[(t['note'], t['lane'])].append(10 * math.log10(E[1] / E[0]))

print('PART 1  runtime median vs bank vs one-pole leakage (h1 -> h2 cell)')
print('cell(note,lane) f0Hz  n | runtime | bank | run-bank | pred leak | coherent range [min,max] | run vs range')
rows = []
for (n, l), v in sorted(cells.items()):
    fret = n - OPEN[l]
    if not 0 <= fret <= 24:
        continue
    pr = pts[(l, fret)]
    bank_amp = math.sqrt(pr[1] / pr[0]) if pr[0] > 0 else 0.0
    f0 = 440.0 * 2 ** ((n - 69) / 12)
    la = leak_amp(f0)
    lo, hi = abs(la - bank_amp), la + bank_amp
    run = st.median(v)
    bank_db = db(pr[1] / pr[0]) if pr[0] > 0 and pr[1] > 0 else float('-inf')
    rows.append((n, l, f0, len(v), run, bank_db, db(la * la), db(lo * lo), db(hi * hi)))
    flag = 'inside' if db(lo * lo) <= run <= db(hi * hi) else ('above by %.1f dB' % (run - db(hi * hi)) if run > db(hi * hi) else 'below by %.1f dB' % (db(lo * lo) - run))
    print(f'({n},{l}) {f0:6.1f} n={len(v)} | {run:+6.1f} | {bank_db:+7.1f} | {run - bank_db:+6.1f} | {db(la * la):+6.1f} | [{db(lo * lo):+6.1f},{db(hi * hi):+6.1f}] | {flag}')

low = [r for r in rows if r[5] <= -30]
print(f'\ncells with bank h2/h1 <= -30 dB: {len(low)}')
for r in low:
    inside = r[7] <= r[4] <= r[8]
    print(f'  ({r[0]},{r[1]}) run {r[4]:+.1f}  bank {r[5]:+.1f}  floor {r[6]:+.1f}  range [{r[7]:+.1f},{r[8]:+.1f}]  inside={inside}')
pos = [r for r in low if r[4] - r[5] > 0]
print(f'  runtime above bank in {len(pos)} of {len(low)}; inside coherent range in {sum(r[7] <= r[4] <= r[8] for r in low)} of {len(low)}')
hi_ = [r for r in rows if r[5] > -30]
print(f'cells with bank h2/h1 > -30 dB: {len(hi_)}; |run-bank| <= 3.7 dB in {sum(abs(r[4] - r[5]) <= 3.7 for r in hi_)}; '
      f'run-bank > +6 dB (not a leakage-sized effect): {[(r[0], r[1], round(r[4] - r[5], 1)) for r in hi_ if r[4] - r[5] > 6]}')

print('\nPART 2  exact = P(pitch present) x P(lane | pitch present)   [saved reassessment, run 42545080876]')
C = json.load(open(CORPUS))['datasets']
print('dataset            labeled   matched  wrong_string  exact%  present%  lane|present%')
for name in ('ordinary', 'constructed', 'isolated-08', 'isolated-05', 'isolated-02', 'physical-long', 'synthetic-four'):
    o = C[name]['off_output']
    lab, m, ws = o['labeled'], o['matched'], o['false_wrong_string_voices']
    pres = m + ws
    print(f'{name:<16} {lab:9d} {m:9d} {ws:12d}  {100 * m / lab:6.2f}  {100 * pres / lab:7.2f}  {100 * m / pres if pres else float("nan"):9.2f}')
o = C['ordinary']['off_output']
lab, m, ws = o['labeled'], o['matched'], o['false_wrong_string_voices']
pres = (m + ws) / lab
lane = m / (m + ws)
print(f'\nordinary: present {100 * pres:.2f}%  lane|present {100 * lane:.2f}%  exact {100 * pres * lane:.2f}%')
print(f'  lane|present -> 95% alone: exact {100 * pres * 0.95:.2f}%     present -> 95% alone: exact {100 * 0.95 * lane:.2f}%')
print(f'  both at 95%: {100 * 0.95 * 0.95:.2f}%   (equal factors need sqrt(0.90) = {math.sqrt(0.90):.4f} each to reach 90%)')
