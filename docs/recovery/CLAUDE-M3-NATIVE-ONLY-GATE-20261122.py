"""Does a gate built from the native confirmation alone (no Basic Pitch model in the loop) reach the filter's aggregate result?  Saved data only.

No audio, model run, job or native edit; nothing promoted.  CLAUDE-M3-SUPPORT-DILATION-20261122 found that CURRENT intersect
(arm A union native), the support held forward 220 ms, plus the native >= 60 lane has coverage 45.22%, precision 61.53%, wrong-pitch
-1,687,401, gap -180,705, exact-set +256,962, all-expected +385,158 and 6 labels losing presence (3 also longest hold).  Arm A is the
model.  The native confirmation (`not quiet and selector_pool_member == 1 and direct == 1`) and the >= 60 lane both come from the
native selector's own trace, so a gate on the native confirmation alone plus the native lane would need no model.  The dilation run
scored native alone at D = 0 and 220 but only as a filter, never with the lane.  This script scores native-only support at
D in {50, 100, 220, 500} ms, with the native >= 60 lane, and also the rescue lane at c = 1.0 and 0.5 (rescue spans are not in the
saved file, so only the saved native >= 60 lane is used here).

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: native alone as a filter at D = 0 (precision 82.28%, 130 labels losing, runs +310%) and D = 220 (coverage 39.7726%,
precision 60.22%, wrong -2,186,897, gap -357,368, 9 labels losing, worst -44,928, exact-set 0, runs -13.07%), and the lane alone
(+1,789,705 genuine, +42,493 wrong, +110,769 gap).  NOT seen: any native-only support plus the lane, or native-only at D = 50, 100, 500.
Predictions, each can fail:
  N0  identity: native-only at D = 220 without the lane reproduces the dilation numbers (present delta -74,605, wrong -2,186,897).
  N1  native-only support plus the lane at D = 220 has wrong-pitch delta <= 0 and gap delta <= 0.
  N2  its coverage is above 44.5%.
  N3  its precision is above 60%.
  N4  its exact-set delta is above +200,000.
  N5  at D = 220 it has between 5 and 9 labels losing presence or longest hold (the lane cannot restore a loss below MIDI 60).
  N6  label losses are non-increasing as D grows over 50, 100, 220, 500.
  N7  at D = 500 the wrong-pitch delta is still <= 0 with the lane.
Report everything whatever it shows.  One recording, one corpus, in-sample; the native confirmation is read from a saved trace; no
lane, unison, string, callback or live-host claim; no native implementation of a gate exists and a real one would change which spans
appear; not a built output.

Usage: python3 -P -E CLAUDE-M3-NATIVE-ONLY-GATE-20261122.py
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
from tools.native_neural_consensus import intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dil = load('dil', 'CLAUDE-M3-SUPPORT-DILATION-20261122.py')
ce = dil.ce
OUT = os.path.join(HERE, 'CLAUDE-M3-NATIVE-ONLY-GATE-20261122.json')
DELAYS_MS = [50, 100, 220, 500]


def run():
    base = json.load(open(ce.BASELINE))['datasets']['ordinary']
    rep = json.load(open(os.path.join(ce.CONSENSUS, 'report.json')))['datasets']['ordinary']
    horizon = rep['common_support']['sample_count']
    rate = rep['common_support']['sample_rate']
    clock = dict(sample_count=horizon, sample_rate=rate)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    current = score(cur_spans, labels, **clock)
    if json.loads(json.dumps(current)) != rep['current']:
        raise SystemExit('CURRENT identity failed')
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, 'ordinary-consensus-spans.json.gz'), 'rt'))
    native = [tuple(x) for x in saved['native_confirmation']]
    native60 = [s for s in native if s[2] >= 60]
    support = union_spans(native, sample_count=horizon)
    ct, cg = current['pitch_sets']['totals'], current['pitch_sets']['unlabeled_gap_voice_samples']
    cur_false = ct['extra_pitch_voice_samples'] + cg
    result = dict(horizon=horizon, variants={})

    def evaluate(name, spans):
        spans = union_spans(spans, sample_count=horizon)
        hybrid = score(spans, labels, **clock)
        cmp = compare(current, hybrid)
        t = hybrid['pitch_sets']['totals']
        gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
        false = t['extra_pitch_voice_samples'] + gap
        losing = [r for r in cmp['label_deltas'] if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0]
        lost = sum(-r['present_samples_delta'] for r in losing if r['present_samples_delta'] < 0)
        frac = sorted((-r['present_samples_delta'] / r['current_present_samples'] for r in losing
                       if r['present_samples_delta'] < 0 and r['current_present_samples']), reverse=True)
        result['variants'][name] = dict(
            coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
            precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
            present_delta=t['present_pitch_samples'] - ct['present_pitch_samples'],
            wrong_delta=t['extra_pitch_voice_samples'] - ct['extra_pitch_voice_samples'], gap_delta=gap - cg,
            false_total=false, false_change_pct_of_current=round(100 * (false - cur_false) / cur_false, 2),
            exact_set_delta=t['exact_pitch_set_samples'] - ct['exact_pitch_set_samples'],
            all_expected_delta=t['all_expected_pitches_samples'] - ct['all_expected_pitches_samples'],
            labels_losing_present_or_longest=len(losing),
            labels_losing_present=sum(1 for r in losing if r['present_samples_delta'] < 0),
            labels_losing_longest=sum(1 for r in losing if r['longest_present_samples_delta'] < 0),
            lost_pitch_samples=lost, lost_share_of_current_present=round(lost / ct['present_pitch_samples'], 4),
            worst_present_loss_samples=min([r['present_samples_delta'] for r in losing] + [0]),
            worst_loss_fraction=round(frac[0], 4) if frac else 0.0,
            losers_above_5pct=sum(1 for f in frac if f > 0.05), losers_above_10pct=sum(1 for f in frac if f > 0.10),
            runs=len(spans), runs_vs_current_pct=round(100 * (len(spans) - len(union_spans(cur_spans, sample_count=horizon)))
                                                      / len(union_spans(cur_spans, sample_count=horizon)), 2),
            no_pitch_safety_regression=cmp['no_pitch_safety_regression'])

    for d in DELAYS_MS:
        sup = dil.dilate(support, int(d * rate / 1000), horizon)
        filt = intersect_spans(cur_spans, sup, sample_count=horizon)
        evaluate(f'native-only support, hold {d} ms', filt)
        evaluate(f'native-only support, hold {d} ms, plus native >= 60 lane', [*filt, *native60])
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run()
    for name, row in out['variants'].items():
        print(name, json.dumps(row))
