"""How much of CURRENT's lower-band orphan output is a SUBSTITUTION for a label it does not otherwise output?  Oracle bound on saved spans and labels.

No audio, model run or job.  The orphan-relation result found that 56% of CURRENT's lower orphan false samples are an
octave or twelfth (and 17% a near neighbour) of a label that is sounding.  If that related label is NOT covered by
CURRENT's own same-pitch output at that moment, the orphan is a substitution: the detector heard the note and rendered
it at the wrong pitch.  An oracle that reassigns such a stretch to the related uncovered label's pitch bounds what a
perfect octave/twelfth/neighbour corrector could gain.  The oracle uses the labels, so it is NOT an implementable rule;
it measures the size of the prize and whether the gate would be met by construction (a reassigned stretch was an orphan,
so no label can lose present samples).

Method.  For each ordinary-corpus CURRENT span below MIDI 60 that is an orphan (overlaps no label of its own pitch),
each stretch of constant active-label set is examined.  Related labels are those active in the stretch with interval
d = span pitch - label pitch of class octave (nonzero multiple of 12), fifth (d mod 12 == 7) or near (|d| <= 2); of
those, the ones CURRENT does not cover with a same-pitch span at every sample of the stretch ("uncovered", checked per
sample by interval union).  The stretch is reassigned to the nearest-by-class (octave, then fifth, then near; ties by
smaller |d|) uncovered related label's pitch.  Reported: substituted samples per class and as a share of the class's
orphan samples, then the scorer's coverage, wrong-pitch, gap, exact-set and per-label loss for the reassigned spans
against CURRENT (and the strict gate).

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the orphan-relation result (class shares) and the anatomy numbers.  NOT seen: any substitution count or
oracle score.  Predictions, each can fail:
  Q1  at least 30% of the octave-class orphan samples are substitutions (the related label is uncovered).
  Q2  at least 30% of the fifth-class orphan samples are substitutions.
  Q3  at least 50% of the near-class orphan samples are substitutions.
  Q4  the oracle raises ordinary coverage by at least 3 percentage points (CURRENT 39.99).
  Q5  the oracle at least doubles ordinary exact-pitch-set samples (CURRENT 53,249).
  Q6  the oracle passes the strict gate no_pitch_safety_regression on ordinary (by construction it should).
Report everything whatever it shows.  Pitch occupancy only; no lane, unison, timing or live-host claim.  An oracle
number is an upper bound on a label-aware corrector, not a result about any detector.

Usage: python3 -P -E CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122.py
"""
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('audit', os.path.join(HERE, 'CLAUDE-M3-TAIL-CLIP-LOSS-AUDIT-20261121.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
split = audit.split
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import compare, score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122.json')


def rel_class(d):
    if d != 0 and d % 12 == 0:
        return 0, 'octave'
    if d % 12 == 7:
        return 1, 'fifth'
    if abs(d) <= 2 and d != 0:
        return 2, 'near'
    return None


def covered_everywhere(spans_by_pitch, pitch, a, b):
    """True if the union of same-pitch spans covers every sample of [a, b)."""
    position = a
    for left, right in spans_by_pitch.get(pitch, ()):
        if right <= position:
            continue
        if left > position:
            return False
        position = right
        if position >= b:
            return True
    return position >= b


def run():
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    result = dict(schema='claude_m3_oracle_substitution_v1', datasets={})
    for name, data in report['datasets'].items():
        base = baseline['datasets'][name]
        horizon = data['common_support']['sample_count']
        clock = dict(sample_count=horizon, sample_rate=split.SAMPLE_RATE)
        labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
        spans = clip_spans(base['pitch_spans'], horizon)
        by_pitch = defaultdict(list)
        for left, right, note in spans:
            by_pitch[note].append((left, right))
        for note in by_pitch:
            by_pitch[note].sort()
        cuts = sorted({s for l in labels for s in (l['start_sample'], l['end_sample'])})
        orphan_by_class = Counter()
        sub_by_class = Counter()
        new_spans = []
        for left, right, note in spans:
            if note >= split.SPLIT or any(l['midi_note'] == note and l['start_sample'] < right and l['end_sample'] > left
                                          for l in labels):
                new_spans.append((left, right, note))
                continue
            edges = [left] + [c for c in cuts if left < c < right] + [right]
            for a, b in zip(edges, edges[1:]):
                active = [l['midi_note'] for l in labels if l['start_sample'] < b and l['end_sample'] > a]
                related = []
                for p in set(active):
                    rc = rel_class(note - p)
                    if rc is not None:
                        related.append((rc[0], abs(note - p), p, rc[1]))
                related.sort()
                kind = related[0][3] if related else None
                if kind is not None:
                    orphan_by_class[kind] += b - a
                target = None
                for _order, _dist, p, cls in related:
                    if not covered_everywhere(by_pitch, p, a, b):
                        target, kind = p, cls
                        break
                if target is None:
                    new_spans.append((a, b, note))
                else:
                    sub_by_class[kind] += b - a
                    new_spans.append((a, b, target))
        current = score(spans, labels, **clock)
        oracle = score(new_spans, labels, **clock)
        cur, orc = split.compact(current), split.compact(oracle)
        cmp = compare(current, oracle)
        summary = audit.summarize(audit.loss_rows(current, oracle))
        result['datasets'][name] = dict(
            orphan_samples_with_related_label={k: orphan_by_class[k] for k in ('octave', 'fifth', 'near')},
            substituted_samples={k: sub_by_class[k] for k in ('octave', 'fifth', 'near')},
            substituted_share={k: round(sub_by_class[k] / orphan_by_class[k], 3) if orphan_by_class[k] else None
                               for k in ('octave', 'fifth', 'near')},
            current=cur, oracle=orc,
            coverage_gain_points=round(orc['coverage_percent'] - cur['coverage_percent'], 2),
            exact_set_ratio=round(orc['exact_pitch_set'] / cur['exact_pitch_set'], 2) if cur['exact_pitch_set'] else None,
            wrong_pitch_delta=orc['wrong_pitch'] - cur['wrong_pitch'], gap_delta=orc['gap'] - cur['gap'],
            strict_gate=bool(cmp['no_pitch_safety_regression']),
            lower_labels_lost=summary.get('lower_labels_lost', 0))
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    print(json.dumps(run(), indent=1))
