"""The additive-hybrid frontier: CURRENT union (Basic Pitch arm A at or above a pitch floor), against the consensus hybrid.  Saved data only.

No audio, no model run, no job, nothing promoted or installed.  CLAUDE-M3-CONSENSUS-EXTRAS-20261122 decomposed what Codex's consensus
hybrid adds (+2,211,863 genuine, +335,235 false pitch-samples; 92% of the added gap samples are tails with a median 41 ms past the
label end).  A union can only add, so the project's strict gate (wrong-pitch and gap extras may not rise) fails for every additive hybrid
that adds one false sample; what separates additive hybrids is how much genuine output each buys per false sample.  This script lays out
the family on the same inputs: CURRENT union A restricted to pitches at or above a floor (none, 48, 60, 72), the consensus hybrid, and
the slice of A at or above 60 that the consensus does not take.  Every hybrid is scored with the project's own score/compare, so the gate
clauses are reported verbatim.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the consensus decomposition (false share 13.2% of additions; by band 29.3% below 48, 12.0% at 48-59, 7.4% at 60-71, 6.4% at
72+; 5.8% genuine already in the consensus), Codex's split report (H_A: coverage 63.11%, wrong 8,037,880, gap 4,658,102, exact-set 1,291,237;
A alone: 54.95%, wrong 3,008,188, gap 3,568,575) and the false-output anatomy of A's 60+ band (1,628,205 false samples).  NOT seen: any score
of CURRENT union A at a floor, or any decomposition of A's additions.  Predictions, each can fail:
  U0  no label loses presence or longest hold in any union (by construction) and every union fails the strict gate only on the wrong-pitch
      and/or gap clauses (exact-set and all-expected deltas are not negative).
  U1  CURRENT union A_{>=60}: ordinary coverage between 63.0% and 64.5%.
  U2  its added false per added genuine sample is above the consensus hybrid's 0.152 and below 0.25.
  U3  its added false share is lowest in the 72+ band and highest in 60-71 among the two upper bands... (i.e. 72+ false share < 60-71 false share).
  U4  the false share of A's own additions below 48 is the highest of the four bands, as it is for the consensus.
  U5  the slice of A_{>=60} that the consensus does not take has a higher false share than the consensus additions at 60 and above (7.4%/6.4%),
      i.e. the native confirmation does filter A's false output at 60 and above.
  U6  at the 50 ms scale, at least 50% of the added gap samples of CURRENT union A_{>=60} fall within 50 ms of the end of a same-pitch label
      (boundary-scale tails), and at least 80% within 220 ms.
  U7  precision (genuine / (genuine + wrong + gap), pitch-samples) of CURRENT union A_{>=60} exceeds CURRENT's 54.2% by at least 6 points.
Report everything whatever it shows.  One recording, one corpus; descriptive counts; no lane, unison, callback, string or live-host claim;
the neural arm A carries measured FIFO timestamps from an offline run and its joint runtime with the native tracker is not measured.

Usage: python3 -P -E CLAUDE-M3-UNION-FRONTIER-20261122.py
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
from tools.native_neural_consensus import EVIDENCE_DIR  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402

spec = importlib.util.spec_from_file_location('ce', os.path.join(HERE, 'CLAUDE-M3-CONSENSUS-EXTRAS-20261122.py'))
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)

OUT = os.path.join(HERE, 'CLAUDE-M3-UNION-FRONTIER-20261122.json')
CONSENSUS = ce.CONSENSUS


def new_runs(spans, cur_by, floor=0):
    add = ce.by_pitch([s for s in spans if s[2] >= floor])
    new = {p: ce.subtract_pitch(v, cur_by.get(p, [])) for p, v in add.items()}
    return {p: v for p, v in new.items() if v}


def anatomy(runs, index, horizon):
    acc = ce.decompose(runs, index, horizon)
    tail = acc['tail_ms']
    total_gap = acc['gap']
    within = lambda ms: round(sum(w for w, d in tail if d <= ms) / total_gap, 3) if total_gap else None
    false = acc['wrong'] + acc['gap']
    return dict(
        genuine=acc['genuine'], wrong=acc['wrong'], gap=acc['gap'], false=false,
        false_share=round(false / (acc['genuine'] + false), 4) if acc['genuine'] + false else None,
        false_per_genuine=round(false / acc['genuine'], 4) if acc['genuine'] else None,
        by_band={k: dict(genuine=v[0], false=v[1], false_share=round(v[1] / (v[0] + v[1]), 4) if v[0] + v[1] else None)
                 for k, v in sorted(acc['band'].items())},
        gap_kind_share={k: round(v / total_gap, 3) for k, v in acc['gap_kind'].items()} if total_gap else {},
        tail_within_ms={ms: within(ms) for ms in (20, 50, 100, 220)},
        wrong_rel_share={k: round(v / acc['wrong'], 3) for k, v in acc['wrong_rel'].items()} if acc['wrong'] else {})


def run():
    base = json.load(open(ce.BASELINE))['datasets']['ordinary']
    rep = json.load(open(os.path.join(CONSENSUS, 'report.json')))['datasets']['ordinary']
    horizon = rep['common_support']['sample_count']
    clock = dict(sample_count=horizon, sample_rate=rep['common_support']['sample_rate'])
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    index = ce.LabelIndex(labels)
    cur_by = ce.by_pitch(cur_spans)
    current = score(cur_spans, labels, **clock)
    if json.loads(json.dumps(current)) != rep['current']:
        raise SystemExit('CURRENT identity failed')
    evidence = json.load(gzip.open(os.path.join(REPO, EVIDENCE_DIR, 'ordinary-bridge-events.json.gz'), 'rt'))
    neural = evidence['arm_spans']['A']
    if json.loads(json.dumps(score(neural, labels, **clock))) != rep['neural_A']:
        raise SystemExit('A identity failed')
    consensus = json.load(gzip.open(os.path.join(CONSENSUS, 'ordinary-consensus-spans.json.gz'), 'rt'))
    cur_false = (current['pitch_sets']['totals']['extra_pitch_voice_samples']
                 + current['pitch_sets']['unlabeled_gap_voice_samples'])
    result = dict(horizon=horizon, current_false=cur_false, hybrids={})

    def evaluate(name, add_spans):
        hybrid_spans = union_spans([*cur_spans, *add_spans], sample_count=horizon)
        hybrid = score(hybrid_spans, labels, **clock)
        cmp = compare(current, hybrid)
        t, c = hybrid['pitch_sets']['totals'], current['pitch_sets']['totals']
        gap, gap0 = hybrid['pitch_sets']['unlabeled_gap_voice_samples'], current['pitch_sets']['unlabeled_gap_voice_samples']
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
            no_pitch_safety_regression=cmp['no_pitch_safety_regression'])
        row['false_total'] = false
        row['false_change_pct_of_current'] = round(100 * (false - cur_false) / cur_false, 2)
        row['anatomy'] = anatomy(new_runs(add_spans, cur_by), index, horizon)
        result['hybrids'][name] = row
        return row

    for floor in (0, 48, 60, 72):
        evaluate(f'CURRENT union A>={floor}', [s for s in neural if s[2] >= floor])
    evaluate('consensus (CURRENT union A intersect native)', consensus['confirmed_neural'])
    # slice: A at or above 60 that the consensus does not take
    take_by = ce.by_pitch(consensus['confirmed_neural'])
    cons_total = ce.by_pitch([s for s in consensus['confirmed_neural']])
    a60 = ce.by_pitch([s for s in neural if s[2] >= 60])
    rest = {}
    for p, ivs in a60.items():
        left = ce.subtract_pitch(ivs, take_by.get(p, []))
        left = ce.subtract_pitch(left, cur_by.get(p, []))
        if left:
            rest[p] = left
    result['slice_A60_not_consensus'] = anatomy(rest, index, horizon)
    cons60 = {p: v for p, v in new_runs(consensus['confirmed_neural'], cur_by, 60).items()}
    result['consensus_additions_60plus'] = anatomy(cons60, index, horizon)
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run()
    for name, row in out['hybrids'].items():
        a = row.pop('anatomy')
        print(name, json.dumps(row))
        print('   anatomy', json.dumps(dict(genuine=a['genuine'], false=a['false'], false_share=a['false_share'], fpg=a['false_per_genuine'],
                                            bands={k: v['false_share'] for k, v in a['by_band'].items()}, tail_within=a['tail_within_ms'],
                                            gap_kind=a['gap_kind_share'])))
        row['anatomy'] = a
    print('slice A>=60 not consensus', json.dumps({k: v for k, v in out['slice_A60_not_consensus'].items() if k != 'by_band'}))
    print('consensus additions >=60', json.dumps({k: v for k, v in out['consensus_additions_60plus'].items() if k != 'by_band'}))
