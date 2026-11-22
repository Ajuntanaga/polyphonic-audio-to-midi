"""Does the native confirmation need the neural arm?  CURRENT union (native confirmation alone), against the consensus.  Saved data only.

No audio, model run, job or native edit; nothing promoted.  The frozen consensus hybrid is CURRENT union (arm A intersect native
confirmation).  The native confirmation (`selector_pool_member == 1 and direct == 1`, projected to completed 512-sample callbacks) is the
saved `native_confirmation` span set.  CLAUDE-M3-UPPER-FATE-20261122 found that at 60-71 the trace's dp_evicted candidates are 98% true
(26,118 true ticks against 467 ghost ticks), so the native confirmation may carry most of the consensus gain without any neural input.
This script scores CURRENT union native confirmation (all pitches, at 48 and above, at 60 and above), and splits the native-only
additions into the part arm A also reports (the consensus) and the part it does not.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the consensus additions (2,211,863 genuine, 335,235 false), the union family with arm A, and the upper-register census
(60-71: dp_evicted candidates 98% true by tick count).  NOT seen: any score or decomposition of the native confirmation on its own.
Predictions, each can fail:
  N0  plumbing: the native-only additions contain the consensus additions, so added genuine >= 2,211,863 and added false >= 335,235.
  N1  native-only added genuine lies between 2.4M and 4.0M pitch-samples.
  N2  native-only added false share (false / (genuine + false)) lies between 10% and 25%.
  N3  the part that arm A removes (native-only additions not in the consensus) has a higher false share than the consensus' 13.16%.
  N4  native-only at 60 and above adds less than 0.20 false per added genuine pitch-sample.
  N5  native-only fails the strict gate only on the wrong-pitch and/or gap clauses (no label loses presence or longest hold; exact-set and
      all-expected deltas are not negative).
  N6  native-only raises whole-hybrid precision above CURRENT's 54.2%.
Report everything whatever it shows.  One recording, one corpus; descriptive counts; the native confirmation is read from a saved trace
with the trace-writer limits noted in earlier notes; no lane, unison, string, callback or live-host claim, and no native implementation
of this union exists (the native detector's own selection would differ).

Usage: python3 -P -E CLAUDE-M3-NATIVE-ONLY-UNION-20261122.py
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
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uf = load('uf', 'CLAUDE-M3-UNION-FRONTIER-20261122.py')
ce = uf.ce
OUT = os.path.join(HERE, 'CLAUDE-M3-NATIVE-ONLY-UNION-20261122.json')


def run():
    base = json.load(open(ce.BASELINE))['datasets']['ordinary']
    rep = json.load(open(os.path.join(ce.CONSENSUS, 'report.json')))['datasets']['ordinary']
    horizon = rep['common_support']['sample_count']
    clock = dict(sample_count=horizon, sample_rate=rep['common_support']['sample_rate'])
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    index = ce.LabelIndex(labels)
    cur_by = ce.by_pitch(cur_spans)
    current = score(cur_spans, labels, **clock)
    if json.loads(json.dumps(current)) != rep['current']:
        raise SystemExit('CURRENT identity failed')
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, 'ordinary-consensus-spans.json.gz'), 'rt'))
    native = [tuple(x) for x in saved['native_confirmation']]
    consensus = [tuple(x) for x in saved['confirmed_neural']]
    cur_false = (current['pitch_sets']['totals']['extra_pitch_voice_samples']
                 + current['pitch_sets']['unlabeled_gap_voice_samples'])
    result = dict(horizon=horizon, current_false=cur_false, hybrids={})

    def evaluate(name, add_spans):
        hybrid = score(union_spans([*cur_spans, *add_spans], sample_count=horizon), labels, **clock)
        cmp = compare(current, hybrid)
        t, c = hybrid['pitch_sets']['totals'], current['pitch_sets']['totals']
        gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
        gap0 = current['pitch_sets']['unlabeled_gap_voice_samples']
        false = t['extra_pitch_voice_samples'] + gap
        row = dict(
            coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
            precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
            present_delta=t['present_pitch_samples'] - c['present_pitch_samples'],
            wrong_delta=t['extra_pitch_voice_samples'] - c['extra_pitch_voice_samples'],
            gap_delta=gap - gap0,
            exact_set_delta=t['exact_pitch_set_samples'] - c['exact_pitch_set_samples'],
            all_expected_delta=t['all_expected_pitches_samples'] - c['all_expected_pitches_samples'],
            labels_losing_present_or_longest=sum(1 for r in cmp['label_deltas']
                                                 if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0),
            no_pitch_safety_regression=cmp['no_pitch_safety_regression'],
            false_total=false, false_change_pct_of_current=round(100 * (false - cur_false) / cur_false, 2))
        row['anatomy'] = uf.anatomy(uf.new_runs(add_spans, cur_by), index, horizon)
        result['hybrids'][name] = row

    evaluate('CURRENT union native, all pitches', native)
    evaluate('CURRENT union native >= 48', [s for s in native if s[2] >= 48])
    evaluate('CURRENT union native >= 60', [s for s in native if s[2] >= 60])
    evaluate('consensus (arm A intersect native)', consensus)
    # native-only additions that arm A does not report: native additions minus the consensus additions
    nat_new = uf.new_runs(native, cur_by)
    con_new = uf.new_runs(consensus, cur_by)
    rest = {}
    for p, ivs in nat_new.items():
        left = ce.subtract_pitch(ivs, con_new.get(p, []))
        if left:
            rest[p] = left
    result['native_not_in_consensus'] = uf.anatomy(rest, index, horizon)
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run()
    for name, row in out['hybrids'].items():
        a = row.pop('anatomy')
        print(name, json.dumps(row))
        print('   anatomy', json.dumps(dict(genuine=a['genuine'], wrong=a['wrong'], gap=a['gap'], false=a['false'], false_share=a['false_share'],
                                            fpg=a['false_per_genuine'], bands={k: v['false_share'] for k, v in a['by_band'].items()},
                                            tail_within=a['tail_within_ms'], gap_kind=a['gap_kind_share'], wrong_rel=a['wrong_rel_share'])))
        row['anatomy'] = a
    b = out['native_not_in_consensus']
    print('native not in consensus', json.dumps({k: v for k, v in b.items() if k != 'by_band'}), json.dumps(b['by_band']))
