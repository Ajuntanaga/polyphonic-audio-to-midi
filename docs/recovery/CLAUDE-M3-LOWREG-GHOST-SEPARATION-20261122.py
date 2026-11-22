"""Among lower-band voices that stand in an octave or twelfth relation to another sounding voice, what separates a ghost from a true chord note?  Saved trace only.

No audio, model run or job.  The orphan-relation result (CLAUDE-M3-LOWREG-ORPHAN-RELATION-20261122) found that 56% of
CURRENT's lower orphan false output is an octave or twelfth of an active label.  A rule that suppresses a voice because
it is harmonically related to another voice would also hit true octave pairs in chords, so the question is which
features separate the two classes AMONG related voices.

Subjects: voice-ticks of a rendered note below MIDI 60 whose candidate is selected this tick.
  true  = a label of the same rendered pitch is active at that tick
  ghost = no same-pitch label active now and none within the previous 1.5 s (the `other` class of the tail-state work)
  (tail ticks are skipped)
Partnered: another sounding voice in the same frame (any band) whose rendered note p has d = n - p nonzero with
d mod 12 in (0, 7) and |d| <= 36 (octave or twelfth class); the nearest |d| is the partner.
Features: direct, local, evidence_ticks, evidence_gap, fund_ratio, band_fund, band_score, score_ratio, fund_energy,
age, attack, and LOGR = log10(fund_energy / partner fund_energy) when both are observed.  For each feature the area
under the ROC curve (ghost vs true) is reported on partnered ticks, with the direction that gives AUC >= 0.5 and the
true-positive rate on ghosts at a 5% false-positive rate on true ticks.  Ticks in one span are strongly correlated, so
these are descriptive tick-level numbers, not span-level evidence.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the orphan-relation result and the tail-state and energy results.  NOT seen: any partnered count or AUC.
Predictions, each can fail:
  G1  at least one single feature reaches AUC >= 0.85 (ghost vs true, partnered voice-ticks).
  G2  `direct` alone has AUC < 0.75.
  G3  AUC(LOGR) exceeds AUC(fund_ratio) by at least 0.05.
  G4  at a 5% false-positive rate on true partnered ticks, the best feature's true-positive rate on ghost ticks is at
      least 50%.
  G5  ghost voice-ticks are at least twice as likely to be partnered as true voice-ticks.
Report everything whatever it shows.  One recording, one corpus; nothing here selects a rule.  Pitch occupancy at
decision-tick resolution; no lane, unison, callback or live-host claim.

Usage: python3 -P -E CLAUDE-M3-LOWREG-GHOST-SEPARATION-20261122.py TRACE.tsv.gz
"""
import gzip
import importlib.util
import json
import math
import os
import sys
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('tailstate', os.path.join(HERE, 'CLAUDE-M3-LOWREG-TAIL-STATE-20261122.py'))
tailstate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tailstate)
split = tailstate.split
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-GHOST-SEPARATION-20261122.json')
TAIL_TICKS = tailstate.TAIL_TICKS
FEATURES = ('direct', 'local', 'evidence_ticks', 'evidence_gap', 'fund_ratio', 'band_fund', 'band_score',
            'score_ratio', 'fund_energy', 'age', 'attack', 'LOGR')


def auc_and_tpr(ghost, true):
    """AUC of ghost > true (direction chosen to be >= 0.5) and TPR on ghosts at 5% FPR on true."""
    g = np.asarray(ghost, dtype=float)
    t = np.asarray(true, dtype=float)
    if len(g) == 0 or len(t) == 0:
        return None
    values = np.concatenate([g, t])
    order = np.argsort(values, kind='mergesort')
    ranks = np.empty(len(values))
    sorted_vals = values[order]
    i = 0
    while i < len(sorted_vals):
        j = i
        while j + 1 < len(sorted_vals) and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    auc = (ranks[:len(g)].sum() - len(g) * (len(g) + 1) / 2.0) / (len(g) * len(t))
    sign = 1.0
    if auc < 0.5:
        auc, sign = 1.0 - auc, -1.0
    threshold = np.quantile(sign * t, 0.95)
    tpr = float(np.mean(sign * g > threshold))
    return dict(auc=round(float(auc), 3), ghost_high=bool(sign > 0), tpr_at_5pct_fpr=round(tpr, 3))


def run(path):
    last_label = {}
    rows = {'true': [], 'ghost': []}
    subject = Counter()
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
            for voice in lows:
                note = voice[1]
                if note in active:
                    kind = 'true'
                elif tick - last_label.get(note, -10 ** 9) > TAIL_TICKS:
                    kind = 'ghost'
                else:
                    continue
                cand = cands.get(voice[0])
                if cand is None or cand['selection'] == 0:
                    continue
                subject[kind] += 1
                partners = [(abs(note - o[1]), o) for o in voices
                            if o is not voice and o[1] != note and (note - o[1]) % 12 in (0, 7) and abs(note - o[1]) <= 36]
                if not partners:
                    continue
                subject[kind + '_partnered'] += 1
                partner = min(partners, key=lambda x: x[0])[1]
                pc = cands.get(partner[0])
                logr = float('nan')
                if (cand.get('energy_observed') == 1 and pc is not None and pc.get('energy_observed') == 1
                        and cand['fund_energy'] > 0 and pc['fund_energy'] > 0):
                    logr = math.log10(cand['fund_energy'] / pc['fund_energy'])
                rows[kind].append([cand[f] if f != 'LOGR' else logr for f in FEATURES])
    result = dict(subject_ticks={k: subject[k] for k in ('true', 'true_partnered', 'ghost', 'ghost_partnered')},
                  partnered_share={k: round(subject[k + '_partnered'] / subject[k], 3) for k in ('true', 'ghost') if subject[k]})
    table = {}
    for i, name in enumerate(FEATURES):
        g = [r[i] for r in rows['ghost'] if not (isinstance(r[i], float) and math.isnan(r[i]))]
        t = [r[i] for r in rows['true'] if not (isinstance(r[i], float) and math.isnan(r[i]))]
        stats = auc_and_tpr(g, t)
        if stats:
            stats.update(n_ghost=len(g), n_true=len(t))
        table[name] = stats
    result['features'] = table
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1))
