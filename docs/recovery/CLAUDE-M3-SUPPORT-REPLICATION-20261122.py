"""Does the support filter and native-only gate hold on the second saved corpus (extended-middle)?  Saved data only.

No audio, model run, job or native edit; nothing promoted.  CLAUDE-M3-SUPPORT-FILTER-20261122 (commit 4c414eb) found on the ordinary
corpus that CURRENT intersect (arm A union the native confirmation) removes 75.8% of CURRENT's wrong-pitch output for 6.0% of its
genuine presence, that a forward hold of the support trades label losses against removal, and that a gate on the native confirmation
alone plus the native >= 60 lane at a 220 ms hold gives coverage 45.07%, precision 62.77%, wrong -2,144,404, gap -246,599, exact-set
+265,475 with 9 of 499 labels losing 0.55% of CURRENT's present time.  Every one of those numbers is in-sample on one recording, and
the hold grid {0, 50, 100, 220, 500} ms was fixed on the ordinary corpus.  The saved baseline, consensus spans and arm A spans also
exist for the second corpus, `extended-middle` (6 labels, 2,233,574 samples; CURRENT coverage 97.5%, exact-set 73.1%, wrong 528,259,
gap 183,006; CURRENT precision 73.97%).  This script runs the same filter and gate, with the same unchanged hold grid, on that corpus.
No value is chosen or tuned on it.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: CURRENT's totals above (coverage, exact-set, wrong, gap) for extended-middle, from the saved consensus report.  NOT seen
(in this stretch of work): any filtered, held or lane-added score on it, arm A's or the native confirmation's span counts scored against
its labels.  Predictions, each can fail:
  X0  identity: CURRENT re-scored here equals the saved consensus report's `current` for extended-middle.
  X1  CURRENT intersect (A union native) at D = 0 removes more than 25% of CURRENT's wrong-pitch output.
  X2  filter precision exceeds CURRENT's 73.97% at every hold in {0, 50, 100, 220, 500} (support = A union native, filter only).
  X3  no hold up to 220 ms reaches zero labels losing present or longest hold for the A union native filter at D = 0 (the confirm delay).
  X4  at D = 220 the lost share of CURRENT's present time (filter only, A union native) is under 1%.
  X5  native-only support plus the native >= 60 lane at D = 220: wrong-pitch delta <= 0 and gap delta <= 0.
  X6  the same variant's exact-set delta is >= 0 and all-expected delta >= 0.
  X7  the same variant's coverage is not below CURRENT's.
  X8  the same variant's total false (wrong + gap) is below CURRENT's.
Report everything whatever it shows.  One recording per corpus, 6 labels, in-sample for design (the hold grid was fixed on ordinary,
not tuned here); arm A is an offline causal run with measured FIFO timestamps; the native confirmation is read from a saved trace; no
lane, unison, string, callback or live-host claim; not a built output.

Usage: python3 -P -E CLAUDE-M3-SUPPORT-REPLICATION-20261122.py [dataset]   (default: extended-middle)
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


dil = load('dil', 'CLAUDE-M3-SUPPORT-DILATION-20261122.py')
ce = dil.ce
DELAYS_MS = [0, 50, 100, 220, 500]


def run(dataset):
    out_path = os.path.join(HERE, f'CLAUDE-M3-SUPPORT-REPLICATION-{dataset.upper()}-20261122.json')
    base = json.load(open(ce.BASELINE))['datasets'][dataset]
    rep = json.load(open(os.path.join(ce.CONSENSUS, 'report.json')))['datasets'][dataset]
    horizon = rep['common_support']['sample_count']
    rate = rep['common_support']['sample_rate']
    clock = dict(sample_count=horizon, sample_rate=rate)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    current = score(cur_spans, labels, **clock)
    identity = json.loads(json.dumps(current)) == rep['current']
    evidence = json.load(gzip.open(os.path.join(REPO, EVIDENCE_DIR, f'{dataset}-bridge-events.json.gz'), 'rt'))
    arm_a = evidence['arm_spans']['A']
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, f'{dataset}-consensus-spans.json.gz'), 'rt'))
    native = [tuple(x) for x in saved['native_confirmation']]
    native60 = [s for s in native if s[2] >= 60]
    support_an = union_spans([*arm_a, *native], sample_count=horizon)
    support_n = union_spans(native, sample_count=horizon)
    ct, cg = current['pitch_sets']['totals'], current['pitch_sets']['unlabeled_gap_voice_samples']
    cur_false = ct['extra_pitch_voice_samples'] + cg
    cur_runs = len(union_spans(cur_spans, sample_count=horizon))
    result = dict(dataset=dataset, horizon=horizon, identity=identity,
                  current=dict(present=ct['present_pitch_samples'], expected=ct['expected_pitch_samples'], wrong=ct['extra_pitch_voice_samples'],
                               gap=cg, false=cur_false, runs=cur_runs, exact_set=ct['exact_pitch_set_samples'],
                               coverage_pct=round(100 * ct['present_pitch_samples'] / ct['expected_pitch_samples'], 4),
                               precision_pct=round(100 * ct['present_pitch_samples'] / (ct['present_pitch_samples'] + cur_false), 2),
                               labels=len(labels)),
                  native_spans=len(native), native60_spans=len(native60), arm_a_spans=len(arm_a), variants={})
    if not identity:
        print('CURRENT identity FAILED')

    def evaluate(name, spans):
        spans = union_spans(spans, sample_count=horizon)
        hybrid = score(spans, labels, **clock)
        cmp = compare(current, hybrid)
        t = hybrid['pitch_sets']['totals']
        gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
        false = t['extra_pitch_voice_samples'] + gap
        losing = [r for r in cmp['label_deltas'] if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0]
        lost = sum(-r['present_samples_delta'] for r in losing if r['present_samples_delta'] < 0)
        result['variants'][name] = dict(
            coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
            precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
            present_delta=t['present_pitch_samples'] - ct['present_pitch_samples'],
            wrong_delta=t['extra_pitch_voice_samples'] - ct['extra_pitch_voice_samples'],
            wrong_removed_share=round(max(0, ct['extra_pitch_voice_samples'] - t['extra_pitch_voice_samples']) / max(1, ct['extra_pitch_voice_samples']), 4),
            gap_delta=gap - cg, gap_removed_share=round(max(0, cg - gap) / max(1, cg), 4),
            false_total=false, false_change_pct_of_current=round(100 * (false - cur_false) / max(1, cur_false), 2),
            exact_set_delta=t['exact_pitch_set_samples'] - ct['exact_pitch_set_samples'],
            all_expected_delta=t['all_expected_pitches_samples'] - ct['all_expected_pitches_samples'],
            labels_losing_present_or_longest=len(losing),
            labels_losing_present=sum(1 for r in losing if r['present_samples_delta'] < 0),
            labels_losing_longest=sum(1 for r in losing if r['longest_present_samples_delta'] < 0),
            lost_pitch_samples=lost, lost_share_of_current_present=round(lost / ct['present_pitch_samples'], 4),
            worst_present_loss_samples=min([r['present_samples_delta'] for r in losing] + [0]),
            runs=len(spans), runs_vs_current_pct=round(100 * (len(spans) - cur_runs) / cur_runs, 2),
            no_pitch_safety_regression=cmp['no_pitch_safety_regression'])

    evaluate('(control) CURRENT union native >= 60 lane', [*cur_spans, *native60])
    for label, support in (('A union native', support_an), ('native only', support_n)):
        for d in DELAYS_MS:
            sup = dil.dilate(support, int(d * rate / 1000), horizon) if d else support
            filt = intersect_spans(cur_spans, sup, sample_count=horizon)
            evaluate(f'CURRENT intersect ({label}), hold {d} ms', filt)
            evaluate(f'  plus native >= 60 lane: ({label}), hold {d} ms', [*filt, *native60])
    with open(out_path, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'extended-middle'
    out = run(name)
    print('identity', out['identity'], 'current', json.dumps(out['current']))
    print('native_spans', out['native_spans'], 'native60_spans', out['native60_spans'], 'arm_a_spans', out['arm_a_spans'])
    for k, row in out['variants'].items():
        print(k, json.dumps(row))
