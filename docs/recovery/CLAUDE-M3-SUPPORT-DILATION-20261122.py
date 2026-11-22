"""Where does the support filter lose labels, and does a causal forward hold of the support repair it?  Saved data only.

No audio, model run, job or native edit; nothing promoted.  CLAUDE-M3-SUPPORT-FILTER-20261122 scored CURRENT intersect support on the
ordinary corpus: with support = Basic Pitch arm A union the native confirmation, it removes 75.8% of CURRENT's wrong-pitch and 35.6% of its
gap voice-samples (7,204,186 false pitch-samples) for 6.0% of its genuine presence (809,253 pitch-samples), raises precision from 54.2% to
75.06%, but 106 labels lose presence or longest hold (worst loss 44,249 pitch-samples).  Adding the native >= 60 lane gives coverage 42.89%,
precision 76.81%, false 4,378,870 (-62%), exact-set +283,679, all-expected +333,214, still 106 labels losing.  Intersection is the causal
model of a confirm-before-emit gate (a note starts when the support arrives and ends when either side ends).  This script asks (1) where
in the label the removed CURRENT samples fall (offset from label start), (2) whether holding the support forward by D ms after it ends
(a causal dilation; never backward) lowers the label losses, and what it costs in precision and wrong-pitch removal, and (3) how many output
runs (note events) each filter makes, because intersection can fragment holds.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the five support-filter results above.  NOT seen: any removal location, any dilation result, any run count, any native-only
or A-only support at D > 0.  Predictions, each can fail:
  P0  identity: A-union-native at D = 0 reproduces the support-filter numbers (present delta -809,253, wrong delta -5,916,050).
  P1  for support = A union native, labels losing present or longest hold fall monotonically (non-increasing) as D grows over 0, 50, 100,
      220, 500 ms.
  P2  whole-hybrid precision falls monotonically (non-increasing) as D grows.
  P3  at D = 220 ms the label losses are at most half of the D = 0 count (at most 53).
  P4  at D = 220 ms the wrong-pitch removal share is still at least 60%.
  P5  at D = 0, at least half of the removed CURRENT own-pitch samples inside label windows fall in the first 220 ms of the label.
  P6  CURRENT intersect native confirmation alone (D = 0) loses more than 150 labels' presence or longest hold (the native confirmation
      has no coasting and expires one callback later).
  P7  the filtered output has more runs (note events) than CURRENT at D = 0 by more than 20%.
  P8  no variant at D <= 220 ms reaches zero label losses.
Report everything whatever it shows.  One recording, one corpus, in-sample; arm A is an offline causal run with measured FIFO timestamps;
the native confirmation is read from a saved trace; no lane, unison, string, callback or live-host claim; a built gate would also add
model latency and compute cost that these saved spans do not include beyond the measured timestamps; not a built output.

Usage: python3 -P -E CLAUDE-M3-SUPPORT-DILATION-20261122.py
"""
import gzip
import importlib.util
import json
import os
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


uf = load('uf', 'CLAUDE-M3-UNION-FRONTIER-20261122.py')
ce = uf.ce
OUT = os.path.join(HERE, 'CLAUDE-M3-SUPPORT-DILATION-20261122.json')
DELAYS_MS = [0, 50, 100, 220, 500]
BUCKETS_MS = [50, 100, 220, 500]


def dilate(spans, extra, horizon):
    return union_spans([(l, min(r + extra, horizon), p) for l, r, p in spans], sample_count=horizon)


def clip(ivs, lo, hi):
    return [(max(a, lo), min(b, hi)) for a, b in ivs if b > lo and a < hi]


def bucketize(removed, start, rate):
    edges = [start + int(ms * rate / 1000) for ms in BUCKETS_MS]
    out = [0] * (len(edges) + 1)
    for a, b in removed:
        for i in range(len(out)):
            lo = start if i == 0 else edges[i - 1]
            hi = edges[i] if i < len(edges) else 10 ** 15
            seg = min(b, hi) - max(a, lo)
            if seg > 0:
                out[i] += seg
    return out


def run():
    base = json.load(open(ce.BASELINE))['datasets']['ordinary']
    rep = json.load(open(os.path.join(ce.CONSENSUS, 'report.json')))['datasets']['ordinary']
    horizon = rep['common_support']['sample_count']
    rate = rep['common_support']['sample_rate']
    clock = dict(sample_count=horizon, sample_rate=rate)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    cur_by = ce.by_pitch(cur_spans)
    current = score(cur_spans, labels, **clock)
    if json.loads(json.dumps(current)) != rep['current']:
        raise SystemExit('CURRENT identity failed')
    evidence = json.load(gzip.open(os.path.join(REPO, EVIDENCE_DIR, 'ordinary-bridge-events.json.gz'), 'rt'))
    arm_a = evidence['arm_spans']['A']
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, 'ordinary-consensus-spans.json.gz'), 'rt'))
    native = [tuple(x) for x in saved['native_confirmation']]
    native60 = [s for s in native if s[2] >= 60]
    ct, cg = current['pitch_sets']['totals'], current['pitch_sets']['unlabeled_gap_voice_samples']
    cur_false = ct['extra_pitch_voice_samples'] + cg
    cur_runs = len(union_spans(cur_spans, sample_count=horizon))
    result = dict(horizon=horizon, current=dict(present=ct['present_pitch_samples'], wrong=ct['extra_pitch_voice_samples'], gap=cg,
                                                 false=cur_false, runs=cur_runs), variants={}, location={})

    def evaluate(name, spans, location=False):
        spans = union_spans(spans, sample_count=horizon)
        hybrid = score(spans, labels, **clock)
        cmp = compare(current, hybrid)
        t = hybrid['pitch_sets']['totals']
        gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
        false = t['extra_pitch_voice_samples'] + gap
        losing = [r for r in cmp['label_deltas'] if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0]
        result['variants'][name] = dict(
            coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
            precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
            present_delta=t['present_pitch_samples'] - ct['present_pitch_samples'],
            present_removed_share=round(max(0, ct['present_pitch_samples'] - t['present_pitch_samples']) / ct['present_pitch_samples'], 4),
            wrong_delta=t['extra_pitch_voice_samples'] - ct['extra_pitch_voice_samples'],
            wrong_removed_share=round(max(0, ct['extra_pitch_voice_samples'] - t['extra_pitch_voice_samples']) / ct['extra_pitch_voice_samples'], 4),
            gap_delta=gap - cg, gap_removed_share=round(max(0, cg - gap) / cg, 4),
            false_total=false, false_change_pct_of_current=round(100 * (false - cur_false) / cur_false, 2),
            exact_set_delta=t['exact_pitch_set_samples'] - ct['exact_pitch_set_samples'],
            all_expected_delta=t['all_expected_pitches_samples'] - ct['all_expected_pitches_samples'],
            labels_losing_present_or_longest=len(losing),
            labels_losing_present=sum(1 for r in losing if r['present_samples_delta'] < 0),
            labels_losing_longest=sum(1 for r in losing if r['longest_present_samples_delta'] < 0),
            worst_present_loss_samples=min([r['present_samples_delta'] for r in losing] + [0]),
            runs=len(spans), runs_vs_current_pct=round(100 * (len(spans) - cur_runs) / cur_runs, 2),
            no_pitch_safety_regression=cmp['no_pitch_safety_regression'])
        if location:
            filt_by = ce.by_pitch(spans)
            lose_ids = {r['label_index'] for r in losing}
            all_b, lose_b = [0] * (len(BUCKETS_MS) + 1), [0] * (len(BUCKETS_MS) + 1)
            for lab in labels:
                p, lo, hi = lab['midi_note'], lab['start_sample'], lab['end_sample']
                removed = ce.subtract_pitch(clip(cur_by.get(p, []), lo, hi), clip(filt_by.get(p, []), lo, hi))
                b = bucketize(removed, lo, rate)
                for i, v in enumerate(b):
                    all_b[i] += v
                    if lab['label_index'] in lose_ids:
                        lose_b[i] += v
            labels_names = [f'0-{BUCKETS_MS[0]}ms'] + [f'{BUCKETS_MS[i - 1]}-{BUCKETS_MS[i]}ms' for i in range(1, len(BUCKETS_MS))] + [f'>{BUCKETS_MS[-1]}ms']
            tot, totl = sum(all_b) or 1, sum(lose_b) or 1
            result['location'][name] = dict(
                removed_in_label_windows=sum(all_b), by_offset=dict(zip(labels_names, all_b)),
                share_by_offset={k: round(v / tot, 4) for k, v in zip(labels_names, all_b)},
                removed_in_losing_labels=sum(lose_b), losing_labels_share_by_offset={k: round(v / totl, 4) for k, v in zip(labels_names, lose_b)})

    support_an = union_spans([*arm_a, *native], sample_count=horizon)
    for d in DELAYS_MS:
        extra = int(d * rate / 1000)
        sup = dilate(support_an, extra, horizon) if d else support_an
        filt = intersect_spans(cur_spans, sup, sample_count=horizon)
        evaluate(f'CURRENT intersect (A union native) hold {d} ms', filt, location=d in (0, 220))
        evaluate(f'  plus native >= 60 lane, hold {d} ms', [*filt, *native60])
    for label, src in (('native alone', native), ('A alone', arm_a)):
        for d in (0, 220):
            extra = int(d * rate / 1000)
            sup = dilate(union_spans(src, sample_count=horizon), extra, horizon) if d else union_spans(src, sample_count=horizon)
            evaluate(f'CURRENT intersect ({label}) hold {d} ms', intersect_spans(cur_spans, sup, sample_count=horizon))
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run()
    print('current', json.dumps(out['current']))
    for name, row in out['variants'].items():
        print(name, json.dumps(row))
    for name, loc in out['location'].items():
        print('LOC', name, json.dumps(loc))
