"""What the native/neural consensus hybrid adds, sample by sample, and what a label-free cleanup of it would cost.  Saved data only.

No audio, no model run, no job, nothing promoted or installed.  Inputs are the frozen ones of Codex's consensus screen
(build/recovery/m3-native-neural-consensus-20261121/, ordinary corpus): CURRENT's saved pitch spans, Basic Pitch arm A's measured-FIFO
spans, the v5 trace's selector_pool_member/direct confirmation, and the labels.  The hybrid is CURRENT union (A intersect native
confirmation).  Codex's report: +2,211,863 expected pitch-samples (+6.54 points), no label loses presence or longest hold, but wrong-pitch
+152,166 and gap +183,069, so the frozen strict gate fails.  This script asks two things.

(1) What are those 335,235 added false samples (tail after the same-pitch label, octave of an active note, a pitch with no label near,
    and which band)?  Every sample the hybrid adds is a sample of A intersect confirmation that CURRENT did not already output, so the
    decomposition is exact.
(2) Can any label-free cleanup of the additions (a threshold on one native candidate feature at the callback, or a causal onset delay
    that withholds the first T ms of each added run) remove the false part cheaply?  Reported as a frontier of removed-false versus
    removed-genuine, not as a rule.  A union can only add, so the strict gate (extras may not rise) is unreachable for any additive
    variant that adds a single false sample; the frontier is therefore the honest quantity and nothing here claims a gate pass.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the report-level deltas above, the shape of the saved files (1,611 added spans, 1,063 hybrid spans), the label format.
NOT seen: any per-sample decomposition of the additions, any feature of an added run, any variant.  Predictions, each can fail:
  X0  my own (pitch, sample) counting of CURRENT-subtracted additions reproduces +2,211,863 genuine, +152,166 wrong, +183,069 gap exactly.
  X1  tail samples (after the last same-pitch label end, within 1.5 s, nearer to that end than to the next same-pitch start) are at least
      60% of the added gap samples.
  X2  at least 50% of the added wrong samples are octave-related to an active label (|pitch - label pitch| a nonzero multiple of 12).
  X3  the 20 largest added false runs hold at least 50% of the added false samples.
  X4  the added false share (false / added) is highest in the 72+ band among the four bands (below 48, 48-59, 60-71, 72+).
  X5  no feature gate that removes at least 25% of the added false samples does so at a removed-false : removed-genuine ratio of 2.0 or better.
  X6  a causal onset delay of T ms (withhold the first T ms of each added run) removes more genuine than false samples at every T in
      {5, 10, 20, 50, 100, 200} ms (ratio below 1.0 at all of them).
  X7  no gate or delay leaves fewer than 150,000 added false samples while keeping at least 75% of the added genuine samples.
Report everything whatever it shows.  One recording, one corpus; ticks and runs are correlated, so these are descriptive counts with no
confidence interval; the threshold grid is label-free (deciles of the feature over all confirmed rows) but the scoring uses labels, so
any best-of-grid figure is in-sample and a lead, not a rule.  The neural arm A is an offline-run reference stream with measured FIFO
timestamps; joint runtime, string assignment, unisons and live delivery are not measured.

Usage: python3 -P -E CLAUDE-M3-CONSENSUS-EXTRAS-20261122.py
"""
import bisect
import csv
import gzip
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.candidate_outcome_analysis import _candidates  # noqa: E402
from tools.native_neural_consensus import (  # noqa: E402
    EVIDENCE_DIR, TRACE_PINS, confirmation_spans, intersect_spans, selector_confirmation)
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-CONSENSUS-EXTRAS-20261122.json')
CONSENSUS = os.path.join(REPO, 'build/recovery/m3-native-neural-consensus-20261121')
BASELINE = os.path.join(REPO, 'docs/recovery/basic-pitch-baseline-20261121.json')
TAIL_SAMPLES = int(1.5 * 96000)
BANDS = [(0, 48, 'below 48'), (48, 60, '48-59'), (60, 72, '60-71'), (72, 200, '72+')]
FEATS = ['score_ratio', 'fund_ratio', 'band_score', 'band_fund', 'local', 'evidence', 'onset', 'age', 'attack', 'release',
         'evidence_ticks', 'evidence_gap', 'selection', 'selector_raw_score', 'selector_best_adjusted_score', 'fund_energy',
         'score_energy', 'best_cal', 'cal_margin']
DELAYS_MS = [5, 10, 20, 50, 100, 200]


def band_of(pitch):
    for lo, hi, name in BANDS:
        if lo <= pitch < hi:
            return name
    raise ValueError(pitch)


def by_pitch(spans):
    grouped = defaultdict(list)
    for left, right, pitch in spans:
        grouped[pitch].append((left, right))
    for pitch in grouped:
        grouped[pitch].sort()
    return grouped


def subtract_pitch(a, b):
    """a minus b, both sorted disjoint interval lists of one pitch."""
    out, j = [], 0
    for left, right in a:
        cur = left
        while j < len(b) and b[j][1] <= cur:
            j += 1
        k = j
        while k < len(b) and b[k][0] < right:
            if b[k][0] > cur:
                out.append((cur, b[k][0]))
            cur = max(cur, b[k][1])
            k += 1
        if cur < right:
            out.append((cur, right))
    return out


def merge(ivs):
    out = []
    for left, right in sorted(ivs):
        if out and left <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], right))
        else:
            out.append((left, right))
    return out


class LabelIndex:
    def __init__(self, labels):
        self.labels = labels
        self.pitch_iv = defaultdict(list)
        for row in labels:
            self.pitch_iv[row['midi_note']].append((row['start_sample'], row['end_sample']))
        self.pitch_iv = {p: merge(v) for p, v in self.pitch_iv.items()}
        self.any_iv = merge([(r['start_sample'], r['end_sample']) for r in labels])
        self.points = sorted({r['start_sample'] for r in labels} | {r['end_sample'] for r in labels})

    _starts = {}

    def overlap(self, ivs, left, right):
        key = id(ivs)
        if key not in self._starts:
            self._starts[key] = [x[0] for x in ivs]
        starts = self._starts[key]
        total = 0
        i = max(0, bisect.bisect_right(starts, left) - 1)
        while i < len(ivs) and ivs[i][0] < right:
            a, b = max(ivs[i][0], left), min(ivs[i][1], right)
            if a < b:
                total += b - a
            i += 1
        return total

    def active_pitches(self, left, right):
        return {r['midi_note'] for r in self.labels if r['start_sample'] < right and r['end_sample'] > left}

    def segments(self, left, right):
        inner = self.points[bisect.bisect_right(self.points, left):bisect.bisect_left(self.points, right)]
        cuts = [left, *inner, right]
        return list(zip(cuts[:-1], cuts[1:]))


def relation(pitch, active):
    """Octave first, then fifth, near, other; sign of the nearest octave partner kept."""
    for q in sorted(active, key=lambda q: abs(pitch - q)):
        if (pitch - q) % 12 == 0:
            return 'octave_up' if pitch > q else 'octave_down'
    for q in active:
        if (pitch - q) % 12 == 7 or (q - pitch) % 12 == 7:
            return 'fifth'
    if any(abs(pitch - q) <= 2 for q in active):
        return 'near'
    return 'other'


def decompose(runs, index, horizon):
    """runs: {pitch: [(l, r)]}.  Exact (pitch, sample) accounting plus anatomy of the false samples."""
    half = horizon // 2
    acc = dict(genuine=0, wrong=0, gap=0, genuine_h=[0, 0], false_h=[0, 0], band=defaultdict(lambda: [0, 0]),
               wrong_rel=defaultdict(int), gap_kind=defaultdict(int), tail_ms=[], runs=[])
    for pitch, ivs in runs.items():
        for left, right in ivs:
            run = dict(pitch=pitch, left=left, right=right, genuine=0, wrong=0, gap=0)
            for a, b in index.segments(left, right):
                length = b - a
                active = index.active_pitches(a, b)
                h = 0 if (a + b) // 2 < half else 1
                if pitch in active:
                    acc['genuine'] += length
                    acc['genuine_h'][h] += length
                    acc['band'][band_of(pitch)][0] += length
                    run['genuine'] += length
                elif active:
                    acc['wrong'] += length
                    acc['false_h'][h] += length
                    acc['band'][band_of(pitch)][1] += length
                    acc['wrong_rel'][relation(pitch, active)] += length
                    run['wrong'] += length
                else:
                    acc['gap'] += length
                    acc['false_h'][h] += length
                    acc['band'][band_of(pitch)][1] += length
                    run['gap'] += length
                    ivp = index.pitch_iv.get(pitch, [])
                    mid = (a + b) // 2
                    k = bisect.bisect_right([x[0] for x in ivp], mid)
                    d_tail = mid - ivp[k - 1][1] if k > 0 else None
                    d_head = ivp[k][0] - mid if k < len(ivp) else None
                    if d_tail is not None and d_tail <= TAIL_SAMPLES and (d_head is None or d_tail <= d_head):
                        kind = 'tail'
                        acc['tail_ms'].append((length, d_tail / 96.0))
                    elif d_head is not None and d_head <= TAIL_SAMPLES:
                        kind = 'head'
                    else:
                        kind = 'orphan'
                    acc['gap_kind'][kind] += length
            run['false'] = run['wrong'] + run['gap']
            acc['runs'].append(run)
    return acc


def weighted_quantiles(pairs, qs):
    pairs = sorted(pairs, key=lambda x: x[1])
    total = sum(w for w, _ in pairs)
    out, run, i = {}, 0, 0
    for q in qs:
        while i < len(pairs) and run + pairs[i][0] < q * total:
            run += pairs[i][0]
            i += 1
        out[q] = round(pairs[min(i, len(pairs) - 1)][1], 1) if pairs else None
    return out


def count_only(runs, index):
    """Genuine, wrong, gap sample totals of the given runs (no anatomy)."""
    g = w = a = 0
    for pitch, ivs in runs.items():
        pit = index.pitch_iv.get(pitch, [])
        for left, right in ivs:
            ann = index.overlap(index.any_iv, left, right)
            gen = index.overlap(pit, left, right)
            g += gen
            w += ann - gen
            a += (right - left) - ann
    return g, w, a


def load_trace_rows(path, expected_raw):
    """Per decision tick: (sample, quiet, [(note, feats)]) for candidates passing the frozen base confirmation."""
    ticks = []
    seen = 0
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        reader = csv.DictReader(stream, delimiter='\t')
        for row in reader:
            sample, quiet = int(row['sample']), int(row['quiet'])
            cands = _candidates({'candidate_text': row['candidates']})
            rows = []
            if not quiet:
                for note, cand in cands.items():
                    if selector_confirmation(cand):
                        vec = [cand[f] for f in FEATS if f != 'cal_margin']
                        vec.append(cand['best_cal'] - cand['second_cal'])
                        rows.append((note, vec))
            ticks.append((sample, rows))
            seen += len(rows)
    return ticks, seen


def variant_spans(ticks, passes, horizon):
    obs = []
    for sample, rows in ticks:
        obs.append((sample, {note for note, vec in rows if passes(vec)}))
    spans, _ = confirmation_spans(obs, sample_count=horizon)
    return spans


def decile_cuts(ticks):
    cols = {f: [] for f in FEATS}
    for _, rows in ticks:
        for _, vec in rows:
            for i, f in enumerate(FEATS):
                cols[f].append(vec[i])
    cuts = {}
    for f, values in cols.items():
        values.sort()
        picks = sorted({values[int(len(values) * q / 10)] for q in range(1, 10)})
        cuts[f] = picks
    return cuts


def run():
    base = json.load(open(BASELINE))['datasets']['ordinary']
    rep = json.load(open(os.path.join(CONSENSUS, 'report.json')))
    ds = rep['datasets']['ordinary']
    horizon = ds['common_support']['sample_count']
    rate = ds['common_support']['sample_rate']
    clock = dict(sample_count=horizon, sample_rate=rate)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    index = LabelIndex(labels)
    saved = json.load(gzip.open(os.path.join(CONSENSUS, 'ordinary-consensus-spans.json.gz'), 'rt'))
    evidence = json.load(gzip.open(os.path.join(REPO, EVIDENCE_DIR, 'ordinary-bridge-events.json.gz'), 'rt'))
    neural = evidence['arm_spans']['A']
    result = dict(horizon=horizon)

    # M0: rebuild the frozen additions from trace + A and compare to the saved ones
    pin = TRACE_PINS['ordinary']
    ticks, confirmed_rows = load_trace_rows(os.path.join(REPO, pin['path']), pin['raw_sha256'])
    result['trace_ticks'], result['confirmed_candidate_rows'] = len(ticks), confirmed_rows
    base_obs_spans = variant_spans(ticks, lambda vec: True, horizon)
    additions = intersect_spans(neural, base_obs_spans, sample_count=horizon)
    result['rebuild_matches_saved_additions'] = [tuple(x) for x in additions] == [tuple(x) for x in saved['confirmed_neural']]
    result['rebuild_matches_saved_confirmation'] = [tuple(x) for x in base_obs_spans] == [tuple(x) for x in saved['native_confirmation']]
    cur_by = by_pitch(cur_spans)
    add_by = by_pitch(additions)
    new_by = {p: subtract_pitch(add_by[p], cur_by.get(p, [])) for p in add_by}
    new_by = {p: v for p, v in new_by.items() if v}
    result['added_runs'] = sum(len(v) for v in new_by.values())
    result['added_samples'] = sum(r - l for v in new_by.values() for l, r in v)

    # X0 and anatomy
    acc = decompose(new_by, index, horizon)
    comp = ds['comparison']['sample_deltas']
    result['x0'] = dict(
        genuine=acc['genuine'], wrong=acc['wrong'], gap=acc['gap'],
        report_present_delta=comp['present_pitch_samples'],
        report_wrong_delta=ds['hybrid']['pitch_sets']['totals']['extra_pitch_voice_samples'] - ds['current']['pitch_sets']['totals']['extra_pitch_voice_samples'],
        report_gap_delta=ds['hybrid']['pitch_sets']['unlabeled_gap_voice_samples'] - ds['current']['pitch_sets']['unlabeled_gap_voice_samples'])
    false_total = acc['wrong'] + acc['gap']
    result['false_total'] = false_total
    result['false_share_of_added'] = round(false_total / (acc['genuine'] + false_total), 4)
    result['gap_kind'] = dict(acc['gap_kind'])
    result['gap_kind_share'] = {k: round(v / acc['gap'], 3) for k, v in acc['gap_kind'].items()}
    result['tail_ms_quantiles'] = weighted_quantiles(acc['tail_ms'], [0.1, 0.5, 0.9])
    result['wrong_rel'] = dict(acc['wrong_rel'])
    result['wrong_rel_share'] = {k: round(v / acc['wrong'], 3) for k, v in acc['wrong_rel'].items()}
    result['octave_share_of_wrong'] = round((acc['wrong_rel'].get('octave_up', 0) + acc['wrong_rel'].get('octave_down', 0)) / acc['wrong'], 3)
    runs_sorted = sorted(acc['runs'], key=lambda r: -r['false'])
    result['top20_false_run_share'] = round(sum(r['false'] for r in runs_sorted[:20]) / false_total, 3)
    result['top5_false_runs'] = [dict(pitch=r['pitch'], ms=round((r['right'] - r['left']) / 96, 1), false=r['false'], genuine=r['genuine'])
                                  for r in runs_sorted[:5]]
    result['by_band'] = {k: dict(genuine=v[0], false=v[1], false_share=round(v[1] / (v[0] + v[1]), 4) if v[0] + v[1] else None)
                         for k, v in sorted(acc['band'].items(), key=lambda kv: kv[0])}
    result['halves'] = dict(genuine=acc['genuine_h'], false=acc['false_h'])
    fr = [r for r in acc['runs'] if r['false'] > (r['genuine'])]
    gr = [r for r in acc['runs'] if r['false'] <= r['genuine']]
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
    result['run_length_ms'] = dict(
        false_majority_runs=len(fr), genuine_majority_runs=len(gr),
        median_false_majority=round(med([(r['right'] - r['left']) / 96 for r in fr]), 1) if fr else None,
        median_genuine_majority=round(med([(r['right'] - r['left']) / 96 for r in gr]), 1) if gr else None)

    # Frontier: feature gates and onset delays, as removals from the base additions
    base_g, base_f = acc['genuine'], false_total
    cuts = decile_cuts(ticks)
    variants = []

    def evaluate(desc, adds):
        new = {p: subtract_pitch(adds[p], cur_by.get(p, [])) for p in adds}
        new = {p: v for p, v in new.items() if v}
        g, w, a = count_only(new, index)
        rg, rf = base_g - g, base_f - (w + a)
        variants.append(dict(desc=desc, genuine=g, wrong=w, gap=a, false=w + a,
                             genuine_removed=rg, false_removed=rf,
                             false_removed_share=round(rf / base_f, 4),
                             genuine_kept_share=round(g / base_g, 4),
                             ratio=round(rf / rg, 3) if rg > 0 else None))

    for f_i, f in enumerate(FEATS):
        for cut in cuts[f]:
            for direction in ('ge', 'le'):
                passes = (lambda v, i=f_i, c=cut: v[i] >= c) if direction == 'ge' else (lambda v, i=f_i, c=cut: v[i] <= c)
                spans = variant_spans(ticks, passes, horizon)
                adds = by_pitch(intersect_spans(neural, spans, sample_count=horizon))
                evaluate(f'{f} {">=" if direction == "ge" else "<="} {round(cut, 6)}', adds)
    for t_ms in DELAYS_MS:
        shift = int(round(t_ms * 96))
        delayed = {p: [(l + shift, r) for l, r in v if r - l > shift] for p, v in new_by.items()}
        delayed = {p: v for p, v in delayed.items() if v}
        g, w, a = count_only(delayed, index)
        rg, rf = base_g - g, base_f - (w + a)
        variants.append(dict(desc=f'onset delay {t_ms} ms', genuine=g, wrong=w, gap=a, false=w + a, genuine_removed=rg,
                             false_removed=rf, false_removed_share=round(rf / base_f, 4), genuine_kept_share=round(g / base_g, 4),
                             ratio=round(rf / rg, 3) if rg > 0 else None))
    result['variant_count'] = len(variants)
    gates = [v for v in variants if not v['desc'].startswith('onset delay')]
    delays = [v for v in variants if v['desc'].startswith('onset delay')]
    quarter = [v for v in gates if v['false_removed_share'] >= 0.25 and v['genuine_removed'] > 0]
    best_ratio = max(quarter, key=lambda v: v['ratio'])['ratio'] if quarter else None
    result['x5_gates_removing_quarter_false'] = len(quarter)
    result['x5_best_ratio_among_them'] = best_ratio
    result['x5_best_quarter_gate'] = max(quarter, key=lambda v: v['ratio']) if quarter else None
    result['delays'] = delays
    keepers = [v for v in variants if v['genuine_kept_share'] >= 0.75]
    result['x7_min_false_with_75pct_genuine'] = min(keepers, key=lambda v: v['false']) if keepers else None
    best_any = [v for v in gates if v['genuine_removed'] > 0 and v['false_removed'] > 0]
    result['top_by_ratio_with_false_removed_ge_10pct'] = sorted(
        [v for v in best_any if v['false_removed_share'] >= 0.10], key=lambda v: -v['ratio'])[:12]
    result['top_by_false_removed_with_ratio_ge_1'] = sorted(
        [v for v in best_any if (v['ratio'] or 0) >= 1.0], key=lambda v: -v['false_removed'])[:12]
    result['gate_variants_total'] = len(gates)
    result['gate_variants_ratio_ge_1'] = sum(1 for v in gates if v['ratio'] and v['ratio'] >= 1.0)

    # precision / recall of the arms (pitch-sample units, arithmetic from saved compact reports)
    split = json.load(open(os.path.join(REPO, 'build/github-results/basic-pitch-cached-44891340815/claude-pitch-split/report.json')))
    comp_split = split['datasets']['ordinary']['compact']
    table = {}
    for name, row in comp_split.items():
        total = row['present'] + row['wrong_pitch'] + row['gap']
        table[name] = dict(recall_pct=row['coverage_percent'], precision_pct=round(100 * row['present'] / total, 2),
                           false=row['wrong_pitch'] + row['gap'])
    c = ds['compact']['hybrid']
    total_c = c['present_pitch_samples'] + c['wrong_pitch_samples'] + c['gap_extra_pitch_samples']
    table['consensus_hybrid'] = dict(recall_pct=round(c['present_percent'], 4),
                                     precision_pct=round(100 * c['present_pitch_samples'] / total_c, 2),
                                     false=c['wrong_pitch_samples'] + c['gap_extra_pitch_samples'])
    result['precision_recall'] = table

    # exact-set and all-expected deltas of the base hybrid, from the frozen comparison
    result['base_hybrid_clauses'] = dict(
        sample_deltas=comp, no_pitch_safety_regression=ds['comparison']['no_pitch_safety_regression'],
        labels_lost=sum(1 for r in ds['comparison']['label_deltas'] if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0))
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run()
    keys = ['rebuild_matches_saved_additions', 'rebuild_matches_saved_confirmation', 'added_runs', 'added_samples', 'x0', 'false_total',
            'false_share_of_added', 'gap_kind_share', 'tail_ms_quantiles', 'wrong_rel_share', 'octave_share_of_wrong',
            'top20_false_run_share', 'by_band', 'halves', 'run_length_ms', 'x5_gates_removing_quarter_false',
            'x5_best_ratio_among_them', 'x7_min_false_with_75pct_genuine', 'variant_count', 'gate_variants_ratio_ge_1',
            'gate_variants_total', 'precision_recall']
    print(json.dumps({k: out[k] for k in keys}, indent=1))
