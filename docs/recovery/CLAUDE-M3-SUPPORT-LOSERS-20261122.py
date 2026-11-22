"""Which labels does the support filter still lose, and how large is each loss?  Saved data only.

No audio, model run, job or native edit; nothing promoted.  CLAUDE-M3-SUPPORT-DILATION-20261122 found that CURRENT intersect
(arm A union the native confirmation), with the support held forward D ms, still has labels that lose presence or longest hold
(106 at D = 0, 28 at 50, 17 at 100, 6 at 220, 5 at 500), and that the removed samples are not concentrated at note onsets at
D = 0 (about 20% in the first 100 ms) but are 36.8% in the first 50 ms at D = 220.  The strict gate counts any label with any
negative present or longest-hold delta, however small.  A confirm-before-emit gate necessarily starts a note when its support
starts, so a label whose support lags CURRENT's first sample loses at least that lag.  This script asks (1) how large each label's
loss is, as milliseconds and as a share of CURRENT's own present time in that label, at each hold, so a per-label tolerance could
be read off; (2) who the labels that still lose at D = 220 and 500 are (pitch, length, where the loss falls, how much of the
label the support covers); (3) whether the losers at 500 are a subset of those at 220.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the dilation counts above and the offset buckets.  NOT seen: any per-label loss size, any loser's identity.
Predictions, each can fail:
  L0  identity: the loser counts reproduce the dilation run (106, 28, 17, 6, 5 at D = 0, 50, 100, 220, 500).
  L1  at D = 220 every losing label loses under 10% of CURRENT's own present time in that label.
  L2  at D = 220 the median loser loses under 50 ms (4,800 pitch-samples).
  L3  at D = 0 at least half of the 106 losers lose under 5% of CURRENT's present time in the label.
  L4  the losers at D = 500 are a subset of the losers at D = 220.
  L5  at D = 220 at least half of the lost samples fall in a label's first 50 ms (confirm delay rather than a mid-note dropout).
  L6  at D = 220 at least four of the six losers are below MIDI 60.
Report everything whatever it shows.  One recording, one corpus, in-sample; arm A is an offline causal run with measured FIFO
timestamps; the native confirmation is read from a saved trace; no lane, unison, string, callback or live-host claim; not a built
output.

Usage: python3 -P -E CLAUDE-M3-SUPPORT-LOSERS-20261122.py
"""
import gzip
import importlib.util
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.native_neural_consensus import EVIDENCE_DIR, intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dil = load('dil', 'CLAUDE-M3-SUPPORT-DILATION-20261122.py')
ce = dil.ce
OUT = os.path.join(HERE, 'CLAUDE-M3-SUPPORT-LOSERS-20261122.json')
DELAYS_MS = [0, 50, 100, 220, 500]
FRACTION_EDGES = [0.01, 0.05, 0.10, 0.25, 0.50]


def run():
    base = json.load(open(ce.BASELINE))['datasets']['ordinary']
    rep = json.load(open(os.path.join(ce.CONSENSUS, 'report.json')))['datasets']['ordinary']
    horizon = rep['common_support']['sample_count']
    rate = rep['common_support']['sample_rate']
    clock = dict(sample_count=horizon, sample_rate=rate)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    by_label = {lab['label_index']: lab for lab in labels}
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    cur_by = ce.by_pitch(cur_spans)
    current = score(cur_spans, labels, **clock)
    if json.loads(json.dumps(current)) != rep['current']:
        raise SystemExit('CURRENT identity failed')
    evidence = json.load(gzip.open(os.path.join(REPO, EVIDENCE_DIR, 'ordinary-bridge-events.json.gz'), 'rt'))
    arm_a = evidence['arm_spans']['A']
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, 'ordinary-consensus-spans.json.gz'), 'rt'))
    native = [tuple(x) for x in saved['native_confirmation']]
    support = union_spans([*arm_a, *native], sample_count=horizon)
    result = dict(horizon=horizon, rate=rate, by_delay={}, losers={})
    losers_by_d = {}
    for d in DELAYS_MS:
        extra = int(d * rate / 1000)
        sup = dil.dilate(support, extra, horizon) if d else support
        filt = intersect_spans(cur_spans, sup, sample_count=horizon)
        hybrid = score(union_spans(filt, sample_count=horizon), labels, **clock)
        cmp = compare(current, hybrid)
        rows = [r for r in cmp['label_deltas'] if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0]
        losers_by_d[d] = {r['label_index'] for r in rows}
        loss_ms, loss_frac = [], []
        for r in rows:
            cur_p = r['current_present_samples']
            loss_ms.append(round(-r['present_samples_delta'] * 1000 / rate, 2))
            loss_frac.append(-r['present_samples_delta'] / cur_p if cur_p else 0.0)
        bins = {f'>{int(e * 100)}%': sum(1 for f in loss_frac if f > e) for e in FRACTION_EDGES}
        total_lost = sum(-r['present_samples_delta'] for r in rows if r['present_samples_delta'] < 0)
        result['by_delay'][str(d)] = dict(
            losers=len(rows), losers_present=sum(1 for r in rows if r['present_samples_delta'] < 0),
            losers_longest=sum(1 for r in rows if r['longest_present_samples_delta'] < 0),
            total_lost_pitch_samples=total_lost,
            lost_share_of_current_present=round(total_lost / current['pitch_sets']['totals']['present_pitch_samples'], 4),
            median_loss_ms=round(statistics.median(loss_ms), 2) if loss_ms else 0.0,
            max_loss_ms=max(loss_ms) if loss_ms else 0.0,
            median_loss_fraction=round(statistics.median(loss_frac), 4) if loss_frac else 0.0,
            max_loss_fraction=round(max(loss_frac), 4) if loss_frac else 0.0,
            losers_above_fraction=bins)
        if d in (220, 500):
            filt_by = ce.by_pitch(union_spans(filt, sample_count=horizon))
            sup_by = ce.by_pitch(sup)
            out = []
            for r in sorted(rows, key=lambda x: x['present_samples_delta']):
                lab = by_label[r['label_index']]
                p, lo, hi = lab['midi_note'], lab['start_sample'], lab['end_sample']
                removed = ce.subtract_pitch(dil.clip(cur_by.get(p, []), lo, hi), dil.clip(filt_by.get(p, []), lo, hi))
                b = dil.bucketize(removed, lo, rate)
                cur_in = sum(e - s for s, e in dil.clip(cur_by.get(p, []), lo, hi))
                sup_in = sum(e - s for s, e in dil.clip(sup_by.get(p, []), lo, hi))
                a_in = sum(e - s for s, e in dil.clip(ce.by_pitch(arm_a).get(p, []), lo, hi))
                n_in = sum(e - s for s, e in dil.clip(ce.by_pitch(native).get(p, []), lo, hi))
                out.append(dict(label_index=r['label_index'], midi_note=p, label_ms=round((hi - lo) * 1000 / rate, 1),
                                current_present_ms=round(r['current_present_samples'] * 1000 / rate, 1),
                                present_delta_ms=round(r['present_samples_delta'] * 1000 / rate, 2),
                                longest_delta_ms=round(r['longest_present_samples_delta'] * 1000 / rate, 2),
                                loss_fraction=round(-r['present_samples_delta'] / r['current_present_samples'], 4) if r['current_present_samples'] else None,
                                removed_by_offset_ms_buckets=dict(zip(['0-50', '50-100', '100-220', '220-500', '>500'], b)),
                                current_in_label_ms=round(cur_in * 1000 / rate, 1),
                                arm_a_in_label_ms=round(a_in * 1000 / rate, 1), native_in_label_ms=round(n_in * 1000 / rate, 1),
                                held_support_in_label_ms=round(sup_in * 1000 / rate, 1)))
            result['losers'][str(d)] = out
    first50 = {}
    for d in ('220', '500'):
        tot = sum(sum(x['removed_by_offset_ms_buckets'].values()) for x in result['losers'][d]) or 1
        first50[d] = round(sum(x['removed_by_offset_ms_buckets']['0-50'] for x in result['losers'][d]) / tot, 4)
    result['first_50ms_share_of_loser_loss'] = first50
    result['subset_500_in_220'] = losers_by_d[500] <= losers_by_d[220]
    result['below_60_at_220'] = sum(1 for x in result['losers']['220'] if x['midi_note'] < 60)
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run()
    for d, row in out['by_delay'].items():
        print('D', d, json.dumps(row))
    print('first_50ms_share_of_loser_loss', json.dumps(out['first_50ms_share_of_loser_loss']),
          'subset_500_in_220', out['subset_500_in_220'], 'below_60_at_220', out['below_60_at_220'])
    for d, rows in out['losers'].items():
        for x in rows:
            print('LOSER D', d, json.dumps(x))
