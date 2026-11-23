"""Boundary-evidence census: at the end of a rapid-mute run, does the saved per-pitch evidence separate a re-struck note from the sustained tail of a pitch that was not re-struck?  Saved data only.

Plan, definitions, identity gates, predictions with odds and the reading rule are fixed in CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-PREREGISTRATION-20261122.md, committed before the real run.

Context.  CLAUDE-M3-RESTART-EVIDENCE-CENSUS-RESULT-20261122.md found no saved causal cue that restarts the 23 re-struck labels without restarting the 224 sustained tails, and its erratum showed
the v5 trace carries no per-pitch evidence in decisions of quiet code 5 (the rapid-mute disposition).  Every marked run, however, ends on an evaluated decision (the mask is applied to the callback that
FOLLOWS a code-5 decision, so each run's last callback holds the first evaluated decisions after the episode), and all 23 positive labels begin in that last callback or at most 25 ms after the run.
This script measures what those decisions say about the pitch, threshold-free: a rank statistic (AUC), no cue, no hold, no debounce, no restart machine.

Unit.  A pair (span, run): a CURRENT span that a marked run starts inside, and that run.  Positive pairs: each of the 23 positive labels (a label that loses present samples under the rapid-mute cut) with the last
run that starts inside its span at or before the label start.  Negative pairs (primary): each of the 224 negative spans at its first run (the one that defines the cut).  Secondary negatives: every later run
that starts inside a negative span.  Window: the decisions with sample in [run start, min(run end + 2400, span end, next run start)), 2400 samples = 25 ms.  Pre reference: the pitch's last decision before the run start
(and not before the span start) whose record has the energy observed.  Features (larger means re-attack, fixed in advance): F1 largest detector onset in the window (onset_observed decisions only); F2 largest
fund_energy in the window over the pre reference; F3 largest rise of fund_energy in the window above its own running minimum; F4 (pitch-agnostic control) largest rise of the global fast input power in the window
above its running minimum since the run start.  Missing counts as the lowest value (a missing value cannot restart anything).

Usage: python3 -P -E CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.py --selftest     (synthetic unit tests and real-data structure gates; no feature-versus-class number is printed)
       python3 -P -E CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.py --dry          (runs every code path on the real traces; prints counts only, writes nothing)
       python3 -P -E CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.py --run
No audio, model run, job or native edit.
"""
import bisect
import collections
import csv
import gzip
import hashlib
import importlib.util
import json
import math
import os
import random
import sys
from array import array

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ce = load('ce', 'CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.py')       # importing does not run its main
rm, chk, fr, ad = ce.rm, ce.chk, ce.fr, ce.ad
from tools.candidate_outcome_analysis import _candidates  # noqa: E402  (the repo's own trace parser, as in the tally and the census)

OUT = os.path.join(HERE, 'CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.json')
CENSUS_JSON = os.path.join(HERE, 'CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.json')
ORDINARY, EXTENDED = 'ordinary', 'extended-middle'
WINDOW = 2400                                   # 25 ms at 96 kHz: the frozen label budget's present-time limit, the same 25 ms as the restart-evidence census
PITCH_FEATURES = ('F1_onset', 'F2_rise_vs_pre', 'F3_rise_in_window')
FEATURES = PITCH_FEATURES + ('F4_global_rise',)
NUISANCE = ('N1_run_length', 'N2_window_length')   # descriptive only: what the geometry alone would give (never in the verdict)
ALL_SCORES = FEATURES + NUISANCE
SEED, RESAMPLES = 20261122, 2000
SENSITIVITIES = (0.9, 0.8, 0.7, 0.5)
SEPARATING = dict(auc=0.75, lower=0.60, coverage=0.80, full_window_positives=15)
STRONG = dict(auc=0.90, lower=0.75)
WHOLE_LOST = (42, 70, 200, 306, 364)           # the five labels the native joint reset lost whole (Codex run 45075475603), by label index


# ---------------------------------------------------------------- features
def ratio(a, b):
    """a / b with the conventions of this census: b > 0 gives a / b; b == 0 and a > 0 gives +inf (an attack from nothing); both zero gives 1."""
    if b > 0.0:
        return a / b
    return math.inf if a > 0.0 else 1.0


def drawup(series):
    """Largest ratio of a value to the running minimum up to and including it (>= 1 for a non-empty series), None for an empty one."""
    low, best = math.inf, None
    for value in series:
        low = min(low, value)
        r = ratio(value, low)
        best = r if best is None or r > best else best
    return best


def feature_values(pre_fund, fund_series, onset_series, power_series):
    out = dict(F1_onset=None, F2_rise_vs_pre=None, F3_rise_in_window=None, F4_global_rise=None)
    if onset_series:
        out['F1_onset'] = max(onset_series)
    if fund_series:
        if pre_fund is not None:
            out['F2_rise_vs_pre'] = max(ratio(f, pre_fund) for f in fund_series)
        out['F3_rise_in_window'] = drawup(fund_series)
    out['F4_global_rise'] = drawup(power_series)
    return out


def window_of(pair):
    run_start, run_end = pair['run']
    return run_start, min(run_end + WINDOW, pair['span'][1], pair['next_start'])


def select_indexed(dec, idx, pair):
    """The decisions a pair's features read, by bisection on the per-pitch arrays."""
    pitch, (lo, _hi), _run = pair['pitch'], pair['span'], pair['run']
    w0, w1 = window_of(pair)
    samples = dec['sample']
    a, b = bisect.bisect_left(samples, w0), bisect.bisect_left(samples, w1)
    power = [dec['power'][i] for i in range(a, b)]
    pre = pre_sample = None
    fund, onset = [], []
    d = idx.get(pitch)
    if d is not None:
        s = d['s']
        left, right = bisect.bisect_left(s, w0), bisect.bisect_left(s, w1)
        j = left - 1
        while j >= 0 and s[j] >= lo:
            if d['e'][j] == 1:
                pre, pre_sample = d['f'][j], s[j]
                break
            j -= 1
        for j in range(left, right):
            if d['e'][j] == 1:
                fund.append(d['f'][j])
            if d['o'][j] == 1:
                onset.append(d['v'][j])
    return dict(pre=pre, pre_sample=pre_sample, fund=fund, onset=onset, power=power, window=(w0, w1))


def select_naive(dec, pair):
    """The same selection by a plain linear scan of every decision (independent of the per-pitch arrays and of bisection); used as the reference."""
    pitch, (lo, _hi) = pair['pitch'], pair['span']
    w0, w1 = window_of(pair)
    pre = pre_sample = None
    fund, onset, power = [], [], []
    for i, s in enumerate(dec['sample']):
        if s >= w1:
            break
        rec = dec['rec'][i].get(pitch)
        if s < w0:
            if s >= lo and rec is not None and rec[1] == 1:
                pre, pre_sample = rec[2], s
        else:
            power.append(dec['power'][i])
            if rec is not None:
                if rec[1] == 1:
                    fund.append(rec[2])
                if rec[3] == 1:
                    onset.append(rec[4])
    return dict(pre=pre, pre_sample=pre_sample, fund=fund, onset=onset, power=power, window=(w0, w1))


def pair_record(pair, sel):
    """Features and descriptive covariates of one pair from its selection."""
    run_start, run_end = pair['run']
    w0, w1 = sel['window']
    values = feature_values(sel['pre'], sel['fund'], sel['onset'], sel['power'])
    values['N1_run_length'] = run_end - run_start
    values['N2_window_length'] = w1 - w0
    cover = dict(decisions=len(sel['power']), evaluated=len(sel['fund']), onset_observed=len(sel['onset']), has_pre=sel['pre'] is not None,
                 pre_gap=None if sel['pre_sample'] is None else run_start - sel['pre_sample'],
                 truncated_by='span_end' if pair['span'][1] <= min(run_end + WINDOW, pair['next_start']) else ('next_run' if pair['next_start'] < run_end + WINDOW else 'window'),
                 full_window=pair['span'][1] - run_end >= WINDOW and pair['next_start'] - run_end >= WINDOW, span_ends_in_run=pair['span'][1] <= run_end)
    return values, cover


def same_value(a, b):
    if a is None or b is None:
        return a is None and b is None
    if math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) <= 1e-12 * max(1.0, abs(a), abs(b))


# ---------------------------------------------------------------- trace
def read_trace(name):
    """One streaming pass over the pinned v5 trace (SHA-256 of the decompressed stream, checked after the pass): per decision the sample, the quiet code, the global input power and the candidate
    records reduced to (active, energy_observed, fund_energy, onset_observed, onset)."""
    pin, digest = chk.PINS[name], hashlib.sha256()
    dec = dict(sample=array('q'), quiet=array('b'), power=array('d'), rec=[])
    with gzip.open(os.path.join(ROOT, pin['trace']), 'rb') as stream:
        def lines():
            for raw in stream:
                digest.update(raw)
                yield raw.decode('utf-8')
        text = lines()
        if next(text).strip() != '# m3_candidate_outcome_v5':
            raise SystemExit('not the complete v5 trace')
        previous = None
        for row in csv.DictReader(text, delimiter='\t'):
            s = int(row['sample'])
            if s % 64 != 63 or (previous is not None and s != previous + 64):
                raise SystemExit('decision grid is not the contiguous 64-sample grid')
            previous = s
            dec['sample'].append(s)
            dec['quiet'].append(int(row['quiet']))
            dec['power'].append(float(row['input_power']))
            cands = _candidates({'candidate_text': row['candidates']})
            dec['rec'].append({note: (c['active'], c.get('energy_observed') or 0, c['fund_energy'], c['onset_observed'] or 0, c['onset']) for note, c in cands.items()})
    if digest.hexdigest() != pin['sha']:
        raise SystemExit(f'{name}: raw trace hash differs from the pin')
    return dec


def index_pitches(dec):
    idx = {}
    for i, rec in enumerate(dec['rec']):
        s = dec['sample'][i]
        for note, (active, observed, fund, onset_observed, onset) in rec.items():
            d = idx.get(note)
            if d is None:
                d = idx[note] = dict(s=array('q'), a=array('b'), e=array('b'), f=array('d'), o=array('b'), v=array('d'))
            d['s'].append(s)
            d['a'].append(active)
            d['e'].append(observed)
            d['f'].append(fund)
            d['o'].append(onset_observed)
            d['v'].append(onset)
    return idx


# ---------------------------------------------------------------- pairs (structure only: no feature value is read here)
def build_pairs(ctx, marked, cur_p, labels_p, horizon):
    kinds, trunc = ce.span_structure(cur_p, marked, labels_p)
    starts = [m[0] for m in marked]
    next_start = lambda k: marked[k + 1][0] if k + 1 < len(marked) else horizon
    pairs, problems = [], collections.Counter()
    pos_spans = [(n, t) for n, t in enumerate(trunc) if t['cls'] == 'positive']
    for i, lab in enumerate(ctx['labels']):
        hit = [(n, t) for n, t in pos_spans if t['pitch'] == lab['midi_note'] and lab['start_sample'] < t['span'][1] and lab['end_sample'] > t['cut']]
        if not hit:
            continue
        if len(hit) > 1:
            problems['label_in_several_positive_spans'] += 1
        n, t = hit[0]
        k = bisect.bisect_right(starts, lab['start_sample']) - 1
        if k < 0 or not (t['span'][0] < marked[k][0] < t['span'][1]):
            problems['positive_label_without_a_run_inside_its_span'] += 1
            continue
        pairs.append(dict(cls='positive', kind='primary', pitch=lab['midi_note'], label=i, span=tuple(t['span']), span_id=n, run=tuple(marked[k]), run_id=k, next_start=next_start(k)))
    for n, t in enumerate(trunc):
        if t['cls'] != 'negative':
            continue
        k = bisect.bisect_left(starts, t['cut'])
        if k >= len(starts) or starts[k] != t['cut'] or marked[k][1] != t['run_end']:
            problems['negative_cut_is_not_a_run'] += 1
            continue
        pairs.append(dict(cls='negative', kind='primary', pitch=t['pitch'], label=None, span=tuple(t['span']), span_id=n, run=tuple(marked[k]), run_id=k, next_start=next_start(k)))
        k2 = k + 1
        while k2 < len(marked) and marked[k2][0] < t['span'][1]:
            pairs.append(dict(cls='negative', kind='secondary', pitch=t['pitch'], label=None, span=tuple(t['span']), span_id=n, run=tuple(marked[k2]), run_id=k2, next_start=next_start(k2)))
            k2 += 1
    for p in pairs:
        w0, w1 = window_of(p)
        if not w1 > w0:
            problems['empty_window'] += 1
    return trunc, pairs, dict(problems)


def run_activity(dec, marked):
    """Part B proxy.  Per marked run, over its code-5 decisions (the gating decision just before the run included): how many candidates are CURRENT-active, which note is the only active one, and per note
    the share of those decisions where it is active."""
    samples, out = dec['sample'], {}
    for k, (run_start, run_end) in enumerate(marked):
        a, b = bisect.bisect_left(samples, run_start - 64), bisect.bisect_left(samples, run_end)
        count, low, sole, active = 0, None, set(), collections.Counter()
        for i in range(a, b):
            if dec['quiet'][i] != 5:
                continue
            notes = [note for note, rec in dec['rec'][i].items() if rec[0] == 1]
            count += 1
            low = len(notes) if low is None else min(low, len(notes))
            if len(notes) == 1:
                sole.add(notes[0])
            active.update(notes)
        out[k] = dict(code5_decisions=count, min_active=low, sole_notes=sorted(sole), active_share={note: n / count for note, n in active.items()} if count else {})
    return out


# ---------------------------------------------------------------- statistics
def rank_value(x):
    return -math.inf if x is None else x


def auc_matrix(pos, neg):
    return [[1.0 if a > b else (0.5 if a == b else 0.0) for b in neg] for a in pos]


def auc(pos, neg):
    if not pos or not neg:
        return None
    return sum(sum(row) for row in auc_matrix(pos, neg)) / (len(pos) * len(neg))


def weighted_auc(matrix, wp, wn):
    num = 0.0
    for i, row in enumerate(matrix):
        if wp[i]:
            num += wp[i] * sum(w * m for w, m in zip(wn, row) if w)
    den = sum(wp) * sum(wn)
    return num / den if den else None


def percentile_ci(values):
    values = sorted(values)
    n = len(values)
    return None if not n else (values[int(0.025 * n)], values[min(n - 1, int(math.ceil(0.975 * n)) - 1)])


def cluster_bootstrap(matrices, pos_clusters, neg_clusters, resamples, seed):
    """Per-replicate AUC of every score under one resampling of the clusters (the same replicates for every score, so differences are paired)."""
    rng = random.Random(seed)
    clusters = sorted(set(pos_clusters) | set(neg_clusters))
    draws = {name: [] for name in matrices}
    skipped = 0
    for _ in range(resamples):
        counts = collections.Counter(rng.choice(clusters) for _ in clusters)
        wp, wn = [counts.get(c, 0) for c in pos_clusters], [counts.get(c, 0) for c in neg_clusters]
        if not sum(wp) or not sum(wn):
            skipped += 1
            continue
        for name, matrix in matrices.items():
            draws[name].append(weighted_auc(matrix, wp, wn))
    return draws, skipped


def operating_point(pos, neg, target):
    """Largest threshold that keeps at least `target` of the positives (value >= threshold) and the share of negatives below it.  Optimistic: the threshold is read off the same data."""
    ordered = sorted(pos, reverse=True)
    k = max(1, math.ceil(target * len(ordered) - 1e-9))
    threshold = ordered[k - 1]
    if threshold == -math.inf:
        return None
    return dict(target=target, threshold=threshold, sensitivity=sum(1 for v in pos if v >= threshold) / len(pos), specificity=sum(1 for v in neg if v < threshold) / len(neg))


def quantiles(values):
    if not values:
        return None
    v = sorted(values)
    pick = lambda q: v[min(len(v) - 1, int(q * len(v)))]
    return dict(n=len(v), min=v[0], q25=pick(0.25), median=pick(0.5), q75=pick(0.75), max=v[-1])


def jsonable(x):
    if isinstance(x, float) and math.isinf(x):
        return 'inf' if x > 0 else '-inf'
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [jsonable(v) for v in x]
    return x


# ---------------------------------------------------------------- synthetic unit tests (plumbing; no real data)
def toy_trace():
    """Ten decisions at 63, 127, ..., 639 for note 50.  Codes 5 at k = 2, 3, 4 (no evidence); energies chosen so every feature has a hand-computed value."""
    samples = [63 + 64 * k for k in range(10)]
    quiet = [0, 0, 5, 5, 5, 0, 0, 2, 0, 0]
    power = [10.0, 9.0, 8.0, 6.0, 5.0, 7.0, 9.0, 3.0, 4.0, 4.5]
    # (active, energy_observed, fund, onset_observed, onset)
    notes = [(1, 1, 4.0, 1, 0.0), (1, 1, 2.0, 1, 0.0), (1, 0, 0.0, 0, 0.0), (1, 0, 0.0, 0, 0.0), (1, 0, 0.0, 0, 0.0),
             (1, 1, 0.5, 1, 0.02), (1, 1, 1.0, 1, 0.30), (1, 1, 3.0, 0, 0.0), (1, 1, 2.5, 1, 0.05), (1, 1, 0.1, 1, 0.0)]
    dec = dict(sample=array('q', samples), quiet=array('b', quiet), power=array('d', power), rec=[{50: n, 60: (0, 1, 1.0, 0, 0.0)} for n in notes])
    return dec


def unit_checks():
    ok, notes = [], []

    def check(label, condition):
        ok.append(bool(condition))
        notes.append((label, bool(condition)))
    check('ratio conventions', ratio(3, 2) == 1.5 and ratio(0, 2) == 0.0 and ratio(1, 0) == math.inf and ratio(0, 0) == 1.0)
    check('drawup', drawup([0.5, 1.0, 3.0, 2.5, 0.1]) == 6.0 and drawup([3.0, 2.0, 1.0]) == 1.0 and drawup([]) is None and drawup([0.0, 2.0]) == math.inf)
    check('auc hand value', abs(auc([3, 2], [1, 2, 2]) - 5 / 6) < 1e-12 and auc([1], [1]) == 0.5 and auc([2, 3], [0, 1]) == 1.0 and auc([0], [1]) == 0.0)
    check('auc missing is the lowest', auc([-math.inf, 1.0], [-math.inf, 0.0]) == (0.5 + 0.0 + 1.0 + 1.0) / 4)
    pos, neg = [3.0, 2.0, 5.0], [1.0, 2.0, 2.0, 4.0]
    matrix = auc_matrix(pos, neg)
    check('weighted auc with unit weights equals the plain auc', abs(weighted_auc(matrix, [1] * 3, [1] * 4) - auc(pos, neg)) < 1e-12)
    check('weighted auc with a doubled positive', abs(weighted_auc(matrix, [2, 1, 1], [1] * 4) - auc([3.0, 3.0, 2.0, 5.0], neg)) < 1e-12)
    a, skipped = cluster_bootstrap({'x': matrix}, [0, 1, 2], [3, 4, 5, 6], 50, 7)
    b, _ = cluster_bootstrap({'x': matrix}, [0, 1, 2], [3, 4, 5, 6], 50, 7)
    c, _ = cluster_bootstrap({'x': matrix}, [0, 1, 2], [3, 4, 5, 6], 50, 8)
    check('bootstrap is deterministic in its seed and differs across seeds', a == b and a != c and all(0.0 <= v <= 1.0 for v in a['x']))
    same_cluster, _ = cluster_bootstrap({'x': matrix}, [0, 0, 0], [0, 0, 0, 0], 20, 1)
    check('one shared cluster reproduces the plain auc in every replicate', all(abs(v - auc(pos, neg)) < 1e-12 for v in same_cluster['x']))
    point = operating_point([5.0, 4.0, 3.0, 2.0], [1.0, 2.5, 4.5, 0.5], 0.5)
    check('operating point', point['threshold'] == 4.0 and point['sensitivity'] == 0.5 and point['specificity'] == 0.75)
    check('operating point unreachable when the threshold is missing', operating_point([-math.inf, -math.inf, 1.0], [0.0], 0.9) is None)
    ci = percentile_ci(list(range(1000)))
    check('percentile interval', ci == (25, 974))
    dec = toy_trace()
    idx = index_pitches(dec)
    pair = dict(pitch=50, span=(0, 700), run=(192, 384), next_start=10 ** 9)
    sel = select_indexed(dec, idx, pair)
    f, cover = pair_record(pair, sel)
    check('hand-computed features', f['F1_onset'] == 0.30 and f['F2_rise_vs_pre'] == 1.5 and f['F3_rise_in_window'] == 6.0 and abs(f['F4_global_rise'] - 1.8) < 1e-12)
    check('pre reference is the last evaluated decision before the run (the code-5 decisions are skipped)', sel['pre'] == 2.0 and sel['pre_sample'] == 127 and cover['pre_gap'] == 65)
    check('window membership', len(sel['power']) == 7 and sel['fund'] == [0.5, 1.0, 3.0, 2.5, 0.1] and sel['onset'] == [0.02, 0.30, 0.05, 0.0])
    check('indexed selection equals the naive scan on the toy pair', all(same_value(a, b) if isinstance(a, float) else a == b for a, b in zip(select_naive(dec, pair).values(), sel.values())) or select_naive(dec, pair) == sel)
    cut = dict(pair, span=(0, 450))                         # window ends at the span end
    f2, c2 = pair_record(cut, select_indexed(dec, idx, cut))
    check('window is cut at the span end', f2['F3_rise_in_window'] == 2.0 and f2['N2_window_length'] == 450 - 192 and c2['truncated_by'] == 'span_end')
    nxt = dict(pair, next_start=400)                         # and at the next run
    f3, c3 = pair_record(nxt, select_indexed(dec, idx, nxt))
    check('window is cut at the next run', f3['N2_window_length'] == 400 - 192 and c3['truncated_by'] == 'next_run' and f3['F3_rise_in_window'] == 1.0)
    late = dict(pair, span=(130, 700))                       # the decision at 127 lies before the span start: no pre reference, F2 missing
    f4, c4 = pair_record(late, select_indexed(dec, idx, late))
    check('no pre reference before the span start', f4['F2_rise_vs_pre'] is None and not c4['has_pre'] and f4['F3_rise_in_window'] == 6.0)
    other = dict(pair, pitch=61)
    f5, c5 = pair_record(other, select_indexed(dec, idx, other))
    check('a pitch with no records has only the global feature', f5['F1_onset'] is None and f5['F2_rise_vs_pre'] is None and f5['F3_rise_in_window'] is None and abs(f5['F4_global_rise'] - 1.8) < 1e-12)
    short = dict(pair, run=(192, 200), span=(0, 700), next_start=10 ** 9)
    f6, c6 = pair_record(short, select_indexed(dec, idx, short))
    check('window length is run-end plus 2400 when nothing cuts it earlier', f6['N2_window_length'] == 700 - 192 and f6['N1_run_length'] == 8)
    # random synthetic traces: the bisection path must equal the plain scan on every pair
    rng = random.Random(11)
    agree = True
    for trial in range(12):
        n = rng.randint(30, 120)
        samples = array('q', [63 + 64 * k for k in range(n)])
        quiet = array('b', [rng.choice((0, 0, 2, 5, 5, 4)) for _ in range(n)])
        power = array('d', [rng.choice((0.0, rng.random() * 10)) for _ in range(n)])
        recs = []
        for k in range(n):
            rec = {}
            for note in (40, 45, 50):
                if rng.random() < 0.8:
                    observed = 0 if quiet[k] in (4, 5) else rng.randint(0, 1)
                    rec[note] = (rng.randint(0, 1), observed, rng.choice((0.0, rng.random() * 5)), observed and rng.randint(0, 1), rng.random())
            recs.append(rec)
        d2 = dict(sample=samples, quiet=quiet, power=power, rec=recs)
        i2 = index_pitches(d2)
        for _ in range(25):
            lo = rng.randrange(0, 63 * 20)
            rs = lo + rng.randrange(1, 800)             # the run starts strictly inside the span, as in every real pair (build_pairs checks it)
            hi = rs + rng.randrange(1, 6000)
            re = rs + rng.choice((512, 1024, 1536))
            p = dict(pitch=rng.choice((40, 45, 50, 55)), span=(lo, hi), run=(rs, re), next_start=re + rng.choice((100, 3000, 10 ** 6)))
            a, b = select_indexed(d2, i2, p), select_naive(d2, p)
            fa, _ = pair_record(p, a)
            fb, _ = pair_record(p, b)
            agree = agree and all(same_value(fa[k], fb[k]) for k in ALL_SCORES) and a['pre_sample'] == b['pre_sample'] and a['window'] == b['window']
    check('bisection selection equals the plain scan on 300 random synthetic pairs', agree)
    fake = lambda a_, lo_, cov_, n_, fa_, flo_: dict(auc=a_, ci_run=(lo_, 1.0), coverage_positive=cov_, auc_full_window_only=dict(positives=n_, auc=fa_, ci_run=(flo_, 1.0)))
    ordinary = {'F1_onset': fake(0.80, 0.65, 0.9, 20, 0.80, 0.65), 'F2_rise_vs_pre': fake(0.95, 0.80, 0.9, 20, 0.70, 0.55), 'F3_rise_in_window': fake(0.95, 0.80, 0.9, 20, 0.92, 0.78),
                'N1_run_length': fake(0.80, 0.65, 1.0, 23, 0.5, 0.4), 'N2_window_length': fake(0.6, 0.4, 1.0, 23, 0.5, 0.4)}
    sep, strong, nuisance = classify(ordinary)
    check('classify needs the primary and the full-window rule; strong is a subset; a passing nuisance score is listed', sep == ['F1_onset', 'F3_rise_in_window'] and strong == ['F3_rise_in_window'] and nuisance == ['N1_run_length'])
    check('classify needs at least 15 full-window positives', 'F1_onset' not in classify(dict(ordinary, F1_onset=fake(0.80, 0.65, 0.9, 14, 0.80, 0.65)))[0])
    check('classify needs 80% positive coverage', 'F3_rise_in_window' not in classify(dict(ordinary, F3_rise_in_window=fake(0.95, 0.80, 0.7, 20, 0.92, 0.78)))[0])
    check('classify needs the lower bound', 'F1_onset' not in classify(dict(ordinary, F1_onset=fake(0.80, 0.55, 0.9, 20, 0.80, 0.65)))[0])
    check('one odds value per prediction', len(ODDS) == len(PREDICTION_TEXT) == 12 and all(0.0 < o < 1.0 for o in ODDS))
    return all(ok), notes


# ---------------------------------------------------------------- one recording
def analyse(name, native_check=True):
    ctx = ad.dataset_context(name)
    horizon = ctx['horizon']
    last, audit = rm.read_quiet(name)
    marked = rm.marked_runs(last, horizon)
    cur_p = fr.by_pitch(ctx['cur_spans'], horizon)
    labels_p = {}
    for lab in ctx['labels']:
        labels_p.setdefault(lab['midi_note'], []).append([lab['start_sample'], lab['end_sample']])
    labels_p = {p: rm.merge_runs(v) for p, v in labels_p.items()}
    trunc, pairs, problems = build_pairs(ctx, marked, cur_p, labels_p, horizon)
    dec = read_trace(name)
    idx = index_pitches(dec)
    for pair in pairs:
        sel = select_indexed(dec, idx, pair)
        pair['values'], pair['cover'] = pair_record(pair, sel)
    census = json.load(open(CENSUS_JSON))['datasets'][name]
    key = lambda t: (t['pitch'], tuple(t['span']), t['cut'], t['run_end'], t['cls'])
    pos_labels = sorted(p['label'] for p in pairs if p['cls'] == 'positive')
    gates = dict(
        trace_pin_verified=True,
        runs_equal_rapid_mute_check=len(marked) == census['marked_runs'],
        truncated_spans_equal_census=[key(t) for t in trunc] == [key(t) for t in census['truncated_spans']],
        positive_labels_equal_census=pos_labels == sorted(census['positive_labels']),
        no_pair_problems=not problems,
        whole_lost_labels_are_positive=name != ORDINARY or set(WHOLE_LOST) <= set(pos_labels),
        primary_negative_pairs_equal_negative_spans=sum(1 for p in pairs if p['cls'] == 'negative' and p['kind'] == 'primary') == sum(1 for t in trunc if t['cls'] == 'negative'),
        gate_decision_before_every_run_is_code_5=all(dec['quiet'][bisect.bisect_left(dec['sample'], rs - 1)] == 5 for rs, _ in marked),
        last_decision_of_every_run_is_not_code_5=all(dec['quiet'][bisect.bisect_left(dec['sample'], re - 1)] != 5 for _, re in marked if re - 1 <= dec['sample'][-1] and re < horizon),   # a run clipped at the horizon is exempt
        code_5_decisions_never_observe_energy=all(rec[note][1] == 0 for i, rec in enumerate(dec['rec']) if dec['quiet'][i] == 5 for note in rec))
    # the plain scan against the bisection path: every primary pair, every pair of a small recording, an even sample of the secondary ones
    primary = [p for p in pairs if p['kind'] == 'primary']
    secondary = [p for p in pairs if p['kind'] != 'primary']
    checked = primary + secondary[::max(1, len(secondary) // 60)]
    agree = 0
    for pair in checked:
        naive, fast = pair_record(pair, select_naive(dec, pair)), (pair['values'], pair['cover'])
        agree += all(same_value(naive[0][k], fast[0][k]) for k in ALL_SCORES) and naive[1] == fast[1]
    gates['plain_scan_equals_bisection'] = agree == len(checked)
    activity = run_activity(dec, marked)
    structure = dict(name=name, horizon=horizon, runs=len(marked), decisions=len(dec['sample']), truncated=len(trunc), problems=problems,
                     pairs=dict(positive=sum(1 for p in pairs if p['cls'] == 'positive'), negative_primary=len(primary) - sum(1 for p in primary if p['cls'] == 'positive'),
                                negative_secondary=len(secondary)),
                     checked_against_plain_scan=len(checked), geometry=dict(
                         decisions_inside_runs_by_code=dict(sorted(collections.Counter(dec['quiet'][i] for rs, re in marked for i in range(bisect.bisect_left(dec['sample'], rs), bisect.bisect_left(dec['sample'], re))).items())),
                         runs_ending_on_code=dict(sorted(collections.Counter(int(dec['quiet'][bisect.bisect_left(dec['sample'], re - 1)]) for _, re in marked if re - 1 <= dec['sample'][-1]).items()))))
    return dict(ctx=ctx, marked=marked, trunc=trunc, pairs=pairs, gates=gates, activity=activity, structure=structure, dec_len=len(dec['sample']))


def coverage_counts(pairs):
    """Counts only (no feature value): by class, how many pairs have any evaluated decision, any onset-observed decision, a pre reference, a window cut by the span end."""
    out = {}
    for cls in ('positive', 'negative'):
        rows = [p for p in pairs if p['cls'] == cls and p['kind'] == 'primary']
        out[cls] = dict(pairs=len(rows), with_evaluated_decision=sum(1 for p in rows if p['cover']['evaluated'] > 0), with_onset_observed=sum(1 for p in rows if p['cover']['onset_observed'] > 0),
                        with_pre_reference=sum(1 for p in rows if p['cover']['has_pre']), span_ends_inside_run=sum(1 for p in rows if p['cover']['span_ends_in_run']),
                        full_25ms_window_possible=sum(1 for p in rows if p['cover']['full_window']))
    return out


# ---------------------------------------------------------------- the analysis proper
def score_block(pairs):
    """Everything computed from the primary ordinary pairs (and the secondary ones for the robustness reading)."""
    pos = [p for p in pairs if p['cls'] == 'positive']
    neg = [p for p in pairs if p['cls'] == 'negative' and p['kind'] == 'primary']
    neg_all = [p for p in pairs if p['cls'] == 'negative']
    rank = lambda rows, f: [rank_value(p['values'][f]) for p in rows]
    result = {}
    matrices = {f: auc_matrix(rank(pos, f), rank(neg, f)) for f in ALL_SCORES}
    for tag, cl in (('run', lambda p: p['run_id']), ('span', lambda p: p['span_id'])):
        draws, skipped = cluster_bootstrap(matrices, [cl(p) for p in pos], [cl(p) for p in neg], RESAMPLES, SEED)
        result['bootstrap_' + tag] = dict(draws=draws, skipped=skipped)
    # The pairs whose full 25 ms window exists (both classes), with their own run-cluster bootstrap.  This is the second condition of the separating rule: it removes the shorter windows of negatives
    # whose span ends early, which would otherwise rank at the bottom for a reason that has nothing to do with the evidence.
    fp, fneg = [p for p in pos if p['cover']['full_window']], [p for p in neg if p['cover']['full_window']]
    fw_draws, fw_skipped = cluster_bootstrap({f: auc_matrix(rank(fp, f), rank(fneg, f)) for f in ALL_SCORES}, [p['run_id'] for p in fp], [p['run_id'] for p in fneg], RESAMPLES, SEED + 1)
    result['bootstrap_full_window_skipped'] = fw_skipped
    for f in ALL_SCORES:
        a = auc(rank(pos, f), rank(neg, f))
        entry = dict(auc=a, ci_run=percentile_ci(result['bootstrap_run']['draws'][f]), ci_span=percentile_ci(result['bootstrap_span']['draws'][f]),
                     coverage_positive=sum(1 for p in pos if p['values'][f] is not None) / len(pos), coverage_negative=sum(1 for p in neg if p['values'][f] is not None) / len(neg),
                     positive=quantiles([p['values'][f] for p in pos if p['values'][f] is not None]), negative=quantiles([p['values'][f] for p in neg if p['values'][f] is not None]),
                     operating_points=[operating_point(rank(pos, f), rank(neg, f), s) for s in SENSITIVITIES])
        # robustness: every negative event, not only the first run of each span
        entry['auc_all_negative_events'] = auc(rank(pos, f), rank(neg_all, f))
        # the pairs whose full 25 ms window exists
        entry['auc_full_window_only'] = dict(positives=len(fp), negatives=len(fneg), auc=auc(rank(fp, f), rank(fneg, f)), ci_run=percentile_ci(fw_draws[f]))
        # matched: positive and negative pairs at the same run
        by_run = collections.defaultdict(lambda: ([], []))
        for p in pos:
            by_run[p['run_id']][0].append(p)
        for p in neg:
            by_run[p['run_id']][1].append(p)
        total = comps = runs = 0
        for ps, ns in by_run.values():
            if ps and ns:
                runs += 1
                for a_ in ps:
                    for b_ in ns:
                        x, y = rank_value(a_['values'][f]), rank_value(b_['values'][f])
                        total += 1.0 if x > y else (0.5 if x == y else 0.0)
                        comps += 1
        entry['matched_within_run'] = dict(runs=runs, comparisons=comps, auc=(total / comps if comps else None))
        result[f] = entry
    # pitch-specific advantage over the global control: paired bootstrap of the best pitch-specific AUC minus F4's
    best = max(PITCH_FEATURES, key=lambda f: result[f]['auc'])
    diff = [a - b for a, b in zip(result['bootstrap_run']['draws'][best], result['bootstrap_run']['draws']['F4_global_rise'])]
    result['best_pitch_feature'] = best
    result['best_minus_control'] = dict(auc_difference=result[best]['auc'] - result['F4_global_rise']['auc'], ci_run=percentile_ci(diff))
    for f in ALL_SCORES:
        del result['bootstrap_run']['draws'][f], result['bootstrap_span']['draws'][f]
    result['counts'] = dict(positive_pairs=len(pos), negative_primary=len(neg), negative_all_events=len(neg_all), positive_spans=len({p['span_id'] for p in pos}), runs_with_a_pair=len({p['run_id'] for p in pos + neg}))
    return result


def extended_share(ext_pairs, ordinary_result):
    """Share of the extended-middle negative pairs below the ordinary sens-0.8 operating point of each score (design-data transfer, descriptive)."""
    out = {}
    for f in FEATURES:
        point = next((o for o in ordinary_result[f]['operating_points'] if o and o['target'] == 0.8), None)
        rows = [p for p in ext_pairs if p['cls'] == 'negative' and p['kind'] == 'primary']
        out[f] = None if point is None else dict(threshold=point['threshold'], below=sum(1 for p in rows if rank_value(p['values'][f]) < point['threshold']), of=len(rows))
    return out


def part_b(pairs, activity):
    """Descriptive proxy for the owner-loss hypothesis: was the pair's pitch the only CURRENT-active candidate at some code-5 decision of its run?"""
    sole = lambda p: p['pitch'] in activity[p['run_id']]['sole_notes']
    rows = {}
    for p in pairs:
        if p['cls'] != 'positive':
            continue
        a = activity[p['run_id']]
        rows[p['label']] = dict(pitch=p['pitch'], run_id=p['run_id'], sole_owner=sole(p), min_active=a['min_active'], active_share=a['active_share'].get(p['pitch'], 0.0), code5_decisions=a['code5_decisions'])
    lost = [rows[i] for i in WHOLE_LOST if i in rows]
    rest = [v for i, v in rows.items() if i not in WHOLE_LOST]
    negatives = [p for p in pairs if p['cls'] == 'negative' and p['kind'] == 'primary']
    return dict(whole_lost_labels=list(WHOLE_LOST), per_label=rows,
                whole_lost=dict(n=len(lost), sole_owner=sum(1 for v in lost if v['sole_owner'])),
                other_positives=dict(n=len(rest), sole_owner=sum(1 for v in rest if v['sole_owner'])),
                negative_primary_pairs=dict(n=len(negatives), sole_owner=sum(1 for p in negatives if sole(p))),
                all_runs=dict(n=len(activity), with_a_sole_active_note=sum(1 for a in activity.values() if a['sole_notes']), min_active_histogram=dict(sorted(collections.Counter(a['min_active'] for a in activity.values()).items(), key=lambda kv: (kv[0] is None, kv[0])))))


ODDS = (0.50, 0.40, 0.55, 0.50, 0.40, 0.80, 0.85, 0.50, 0.60, 0.40, 0.50, 0.70)
SETTLED_BY_DRY_RUN = (6, 8)       # P7 and P9 (0-based): the counts-only dry run showed F2 defined for all 23 positives and no F2 for 6 of the 9 extended-middle pairs; scored, but reported with and without them
PREDICTION_TEXT = (
    'P1 F2 (rise over the pre reference) has AUC >= 0.75',
    'P2 F1 (detector onset) has AUC >= 0.75',
    'P3 F3 (rise within the window) has AUC >= 0.75',
    'P4 the global control F4 has AUC < 0.65',
    'P5 at least one of F1-F3 meets the separating rule (primary pairs: AUC >= 0.75, run-cluster lower bound >= 0.60, positive coverage >= 80%; and on the pairs with a full 25 ms window: AUC >= 0.75, lower bound >= 0.60, at least 15 positives)',
    'P6 none of F1-F3 meets the strong rule (separating, and primary AUC >= 0.90 with lower bound >= 0.75)',
    'P7 F2 is defined for at least 80% of the 23 positive pairs',
    'P8 the best pitch-specific AUC exceeds the global control F4 AUC by at least 0.10',
    'P9 at least 5 of the 9 extended-middle negative pairs lie below the ordinary sens-0.8 threshold of F2',
    'P10 at least 4 of the 5 whole-lost labels have a sole-owner moment (their pitch is the only CURRENT-active candidate at some code-5 decision of the run)',
    'P11 the sole-owner share among the 5 whole-lost labels exceeds the share among the other 18 positives',
    'P12 the F2 AUC over all negative events differs from the primary F2 AUC by at most 0.05')


def classify(ordinary):
    """The separating rule fixed in the pre-registration.  A pitch-specific feature separates only if it passes on the primary pairs (AUC, run-cluster lower bound, positive coverage) AND on the pairs whose
    full 25 ms window exists (AUC, lower bound, at least 15 positives there).  Strong: also AUC >= 0.90 and lower bound >= 0.75 on the primary pairs.  The nuisance scores (run length, window length) are
    listed when they pass the primary rule alone.  Returns (separating, strong, nuisance_passing)."""
    separating, strong, nuisance = [], [], []
    for x in PITCH_FEATURES:
        e, fw = ordinary[x], ordinary[x]['auc_full_window_only']
        primary = e['auc'] >= SEPARATING['auc'] and e['ci_run'] is not None and e['ci_run'][0] >= SEPARATING['lower'] and e['coverage_positive'] >= SEPARATING['coverage']
        robust = fw['positives'] >= SEPARATING['full_window_positives'] and fw['auc'] is not None and fw['ci_run'] is not None and fw['auc'] >= SEPARATING['auc'] and fw['ci_run'][0] >= SEPARATING['lower']
        if primary and robust:
            separating.append(x)
            if e['auc'] >= STRONG['auc'] and e['ci_run'][0] >= STRONG['lower']:
                strong.append(x)
    for x in NUISANCE:
        e = ordinary[x]
        if e['auc'] >= SEPARATING['auc'] and e['ci_run'] is not None and e['ci_run'][0] >= SEPARATING['lower']:
            nuisance.append(x)
    return separating, strong, nuisance


def predictions(ordinary, ext, partb):
    f = lambda name: ordinary[name]
    separating, strong, nuisance = classify(ordinary)
    share = lambda d: (d['sole_owner'] / d['n']) if d['n'] else 0.0
    ext_f2 = ext['F2_rise_vs_pre']
    outcomes = (f('F2_rise_vs_pre')['auc'] >= 0.75, f('F1_onset')['auc'] >= 0.75, f('F3_rise_in_window')['auc'] >= 0.75, f('F4_global_rise')['auc'] < 0.65, bool(separating), not strong,
                f('F2_rise_vs_pre')['coverage_positive'] >= 0.80, ordinary['best_minus_control']['auc_difference'] >= 0.10,
                ext_f2 is not None and ext_f2['below'] >= 5, partb['whole_lost']['sole_owner'] >= 4, share(partb['whole_lost']) > share(partb['other_positives']),
                abs(f('F2_rise_vs_pre')['auc_all_negative_events'] - f('F2_rise_vs_pre')['auc']) <= 0.05)
    brier = [(o - (1.0 if hit else 0.0)) ** 2 for o, hit in zip(ODDS, outcomes)]
    opened = [i for i in range(len(ODDS)) if i not in SETTLED_BY_DRY_RUN]
    return dict(items=[dict(text=t, odds=o, outcome=bool(h), settled_by_dry_run=i in SETTLED_BY_DRY_RUN) for i, (t, o, h) in enumerate(zip(PREDICTION_TEXT, ODDS, outcomes))], hits=sum(outcomes),
                brier_sum=sum(brier), brier_mean=sum(brier) / len(brier), hits_not_settled=sum(1 for i in opened if outcomes[i]), brier_sum_not_settled=sum(brier[i] for i in opened), not_settled=len(opened)), separating, strong, nuisance


def verdict(ordinary, separating, strong, nuisance):
    control = ordinary['F4_global_rise']
    advantage = ordinary['best_minus_control']['ci_run']
    if not separating:
        reading = 'NOT SEPARATING: no pitch-specific feature meets the rule; saved boundary evidence does not separate re-struck notes from sustained tails.  An in-run observation or a faster onset feature would be needed (native lane).'
    elif advantage and advantage[0] > 0:
        reading = 'SEPARATING, PITCH-SPECIFIC (a lead on design data only): ' + ', '.join(separating) + ' meet the rule and the best of them beats the global control with a positive lower bound.'
    else:
        reading = 'SEPARATING BUT NOT SHOWN PITCH-SPECIFIC: ' + ', '.join(separating) + ' meet the rule, but the difference from the global control F4 has no positive lower bound.'
    if nuisance:
        reading += '  The nuisance score(s) ' + ', '.join(nuisance) + ' also pass the primary rule: run length or window length alone separates, so a pitch feature is informative only to the extent that it beats them.'
    return dict(separating=separating, strong=strong, nuisance_passing=nuisance, global_control_auc=control['auc'], global_control_separating=bool(control['auc'] >= SEPARATING['auc'] and control['ci_run'] and control['ci_run'][0] >= SEPARATING['lower']), reading=reading)


def compute():
    out = dict(schema='m3_boundary_evidence_census_v1', window_samples=WINDOW, seed=SEED, resamples=RESAMPLES, features=list(ALL_SCORES), datasets={})
    runs = {}
    for name in (ORDINARY, EXTENDED):
        runs[name] = analyse(name)
    ordinary = score_block(runs[ORDINARY]['pairs'])
    ext_pairs = runs[EXTENDED]['pairs']
    ext = extended_share(ext_pairs, ordinary)
    partb = part_b(runs[ORDINARY]['pairs'], runs[ORDINARY]['activity'])
    preds, separating, strong, nuisance = predictions(ordinary, ext, partb)
    out['ordinary'], out['extended_middle_share_below_ordinary_sens_0_8'], out['part_b'] = ordinary, ext, partb
    out['predictions'], out['verdict'] = preds, verdict(ordinary, separating, strong, nuisance)
    for name in (ORDINARY, EXTENDED):
        r = runs[name]
        out['datasets'][name] = dict(structure=r['structure'], gates=r['gates'], coverage_counts=coverage_counts(r['pairs']),
                                     pairs=[dict(kind=p['kind'], cls=p['cls'], pitch=p['pitch'], label=p['label'], span=p['span'], run=p['run'], run_id=p['run_id'], span_id=p['span_id'], values=p['values'], cover=p['cover']) for p in r['pairs']])
    out['gates_all_pass'] = all(all(r['gates'].values()) for r in runs.values())
    out['inputs'] = {n: dict(trace_sha256=chk.PINS[n]['sha']) for n in chk.PINS}
    out['census_json_sha256'] = hashlib.sha256(open(CENSUS_JSON, 'rb').read()).hexdigest()
    return out


def fmt(x):
    if x is None:
        return 'None'
    if isinstance(x, float):
        return 'inf' if math.isinf(x) and x > 0 else ('-inf' if math.isinf(x) else f'{x:.4g}')
    return str(x)


def report(out):
    print('verdict', out['verdict']['reading'])
    p = out['predictions']
    print('predictions: hits', p['hits'], 'of', len(p['items']), 'Brier sum', round(p['brier_sum'], 4), 'mean', round(p['brier_mean'], 4),
          '| not settled by the dry run: hits', p['hits_not_settled'], 'of', p['not_settled'], 'Brier sum', round(p['brier_sum_not_settled'], 4))
    for item in p['items']:
        print(' ', 'HIT ' if item['outcome'] else 'MISS', item['odds'], '(settled by the dry run)' if item['settled_by_dry_run'] else '', item['text'])
    o = out['ordinary']
    print('counts', json.dumps(o['counts']), 'bootstrap skipped (run, span)', o['bootstrap_run']['skipped'], o['bootstrap_span']['skipped'])
    for f in ALL_SCORES:
        e = o[f]
        fw = e['auc_full_window_only']
        rounded = lambda ci: None if ci is None else tuple(round(v, 3) for v in ci)
        print(f'{f:19s} AUC {e["auc"]:.4f} run CI {rounded(e["ci_run"])} span CI {rounded(e["ci_span"])} coverage pos {e["coverage_positive"]:.3f} neg {e["coverage_negative"]:.3f} '
              f'| all-events AUC {e["auc_all_negative_events"]:.4f} | full-window AUC {fmt(fw["auc"])} run CI {rounded(fw["ci_run"])} ({fw["positives"]}+/{fw["negatives"]}-) | matched-in-run AUC {fmt(e["matched_within_run"]["auc"])} ({e["matched_within_run"]["runs"]} runs, {e["matched_within_run"]["comparisons"]} comparisons)')
        print('    positive', {k: fmt(v) for k, v in (e['positive'] or {}).items()}, '| negative', {k: fmt(v) for k, v in (e['negative'] or {}).items()})
        print('    operating points (optimistic)', [None if p is None else (p['target'], fmt(p['threshold']), round(p['sensitivity'], 3), round(p['specificity'], 3)) for p in e['operating_points']])
    print('best pitch-specific', o['best_pitch_feature'], 'minus control: AUC difference', round(o['best_minus_control']['auc_difference'], 4), 'run CI', o['best_minus_control']['ci_run'])
    print('extended-middle negatives below the ordinary sens-0.8 threshold', json.dumps(jsonable(out['extended_middle_share_below_ordinary_sens_0_8'])))
    b = out['part_b']
    print('part B', json.dumps(jsonable({k: v for k, v in b.items() if k != 'per_label'})))
    print('part B per label (whole-lost first)', json.dumps(jsonable({str(i): b['per_label'][i] for i in list(WHOLE_LOST) if i in b['per_label']})))
    for name, d in out['datasets'].items():
        print(name, 'coverage counts', json.dumps(d['coverage_counts']), 'gates', json.dumps(d['gates']))


def main():
    if os.path.exists(OUT):
        raise SystemExit('refusing to overwrite ' + OUT)
    out = compute()
    if not out['gates_all_pass']:
        raise SystemExit('identity gates failed; nothing written: ' + json.dumps({n: d['gates'] for n, d in out['datasets'].items()}))
    with open(OUT, 'w') as stream:
        json.dump(jsonable(out), stream, indent=1)
    report(out)


def selftest():
    good, notes = unit_checks()
    print('unit checks', 'PASS' if good else 'FAIL', [f'{n}: {"ok" if v else "FAIL"}' for n, v in notes])
    ok = good
    for name in (ORDINARY, EXTENDED):
        r = analyse(name)
        s = r['structure']
        print(f"{name}: runs {s['runs']}, decisions {s['decisions']:,}, truncated spans {s['truncated']}, pairs {json.dumps(s['pairs'])}, problems {json.dumps(s['problems'])}; checked against the plain scan: {s['checked_against_plain_scan']}")
        print('  geometry: decisions inside runs by quiet code', json.dumps(s['geometry']['decisions_inside_runs_by_code']), '; runs ending on code', json.dumps(s['geometry']['runs_ending_on_code']))
        print('  gates', json.dumps(r['gates']))
        ok = ok and all(r['gates'].values())
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return ok


def dry():
    """Execute every code path of the run on the real traces; print counts and gate results only (no score, interval, prediction or feature-versus-class number) and write nothing."""
    out = compute()
    for name, d in out['datasets'].items():
        s = d['structure']
        print(f"{name}: runs {s['runs']}, truncated spans {s['truncated']}, pairs {json.dumps(s['pairs'])}, problems {json.dumps(s['problems'])}")
        print('  coverage counts (by class; no feature values)', json.dumps(d['coverage_counts']))
        print('  gates', json.dumps(d['gates']))
    print('DRY RUN OK: nothing written, no result printed; identity gates', 'PASS' if out['gates_all_pass'] else 'FAIL')
    return out['gates_all_pass']


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        raise SystemExit(0 if selftest() else 1)
    if sys.argv[1:] == ['--dry']:
        raise SystemExit(0 if dry() else 1)
    if sys.argv[1:] == ['--run']:
        main()
    else:
        raise SystemExit(__doc__)
