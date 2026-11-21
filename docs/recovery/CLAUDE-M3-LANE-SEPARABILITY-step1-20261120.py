#!/usr/bin/env python3
"""Bank-only lane-separability map for the M3 factory calibration bank.

Reads (no audio, nothing launched):
  * factory-calibration-v2.m3cb   (calibration image v2, layout from native/src/calibration_state_image.cpp)
  * takes.json                    (held-take runtime cell energies from step1 of the octave-parent analysis; used only
                                   for the within-cell spread of 10log10(E2/E1) in dB)
Prints, per pitch, how many (lane, fret) candidates exist and how many candidate pairs are separable by
  (a) bank cents,   (b) bank harmonic-share shape,   (c) share shape as a runtime one-pole cell would report it
      (bank share + leakage from the other partials through the one-pole response, incoherent sum).
The leakage model is an approximation (phases ignored) and every threshold is a descriptive choice, not a tuned value.
"""
import json, math, struct, sys, statistics as st, collections, os

BANK = sys.argv[1]
TAKES = sys.argv[2]
FS = 96000.0
D = math.exp(-1.0 / (0.040 * FS))            # kFastEnergySeconds = 0.040
OPEN = [32, 36, 40, 44, 48, 52, 56, 60]

raw = open(BANK, 'rb').read()
assert raw[:4] == b'M3CB', raw[:4]
off = 24
mask = raw[off]; off += 1
pts = {}
for lane in range(8):
    for fret in range(25):
        cents, = struct.unpack_from('<h', raw, off); off += 2
        prof = struct.unpack_from('<6H', raw, off); off += 12
        det = struct.unpack_from('<6h', raw, off); off += 12
        dm = raw[off]; off += 1
        conf, cnt = struct.unpack_from('<HH', raw, off); off += 4
        q = raw[off]; off += 1
        pts[(lane, fret)] = dict(cents=cents / 256.0, prof=[p / 32768.0 for p in prof], det=[x / 256.0 for x in det],
                                 dm=dm, conf=conf, cnt=cnt, q=q)
assert off == len(raw), (off, len(raw))
print('calibrated_string_mask', bin(mask), 'points', len(pts))
print('quality distribution', collections.Counter(p['q'] for p in pts.values()))
print('observation_count: min/median/max', min(p['cnt'] for p in pts.values()),
      st.median(p['cnt'] for p in pts.values()), max(p['cnt'] for p in pts.values()))

# within-cell spread of runtime 10log10(E2/E1) from held takes
T = json.load(open(TAKES))
cells = collections.defaultdict(list)
for t in T:
    E = t.get('E')
    if E and len(E) >= 2 and E[0] > 0 and E[1] > 0:
        cells[(t['note'], t['lane'])].append(10 * math.log10(E[1] / E[0]))
sds = [st.pstdev(v) for v in cells.values() if len(v) >= 4]
SIGMA = st.median(sds)
print(f'within-cell sd of runtime h2/h1 (cells with >=4 takes): n={len(sds)} median={SIGMA:.2f} dB '
      f'[min {min(sds):.2f}, max {max(sds):.2f}]')


def leak(delta_hz):
    """energy leakage of a unit partial at +-delta_hz through a one-pole cell centred delta_hz away"""
    w = 2 * math.pi * delta_hz / FS
    a = (1 - D) ** 2
    return a / (a + 2 * D * (1 - math.cos(w)))


def db(x):
    return 10 * math.log10(x)


RES = 1.5 / 32768.0       # bank share resolution: treat anything below ~1.5 LSB as 'below resolution'


def shape_vec(share, f0, runtime):
    s = list(share)
    if runtime:
        s2 = []
        for k in range(6):
            lk = sum(s[j] * leak(abs(k - j) * f0) for j in range(6) if j != k)
            s2.append(s[k] + lk)
        s = s2
    ref = max(s[0], RES)
    return [db(max(s[k], RES) / ref) for k in range(1, 6)]


def sep(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


rows = []
by_pitch = {}
for p in range(32, 85):
    cand = [(l, p - OPEN[l]) for l in range(8) if 0 <= p - OPEN[l] <= 24]
    f0 = 440.0 * 2 ** ((p - 69) / 12)
    by_pitch[p] = cand
    for i in range(len(cand)):
        for j in range(i + 1, len(cand)):
            A, B = pts[cand[i]], pts[cand[j]]
            dc = abs(A['cents'] - B['cents'])
            sb = sep(shape_vec(A['prof'], f0, False), shape_vec(B['prof'], f0, False))
            sr = sep(shape_vec(A['prof'], f0, True), shape_vec(B['prof'], f0, True))
            rows.append(dict(p=p, a=cand[i], b=cand[j], dc=dc, sb=sb, sr=sr))

print(f'\n{len(rows)} lane pairs over pitches 32..84 (pairs = two (lane,fret) options for one pitch)')
for thr_c in (3, 5, 10):
    print(f'  pairs with |bank cents diff| >= {thr_c:>2} c: {sum(r["dc"] >= thr_c for r in rows):4d} '
          f'({100 * sum(r["dc"] >= thr_c for r in rows) / len(rows):.1f}%)')
for m in (1, 2, 3):
    t = m * SIGMA
    nb = sum(r['sb'] >= t for r in rows)
    nr = sum(r['sr'] >= t for r in rows)
    print(f'  shape sep >= {m} sigma ({t:.1f} dB): bank {nb:4d} ({100 * nb / len(rows):.1f}%), '
          f'runtime-floor model {nr:4d} ({100 * nr / len(rows):.1f}%)')

t2 = 2 * SIGMA
only_bank = [r for r in rows if r['sb'] >= t2 and r['sr'] < t2]
print(f'\nshape separable in bank but NOT through the floor model at 2 sigma: {len(only_bank)} pairs '
      f'({100 * len(only_bank) / len(rows):.1f}%)')
lane_pair_counts = collections.Counter((r['a'][0], r['b'][0]) for r in only_bank)
print('  by lane pair (lane a, lane b): ', dict(sorted(lane_pair_counts.items())))
ff = collections.Counter()
for r in only_bank:
    ff['pitch<=47' if r['p'] <= 47 else ('48..59' if r['p'] <= 59 else '>=60')] += 1
print('  by pitch band:', dict(ff))

# lane pairs that neither cents (>=10 c) nor shape-through-floor (>=2 sigma) separate
none = [r for r in rows if r['dc'] < 10 and r['sr'] < t2]
print(f'\nnot separable by cents>=10c nor runtime-floor shape>=2sigma: {len(none)} pairs ({100 * len(none) / len(rows):.1f}%)')
none_b = [r for r in rows if r['dc'] < 10 and r['sb'] < t2]
print(f'not separable by cents>=10c nor BANK shape>=2sigma (no floor): {len(none_b)} pairs ({100 * len(none_b) / len(rows):.1f}%)')
rescued = [r for r in none if r['sb'] >= t2]
print(f'  of the {len(none)}: {len(rescued)} would be separable by shape if the floor were removed')

print('\nper pitch: candidates, pairs, sep by cents>=10c / bank shape>=2s / runtime shape>=2s / any-runtime')
for p in range(32, 85):
    c = by_pitch[p]
    rp = [r for r in rows if r['p'] == p]
    if not rp:
        continue
    nc = sum(r['dc'] >= 10 for r in rp)
    nb = sum(r['sb'] >= t2 for r in rp)
    nr = sum(r['sr'] >= t2 for r in rp)
    na = sum((r['dc'] >= 10) or (r['sr'] >= t2) for r in rp)
    print(f'  {p:2d} lanes {len(c)} pairs {len(rp):2d}: cents {nc:2d}  bankshape {nb:2d}  rtshape {nr:2d}  either {na:2d}')

json.dump(dict(sigma_db=SIGMA, rows=[dict(r, a=list(r['a']), b=list(r['b'])) for r in rows]),
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lane_separability_rows.json'), 'w'))
