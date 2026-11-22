"""Audio level at label ends: is the labelled pitch still sounding after the label?  Local half of the registered read.

Plan, definitions and predictions: CLAUDE-M3-AUDIO-RELEASE-PROPOSAL-20261122.md (written before any audio was opened).  Two steps:
  build-ends  UNMODIFIED_DIR ADAPTED_DIR OUT.json   labels + saved stream tapes only: the evaluable ends, their presence group, and the
                                                    label-only 'contested' flags.  Reads no audio.  Output is pinned and dispatched to the worker.
  analyse     ENDS.json CURVES.json [OUT.json]      joins the worker's level curves (tools/portable_audio_release_levels.py, GitHub Actions)
                                                    to the ends and evaluates the registered checks and predictions.
  --selftest                                        definition checks on constructed inputs.
"""
import hashlib
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

import numpy as np  # noqa: E402

from tools import audio_release_levels as lv  # noqa: E402

CORPORA = ('ordinary', 'extended-middle')
GROUPS = ('both', 'adapted_only', 'original_only', 'neither')
CONTEST_FRACTION, CONTEST_HZ, CONTEST_J = 0.035, 25.0, 4
END_CONTEST_MS = (-80, 200)           # other labelled pitches overlapping [E-80 ms, E+200 ms)
START_CONTEST_MS = (-140, 140)        # and [S-140 ms, S+140 ms) for the alignment check
TAUS = (0, 40, 100, 200)              # window [E+tau, E+tau+80 ms)
PRE_J, WITHIN_J = -8, -16             # grid steps: [E-80 ms, E) and [E-160 ms, E-80 ms)
RISE_DELTAS = (-60, -40, -20, 0, 20, 40, 60)
RING_DB, RING_DB_LOOSE = -6.0, -12.0
A1_DB, A2_DB, A3_DB = -6.0, 6.0, 3.0
MIN_N = 15
V1_RISE_DB, V1_ARGMAX_MS = 10.0, 20
V2_LOW, V2_HIGH = -8.0, 1.0
BOOT_SEED, BOOT_N = 20261122, 2000
STRATA = ('all', 'uncontested', 'contested')


def load_module(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def contested(unions, midi, lo, hi):
    """True when another pitch has a labelled span overlapping [lo, hi) and one of its first CONTEST_J harmonics lies within
    max(3.5%, 25 Hz) of a measured harmonic of this pitch (25 Hz is about the half-width of the 80 ms Hann main lobe)."""
    own = [k * lv.fundamental(midi) for k in lv.harmonic_numbers(midi)]
    for other, spans in unions.items():
        if other == midi or not any(a < hi and b > lo for a, b in spans):
            continue
        for j in range(1, CONTEST_J + 1):
            f = j * lv.fundamental(other)
            if any(abs(f - fk) <= max(CONTEST_FRACTION * fk, CONTEST_HZ) for fk in own):
                return True
    return False


def group_of(row):
    u, a = row['unmodified']['detected'], row['adapted']['detected']
    return 'both' if u and a else 'adapted_only' if a else 'original_only' if u else 'neither'


def build_ends(unmodified_dir, adapted_dir):
    rc = load_module('rc', 'CLAUDE-M3-REAL-RELEASE-CURVES-20261122.py')
    support = rc.load_module('asup', 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py')
    out = dict(schema='m3_audio_release_ends_v1', sample_rate=lv.SOURCE_RATE, corpora={}, pins={})
    for corpus in CORPORA:
        tapes = {}
        for arm, directory in (('unmodified', unmodified_dir), ('adapted', adapted_dir)):
            check, tapes[arm] = rc.mapping_check(directory, corpus)
            if not check['c0a'] or check['c0b'] is False:
                raise SystemExit('Mapping check failed for %s/%s' % (arm, corpus))
            out['pins'][arm + '/' + corpus] = {f: rc.sha12(os.path.join(directory, corpus + f)) for f in ('-stream.npz', '-events.json')}
        ctx = support.dataset_context(corpus)
        _, rows = rc.analyse(tapes, ctx['labels'], ctx['horizon'])
        unions = rc.union_by_pitch(ctx['labels'])
        ends = []
        for i, r in enumerate(rows):
            ends.append(dict(idx=i, midi_note=r['midi_note'], start=r['start'], end=r['end'], window=r['window'], group=group_of(r),
                             contested_end=contested(unions, r['midi_note'], r['end'] + lv.ms_samples(END_CONTEST_MS[0]),
                                                     r['end'] + lv.ms_samples(END_CONTEST_MS[1])),
                             contested_start=contested(unions, r['midi_note'], r['start'] + lv.ms_samples(START_CONTEST_MS[0]),
                                                       r['start'] + lv.ms_samples(START_CONTEST_MS[1]))))
        out['corpora'][corpus] = dict(horizon=int(ctx['horizon']), ends=ends)
    out['counts'] = counts(out)
    return out


def counts(ends_file):
    result = {}
    for corpus, block in ends_file['corpora'].items():
        table = {}
        for stratum in STRATA:
            table[stratum] = {g: sum(1 for e in block['ends'] if e['group'] == g and in_stratum(e, stratum)) for g in GROUPS}
        table['contested_start'] = sum(e['contested_start'] for e in block['ends'])
        table['ends'] = len(block['ends'])
        result[corpus] = table
    return result


def in_stratum(end, stratum):
    return stratum == 'all' or (stratum == 'contested') == bool(end['contested_end'])


def val(curve, grid, j):
    i = lv.grid_index(grid, j)
    if i is None or curve is None:
        return None
    v = curve[i]
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def derive(end, end_levels, start_levels):
    """Registered per-end quantities.  R(tau) = level of [E+tau, E+tau+80 ms) minus level of [E-80 ms, E); defined only when the window ends by W."""
    after_ms = (end['window'] - end['end']) * 1000.0 / lv.SOURCE_RATE
    pre = val(end_levels, lv.END_GRID, PRE_J)
    r = {}
    for tau in TAUS:
        post = val(end_levels, lv.END_GRID, tau // lv.HOP_MS)
        r[tau] = None if pre is None or post is None or lv.WINDOW_MS + tau > after_ms + 1e-9 else post - pre
    earlier = val(end_levels, lv.END_GRID, WITHIN_J)
    within = None if pre is None or earlier is None or (end['end'] - end['start']) < lv.ms_samples(2 * lv.WINDOW_MS) else pre - earlier
    rise = {}
    for d in RISE_DELTAS:
        after, before = val(start_levels, lv.START_GRID, d // lv.HOP_MS), val(start_levels, lv.START_GRID, d // lv.HOP_MS - lv.WINDOW_MS // lv.HOP_MS)
        rise[d] = None if after is None or before is None else after - before
    return dict(pre=pre, R=r, within=within, rise=rise)


def describe(values):
    v = [x for x in values if x is not None]
    if not v:
        return dict(n=0)
    q = np.percentile(v, [25, 50, 75])
    return dict(n=len(v), p25=round(float(q[0]), 2), median=round(float(q[1]), 2), p75=round(float(q[2]), 2),
                share_ge_m6=round(sum(x >= RING_DB for x in v) / len(v), 3), share_ge_m12=round(sum(x >= RING_DB_LOOSE for x in v) / len(v), 3))


def bootstrap_difference(a, b, seed=BOOT_SEED, n=BOOT_N):
    a, b = [x for x in a if x is not None], [x for x in b if x is not None]
    if not a or not b:
        return None
    rng = np.random.default_rng(seed)
    diffs = [np.median(rng.choice(a, len(a))) - np.median(rng.choice(b, len(b))) for _ in range(n)]
    low, high = np.percentile(diffs, [2.5, 97.5])
    return dict(low=round(float(low), 2), high=round(float(high), 2))


def analyse_corpus(ends, curves, verdicts):
    by_idx = {c['idx']: c for c in curves}
    rows = []
    for e in ends:
        c = by_idx[e['idx']]
        if c['midi_note'] != e['midi_note']:
            raise SystemExit('Curve and end disagree on the pitch at index %d' % e['idx'])
        rows.append(dict(e, **derive(e, c['end_levels'], c['start_levels'])))
    out = dict(ends=len(rows), strata={})
    for stratum in STRATA:
        block = {}
        for g in GROUPS:
            sel = [r for r in rows if r['group'] == g and in_stratum(r, stratum)]
            block[g] = dict(ends=len(sel), pre=describe([r['pre'] for r in sel]), within=describe([r['within'] for r in sel]),
                            **{'R%d' % tau: describe([r['R'][tau] for r in sel]) for tau in TAUS})
        out['strata'][stratum] = block
    # V1: alignment of the labels with the audio, from rises at label starts that no other labelled pitch contests.
    clean = [r for r in rows if not r['contested_start']]
    medians = {d: describe([r['rise'][d] for r in clean]) for d in RISE_DELTAS}
    usable = {d: m['median'] for d, m in medians.items() if m['n'] >= MIN_N}
    if 0 in usable and len(usable) == len(RISE_DELTAS):
        best = max(usable, key=usable.get)
        v1 = dict(rise_at_0_db=usable[0], argmax_ms=best, passed=usable[0] >= V1_RISE_DB and abs(best) <= V1_ARGMAX_MS)
    else:
        v1 = dict(passed=None, note='fewer than %d clean starts' % MIN_N)
    out['V1_alignment'] = dict(clean_starts=len(clean), median_rise_by_delta_ms=medians, **v1)
    if not verdicts:
        return out
    # Verdict stratum: the uncontested ends when adapted-only and neither each have at least MIN_N of them with a defined R(0), else all ends.
    def n_valid(g, stratum):
        return sum(1 for r in rows if r['group'] == g and in_stratum(r, stratum) and r['R'][0] is not None)
    stratum = 'uncontested' if n_valid('adapted_only', 'uncontested') >= MIN_N and n_valid('neither', 'uncontested') >= MIN_N else 'all'
    pick = lambda g, f: [f(r) for r in rows if r['group'] == g and in_stratum(r, stratum)]  # noqa: E731
    r0 = {g: describe(pick(g, lambda r: r['R'][0])) for g in GROUPS}
    pre = {g: describe(pick(g, lambda r: r['pre'])) for g in GROUPS}
    v = dict(stratum=stratum)
    a1 = r0['adapted_only'].get('median')
    v['A1_adapted_only_rings'] = dict(median_R0_db=a1, bar_db=A1_DB, verdict=None if a1 is None else ('pass' if a1 >= A1_DB else 'miss'))
    d = None if r0['adapted_only']['n'] < MIN_N or r0['neither']['n'] < MIN_N else r0['adapted_only']['median'] - r0['neither']['median']
    v['A2_adapted_only_over_neither'] = dict(difference_db=None if d is None else round(d, 2), bar_db=A2_DB,
                                              bootstrap_95=bootstrap_difference(pick('adapted_only', lambda r: r['R'][0]), pick('neither', lambda r: r['R'][0])),
                                              verdict='not evaluated' if d is None else ('pass' if d >= A2_DB else 'miss'))
    m = {g: pre[g].get('median') if pre[g]['n'] >= MIN_N else None for g in ('both', 'adapted_only', 'neither')}
    if None in m.values():
        v['A3_level_ordering'] = dict(verdict='not evaluated', medians_db=m)
    else:
        v['A3_level_ordering'] = dict(medians_db=m, verdict='pass' if m['both'] - m['adapted_only'] >= A3_DB and m['adapted_only'] - m['neither'] >= A3_DB else 'miss')
    w = describe([r['within'] for r in rows if in_stratum(r, stratum)])        # every group: the control is about sounding notes, not about presence
    v['V2_within_label'] = dict(n=w['n'], median_db=w.get('median'), band_db=[V2_LOW, V2_HIGH],
                                passed=None if w['n'] < MIN_N else V2_LOW <= w['median'] <= V2_HIGH)
    v['measurement_confirmed'] = bool(out['V1_alignment'].get('passed')) and bool(v['V2_within_label']['passed'])
    v['R0_by_group'] = r0
    out['verdicts'] = v
    return out


def analyse(ends_file, curves_file):
    result = dict(counts=ends_file['counts'], corpora={})
    for corpus in CORPORA:
        result['corpora'][corpus] = analyse_corpus(ends_file['corpora'][corpus]['ends'], curves_file['corpora'][corpus]['ends'], verdicts=(corpus == 'ordinary'))
    return result


def selftest():
    # contested(): octave, adjacent pitch at low frequency, a fifth, a high major third.
    s = (0, 10 ** 9)
    assert contested({52: [s]}, 40, 0, 100)                     # octave: 2 f0 = f(52)
    assert contested({41: [s]}, 40, 0, 100)                     # 69.3 Hz vs 65.4 Hz: inside the 25 Hz resolution
    assert contested({76: [s]}, 69, 0, 100)                     # a fifth: 2 f(76) = 3 f(69)
    assert not contested({73: [s]}, 69, 0, 100)                 # a high major third shares no resolved harmonic
    assert not contested({52: [(0, 50)]}, 40, 100, 200)         # the other pitch is not sounding in the interval
    assert not contested({40: [s]}, 40, 0, 100)                 # the pitch itself is not "another" pitch
    # derive(): R(tau) only when the window ends by W; within needs 160 ms inside the label; rise uses the start curve.
    n_e, n_s = 51, 41
    e = [-30.0] * n_e
    for j in range(-8, 0):
        e[j - lv.END_GRID[0]] = -20.0                         # the pre-end window level
    for j in range(0, 31):
        e[j - lv.END_GRID[0]] = -26.0 - 0.1 * j               # a drop of 6 dB at j = 0 and a slow fall afterwards
    e[-16 - lv.END_GRID[0]] = -19.0                           # the window before the pre-end window is 1 dB louder
    s_levels = [-40.0] * n_s
    for j in range(0, 21):
        s_levels[j - lv.START_GRID[0]] = -20.0                # a 20 dB rise at the label start
    end = dict(start=0, end=96000, window=96000 + lv.ms_samples(130), group='both', midi_note=60, idx=0, contested_end=False, contested_start=False)
    d = derive(end, e, s_levels)
    assert abs(d['pre'] + 20.0) < 1e-9 and abs(d['R'][0] + 6.0) < 1e-9 and abs(d['R'][40] + 6.4) < 1e-9
    assert d['R'][100] is None and d['R'][200] is None         # the window ends 130 ms after E: 80 + 100 does not fit
    assert abs(d['within'] + 1.0) < 1e-9
    assert abs(d['rise'][0] - 20.0) < 1e-9 and abs(d['rise'][-60]) < 1e-9 and abs(d['rise'][60] - 20.0) < 1e-9
    short = dict(end, start=96000 - lv.ms_samples(150))
    assert derive(short, e, s_levels)['within'] is None        # shorter than 160 ms
    # analyse_corpus() on a constructed corpus: adapted-only rings (-2 dB), neither is damped (-20 dB), both rings, levels ordered.
    def curve(pre, after, within_drop):
        levels = [-60.0] * n_e
        for j in range(-8, 0):
            levels[j - lv.END_GRID[0]] = pre
        for j in range(0, 31):
            levels[j - lv.END_GRID[0]] = pre + after
        for j in range(-16, -8):
            levels[j - lv.END_GRID[0]] = pre + within_drop
        return levels
    plan = dict(both=(-20.0, -2.0, 1.0, 30), adapted_only=(-30.0, -2.5, 1.0, 30), original_only=(-35.0, -3.0, 1.0, 3), neither=(-40.0, -22.0, 1.0, 30))
    ends, curves, idx = [], [], 0
    for g, (pre, after, within, count) in plan.items():
        for i in range(count):
            ends.append(dict(idx=idx, midi_note=60, start=0, end=96000, window=96000 + lv.ms_samples(1000), group=g, contested_end=False,
                             contested_start=False))
            wobble = 0.05 * (i % 5)
            curves.append(dict(idx=idx, midi_note=60, end_levels=curve(pre + wobble, after, within), start_levels=s_levels))
            idx += 1
    result = analyse_corpus(ends, curves, verdicts=True)
    v = result['verdicts']
    assert v['stratum'] == 'uncontested'
    assert v['A1_adapted_only_rings']['verdict'] == 'pass' and v['A2_adapted_only_over_neither']['verdict'] == 'pass'
    assert abs(v['A2_adapted_only_over_neither']['difference_db'] - 19.5) < 1e-9
    assert v['A3_level_ordering']['verdict'] == 'pass'                                  # -20.1, -30.1, -40.1: steps of 10 dB
    assert v['V2_within_label']['passed'] is True and result['V1_alignment']['passed'] is True and v['measurement_confirmed'] is True
    assert result['strata']['all']['original_only']['R0']['n'] == 3
    # A group of fewer than MIN_N ends makes its verdict "not evaluated", and a contested majority sends the verdict to 'all'.
    for e in ends:
        if e['group'] == 'neither':
            e['contested_end'] = True
    assert analyse_corpus(ends, curves, verdicts=True)['verdicts']['stratum'] == 'all'
    # A miss: an adapted-only that has already dropped 12 dB fails A1; a measurement without a rise at the start fails V1.
    flat = [dict(c, end_levels=curve(-30.0, -12.0, 1.0)) if e['group'] == 'adapted_only' else c for e, c in zip(ends, curves)]
    assert analyse_corpus(ends, flat, verdicts=True)['verdicts']['A1_adapted_only_rings']['verdict'] == 'miss'
    no_rise = [dict(c, start_levels=[-40.0] * n_s) for c in curves]
    assert analyse_corpus(ends, no_rise, verdicts=True)['V1_alignment']['passed'] is False
    # Bootstrap is deterministic.
    a, b = [1.0, 2.0, 3.0, 4.0], [0.0, 1.0, 2.0]
    assert bootstrap_difference(a, b) == bootstrap_difference(a, b)
    print('selftest ok')


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        selftest()
    elif len(sys.argv) >= 5 and sys.argv[1] == 'build-ends':
        result = build_ends(sys.argv[2], sys.argv[3])
        text = json.dumps(result, indent=1)
        open(sys.argv[4], 'w').write(text + '\n')
        print(json.dumps(result['counts'], indent=1))
    elif len(sys.argv) >= 4 and sys.argv[1] == 'analyse':
        result = analyse(json.load(open(sys.argv[2])), json.load(open(sys.argv[3])))
        text = json.dumps(result, indent=1)
        if len(sys.argv) >= 5:
            open(sys.argv[4], 'w').write(text + '\n')
        print(text)
    else:
        raise SystemExit(__doc__)
