"""Does the support filter plus a rescue lane add coverage without losing the filter's precision?  Saved data only.

No audio, model run, job or native edit; nothing promoted.  Two saved results are being combined for the first time.
(1) CLAUDE-M3-SUPPORT-DILATION-20261122 (ordinary): CURRENT intersect (arm A union native confirmation), support held forward D ms, plus the
native confirmation at pitch >= 60, at D = 220 has coverage 45.215%, precision 61.53%, wrong -1,687,401, gap -180,705, exact-set +256,962,
6 labels losing; at D = 50 coverage 44.878%, precision 69.65%, 28 labels losing.
(2) CLAUDE-M3-NATIVE-RESCUE-FRONTIER-20261122 (ordinary): CURRENT union a rescue lane at pitch >= 60 (native confirmation, plus non-quiet
candidates with selection in {1, 2, 3} and score_ratio >= c, projected one block per completed 512-sample callback) loses no label and gives
coverage 45.285 / 46.206 / 47.255 / 49.562 / 53.471% for c = inf / 1.0 / 0.8 / 0.5 / 0.25, precision 56.94 ... 57.69%, false +7.9 ... +28.7%.
The rescue lane was scored on top of unfiltered CURRENT only.  This script scores it on top of the filtered output, and also a SUPPORTED rescue
lane: the rescue spans intersected with arm A held forward D ms (a rescue candidate is emitted only where the model also reports the pitch),
so the rescue is the native confirmation union (rescue candidates that arm A also supports).  Arm A is the Basic Pitch model's offline causal
run with measured FIFO timestamps; held support is causal (extends forward only).

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the two result sets above.  NOT seen: any filtered output combined with a rescue span, or any rescue span intersected with arm A.
Grid fixed before the run, not tuned: D in {50, 220} ms, c in {inf, 1.0, 0.5, 0.25}.  Predictions, each can fail:
  C0  identity: the c = inf lane reproduces the saved native confirmation at pitch >= 60, and the filter at D = 220 plus that lane reproduces
      the dilation run (coverage 45.215%, wrong delta -1,687,401, 6 labels losing).
  C1  filter (D = 220) plus the unsupported rescue lane at c = 0.5 has coverage above 48.0%.
  C2  filter (D = 220) plus the unsupported rescue lane at c = 0.25 has precision above 55% and wrong-pitch delta <= 0 and gap delta <= 0.
  C3  filter (D = 220) plus the unsupported rescue lane at c = 0.25 has exact-set delta above +256,962 (the lane-free native filter's).
  C4  at D = 220 the number of labels losing present or longest hold falls below 6 once the rescue lane is added (a lane can restore a
      pitch >= 60 loser; label 42 at pitch 60 loses 3.3 ms).
  C5  the supported rescue lane at c = 0.25, D = 220 has a lower false-per-added-genuine than the unsupported lane at c = 0.25, D = 220
      (compared as marginal over the same filter without any lane).
  C6  the supported rescue lane at c = 0.25, D = 220 reaches coverage of at least 47.0%.
  C7  the supported rescue lane at c = 0.25, D = 220 has precision above the unsupported lane's at the same c and D.
  C8  at D = 50 the label losses (28 with the native lane) are not reduced below 20 by any rescue lane (the lane cannot restore pitches < 60
      and the losses are mostly confirm-delay at onsets).
Report everything whatever it shows.  One recording, one corpus, in-sample for design (the grid was fixed before the run); the trace is a
diagnostic writer's record; descriptive counts; no lane, unison, string, callback or live-host claim; no native implementation of any gate or
lane exists, and a real one would change which spans appear; not a built output.

Usage: python3 -P -E CLAUDE-M3-SUPPORT-RESCUE-COMBINED-20261122.py TRACE.tsv.gz
"""
import gzip
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402
from tools.native_neural_consensus import EVIDENCE_DIR, confirmation_spans, intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dil = load('dil', 'CLAUDE-M3-SUPPORT-DILATION-20261122.py')
rf = load('rf', 'CLAUDE-M3-NATIVE-RESCUE-FRONTIER-20261122.py')
ce = dil.ce
OUT = os.path.join(HERE, 'CLAUDE-M3-SUPPORT-RESCUE-COMBINED-20261122.json')
CUTS = [math.inf, 1.0, 0.5, 0.25]
DELAYS_MS = [50, 220]
FLOOR = 60


def run(path):
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
    evidence = json.load(gzip.open(os.path.join(REPO, EVIDENCE_DIR, 'ordinary-bridge-events.json.gz'), 'rt'))
    arm_a = evidence['arm_spans']['A']
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, 'ordinary-consensus-spans.json.gz'), 'rt'))
    native = [tuple(x) for x in saved['native_confirmation']]
    native60 = union_spans([s for s in native if s[2] >= FLOOR], sample_count=horizon)
    arm_a60 = union_spans([s for s in arm_a if s[2] >= FLOOR], sample_count=horizon)
    support_an = union_spans([*arm_a, *native], sample_count=horizon)

    obs = {c: [] for c in CUTS}
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            cands = {} if frame['quiet'] else _candidates(frame)
            for c in CUTS:
                obs[c].append((frame['sample'], rf.lane_notes(cands, c) if cands else set()))
    rescue = {}
    for c in CUTS:
        spans, _ = confirmation_spans(obs[c], sample_count=horizon, block_size=512)
        rescue[c] = union_spans(spans, sample_count=horizon)

    ct, cg = current['pitch_sets']['totals'], current['pitch_sets']['unlabeled_gap_voice_samples']
    cur_false = ct['extra_pitch_voice_samples'] + cg
    cur_runs = len(union_spans(cur_spans, sample_count=horizon))
    result = dict(horizon=horizon, identity=dict(native60_equals_saved=[list(s) for s in rescue[math.inf]] == [list(s) for s in native60]),
                  current=dict(present=ct['present_pitch_samples'], expected=ct['expected_pitch_samples'], false=cur_false,
                               wrong=ct['extra_pitch_voice_samples'], gap=cg),
                  variants={})

    def evaluate(name, spans, baseline=None):
        spans = union_spans(spans, sample_count=horizon)
        hybrid = score(spans, labels, **clock)
        cmp = compare(current, hybrid)
        t = hybrid['pitch_sets']['totals']
        gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
        false = t['extra_pitch_voice_samples'] + gap
        losing = [r for r in cmp['label_deltas'] if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0]
        lost = sum(-r['present_samples_delta'] for r in losing if r['present_samples_delta'] < 0)
        row = dict(
            coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
            precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
            present_delta=t['present_pitch_samples'] - ct['present_pitch_samples'],
            wrong_delta=t['extra_pitch_voice_samples'] - ct['extra_pitch_voice_samples'], gap_delta=gap - cg,
            false_total=false, false_change_pct_of_current=round(100 * (false - cur_false) / cur_false, 2),
            exact_set_delta=t['exact_pitch_set_samples'] - ct['exact_pitch_set_samples'],
            all_expected_delta=t['all_expected_pitches_samples'] - ct['all_expected_pitches_samples'],
            labels_losing_present_or_longest=len(losing), lost_pitch_samples=lost,
            lost_share_of_current_present=round(lost / ct['present_pitch_samples'], 4),
            runs_vs_current_pct=round(100 * (len(spans) - cur_runs) / cur_runs, 2),
            no_pitch_safety_regression=cmp['no_pitch_safety_regression'])
        if baseline is not None:
            b = result['variants'][baseline]
            dg = row['present_delta'] - b['present_delta']
            df = row['false_total'] - b['false_total']
            row['added_vs_' + baseline.strip()[:24]] = dict(genuine=dg, false=df, false_per_genuine=round(df / dg, 4) if dg > 0 else None)
        result['variants'][name] = row
        return row

    for d in DELAYS_MS:
        sup = dil.dilate(support_an, int(d * rate / 1000), horizon)
        filt = intersect_spans(cur_spans, sup, sample_count=horizon)
        base_name = f'D{d} filter only (A union native)'
        evaluate(base_name, filt)
        held_a = dil.dilate(arm_a60, int(d * rate / 1000), horizon)
        for c in CUTS:
            tag = 'native lane (c=inf)' if c == math.inf else f'rescue c={c}'
            evaluate(f'D{d} filter + unsupported {tag}', [*filt, *rescue[c]], baseline=base_name)
            if c != math.inf:
                supported = union_spans([*native60, *intersect_spans(rescue[c], held_a, sample_count=horizon)], sample_count=horizon)
                evaluate(f'D{d} filter + supported {tag}', [*filt, *supported], baseline=base_name)
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1])
    print('identity', json.dumps(out['identity']), 'current', json.dumps(out['current']))
    for name, row in out['variants'].items():
        print(name, json.dumps(row))
