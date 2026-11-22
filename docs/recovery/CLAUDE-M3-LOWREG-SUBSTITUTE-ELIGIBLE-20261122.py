"""Label-free version of the substitution-candidate test: would the target pitch be in the candidate table without label annotations?  Saved trace only.

No audio, model run or job.  CLAUDE-M3-LOWREG-SUBSTITUTE-CANDIDATE-20261122 found the uncovered related label's pitch in the
candidate table at 100% of substitution ticks.  That is a logging artefact: with annotations on, the v5 trace writer serializes
a row for every active label's pitch and for that pitch plus 12 (native/offline/replay.cpp, `requested`), whatever the
detector thinks.  Rows for other pitches are written only when the detector has a reason: `active`, a rescue mask, a
selected or coasting disposition, an emitted voice's detected note, or a weak direct candidate (score ratio at least 0.20,
a direct fundamental peak, and local or candidate evidence).  This script re-applies exactly that label-free inclusion filter
to every row, so a row counts as "logged without labels" only if the detector would have written it anyway.

Subjects and substitution ticks are those of the substitute-candidate script: a selected or coasting lower voice (rendered note
n below MIDI 60) with no same-pitch label now or within 1.5 s, beside an active label L (pitch p; octave, twelfth-like or near
of n) that no voice renders; p by (class order, |d|).  A DECOY is a pitch q related to n (octave, twelfth-like or near; q not
n, not an active label) whose row passes the label-free filter at that tick.  Features come from detector diagnostics computed
for any pitch, so they are not label-dependent; only which rows exist is.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the substitute-candidate result (100% existence, an artefact; targets 92.7% not emitted; target fund_ratio
above the ghost's in 83.6% of ticks).  NOT seen: any label-free logging rate or decoy count.  Predictions, each can fail:
  E1  at least 50% of substitution ticks have the target row logged without labels.
  E2  that rate is at least three times the label-free rate for non-label lower-band pitches (MIDI 32 to 59, not n, not active).
  E3  at least 50% of substitution ticks have zero decoys.
  E4  where the target is logged without labels and at least one decoy exists, the target has the largest fund_ratio among
      target and decoys in at least 50% of those ticks.
  E5  at least 25% of substitution ticks have the target logged without labels AND zero decoys.
Report the whole table whatever it shows, with the octave class separately.  Pitch occupancy at decision-tick resolution;
no lane, unison, callback or live-host claim.  Nothing here selects a native rule.

Usage: python3 -P -E CLAUDE-M3-LOWREG-SUBSTITUTE-ELIGIBLE-20261122.py TRACE.tsv.gz
"""
import gzip
import importlib.util
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('oracle', os.path.join(HERE, 'CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122.py'))
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
spec = importlib.util.spec_from_file_location('tailstate', os.path.join(HERE, 'CLAUDE-M3-LOWREG-TAIL-STATE-20261122.py'))
tailstate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tailstate)
split = tailstate.split
rel_class = oracle.rel_class
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-SUBSTITUTE-ELIGIBLE-20261122.json')
TAIL_TICKS = tailstate.TAIL_TICKS
LOW_RANGE = range(32, split.SPLIT)
CLASSES = ('octave', 'fifth', 'near')


def logged_without_labels(row, emitted):
    """The writer's inclusion filter with the label-requested pitches removed."""
    weak_direct = row['score_ratio'] >= 0.20 and row['direct'] != 0 and (row['local'] != 0 or row['evidence'] != 0)
    return bool(row['note'] in emitted or row['active'] or row['rescue_mask'] != 0 or weak_direct
                or row['selection'] in (4, 5))


def run(path):
    last_label = {}
    count = Counter()
    by_class = {c: Counter() for c in CLASSES}
    decoy_hist = Counter()
    base_hits = base_trials = 0
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            tick = frame['tick']
            active = {row[1] for row in frame['labels']}
            for note in active:
                last_label[note] = tick
            voices = frame['voices']
            lows = [v for v in voices if v[1] < split.SPLIT]
            if not lows:
                continue
            cands = _candidates(frame)
            rendered = {v[1] for v in voices}
            emitted = {v[0] for v in voices}
            for voice in lows:
                n = voice[1]
                if n in active or tick - last_label.get(n, -10 ** 9) <= TAIL_TICKS:
                    continue
                own = cands.get(voice[0])
                if own is None or own['selection'] == 0:
                    continue
                related = []
                for p in active:
                    rc = rel_class(n - p)
                    if rc is not None:
                        related.append((rc[0], abs(n - p), p, rc[1]))
                uncovered = sorted(r for r in related if r[2] not in rendered)
                if not uncovered:
                    continue
                count['substitution_ticks'] += 1
                _order, _dist, p, cls = uncovered[0]
                by_class[cls]['ticks'] += 1
                target = cands[p]          # present in every case (annotation logging); label-free status is tested below
                free = logged_without_labels(target, emitted)
                decoys = [q for q, row in cands.items()
                          if q != n and q not in active and rel_class(n - q) is not None and logged_without_labels(row, emitted)]
                decoy_hist[min(len(decoys), 3)] += 1
                if free:
                    count['target_logged_label_free'] += 1
                    by_class[cls]['free'] += 1
                if not decoys:
                    count['zero_decoys'] += 1
                    by_class[cls]['zero_decoys'] += 1
                    if free:
                        count['free_and_zero_decoys'] += 1
                        by_class[cls]['free_and_zero'] += 1
                elif free:
                    count['free_with_decoys'] += 1
                    by_class[cls]['free_with_decoys'] += 1
                    best = max(cands[q]['fund_ratio'] for q in decoys)
                    if target['fund_ratio'] > best:
                        count['target_best_fund_ratio'] += 1
                        by_class[cls]['target_best'] += 1
                for q in LOW_RANGE:
                    if q in active or q == n:
                        continue
                    base_trials += 1
                    row = cands.get(q)
                    base_hits += row is not None and logged_without_labels(row, emitted)
    sub = count['substitution_ticks']
    base = base_hits / base_trials if base_trials else None
    free_rate = count['target_logged_label_free'] / sub if sub else None
    out = dict(
        counts={k: count[k] for k in ('substitution_ticks', 'target_logged_label_free', 'zero_decoys', 'free_and_zero_decoys',
                                      'free_with_decoys', 'target_best_fund_ratio')},
        label_free_existence_rate=round(free_rate, 3) if free_rate is not None else None,
        base_rate_non_label_lower_pitch=round(base, 4) if base is not None else None,
        existence_over_base=round(free_rate / base, 2) if base and free_rate is not None else None,
        decoy_count_histogram_ticks={str(k): decoy_hist[k] for k in (0, 1, 2, 3)},
        zero_decoy_share=round(count['zero_decoys'] / sub, 3) if sub else None,
        target_best_share_when_free_and_decoys=round(count['target_best_fund_ratio'] / count['free_with_decoys'], 3)
        if count['free_with_decoys'] else None,
        free_and_zero_decoy_share=round(count['free_and_zero_decoys'] / sub, 3) if sub else None,
        by_class={c: dict(ticks=by_class[c]['ticks'], free=by_class[c]['free'], zero_decoys=by_class[c]['zero_decoys'],
                          free_and_zero=by_class[c]['free_and_zero'], free_with_decoys=by_class[c]['free_with_decoys'],
                          target_best=by_class[c]['target_best'],
                          free_rate=round(by_class[c]['free'] / by_class[c]['ticks'], 3) if by_class[c]['ticks'] else None,
                          free_and_zero_share=round(by_class[c]['free_and_zero'] / by_class[c]['ticks'], 3)
                          if by_class[c]['ticks'] else None)
                  for c in CLASSES})
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1))
