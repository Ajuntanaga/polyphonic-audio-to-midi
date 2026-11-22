"""Does the voice's own fundamental energy fall on the ticks where its output outlives the label?  Saved trace only.

No audio, model run or job.  The tail-state result left 37% of selected lower-band tail ticks WITH a direct fundamental
peak, so no "unsupported" rule can clip them.  Hypothesis: when the player damps the string at note-off, the voice's
own fundamental energy (candidate field fund_energy, trace v5, valid only when energy_observed == 1) falls quickly, and
a causal feature of that fall could separate tail from true ticks.  Two causal features per voice (keyed by rendered
note; state reset whenever the voice is absent for a tick):
  R = fund_energy / running maximum of fund_energy since the voice appeared
  W = fund_energy / maximum of fund_energy over the previous 150 ms (225 ticks), including this tick
Classes as in the tail-state script: true / tail / other (other is not analysed).  Only SELECTED ticks with
energy_observed == 1 are scored.  A flag is feature < threshold, grid 0.5, 0.25, 0.1, 0.05.  Reported for the
direct != 0 subset (the part the unsupported-run rule cannot reach) and for all selected ticks.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the tail-state and unsupported-run results, the v5 header, the candidate field list.  NOT seen: any
fund_energy value.  Predictions, each can fail:
  E1  among selected tail ticks with direct != 0, at least 90% have energy_observed == 1 (otherwise the feature is
      unusable there).
  E2  W < 0.25 flags at least 20% of selected tail ticks with direct != 0 while flagging at most 5% of selected true
      ticks with direct != 0 (a damped release exists and is separable).
  E3  no R threshold in the grid has a true-positive rate of at least 30% on selected tail ticks with direct != 0 with
      a false-positive rate of at most 10% on selected true ticks with direct != 0 (natural decay confounds R).
Report the whole grid whatever it shows.  One recording; nothing here selects a threshold.  Pitch occupancy at
decision-tick resolution; no lane, unison, callback or live-host claim.

Usage: python3 -P -E CLAUDE-M3-LOWREG-ENERGY-DECAY-20261122.py TRACE.tsv.gz
"""
import gzip
import importlib.util
import json
import os
import sys
from collections import Counter, deque

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('tailstate', os.path.join(HERE, 'CLAUDE-M3-LOWREG-TAIL-STATE-20261122.py'))
tailstate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tailstate)
split = tailstate.split
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-ENERGY-DECAY-20261122.json')
TAIL_TICKS = tailstate.TAIL_TICKS
WINDOW = 225                      # 150 ms at 0.667 ms per tick
THRESHOLDS = (0.5, 0.25, 0.1, 0.05)


def run(path):
    last_label = {}
    peak = {}
    recent = {}                   # note -> deque of (tick, energy) with decreasing energy (monotonic window max)
    seen = Counter()              # (kind, direct_nonzero, observed)
    hits = {f: Counter() for f in ('R', 'W')}   # (feature, thr, kind, subset) -> count
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            tick = frame['tick']
            active = {row[1] for row in frame['labels']}
            for note in active:
                last_label[note] = tick
            lows = [v for v in frame['voices'] if v[1] < split.SPLIT]
            present = {v[1] for v in lows}
            for note in [n for n in peak if n not in present]:
                del peak[note]
                recent.pop(note, None)
            if not lows:
                continue
            cands = _candidates(frame)
            for voice in lows:
                note = voice[1]
                cand = cands.get(voice[0])
                if cand is None or 'fund_energy' not in cand:
                    continue
                energy = cand['fund_energy']
                if cand['energy_observed'] == 1:
                    peak[note] = max(peak.get(note, 0.0), energy)
                    window = recent.setdefault(note, deque())
                    while window and window[-1][1] <= energy:
                        window.pop()
                    window.append((tick, energy))
                    while window[0][0] <= tick - WINDOW:
                        window.popleft()
                if note in active:
                    kind = 'true'
                elif tick - last_label.get(note, -10 ** 9) <= TAIL_TICKS:
                    kind = 'tail'
                else:
                    continue
                if cand['selection'] == 0:
                    continue
                dnz = cand['direct'] != 0
                observed = cand['energy_observed'] == 1
                seen[(kind, dnz, observed)] += 1
                if not observed or peak.get(note, 0.0) <= 0.0:
                    continue
                feats = {'R': energy / peak[note], 'W': energy / recent[note][0][1]}
                for name, value in feats.items():
                    for thr in THRESHOLDS:
                        if value < thr:
                            hits[name][(thr, kind, 'all')] += 1
                            if dnz:
                                hits[name][(thr, kind, 'direct')] += 1
    obs = Counter()
    for (kind, dnz, observed), n in seen.items():
        obs[(kind, 'direct' if dnz else 'nodirect', observed)] += n
    base = {}
    for kind in ('tail', 'true'):
        direct_obs = obs[(kind, 'direct', True)]
        all_obs = direct_obs + obs[(kind, 'nodirect', True)]
        base[kind] = dict(selected_direct_observed=direct_obs, selected_all_observed=all_obs,
                          selected_direct_total=direct_obs + obs[(kind, 'direct', False)],
                          selected_all_total=all_obs + obs[(kind, 'direct', False)] + obs[(kind, 'nodirect', False)])
    grid = {}
    for name in ('R', 'W'):
        for thr in THRESHOLDS:
            row = {}
            for subset in ('direct', 'all'):
                tail_n = base['tail']['selected_%s_observed' % subset]
                true_n = base['true']['selected_%s_observed' % subset]
                row[subset] = dict(tail_flag_rate=round(hits[name][(thr, 'tail', subset)] / tail_n, 3) if tail_n else None,
                                   true_flag_rate=round(hits[name][(thr, 'true', subset)] / true_n, 3) if true_n else None)
            grid['%s<%g' % (name, thr)] = row
    out = dict(base=base, grid=grid)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1))
