"""Disposition-code split of CURRENT's lower-band tails, and flag rates by code.  Saved trace and saved spans only.

No audio, model run or job.  CLAUDE-M3-LOWREG-TAIL-STATE-20261122 reported "81% of lower tail ticks are SELECTED, 19% coasting".
Its script defines `selected = candidate['selection'] != 0`.  `selection` is a disposition code (0 quiet, 1 below_threshold,
2 spectral_rejected, 3 dp_evicted, 4 selected, 5 coasting), and for a rendered voice only codes 0, 4 and 5 occur, so that
note's "selected" is codes 4 and 5 together and its "coasting" is code 0 alone.  This script tabulates the codes separately,
with whether the voice's pitch is occupied in CURRENT's saved pitch spans at the tick's sample, and repeats the flag rates of
that note per code.  Classes (true, tail, other) and the 1.5 s tail window are those of the tail-state script.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the code counts by class and the occupancy of tail ticks by code (an earlier scratch tally).  NOT seen: any
flag rate by code.  Predictions, each can fail:
  C1  `direct == 0` is more common among code-5 tail ticks than among code-4 tail ticks.
  C2  `direct == 0` among code-4 tail ticks is at least 0.40.
  C3  `direct == 0` among code-4 true ticks is at most 0.10.
  C4  `fund_ratio < 0.2` among code-5 tail ticks is at least 0.15.
Report the whole table whatever it shows.  Pitch occupancy at decision-tick resolution; no lane, unison, callback or live-host
claim.  Nothing here selects a native rule.

Usage: python3 -P -E CLAUDE-M3-LOWREG-TAIL-CODES-20261122.py TRACE.tsv.gz
"""
import bisect
import gzip
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('tailstate', os.path.join(HERE, 'CLAUDE-M3-LOWREG-TAIL-STATE-20261122.py'))
tailstate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tailstate)
split = tailstate.split
FLAGS = tailstate.FLAGS
TAIL_TICKS = tailstate.TAIL_TICKS
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-TAIL-CODES-20261122.json')
CODE_NAMES = {0: 'quiet', 1: 'below_threshold', 2: 'spectral_rejected', 3: 'dp_evicted', 4: 'selected', 5: 'coasting'}


def run(path):
    base = json.load(open(split.BASELINE))['datasets']['ordinary']
    occ = defaultdict(list)
    for left, right, pitch in base['pitch_spans']:
        occ[pitch].append((left, right))
    for pitch in occ:
        occ[pitch].sort()

    def occupied(pitch, sample):
        iv = occ.get(pitch)
        if not iv:
            return False
        i = bisect.bisect_right(iv, (sample, 10 ** 12)) - 1
        return i >= 0 and iv[i][0] <= sample < iv[i][1]

    last_label = {}
    counts = Counter()
    flags = {k: Counter() for k in FLAGS}
    release = defaultdict(list)
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            tick, sample = frame['tick'], frame['sample']
            active = {row[1] for row in frame['labels']}
            for note in active:
                last_label[note] = tick
            lows = [v for v in frame['voices'] if v[1] < split.SPLIT]
            if not lows:
                continue
            cands = _candidates(frame)
            for voice in lows:
                note = voice[1]
                kind = 'true' if note in active else 'tail' if tick - last_label.get(note, -10 ** 9) <= TAIL_TICKS else 'other'
                cand = cands.get(voice[0])
                if cand is None:
                    counts[(kind, 'no_candidate', occupied(note, sample))] += 1
                    continue
                code = cand['selection']
                counts[(kind, CODE_NAMES[code], occupied(note, sample))] += 1
                for name, fn in FLAGS.items():
                    flags[name][(kind, code, fn(cand))] += 1
                if kind == 'tail':
                    release[code].append(cand['release'])
    table = {}
    for (kind, code, occ_flag), value in sorted(counts.items(), key=lambda kv: str(kv[0])):
        table.setdefault(kind, {})[f'{code}/{"occupied" if occ_flag else "not_occupied"}'] = value
    rates = {}
    for name, counter in flags.items():
        rates[name] = {}
        for kind in ('tail', 'true', 'other'):
            for code in (4, 5):
                yes, no = counter[(kind, code, True)], counter[(kind, code, False)]
                rates[name][f'{kind}/{CODE_NAMES[code]}'] = dict(
                    with_flag=round(yes / (yes + no), 3) if yes + no else None, ticks=yes + no)
    quant = {CODE_NAMES[c]: dict(n=len(v), quantiles=[sorted(v)[int(q * (len(v) - 1))] for q in (0, .25, .5, .75, 1)])
             for c, v in release.items() if v}
    out = dict(counts_by_class_code_occupancy=table, flag_rates_by_class_and_code=rates, tail_release_field_by_code=quant)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1))
