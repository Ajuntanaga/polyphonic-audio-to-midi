"""How far can an additive native lane at MIDI 60 and above go if rejected candidates are rescued by score_ratio?  Saved data only.

No audio, model run, job or native edit; nothing promoted.  CLAUDE-M3-NATIVE-ONLY-UNION-20261122 found that CURRENT union the native
confirmation (`not quiet and selector_pool_member == 1 and direct == 1`) at pitch >= 60 adds +1,789,705 genuine and +153,262 false
pitch-samples, and the upper-register census found that 73.0% of 60-71 true ticks (96.6% at 72+) sit at below_threshold with a weak
score_ratio (best single-feature AUC 0.81 at 60-71, 20.5% of true ticks at a 1% ghost rate).  This script asks what a rescue family costs:
lane(c) = the native confirmation, plus any non-quiet candidate at pitch >= 60 with selection in {1 below_threshold, 2 spectral_rejected,
3 dp_evicted} and score_ratio >= c, projected to completed 512-sample callbacks exactly as the consensus tool does (latest observation per
callback, one block, no coasting), unioned with CURRENT and scored with the project's own score/compare.  c = infinity is the native-only
lane.  c is a screen over a family of five values chosen before the run, not a tuned rule; the score_ratio pass level is NOT established
(61 of 135 labels at 60-71 reach a score_ratio >= 1.0 but only 17 reach selected), so c = 1.0 is just a grid point.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the native-only union and census numbers named above, and the post-hoc shares of below_threshold candidates with
score_ratio >= 0.1/0.25/0.5/0.8 (60-71 true 51.1/31.2/16.0/6.5%, ghost 16.9/10.8/5.6/1.7%).  NOT seen: any span-level score of a rescue lane.
Predictions, each can fail:
  R0  identity: lane(infinity) reproduces the saved native confirmation restricted to pitch >= 60, and its added genuine / false are
      1,789,705 / 153,262.
  R1  as c falls (1.0, 0.8, 0.5, 0.25) added genuine rises and false share of additions rises at every step.
  R2  the marginal false per marginal genuine from lane(infinity) to lane(0.5) exceeds 0.25 (worse than the native-only lane's 0.086 and
      the consensus' 0.152).
  R3  at c = 0.25 whole-hybrid precision falls below the native-only lane's 56.94%.
  R4  at c = 1.0 the added genuine over the native-only lane is under 1.0 pp of expected pitch-samples (about 340,000 pitch-samples).
  R5  at c = 0.25 the 72+ band adds fewer than 500,000 genuine pitch-samples.
  R6  no lane loses any label's presence or longest hold (by construction) and every lane fails the strict gate only on wrong-pitch
      and/or gap clauses (exact-set and all-expected deltas not negative).
Report everything whatever it shows.  One recording, one corpus, in-sample; the trace is a diagnostic writer's record; descriptive counts;
no lane, unison, string, callback or live-host claim; no native implementation of any lane exists, and a real one would change which spans
appear (selection, voice slots, retrigger, release).

Usage: python3 -P -E CLAUDE-M3-NATIVE-RESCUE-FRONTIER-20261122.py TRACE.tsv.gz
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
from tools.native_neural_consensus import confirmation_spans  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uf = load('uf', 'CLAUDE-M3-UNION-FRONTIER-20261122.py')
ce = uf.ce
OUT = os.path.join(HERE, 'CLAUDE-M3-NATIVE-RESCUE-FRONTIER-20261122.json')
CUTS = [math.inf, 1.0, 0.8, 0.5, 0.25]
FLOOR = 60


def lane_notes(cands, cut):
    notes = set()
    for note, cand in cands.items():
        if note < FLOOR:
            continue
        if cand['selector_pool_member'] == 1 and cand['direct'] == 1:
            notes.add(note)
        elif cut != math.inf and cand['selection'] in (1, 2, 3) and cand['score_ratio'] >= cut:
            notes.add(note)
    return notes


def run(path):
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
    obs = {c: [] for c in CUTS}
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            cands = {} if frame['quiet'] else _candidates(frame)
            for c in CUTS:
                obs[c].append((frame['sample'], lane_notes(cands, c) if cands else set()))
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, 'ordinary-consensus-spans.json.gz'), 'rt'))
    saved_native60 = union_spans([tuple(x) for x in saved['native_confirmation'] if x[2] >= FLOOR], sample_count=horizon)
    cur_false = (current['pitch_sets']['totals']['extra_pitch_voice_samples']
                 + current['pitch_sets']['unlabeled_gap_voice_samples'])
    expected = current['pitch_sets']['totals']['expected_pitch_samples']
    result = dict(horizon=horizon, current_false=cur_false, expected_pitch_samples=expected, lanes={}, identity={})
    prev = None
    for c in CUTS:
        spans, audit = confirmation_spans(obs[c], sample_count=horizon, block_size=512)
        if c == math.inf:
            result['identity']['native60_equals_saved'] = [list(s) for s in spans] == [list(s) for s in saved_native60]
        hybrid = score(union_spans([*cur_spans, *spans], sample_count=horizon), labels, **clock)
        cmp = compare(current, hybrid)
        t, k = hybrid['pitch_sets']['totals'], current['pitch_sets']['totals']
        gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
        gap0 = current['pitch_sets']['unlabeled_gap_voice_samples']
        false = t['extra_pitch_voice_samples'] + gap
        anat = uf.anatomy(uf.new_runs(spans, cur_by), index, horizon)
        row = dict(
            cut='infinity (native-only)' if c == math.inf else c,
            coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
            precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
            present_delta=t['present_pitch_samples'] - k['present_pitch_samples'],
            present_delta_pp_of_expected=round(100 * (t['present_pitch_samples'] - k['present_pitch_samples']) / expected, 3),
            wrong_delta=t['extra_pitch_voice_samples'] - k['extra_pitch_voice_samples'], gap_delta=gap - gap0,
            exact_set_delta=t['exact_pitch_set_samples'] - k['exact_pitch_set_samples'],
            all_expected_delta=t['all_expected_pitches_samples'] - k['all_expected_pitches_samples'],
            labels_losing_present_or_longest=sum(1 for r in cmp['label_deltas']
                                                 if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0),
            no_pitch_safety_regression=cmp['no_pitch_safety_regression'],
            false_total=false, false_change_pct_of_current=round(100 * (false - cur_false) / cur_false, 2),
            added_genuine=anat['genuine'], added_false=anat['false'], false_share=anat['false_share'],
            false_per_genuine=anat['false_per_genuine'],
            by_band={b: v for b, v in anat['by_band'].items()}, tail_within_ms=anat['tail_within_ms'],
            gap_kind_share=anat['gap_kind_share'], wrong_rel_share=anat['wrong_rel_share'],
            observed_callbacks=audit['observed_callbacks'])
        if prev is not None:
            dg, df = anat['genuine'] - prev['added_genuine'], anat['false'] - prev['added_false']
            row['marginal_vs_previous'] = dict(genuine=dg, false=df, false_per_genuine=round(df / dg, 4) if dg else None)
        result['lanes'][str(c)] = row
        prev = row
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1])
    print('identity', json.dumps(out['identity']), 'expected', out['expected_pitch_samples'])
    for key, row in out['lanes'].items():
        r = dict(row)
        print(key, json.dumps({k: r[k] for k in ('coverage_pct', 'precision_pct', 'added_genuine', 'added_false', 'false_share',
                                                  'false_per_genuine', 'wrong_delta', 'gap_delta', 'exact_set_delta',
                                                  'all_expected_delta', 'labels_losing_present_or_longest',
                                                  'false_change_pct_of_current', 'present_delta_pp_of_expected')}))
        print('    bands', json.dumps(r['by_band']), 'marginal', json.dumps(r.get('marginal_vs_previous')))
