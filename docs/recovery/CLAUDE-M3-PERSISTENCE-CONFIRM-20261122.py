"""Can the support filter trust a CURRENT note that has persisted unsupported for L ms, and does that save the labels it still loses?  Saved data only.

No audio, model run, job or native edit; nothing promoted.  CLAUDE-M3-SUPPORT-LOSERS-20261122 found that at D = 220 the filter
CURRENT intersect (arm A union the native confirmation, held forward D ms) still loses 6 labels' present or longest hold on the ordinary
corpus, and the largest loss (label 229, pitch 42: 152 ms, 79.7% of its present time) is a true CURRENT note that arm A never reports and
the native confirmation barely covers (16 ms).  The strict label clause cannot be met by any rule that waits for the support, but a rule
could also confirm by persistence: emit a CURRENT note when it is supported OR after it has lasted L ms without support.  That is causal
(the emitter only needs to know how long CURRENT's own note has been alive), costs a delay of L ms for unsupported notes instead of
never emitting them, and will let long unsupported false notes through.  This script adds, for each CURRENT run (maximal same-pitch span)
longer than L, the span from (start + L) to its end to the support, then scores CURRENT intersect that support.  Grid fixed before the
run: L in {inf, 500, 220, 100, 50} ms, D in {50, 220} ms, both corpora (ordinary and extended-middle), filter only (no lane).

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the D = 50 / 220 filter-only numbers on both corpora (ordinary D = 220: present -23,687, wrong removal 22.2%, 6 labels
losing, precision 58.93%; D = 50: 28 labels, wrong removal 56.1%, precision 67.45%) and the loser table.  NOT seen: any persistence rule.
Predictions, each can fail:
  Q0  identity: L = inf reproduces the filter-only numbers (ordinary D = 220: present delta -23,687, 6 labels losing).
  Q1  ordinary, D = 220: at L = 100 fewer than 6 labels lose present or longest hold.
  Q2  ordinary, D = 220: at L = 100 the wrong-pitch removal share is below 15% (it was 22.2% with no persistence rule).
  Q3  ordinary, D = 220: labels losing are non-increasing as L falls over inf, 500, 220, 100, 50.
  Q4  ordinary, D = 220: precision is non-increasing as L falls.
  Q5  ordinary, D = 220: at L = 220 the wrong-pitch removal share stays above 20%.
  Q6  extended-middle, D = 220: every L keeps 0 labels losing and the safety flag True (the filter was already clean there), and the
      wrong-pitch removal share at L = 100 is below its L = inf value (26.0%).
  Q7  ordinary, D = 50: at L = 100 labels losing fall to under half of 28 (at most 13).
Report everything whatever it shows.  One recording per corpus, in-sample for design (the grid was fixed before the run); arm A is an
offline causal run with measured FIFO timestamps; the native confirmation is read from a saved trace; no lane, unison, string, callback or
live-host claim; a run is a maximal same-pitch span and persistence is measured on CURRENT's saved spans, not on a live emitter; not a built
output.

Usage: python3 -P -E CLAUDE-M3-PERSISTENCE-CONFIRM-20261122.py
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
from tools.native_neural_consensus import EVIDENCE_DIR, intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dil = load('dil', 'CLAUDE-M3-SUPPORT-DILATION-20261122.py')
ce = dil.ce
OUT = os.path.join(HERE, 'CLAUDE-M3-PERSISTENCE-CONFIRM-20261122.json')
HOLDS_MS = [50, 220]
PERSIST_MS = [math.inf, 500, 220, 100, 50]
DATASETS = ['ordinary', 'extended-middle']


def persistence_support(cur_union, limit, horizon):
    return union_spans([(l + limit, r, p) for l, r, p in cur_union if r - l > limit], sample_count=horizon) if limit != math.inf else []


def run_dataset(dataset):
    base = json.load(open(ce.BASELINE))['datasets'][dataset]
    rep = json.load(open(os.path.join(ce.CONSENSUS, 'report.json')))['datasets'][dataset]
    horizon = rep['common_support']['sample_count']
    rate = rep['common_support']['sample_rate']
    clock = dict(sample_count=horizon, sample_rate=rate)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    current = score(cur_spans, labels, **clock)
    identity = json.loads(json.dumps(current)) == rep['current']
    cur_union = union_spans(cur_spans, sample_count=horizon)
    evidence = json.load(gzip.open(os.path.join(REPO, EVIDENCE_DIR, f'{dataset}-bridge-events.json.gz'), 'rt'))
    arm_a = evidence['arm_spans']['A']
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, f'{dataset}-consensus-spans.json.gz'), 'rt'))
    native = [tuple(x) for x in saved['native_confirmation']]
    support_an = union_spans([*arm_a, *native], sample_count=horizon)
    ct, cg = current['pitch_sets']['totals'], current['pitch_sets']['unlabeled_gap_voice_samples']
    cur_false = ct['extra_pitch_voice_samples'] + cg
    cur_runs = len(cur_union)
    out = dict(identity=identity, horizon=horizon, current=dict(present=ct['present_pitch_samples'], wrong=ct['extra_pitch_voice_samples'],
                                                                 gap=cg, runs=cur_runs), variants={})
    for d in HOLDS_MS:
        held = dil.dilate(support_an, int(d * rate / 1000), horizon)
        for limit in PERSIST_MS:
            lim_samples = int(limit * rate / 1000) if limit != math.inf else math.inf
            sup = union_spans([*held, *persistence_support(cur_union, lim_samples, horizon)], sample_count=horizon)
            spans = union_spans(intersect_spans(cur_spans, sup, sample_count=horizon), sample_count=horizon)
            hybrid = score(spans, labels, **clock)
            cmp = compare(current, hybrid)
            t = hybrid['pitch_sets']['totals']
            gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
            false = t['extra_pitch_voice_samples'] + gap
            losing = [r for r in cmp['label_deltas'] if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0]
            lost = sum(-r['present_samples_delta'] for r in losing if r['present_samples_delta'] < 0)
            out['variants'][f'D{d} persist {"inf" if limit == math.inf else int(limit)} ms'] = dict(
                coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
                precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
                present_delta=t['present_pitch_samples'] - ct['present_pitch_samples'],
                wrong_delta=t['extra_pitch_voice_samples'] - ct['extra_pitch_voice_samples'],
                wrong_removed_share=round(max(0, ct['extra_pitch_voice_samples'] - t['extra_pitch_voice_samples']) / max(1, ct['extra_pitch_voice_samples']), 4),
                gap_delta=gap - cg, false_change_pct_of_current=round(100 * (false - cur_false) / max(1, cur_false), 2),
                exact_set_delta=t['exact_pitch_set_samples'] - ct['exact_pitch_set_samples'],
                labels_losing_present_or_longest=len(losing), lost_pitch_samples=lost,
                lost_share_of_current_present=round(lost / ct['present_pitch_samples'], 4),
                runs=len(spans), runs_vs_current_pct=round(100 * (len(spans) - cur_runs) / cur_runs, 2),
                no_pitch_safety_regression=cmp['no_pitch_safety_regression'])
    return out


if __name__ == '__main__':
    result = {name: run_dataset(name) for name in DATASETS}
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    for name, out in result.items():
        print(name, 'identity', out['identity'], json.dumps(out['current']))
        for k, v in out['variants'].items():
            print(' ', k, json.dumps(v))
