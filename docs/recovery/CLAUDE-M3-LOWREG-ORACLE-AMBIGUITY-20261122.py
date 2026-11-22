"""How ambiguous is the oracle substitution?  How much of its gain survives when the target is the ONLY candidate?  Saved spans and labels only.

No audio, model run or job.  The oracle substitution result (CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122) reassigned each
lower orphan stretch to the first uncovered related label (octave, then fifth, then near) and gained +5.06 coverage points.
Two things need checking before that number is read as the size of a prize:
  (a) its per-class "substituted share" printed 1.045 for `near` because the denominator counted a stretch only under its
      first-priority related class.  Here each class gets its own denominator: the samples in stretches where some active
      label stands in that class's relation to the orphan pitch.
  (b) a chord has several active labels, so a stretch can have several uncovered related labels, and the oracle picks one
      with the labels in hand.  The orphan-null control showed the fifth relation to be at chance and the octave relation
      about 20 points above it.  So count the uncovered related candidates per stretch, and rescore the oracle when a
      substitution is made ONLY if exactly one uncovered related label exists (`unique`), and only if that one is an octave
      (`octave_unique`).  `all` reproduces the original oracle (sanity check A0: +5.06 points, 2.56x exact-set).

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the oracle substitution result and the orphan-null control.  NOT seen: any candidate count or restricted
oracle score.  Predictions, each can fail:
  A0  `all` reproduces the oracle on ordinary: coverage gain 5.06 points, exact-set 136,578.
  A1  at least 60% of ordinary stretch samples that have an uncovered related label have EXACTLY ONE.
  A2  the `unique` oracle keeps at least half of the full oracle's coverage gain (>= 2.53 points) on ordinary.
  A3  the `octave_unique` oracle gains at least 1.5 coverage points on ordinary.
  A4  every per-class share, with the per-class denominator, is at most 1 (the earlier 1.045 was a denominator artefact).
Report the whole table whatever it shows.  Oracle numbers use the labels and are upper bounds on a label-aware corrector,
not results about any detector; the strict gate is met by construction because only orphan stretches are reassigned.
Pitch occupancy only; no lane, unison, timing or live-host claim.

Usage: python3 -P -E CLAUDE-M3-LOWREG-ORACLE-AMBIGUITY-20261122.py
"""
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('oracle', os.path.join(HERE, 'CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122.py'))
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
audit, split = oracle.audit, oracle.split
rel_class, covered_everywhere = oracle.rel_class, oracle.covered_everywhere
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import compare, score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-ORACLE-AMBIGUITY-20261122.json')
MODES = ('all', 'unique', 'octave_unique')
CLASSES = ('octave', 'fifth', 'near')


def run():
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    result = dict(schema='claude_m3_oracle_ambiguity_v1', datasets={})
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
        available, chosen = Counter(), Counter()
        n_uncovered = Counter()
        new = {m: [] for m in MODES}
        for left, right, note in spans:
            own = any(l['midi_note'] == note and l['start_sample'] < right and l['end_sample'] > left for l in labels)
            if note >= split.SPLIT or own:
                for m in MODES:
                    new[m].append((left, right, note))
                continue
            edges = [left] + [c for c in cuts if left < c < right] + [right]
            for a, b in zip(edges, edges[1:]):
                active = {l['midi_note'] for l in labels if l['start_sample'] < b and l['end_sample'] > a}
                related = []
                for p in active:
                    rc = rel_class(note - p)
                    if rc is not None:
                        related.append((rc[0], abs(note - p), p, rc[1]))
                related.sort()
                for cls in {r[3] for r in related}:
                    available[cls] += b - a
                uncovered = [r for r in related if not covered_everywhere(by_pitch, r[2], a, b)]
                if related:
                    n_uncovered[min(len(uncovered), 3)] += b - a
                first = uncovered[0] if uncovered else None
                if first:
                    chosen[first[3]] += b - a
                pick = {'all': first,
                        'unique': first if len(uncovered) == 1 else None,
                        'octave_unique': first if len(uncovered) == 1 and first[3] == 'octave' else None}
                for m in MODES:
                    new[m].append((a, b, pick[m][2]) if pick[m] else (a, b, note))
        current = score(spans, labels, **clock)
        cur = split.compact(current)
        table = {}
        for m in MODES:
            scored = score(new[m], labels, **clock)
            orc = split.compact(scored)
            cmp = compare(current, scored)
            table[m] = dict(
                present=orc['present'], coverage_percent=orc['coverage_percent'],
                coverage_gain_points=round(orc['coverage_percent'] - cur['coverage_percent'], 2),
                exact_pitch_set=orc['exact_pitch_set'],
                exact_set_ratio=round(orc['exact_pitch_set'] / cur['exact_pitch_set'], 2) if cur['exact_pitch_set'] else None,
                wrong_pitch_delta=orc['wrong_pitch'] - cur['wrong_pitch'], gap_delta=orc['gap'] - cur['gap'],
                strict_gate=bool(cmp['no_pitch_safety_regression']),
                lower_labels_lost=audit.summarize(audit.loss_rows(current, scored)).get('lower_labels_lost', 0))
        with_related = sum(n_uncovered.values())
        with_uncovered = sum(v for k, v in n_uncovered.items() if k >= 1)
        result['datasets'][name] = dict(
            current=cur,
            samples_by_uncovered_related_count={str(k): n_uncovered[k] for k in (0, 1, 2, 3)},
            share_exactly_one_among_with_uncovered=round(n_uncovered[1] / with_uncovered, 3) if with_uncovered else None,
            available_samples_by_class={c: available[c] for c in CLASSES},
            chosen_samples_by_class={c: chosen[c] for c in CLASSES},
            share_by_class={c: round(chosen[c] / available[c], 3) if available[c] else None for c in CLASSES},
            modes=table)
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    print(json.dumps(run(), indent=1))
