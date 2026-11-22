"""Tick-level gain and harm of a label-free re-render rule on CURRENT's lower voices.  Saved trace only.

No audio, model run or job.  The eligibility result (CLAUDE-M3-LOWREG-SUBSTITUTE-CANDIDATE-20261122) says that beside a ghost the
right pitch is logged without labels in 41% of substitution ticks and wins on fundamental share 80% of the time when decoys exist.
That counted only ticks chosen with labels.  A rule must also decide on ticks it cannot identify, so here it is applied to EVERY
emitted voice below MIDI 60 and scored afterwards against the labels, in voice-ticks (one tick = 64 samples = 0.667 ms at 96 kHz).

Rule family (all inputs are detector-side trace fields, no label):
  for a lower voice V with rendered note n and candidate c: Q = pitches q (any band; q not n; q not rendered by any voice this
  tick) related to n by octave, twelfth-like (7 mod 12) or near (|d| <= 2), whose row passes the writer's label-free filter
  (active, rescue mask, selected or coasting, emitted detected note, or weak direct: score_ratio >= 0.20, direct, local or
  evidence).  q* = the member of Q with the largest fund_ratio.  Rule A(theta) fires if fund_ratio(q*) >= theta * fund_ratio(c)
  (fund_ratio(c) floored at 1e-6).  Rule B(theta) fires if A(theta) fires AND c has no direct fundamental peak (direct == 0).
  A fired voice-tick replaces n by q*.
Accounting by labels: n_active = a label of pitch n is active this tick; q_active = a label of pitch q* is active.  Present
change = [q_active] - [n_active]; false change = [not q_active] - [not n_active].  V classes: true (n_active), tail (no label
of n now, one within the previous 1.5 s), ghost (neither).
theta sweep: 1.0, 1.5, 2, 3, 5, 10.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the substitution-candidate and eligibility results.  NOT seen: any firing count on true voices or any net
change.  Predictions, each can fail:
  H1  rule A at theta 1.0 has a negative net present change (it destroys more correct voice-ticks than it adds).
  H2  at least one (rule, theta) combination in the sweep has a positive net present change.
  H3  for the (rule, theta) with the largest positive net present change, at least 25% of fired voice-ticks are on true voices.
  H4  rule A at theta 1.0 has more than 50% of its fires with q* not an active label (the replacement is itself false).
  H5  rule B is cleaner than rule A: at every theta the share of fires on true voices is lower under B than under A.
Report the whole table whatever it shows.  Pitch occupancy at decision-tick resolution; no lane, unison, callback or live-host
claim.  Nothing here selects a native rule, and a tick-level count is not the span-level strict gate.

Usage: python3 -P -E CLAUDE-M3-LOWREG-RERENDER-HARM-20261122.py TRACE.tsv.gz
"""
import gzip
import importlib.util
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('elig', os.path.join(HERE, 'CLAUDE-M3-LOWREG-SUBSTITUTE-ELIGIBLE-20261122.py'))
elig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(elig)
split, tailstate, rel_class = elig.split, elig.tailstate, elig.rel_class
logged_without_labels = elig.logged_without_labels
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-RERENDER-HARM-20261122.json')
TAIL_TICKS = tailstate.TAIL_TICKS
THETAS = (1.0, 1.5, 2.0, 3.0, 5.0, 10.0)
KINDS = ('true', 'tail', 'ghost')


def run(path):
    last_label = {}
    totals = Counter()
    fires = []          # (kind, n_active, q_active, rel class of q* to n, ratio, own_direct)
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
                own = cands.get(voice[0])
                if own is None or own['selection'] == 0:
                    continue
                if n in active:
                    kind = 'true'
                elif tick - last_label.get(n, -10 ** 9) <= TAIL_TICKS:
                    kind = 'tail'
                else:
                    kind = 'ghost'
                totals[kind] += 1
                best = None
                for q, row in cands.items():
                    if q == n or q in rendered:
                        continue
                    rc = rel_class(n - q)
                    if rc is None or not logged_without_labels(row, emitted):
                        continue
                    if best is None or row['fund_ratio'] > best[0]:
                        best = (row['fund_ratio'], q, rc[1])
                if best is None:
                    continue
                own_fr = max(own['fund_ratio'], 1e-6)
                fires.append((kind, n in active, best[1] in active, best[2], best[0] / own_fr, own['direct']))
    table = {}
    for rule in ('A', 'B'):
        for theta in THETAS:
            cells = Counter()
            by_kind = Counter()
            for kind, n_act, q_act, cls, ratio, own_direct in fires:
                if ratio < theta or (rule == 'B' and own_direct != 0):
                    continue
                cells[(n_act, q_act)] += 1
                by_kind[kind] += 1
            fired = sum(cells.values())
            present = sum(v for (n_act, q_act), v in cells.items() if q_act) - sum(
                v for (n_act, q_act), v in cells.items() if n_act)
            false = sum(v for (n_act, q_act), v in cells.items() if not q_act) - sum(
                v for (n_act, q_act), v in cells.items() if not n_act)
            table[f'{rule}{theta:g}'] = dict(
                fired=fired, fired_by_kind={k: by_kind[k] for k in KINDS},
                n_active_q_active=cells[(True, True)], n_active_q_false=cells[(True, False)],
                n_false_q_active=cells[(False, True)], n_false_q_false=cells[(False, False)],
                net_present_change_ticks=present, net_false_change_ticks=false,
                share_fires_on_true=round(by_kind['true'] / fired, 3) if fired else None,
                share_fires_q_false=round((cells[(True, False)] + cells[(False, False)]) / fired, 3) if fired else None)
    out = dict(voice_ticks_by_kind={k: totals[k] for k in KINDS}, rule_table=table)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1))
