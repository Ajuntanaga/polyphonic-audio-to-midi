"""Can CURRENT's own false output be removed where neither Basic Pitch nor the native confirmation supports it?  Saved data only.

No audio, model run, job or native edit; nothing promoted.  Codex's reply to the additive-hybrid note (`CODEX-M3-HYBRID-AND-NATIVE-REPLY-20261122.md`) keeps the original
gates and says a combined replacement must measure the recovered pitches and the removal of CURRENT errors together, per label and
hold.  Every hybrid so far was additive.  CURRENT's false output (11,429,794 pitch-samples: wrong 7,808,309, gap 3,621,485) is about 75
times the false the native >= 60 lane adds (153,262), so removal is where the large error mass is.  This script scores a support filter
on CURRENT's own spans: CURRENT intersect support, where support is Basic Pitch arm A (same pitch), or arm A union the native
confirmation (same pitch, all pitches), optionally followed by the additive native >= 60 lane.  Spans are intersected per pitch; scored with
the project's own score/compare.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the additive unions, CURRENT's and arm A's aggregate scores (A alone: coverage 54.95%, wrong 3,008,188, gap 3,568,575) and the earlier
lower-register finding that removal rules lose labels (five long octave-pair runs for the re-render rule).  NOT seen: any score of a
CURRENT-intersect-support span set.  Predictions, each can fail:
  S0  plumbing: every filtered CURRENT span set is contained in CURRENT (present, wrong and gap deltas are all <= 0 before any addition).
  S1  CURRENT intersect A removes more than 25% of CURRENT's wrong-pitch voice-samples.
  S2  CURRENT intersect A loses at least one label's presence or longest hold (the strict gate fails on label losses, not only on extras).
  S3  the filtered CURRENT has higher precision than CURRENT's 54.2% (it removes a larger fraction of false than of genuine).
  S4  adding arm A's union with the native confirmation to the support does not rescue the label losses: at least one label still loses
      presence or longest hold under CURRENT intersect (A union native).
  S5  the fraction of CURRENT genuine removed by CURRENT intersect A exceeds 15%.
  S6  CURRENT intersect (A union native) union the native >= 60 lane has coverage above CURRENT's 39.99%.
Report everything whatever it shows.  One recording, one corpus, in-sample; arm A is an offline causal run with measured FIFO timestamps
and the native confirmation is read from a saved trace; no lane, unison, string, callback or live-host claim; not a built output.

Usage: python3 -P -E CLAUDE-M3-SUPPORT-FILTER-20261122.py
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
OUT = os.path.join(HERE, 'CLAUDE-M3-SUPPORT-FILTER-20261122.json')


def run():
    base = json.load(open(ce.BASELINE))['datasets']['ordinary']
    rep = json.load(open(os.path.join(ce.CONSENSUS, 'report.json')))['datasets']['ordinary']
    horizon = rep['common_support']['sample_count']
    clock = dict(sample_count=horizon, sample_rate=rep['common_support']['sample_rate'])
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    current = score(cur_spans, labels, **clock)
    if json.loads(json.dumps(current)) != rep['current']:
        raise SystemExit('CURRENT identity failed')
    evidence = json.load(gzip.open(os.path.join(REPO, EVIDENCE_DIR, 'ordinary-bridge-events.json.gz'), 'rt'))
    arm_a = evidence['arm_spans']['A']
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, 'ordinary-consensus-spans.json.gz'), 'rt'))
    native = [tuple(x) for x in saved['native_confirmation']]
    native60 = [s for s in native if s[2] >= 60]
    support_a_native = union_spans([*arm_a, *native], sample_count=horizon)
    ct, cg = current['pitch_sets']['totals'], current['pitch_sets']['unlabeled_gap_voice_samples']
    cur_false = ct['extra_pitch_voice_samples'] + cg
    result = dict(horizon=horizon, current=dict(present=ct['present_pitch_samples'], wrong=ct['extra_pitch_voice_samples'],
                                                 gap=cg, false=cur_false), variants={})

    def evaluate(name, spans):
        hybrid = score(union_spans(spans, sample_count=horizon), labels, **clock)
        cmp = compare(current, hybrid)
        t = hybrid['pitch_sets']['totals']
        gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
        false = t['extra_pitch_voice_samples'] + gap
        losing = [r for r in cmp['label_deltas']
                  if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0]
        result['variants'][name] = dict(
            coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
            precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
            present_delta=t['present_pitch_samples'] - ct['present_pitch_samples'],
            present_removed_share=round(max(0, ct['present_pitch_samples'] - t['present_pitch_samples']) / ct['present_pitch_samples'], 4),
            wrong_delta=t['extra_pitch_voice_samples'] - ct['extra_pitch_voice_samples'],
            wrong_removed_share=round(max(0, ct['extra_pitch_voice_samples'] - t['extra_pitch_voice_samples']) / ct['extra_pitch_voice_samples'], 4),
            gap_delta=gap - cg,
            gap_removed_share=round(max(0, cg - gap) / cg, 4),
            false_total=false, false_delta=false - cur_false,
            exact_set_delta=t['exact_pitch_set_samples'] - ct['exact_pitch_set_samples'],
            all_expected_delta=t['all_expected_pitches_samples'] - ct['all_expected_pitches_samples'],
            labels_losing_present_or_longest=len(losing),
            labels_losing_present=sum(1 for r in losing if r['present_samples_delta'] < 0),
            labels_losing_longest=sum(1 for r in losing if r['longest_present_samples_delta'] < 0),
            worst_present_loss_samples=min([r['present_samples_delta'] for r in losing] + [0]),
            no_pitch_safety_regression=cmp['no_pitch_safety_regression'])

    filtered_a = intersect_spans(cur_spans, arm_a, sample_count=horizon)
    filtered_an = intersect_spans(cur_spans, support_a_native, sample_count=horizon)
    evaluate('CURRENT intersect A', filtered_a)
    evaluate('CURRENT intersect (A union native)', filtered_an)
    evaluate('CURRENT intersect (A union native), union native >= 60 lane', [*filtered_an, *native60])
    evaluate('CURRENT intersect A, union native >= 60 lane', [*filtered_a, *native60])
    evaluate('(control) CURRENT union native >= 60 lane', [*cur_spans, *native60])
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run()
    print('current', json.dumps(out['current']))
    for name, row in out['variants'].items():
        print(name, json.dumps(row))
