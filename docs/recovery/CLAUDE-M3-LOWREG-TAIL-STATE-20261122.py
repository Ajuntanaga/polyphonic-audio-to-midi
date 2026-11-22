"""What state is CURRENT's candidate in while its lower-band output outlives the label?  Saved trace only.

No audio, no model run, no job.  Reads the saved per-decision outcome trace of the unfiltered-observation run
(44835727027, ordinary, CURRENT ON, block 512; schema m3_candidate_outcome_v5) and classifies every decision tick on
which a voice below MIDI 60 is sounding:
  true  = a label of the same rendered pitch is active at that tick
  tail  = no same-pitch label is active, but one was active within the previous 1.5 s
  other = neither (a different false output; not analysed further)
For each class, the state of that voice's candidate: selection flag (selected this decision) or coasting, direct
fundamental peak, local evidence, evidence gap, fundamental share, and whether the voice is a resolved unison
(more than one string bit).  Purpose: decide which mechanism keeps the lower tails alive BEFORE any native trial is
designed.  Pitch occupancy only; no lane, unison-multiplicity, callback or live-host claim.  Nothing is a candidate.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the schema and two sample rows, the native release code, the tail anatomy (58% of CURRENT's lower
false output is tail, median tail 295 ms, above the 220 ms maximum ordinary hold).  NOT seen: any class count.
Predictions, each can fail:
  S1  at least 30% of lower-band tail ticks are SELECTED ticks (re-selection keeps the voice alive), not coasting.
  S2  resolved unisons (more than one string bit) are under 20% of lower-band tail ticks.
  S3  among selected tail ticks, direct == 0 (no direct fundamental peak) is at least 60%, against at most 30%
      among selected true ticks.
  S4  no single feature flag (direct == 0, evidence_gap > 0, fund_ratio < 0.2, local == 0) separates selected tail
      ticks from selected true ticks with a true-positive rate of at least 50% and a false-positive rate of at most 10%.
The S4 outcome matters most: a flag that passes would be a specific, non-repeat trial hypothesis; none passing
agrees with the earlier rejected sustain-renewal trials.

Usage: python3 -P -E CLAUDE-M3-LOWREG-TAIL-STATE-20261122.py TRACE.tsv.gz
"""
import gzip
import importlib.util
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('fate', os.path.join(HERE, 'CLAUDE-M3-LOWREG-ACTIVATION-FATE-20261122.py'))
fate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fate)
split = fate.split
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-TAIL-STATE-20261122.json')
TICK_MS = 64 * 1000.0 / 96000.0
TAIL_TICKS = int(1.5 * 96000 / 64)
FLAGS = {'direct0': lambda c: c['direct'] == 0, 'gap': lambda c: c['evidence_gap'] > 0,
         'fund_low': lambda c: c['fund_ratio'] < 0.2, 'local0': lambda c: c['local'] == 0}


def run(path):
    last_label = {}
    counts = Counter()
    flags = {k: Counter() for k in FLAGS}
    coast_release = []
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))   # v5 adds input_power, floor_stats
            tick = frame['tick']
            active = {row[1] for row in frame['labels']}
            for note in active:
                last_label[note] = tick
            lows = [v for v in frame['voices'] if v[1] < split.SPLIT]
            if not lows:
                continue
            cands = _candidates(frame)
            for voice in lows:
                note = voice[1]
                if note in active:
                    kind = 'true'
                elif tick - last_label.get(note, -10 ** 9) <= TAIL_TICKS:
                    kind = 'tail'
                else:
                    kind = 'other'
                cand = cands.get(voice[0])
                if cand is None:
                    counts[(kind, 'no_candidate')] += 1
                    continue
                selected = cand['selection'] != 0
                unison = bin(voice[7]).count('1') > 1
                counts[(kind, 'selected' if selected else 'coasting', 'unison' if unison else 'single')] += 1
                if selected:
                    for name, fn in FLAGS.items():
                        flags[name][(kind, fn(cand))] += 1
                elif kind == 'tail':
                    coast_release.append(cand['release'])
    total = {k: sum(v for key, v in counts.items() if key[0] == k) for k in ('true', 'tail', 'other')}
    table = {'/'.join(map(str, key)): dict(ticks=v, ms=round(v * TICK_MS, 1)) for key, v in sorted(counts.items())}
    rate = {}
    for name, c in flags.items():
        tail = c[('tail', True)] + c[('tail', False)]
        true = c[('true', True)] + c[('true', False)]
        rate[name] = dict(selected_tail_with_flag=round(c[('tail', True)] / tail, 3) if tail else None,
                          selected_true_with_flag=round(c[('true', True)] / true, 3) if true else None,
                          selected_tail_ticks=tail, selected_true_ticks=true)
    coast_release.sort()
    out = dict(total_ticks=total, classes=table, selected_flag_rates=rate,
               tail_coasting_release_ticks=dict(n=len(coast_release),
                                                 quantiles=[coast_release[int(q * (len(coast_release) - 1))] for q in (0, .25, .5, .75, 1)]
                                                 if coast_release else None))
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1))
